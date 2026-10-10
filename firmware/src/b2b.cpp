#include "b2b.h"
#include "crypto_aes128.h"
#include <string.h>

/* Dedup key packs (src,msg_id) into 24 bits and uses the top bit as a valid
 * flag so a zeroed slot never aliases the (src=0,msg_id=0) key. */
static uint32_t seen_key(uint16_t src, uint8_t msg_id) {
    return (((uint32_t)src << 8) | msg_id) | 0x80000000u;
}

/* Entries older than B2B_SEEN_TTL_MIN of conservatively bounded wall time are
 * treated as absent, so an 8-bit msg_id that wrapped during a multi-day
 * separation cannot collide with a stale key and silently drop a fresh frame.
 * The unsigned subtraction is wrap-safe for the raw RTC-second epoch. */
static bool seen_has(b2b_t* b, uint32_t key, uint32_t now_rtc_sec) {
    for (int i = 0; i < B2B_SEEN_N; i++) {
        if (b->seen[i] != key) continue;
        uint32_t elapsed_rtc_sec = now_rtc_sec - b->seen_rtc_sec[i];
        if (b2b_elapsed_lower_minutes(elapsed_rtc_sec) <=
            B2B_SEEN_TTL_MIN) return true;
        b->seen[i] = 0;    /* stale: clear rather than retaining dead keys */
    }
    return false;
}

/* Invalidate a seen entry (used when a refunded frame must be dropped: the
 * neighbour's re-beacon must genuinely retry, not DUP out). */
static void seen_remove(b2b_t* b, uint32_t key) {
    for (int i = 0; i < B2B_SEEN_N; i++)
        if (b->seen[i] == key) b->seen[i] = 0;
}

static void seen_add(b2b_t* b, uint32_t key, uint32_t now_rtc_sec) {
    b->seen[b->seen_head] = key;
    b->seen_rtc_sec[b->seen_head] = now_rtc_sec;
    b->seen_head = (uint8_t)((b->seen_head + 1) % B2B_SEEN_N);
}

void b2b_reset(b2b_t* b, uint16_t self_id) {
    memset(b, 0, sizeof(*b));
    b->self_id = self_id;
}

void b2b_add_airtime(b2b_t* b, uint32_t credit_ms) {
    /* Capped: a long quiet leg must not bank an unbounded TX burst.  The
     * Meshtastic relay anchors its cap to elapsed wall-clock per window; the
     * equivalent here is at most ~2 pass-grants of standing credit. Compare
     * before adding so even an adversarial UINT32_MAX grant cannot wrap the
     * sum below the cap. */
    if (b->airtime_budget_ms >= B2B_AIRTIME_CAP_MS ||
        credit_ms >= B2B_AIRTIME_CAP_MS - b->airtime_budget_ms) {
        b->airtime_budget_ms = B2B_AIRTIME_CAP_MS;
    } else {
        b->airtime_budget_ms += credit_ms;
    }
}

uint32_t b2b_age_upper_minutes(uint32_t elapsed_rtc_sec) {
    const uint64_t denominator =
        (uint64_t)B2B_RTC_MIN_LSI_HZ * 60u;
    uint64_t numerator =
        (uint64_t)elapsed_rtc_sec * B2B_RTC_CONFIGURED_LSI_HZ;
    uint64_t result = (numerator + denominator - 1u) / denominator;
    return result > UINT32_MAX ? UINT32_MAX : (uint32_t)result;
}

uint32_t b2b_elapsed_lower_minutes(uint32_t elapsed_rtc_sec) {
    const uint64_t denominator =
        (uint64_t)B2B_RTC_MAX_LSI_HZ * 60u;
    uint64_t result =
        ((uint64_t)elapsed_rtc_sec * B2B_RTC_CONFIGURED_LSI_HZ) /
        denominator;
    return result > UINT32_MAX ? UINT32_MAX : (uint32_t)result;
}

bool b2b_interval_due(bool ever_completed, uint32_t now_rtc_sec,
                      uint32_t last_rtc_sec, uint32_t interval_min) {
    return !ever_completed ||
        b2b_elapsed_lower_minutes(now_rtc_sec - last_rtc_sec) >= interval_min;
}

