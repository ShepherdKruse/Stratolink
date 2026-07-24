#include "b2b.h"
#include <string.h>

/* Dedup key packs (src,msg_id) into 24 bits and uses the top bit as a valid
 * flag so a zeroed slot never aliases the (src=0,msg_id=0) key. */
static uint32_t seen_key(uint16_t src, uint8_t msg_id) {
    return (((uint32_t)src << 8) | msg_id) | 0x80000000u;
}

/* Entries older than B2B_SEEN_TTL_MIN are treated as absent, so an 8-bit
 * msg_id that wrapped during a multi-day separation cannot collide with a
 * stale key and silently drop a fresh frame.  The unsigned subtraction is
 * wrap-safe for any now_min epoch. */
static bool seen_has(b2b_t* b, uint32_t key, uint16_t now_min) {
    for (int i = 0; i < B2B_SEEN_N; i++) {
        if (b->seen[i] != key) continue;
        if ((uint16_t)(now_min - b->seen_min[i]) <= B2B_SEEN_TTL_MIN) return true;
        b->seen[i] = 0;    /* stale: clear so the slot cannot resurrect as
                            * fresh when the 16-bit minute clock wraps */
    }
    return false;
}

/* Invalidate a seen entry (used when a refunded frame must be dropped: the
 * neighbour's re-beacon must genuinely retry, not DUP out). */
static void seen_remove(b2b_t* b, uint32_t key) {
    for (int i = 0; i < B2B_SEEN_N; i++)
        if (b->seen[i] == key) b->seen[i] = 0;
}

static void seen_add(b2b_t* b, uint32_t key, uint16_t now_min) {
    b->seen[b->seen_head] = key;
    b->seen_min[b->seen_head] = now_min;
    b->seen_head = (uint8_t)((b->seen_head + 1) % B2B_SEEN_N);
}

void b2b_reset(b2b_t* b, uint16_t self_id) {
    memset(b, 0, sizeof(*b));
    b->self_id = self_id;
}

void b2b_add_airtime(b2b_t* b, uint32_t credit_ms) {
    /* Capped: a long quiet leg must not bank an unbounded TX burst.  The
     * Meshtastic relay anchors its cap to elapsed wall-clock per window; the
     * equivalent here is at most ~2 pass-grants of standing credit. */
    uint32_t c = b->airtime_budget_ms + credit_ms;
    b->airtime_budget_ms = (c > B2B_AIRTIME_CAP_MS) ? B2B_AIRTIME_CAP_MS : c;
}

int b2b_encode(const b2b_frame_t* f, uint8_t* buf, int cap) {
    if (f->len > B2B_PAYLOAD_MAX) return 0;
    int total = B2B_HDR_LEN + f->len;
    if (cap < total) return 0;
    buf[0] = (uint8_t)(f->src >> 8);
    buf[1] = (uint8_t)(f->src & 0xFF);
    buf[2] = f->msg_id;
    buf[3] = f->ttl;
    buf[4] = (uint8_t)(f->type & 0x03);          /* bits 2-7 reserved, sent 0 */
    buf[5] = f->len;
    memcpy(buf + B2B_HDR_LEN, f->payload, f->len);
    return total;
}

bool b2b_parse(const uint8_t* buf, int n, b2b_frame_t* out) {
    if (n < B2B_HDR_LEN) return false;
    uint8_t len = buf[5];
    if (len > B2B_PAYLOAD_MAX) return false;
    if (n != B2B_HDR_LEN + len) return false;    /* the radio hands exact
                                                  * packet lengths; anything
                                                  * else is an upstream bug */
    if (buf[4] & ~0x03) return false;            /* reserved bits must be 0 so
                                                  * future versions fail loudly */
    out->src    = (uint16_t)((buf[0] << 8) | buf[1]);
    out->msg_id = buf[2];
    out->ttl    = buf[3];
    out->type   = (uint8_t)(buf[4] & 0x03);
    out->len    = len;
    memcpy(out->payload, buf + B2B_HDR_LEN, len);
    return true;
}

/* Type-specific payload shape.  COMMAND minimum is [target:2][opcode:1][seq:1];
 * ACK is exactly [target:2][seq:1]; crumbs come in whole 6-byte units.  Anything
 * shorter is garbage by construction and dies at first hearing, not after ttl
 * hops of wasted airtime. */
static bool shape_ok(const b2b_frame_t* f) {
    switch (f->type) {
        case B2B_TYPE_CRUMB:   return f->len > 0 && (f->len % B2B_CRUMB_LEN) == 0;
        case B2B_TYPE_COMMAND: return f->len >= 4;
        case B2B_TYPE_ACK:     return f->len == 3;
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

b2b_result_t b2b_ingest(b2b_t* b, const b2b_frame_t* f, uint16_t now_min) {
    b->stats.rx++;

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
    if (seen_has(b, key, now_min) || queued_already(b, f->src, f->msg_id)) {
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
        seen_add(b, key, now_min);
        b->stats.local++;
        return B2B_LOCAL;
    }

    /* ttl 0 on arrival: consumed (delivered if broadcast), never re-emitted. */
    if (f->ttl == 0) {
        seen_add(b, key, now_min);
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

    seen_add(b, key, now_min);
    b2b_frame_t nf = *f;
    nf.ttl = (uint8_t)(f->ttl - 1);              /* ttl 1 goes out as ttl 0 */
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
    out->src    = b->self_id;
    out->msg_id = b->next_msg_id;        /* burned only on success */
    out->ttl    = B2B_TTL_DEFAULT;
    out->type   = (uint8_t)type;
    out->len    = len;
    /* A frame our own peers would reject as malformed must never reach the
     * radio: it would cost every hearer airtime and be diagnosable only via a
     * REMOTE balloon's malformed counter, the worst possible place. */
    if (len > B2B_PAYLOAD_MAX || !shape_ok(out)) return false;
    if (len && payload) memcpy(out->payload, payload, len);
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