int b2b_encode(const b2b_frame_t* f, uint8_t* buf, int cap) {
    if (!f || !buf || f->len > B2B_PAYLOAD_MAX ||
        f->ttl > B2B_TTL_DEFAULT || f->src == B2B_ID_BROADCAST) return 0;
    int total = B2B_HDR_LEN + f->len;
    if (cap < total) return 0;
    buf[0] = B2B_MAGIC_0;
    buf[1] = B2B_MAGIC_1;
    buf[2] = B2B_WIRE_VERSION;
    buf[3] = (uint8_t)(f->src >> 8);
    buf[4] = (uint8_t)(f->src & 0xFF);
    buf[5] = f->msg_id;
    buf[6] = f->ttl;
    buf[7] = (uint8_t)(f->type & 0x03);          /* bits 2-7 reserved, sent 0 */
    buf[8] = f->len;
    memcpy(buf + B2B_HDR_LEN, f->payload, f->len);
    return total;
}

bool b2b_is_namespaced(const uint8_t* buf, int n) {
    return buf && n >= 2 &&
           buf[0] == B2B_MAGIC_0 && buf[1] == B2B_MAGIC_1;
}

bool b2b_parse(const uint8_t* buf, int n, b2b_frame_t* out) {
    if (!buf || !out || n < B2B_HDR_LEN) return false;
    if (buf[0] != B2B_MAGIC_0 || buf[1] != B2B_MAGIC_1 ||
        buf[2] != B2B_WIRE_VERSION) return false;
    if (buf[6] > B2B_TTL_DEFAULT) return false;    /* an unauthenticated TTL is
                                                   * mutable for forwarding but
                                                   * never allowed to amplify
                                                   * beyond the origin cap */
    if (buf[3] == 0xFF && buf[4] == 0xFF) return false; /* broadcast is a
                                                        * target only */
    uint8_t len = buf[8];
    if (len > B2B_PAYLOAD_MAX) return false;
    if (n != B2B_HDR_LEN + len) return false;    /* the radio hands exact
                                                  * packet lengths; anything
                                                  * else is an upstream bug */
    if (buf[7] & ~0x03) return false;            /* reserved bits must be 0 so
                                                  * future versions fail loudly */
    out->src    = (uint16_t)((buf[3] << 8) | buf[4]);
    out->msg_id = buf[5];
    out->ttl    = buf[6];
    out->type   = (uint8_t)(buf[7] & 0x03);
    out->len    = len;
    memcpy(out->payload, buf + B2B_HDR_LEN, len);
    out->queued_rtc_sec = 0;
    return true;
}

uint8_t b2b_authenticated_body_len(const b2b_frame_t* frame) {
    if (!frame || frame->type > B2B_TYPE_ACK ||
        frame->len < B2B_AUTH_TAG_LEN) return 0;
    uint8_t body_len = (uint8_t)(frame->len - B2B_AUTH_TAG_LEN);
    if (frame->type == B2B_TYPE_CRUMB)
        return body_len && (body_len % B2B_CRUMB_LEN) == 0 ? body_len : 0;
    if (frame->type == B2B_TYPE_COMMAND)
        return body_len >= 4 ? body_len : 0;
    return body_len == 3 ? body_len : 0;
}

bool b2b_auth_tag(const uint8_t key[16], const b2b_frame_t* frame,
                  uint8_t out[B2B_AUTH_TAG_LEN]) {
    if (!key || !frame || !out || frame->src == B2B_ID_BROADCAST) return false;
    uint8_t body_len = b2b_authenticated_body_len(frame);
    if (!body_len) return false;
    uint8_t message[7 + B2B_PAYLOAD_MAX] = {};
    message[0] = B2B_MAGIC_0;
    message[1] = B2B_MAGIC_1;
    message[2] = B2B_WIRE_VERSION;
    message[3] = (uint8_t)(frame->src >> 8);
    message[4] = (uint8_t)frame->src;
    message[5] = frame->msg_id;
    message[6] = frame->type;
    memcpy(message + 7, frame->payload, body_len);
    uint8_t mac[16];
    if (!aes128_cmac(key, message, (size_t)7 + body_len, mac)) return false;
    memcpy(out, mac, B2B_AUTH_TAG_LEN);
    return true;
}

bool b2b_auth_verify(const uint8_t key[16], const b2b_frame_t* frame) {
    if (!key || !frame) return false;
    uint8_t body_len = b2b_authenticated_body_len(frame);
    if (!body_len) return false;
    uint8_t expected[B2B_AUTH_TAG_LEN];
    if (!b2b_auth_tag(key, frame, expected)) return false;
    uint8_t diff = 0;
    const uint8_t* actual = frame->payload + body_len;
    for (uint8_t i = 0; i < B2B_AUTH_TAG_LEN; ++i)
        diff |= (uint8_t)(expected[i] ^ actual[i]);
    return diff == 0;
}

bool b2b_refresh_authenticated_age(
    const uint8_t key[16], b2b_frame_t* frame, uint32_t now_rtc_sec) {
    if (!frame) return false;
    if (!key || !b2b_auth_verify(key, frame)) return false;
    if (frame->type != B2B_TYPE_CRUMB) {
        frame->queued_rtc_sec = now_rtc_sec;
        return true;
    }

    b2b_frame_t updated = *frame;
    uint8_t body_len = b2b_authenticated_body_len(&updated);
    if (!body_len) return false;
    uint32_t elapsed_min = b2b_age_upper_minutes(
        now_rtc_sec - updated.queued_rtc_sec);
    for (uint8_t i = 0; i < body_len; i += B2B_CRUMB_LEN) {
        uint8_t* age = &updated.payload[i + B2B_CRUMB_LEN - 1u];
        uint32_t remaining = 255u - *age;
        *age = elapsed_min >= remaining
            ? 255u
            : (uint8_t)(*age + elapsed_min);
    }
    updated.queued_rtc_sec = now_rtc_sec;
    uint8_t tag[B2B_AUTH_TAG_LEN];
    if (!b2b_auth_tag(key, &updated, tag)) return false;
    memcpy(updated.payload + body_len, tag, sizeof(tag));
    *frame = updated;
    return true;
}

static bool crumb_shape_ok(const b2b_frame_t* f) {
    uint8_t body_len = b2b_authenticated_body_len(f);
    if (!body_len) return false;
    for (uint8_t i = 0; i < body_len; i += B2B_CRUMB_LEN) {
        int16_t lat_cd = (int16_t)(((uint16_t)f->payload[i] << 8) |
                                  f->payload[i + 1]);
        int16_t lon_cd = (int16_t)(((uint16_t)f->payload[i + 2] << 8) |
                                  f->payload[i + 3]);
        if (lat_cd < -9000 || lat_cd > 9000 ||
            lon_cd < -18000 || lon_cd > 18000) return false;
    }
    return true;
}

/* Type-specific payload shape. Every wire-v3 type reserves the same 8-byte
 * authentication tag, verified by the radio integration before ingest. */
static bool shape_ok(const b2b_frame_t* f) {
    switch (f->type) {
        case B2B_TYPE_CRUMB:   return crumb_shape_ok(f);
        case B2B_TYPE_COMMAND:
        case B2B_TYPE_ACK:
            return b2b_authenticated_body_len(f) != 0;
        default:               return false;      /* type 3 is undefined */
    }
}

/* A frame already sitting in the forward queue must not be enqueued again
 * (its seen entry can be evicted or age out while it waits on a starved
 * budget, and its re-beacon would then double-book queue slots and airtime). */
static bool queued_already(const b2b_t* b, uint16_t src, uint8_t msg_id) {
    uint8_t idx = b->fwd_head;
    for (uint8_t i = 0; i < b->fwd_count; i++) {
        if (b->fwd[idx].src == src && b->fwd[idx].msg_id == msg_id) return true;
        idx = (uint8_t)((idx + 1) % B2B_FWD_N);
    }
    return false;
}

/* Target of a COMMAND/ACK (first two payload bytes, doc 08). */
static uint16_t frame_target(const b2b_frame_t* f) {
    return (uint16_t)((f->payload[0] << 8) | f->payload[1]);
}

b2b_result_t b2b_ingest(
    b2b_t* b, const b2b_frame_t* f, uint32_t now_rtc_sec) {
    b->stats.rx++;

    /* 0xFFFF is meaningful only in a COMMAND/ACK target. Accepting it as an
     * origin would merge every misprovisioned sender into one dedup identity
     * and make the reserved namespace look like a real fleet node. */
    if (f->src == B2B_ID_BROADCAST) {
        b->stats.malformed++;
        return B2B_MALFORMED;
    }

    /* Our own frame heard back off the mesh: healthy (the mesh is working),
     * and this src guard IS the loop protection for originated frames. */
    if (f->src == b->self_id) {
        b->stats.own_echo++;
        return B2B_OWN;
    }

    if (f->len > B2B_PAYLOAD_MAX || !shape_ok(f)) {
        b->stats.malformed++;
        return B2B_MALFORMED;
    }

    uint32_t key = seen_key(f->src, f->msg_id);
    if (seen_has(b, key, now_rtc_sec) ||
        queued_already(b, f->src, f->msg_id)) {
        b->stats.dup++;
        return B2B_DUP;
    }

    bool addressed = false, broadcast = false;
    if (f->type == B2B_TYPE_COMMAND || f->type == B2B_TYPE_ACK) {
        uint16_t target = frame_target(f);
        broadcast = (target == B2B_ID_BROADCAST);
        addressed = broadcast || (target == b->self_id);
    }

    /* Unicast to us: consume locally, never forwarded on. */
    if (addressed && !broadcast) {
        seen_add(b, key, now_rtc_sec);
        b->stats.local++;
        return B2B_LOCAL;
    }

    /* ttl 0 on arrival: consumed (delivered if broadcast), never re-emitted. */
    if (f->ttl == 0) {
        seen_add(b, key, now_rtc_sec);
        if (broadcast) { b->stats.local++; return B2B_LOCAL; }
        b->stats.expired++;
        return B2B_EXPIRED;
    }

    /* Queue refusal does NOT mark the frame seen: store-and-forward lives on
     * the neighbour's re-beacons, and a consumed-on-refusal frame would be
     * DUP-dropped forever.  The airtime budget is applied later, at the radio
     * hand-off (b2b_next_forward), for the same reason.  A blocked BROADCAST
     * is DELIVERED now via B2B_LOCAL_BLOCKED (a fleet-wide safe-mode must not
     * wait for queue space; the caller dispatches on any LOCAL* result), and
     * the repeat delivery a later retry causes is absorbed by the doc-08
     * seq-idempotent command layer. */
    if (b->fwd_count >= B2B_FWD_N) {
        b->stats.queue_full++;
        if (broadcast) { b->stats.local++; return B2B_LOCAL_BLOCKED; }
        return B2B_BLOCKED;
    }

    seen_add(b, key, now_rtc_sec);
    b2b_frame_t nf = *f;
    nf.ttl = (uint8_t)(f->ttl - 1);              /* ttl 1 goes out as ttl 0 */
    nf.queued_rtc_sec = now_rtc_sec;
    b->fwd[b->fwd_tail] = nf;
    b->fwd_tail = (uint8_t)((b->fwd_tail + 1) % B2B_FWD_N);
    b->fwd_count++;

    /* Broadcast commands are for everyone: delivered here AND forwarded on.
     * Dedup prevents double delivery when our forward echoes back. */
    if (broadcast) {
        b->stats.local++;
        return B2B_LOCAL_FORWARD;
    }
    return B2B_FORWARD;
}

const b2b_frame_t* b2b_peek_forward(const b2b_t* b) {
    return b->fwd_count ? &b->fwd[b->fwd_head] : (const b2b_frame_t*)0;
}

bool b2b_next_forward(b2b_t* b, b2b_frame_t* out, uint32_t toa_ms) {
    if (b->fwd_count == 0) return false;
    if (toa_ms > b->airtime_budget_ms) {
        /* Budget refusal leaves the queue intact for a later pass. */
        b->stats.airtime_block++;
        return false;
    }
    b->airtime_budget_ms -= toa_ms;
    b->stats.airtime_ms += toa_ms;
    b->stats.fwd++;
    *out = b->fwd[b->fwd_head];
    b->fwd_head = (uint8_t)((b->fwd_head + 1) % B2B_FWD_N);
    b->fwd_count--;
    return true;
}

bool b2b_next_forward_fresh(
    b2b_t* b, b2b_frame_t* out, uint32_t toa_ms,
    const uint8_t key[16], uint32_t now_rtc_sec) {
    if (!b || !out || b->fwd_count == 0) return false;
    if (toa_ms > b->airtime_budget_ms) {
        b->stats.airtime_block++;
        return false;
    }

    b2b_frame_t candidate = b->fwd[b->fwd_head];
    if (!b2b_refresh_authenticated_age(key, &candidate, now_rtc_sec)) {
        /* It authenticated before ingest; a later mismatch is local
         * corruption. Do not let one bad head block the queue forever. */
        b->fwd_head = (uint8_t)((b->fwd_head + 1) % B2B_FWD_N);
        b->fwd_count--;
        b->stats.auth_fail++;
        return false;
    }

    b->airtime_budget_ms -= toa_ms;
    b->stats.airtime_ms += toa_ms;
    b->stats.fwd++;
    *out = candidate;
    b->fwd_head = (uint8_t)((b->fwd_head + 1) % B2B_FWD_N);
    b->fwd_count--;
    return true;
}

void b2b_refund(b2b_t* b, const b2b_frame_t* f, uint32_t toa_ms) {
    /* TX failed or the window aborted after the pop: undo the charge and put
     * the frame back (tail is fine; ordering is best-effort).  If the queue
     * refilled in between the frame is dropped, which the neighbour's next
     * re-beacon will repair. */
    b2b_add_airtime(b, toa_ms);
    if (b->stats.airtime_ms >= toa_ms) b->stats.airtime_ms -= toa_ms;
    if (b->stats.fwd) b->stats.fwd--;
    if (b->fwd_count < B2B_FWD_N) {
        b->fwd[b->fwd_tail] = *f;
        b->fwd_tail = (uint8_t)((b->fwd_tail + 1) % B2B_FWD_N);
        b->fwd_count++;
    } else {
        /* Queue refilled between pop and refund: the frame is lost from our
         * queue, so unmark it seen or the neighbour's re-beacons would DUP
         * out for up to B2B_SEEN_TTL_MIN instead of repairing the loss. */
        seen_remove(b, seen_key(f->src, f->msg_id));
    }
}

bool b2b_make(b2b_t* b, b2b_type_t type, const uint8_t* payload, uint8_t len,
              b2b_frame_t* out) {
    if (!b || !out || b->self_id == B2B_ID_BROADCAST ||
        len > B2B_PAYLOAD_MAX || (len && !payload)) return false;

    out->src    = b->self_id;
    out->msg_id = b->next_msg_id;        /* burned only on success */
    out->ttl    = B2B_TTL_DEFAULT;
    out->type   = (uint8_t)type;
    out->len    = len;
    out->queued_rtc_sec = 0;
    if (len) memcpy(out->payload, payload, len);

    /* A frame our own peers would reject as malformed must never reach the
     * radio: it would cost every hearer airtime and be diagnosable only via a
     * REMOTE balloon's malformed counter, the worst possible place. */
    if (!shape_ok(out)) return false;
    b->next_msg_id++;
    /* No seen-ring write here: echoes of our own frames are dropped by the
     * src==self guard in b2b_ingest, and seeding would only evict live
     * neighbour dedup keys from the 32-slot ring. */
    return true;
}

void b2b_crumb_pack(const b2b_crumb_t* c, uint8_t out[6]) {
    out[0] = (uint8_t)((uint16_t)c->lat_cd >> 8);
    out[1] = (uint8_t)((uint16_t)c->lat_cd & 0xFF);
    out[2] = (uint8_t)((uint16_t)c->lon_cd >> 8);
    out[3] = (uint8_t)((uint16_t)c->lon_cd & 0xFF);
    out[4] = c->alt_hm;
    out[5] = c->age_min;
}

void b2b_crumb_unpack(const uint8_t in[6], b2b_crumb_t* c) {
    c->lat_cd  = (int16_t)((in[0] << 8) | in[1]);
    c->lon_cd  = (int16_t)((in[2] << 8) | in[3]);
    c->alt_hm  = in[4];
    c->age_min = in[5];
}
