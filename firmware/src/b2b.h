#ifndef B2B_H
#define B2B_H

/* Balloon-to-balloon (B2B) store-and-forward for the Stratolink constellation.
 *
 * Carries compact position crumbs and addressable commands across the 69% of
 * the flight that has no gateway in reach (the ocean leg, doc 08 section 8).
 * A balloon that hears a neighbour's frame it has not seen before re-emits it
 * on the shared P2P/relay radio with the hop budget decremented, so telemetry
 * walks out of the dark leg and commands walk in, one hop per pass.
 *
 * Frame (versioned 9-byte header + payload):
 *   ["SB":2][ver:1][src:2][msg_id:1][ttl:1][flags:1][len:1][payload:len]
 *     "SB"    StratoLink B2B discriminator. Required because these frames
 *             share the LongFast PHY with ordinary Meshtastic packets.
 *     ver     wire version, currently 3; unknown versions fail closed
 *     src     originating balloon id (0xFFFF reserved for broadcast targets)
 *     msg_id  per-source monotonic counter; dedup key = (src<<8 | msg_id)
 *     ttl     remaining hops.  A frame arriving with ttl 0 is consumed but
 *             never re-emitted; ttl >= 1 forwards with ttl-1 (so ttl 1 goes
 *             out once more as ttl 0).  Default 3 = origin plus three hops.
 *     flags   bits 0-1 type (b2b_type_t); bits 2-7 reserved, must be 0
 *     len     payload length in bytes (0..B2B_PAYLOAD_MAX)
 *
 * Payload by type:
 *   CRUMB    N x 6-byte b2b_crumb_t + auth_tag:8; body is nonempty and a
 *            multiple of 6
 *   COMMAND  [target:2][opcode:1][seq:1][args][auth_tag:8], len >= 12;
 *            target 0xFFFF = broadcast (delivered AND forwarded)
 *   ACK      [target:2][seq:1][auth_tag:8], len == 11
 *
 * Every frame type is authenticated by the radio integration before this pure
 * routing layer ingests it. The tag covers immutable origin fields and the
 * application body (TTL is excluded because each relay decrements it). A
 * trusted fleet relay advances a queued crumb's age and renews that tag before
 * forwarding; source, message ID, position, and original age remain bound.
 *
 * Design rules, learned from the adversarial review of the first cut:
 *   - Dedup marks a frame seen ONLY when it is actually consumed (forwarded,
 *     delivered, or ttl-expired).  A frame refused for queue space returns
 *     B2B_BLOCKED unmarked, so the neighbour's next re-beacon retries it.
 *     Store-and-forward lives on retries; consuming on refusal defeats it.
 *   - Seen entries age out after B2B_SEEN_TTL_MIN so the 8-bit msg_id
 *     wrapping during a multi-day separation cannot collide with stale keys.
 *   - The airtime budget is checked and charged when a frame is handed to the
 *     radio (b2b_next_forward), not at ingest, and credit is capped so a long
 *     quiet leg cannot bank an unbounded TX burst (a brownout vector on a
 *     supercap airframe).  b2b_refund() returns a popped frame after TX
 *     failure or a window abort.
 *   - Our own frames heard back off the mesh are healthy (B2B_OWN), not
 *     malformed; the src==self guard is the loop protection.
 *
 * Pure logic, no radio/Arduino dependency, host-testable. */

#include <stdint.h>
#include <stdbool.h>

#define B2B_MAGIC_0       0x53
#define B2B_MAGIC_1       0x42
#define B2B_WIRE_VERSION  3
#define B2B_HDR_LEN       9
#define B2B_CRUMB_LEN     6
#define B2B_PAYLOAD_MAX   44          /* complete frame <= US915 DR1's 53-byte
                                       * application limit; fits 6 crumbs +
                                       * the common 8-byte authentication tag */
#define B2B_AUTH_TAG_LEN  8
#define B2B_FRAME_MAX     (B2B_HDR_LEN + B2B_PAYLOAD_MAX)
#if B2B_FRAME_MAX > 53
#error "B2B tunnel exceeds the US915 DR1 LoRaWAN application payload ceiling"
#endif
#define B2B_ID_BROADCAST  0xFFFFu
#define B2B_SEEN_N        32          /* recent dedup keys retained */
#define B2B_SEEN_TTL_MIN  240         /* seen entries age out after 4 h; msg_id
                                       * wraps no faster than ~85 h at the
                                       * 20-min cadence, so 4 h is safe by 20x */
#define B2B_FWD_N         8           /* store-and-forward queue depth */
#define B2B_TTL_DEFAULT   3           /* origin + 3 hops of reach */
#define B2B_AIRTIME_CAP_MS 6000       /* max banked credit, ~2 pass-grants; a
                                       * quiet leg must not bank a TX burst */
#define B2B_RTC_CONFIGURED_LSI_HZ 32000u
#define B2B_RTC_MIN_LSI_HZ        29500u
#define B2B_RTC_MAX_LSI_HZ        34000u

typedef enum {
    B2B_TYPE_CRUMB   = 0,
    B2B_TYPE_COMMAND = 1,
    B2B_TYPE_ACK     = 2,
} b2b_type_t;

/* Result of ingesting a heard frame. */
typedef enum {
    B2B_DUP           = 0,  /* already seen; dropped */
    B2B_FORWARD       = 1,  /* fresh; queued for re-emission (ttl decremented) */
    B2B_LOCAL         = 2,  /* addressed to us; delivered locally only */
    B2B_LOCAL_FORWARD = 3,  /* broadcast: delivered locally AND queued */
    B2B_EXPIRED       = 4,  /* fresh but arrived with ttl 0; consumed */
    B2B_MALFORMED     = 5,  /* inconsistent header/len/type; dropped */
    B2B_OWN           = 6,  /* our own frame echoed back; healthy, dropped */
    B2B_BLOCKED       = 7,  /* no queue space; NOT marked seen, retryable */
    B2B_LOCAL_BLOCKED = 8,  /* broadcast: delivered locally NOW, but not queued
                             * (queue full) and not marked seen, so the forward
                             * leg retries on the neighbour's next re-beacon.
                             * The repeat local delivery that retry causes is
                             * absorbed by the seq-idempotent command layer. */
} b2b_result_t;

/* 6-byte packed position crumb: lat/lon at 0.01 deg (~1.1 km), alt in 100 m
 * steps to 25.5 km, and a coarse age in minutes (saturating at 255). */
typedef struct {
    int16_t  lat_cd;    /* degrees * 100 */
    int16_t  lon_cd;    /* degrees * 100 */
    uint8_t  alt_hm;    /* metres / 100 */
    uint8_t  age_min;   /* minutes since sampled, saturating */
} b2b_crumb_t;

typedef struct {
    uint16_t src;
    uint8_t  msg_id;
    uint8_t  ttl;
    uint8_t  type;      /* b2b_type_t */
    uint8_t  len;
    uint8_t  payload[B2B_PAYLOAD_MAX];
    /* Local queue metadata; never encoded and never included in the CMAC.
     * A relay uses it to advance authenticated crumb ages while a frame waits
     * for RF airtime or a TTN uplink. */
    uint32_t queued_rtc_sec;
} b2b_frame_t;

typedef struct {
    uint32_t rx;            /* frames ingested */
    uint32_t dup;           /* dropped as duplicates */
    uint32_t fwd;           /* frames handed to the radio for re-emission */
    uint32_t local;         /* delivered to us (incl. broadcast deliveries) */
    uint32_t expired;       /* arrived with ttl 0 */
    uint32_t malformed;     /* header/len/type inconsistencies */
    uint32_t auth_fail;     /* frame rejected before ingest */
    uint32_t own_echo;      /* our own frames heard back (mesh is working) */
    uint32_t queue_full;    /* ingests refused for queue space (retryable) */
    uint32_t airtime_block; /* radio hand-offs refused by the airtime budget */
    uint32_t airtime_ms;    /* cumulative airtime charged for forwards */
    uint32_t cad_busy;      /* carrier active; frame retained for retry */
    uint32_t cad_error;     /* CAD radio failure; frame retained for retry */
    uint32_t tx_error;      /* clear-CAD transmit failure; retained/refunded */
    uint32_t window_block;  /* not enough relay-window time for safe hand-off */
    uint32_t ack_drop;      /* authenticated command ACK could not be queued */
    uint32_t ttn_drop;      /* authenticated frame lost to a full TTN queue */
} b2b_stats_t;

/* State handle.  Zero-initialise before first use, or call b2b_reset. */
typedef struct {
    uint16_t self_id;
    uint32_t seen[B2B_SEEN_N];     /* (key<<0 | 0x80000000 valid) */
    uint32_t seen_rtc_sec[B2B_SEEN_N]; /* raw nominal RTC seconds at insert */
    uint8_t  seen_head;
    b2b_frame_t fwd[B2B_FWD_N];
    uint8_t  fwd_head, fwd_tail, fwd_count;
    uint32_t airtime_budget_ms;    /* remaining airtime credit, capped */
    uint8_t  next_msg_id;
    b2b_stats_t stats;
} b2b_t;

void b2b_reset(b2b_t* b, uint16_t self_id);

/* Grant airtime credit for the forwarder, once per pass.  Intended grant is
 * <= 3000 ms per pass (roughly ten SF9 crumb frames); banked credit is capped
 * at B2B_AIRTIME_CAP_MS, i.e. two such grants, so a quiet leg cannot bank a
 * TX burst.  Grants above the cap are clamped, not an error. */
void b2b_add_airtime(b2b_t* b, uint32_t credit_ms);

/* The STM32WLE5 LSI is guaranteed only from 29.5 to 34 kHz while STM32RTC is
 * configured for 32 kHz. Freshness needs an upper wall-time bound; replay
 * retention and minimum origin spacing need a lower wall-time bound. These
 * functions intentionally convert a raw RTC-domain DELTA in opposite
 * directions instead of inventing one globally "corrected" clock. */
uint32_t b2b_age_upper_minutes(uint32_t elapsed_rtc_sec);
uint32_t b2b_elapsed_lower_minutes(uint32_t elapsed_rtc_sec);

/* Wrap-safe scheduler used by the hourly local-crumb origin path. `now` and
 * `last` are raw nominal RTC seconds; the interval cannot become due before
 * the requested amount of real wall time at the datasheet-fastest LSI. */
bool b2b_interval_due(bool ever_completed, uint32_t now_rtc_sec,
                      uint32_t last_rtc_sec, uint32_t interval_min);

/* Serialize/parse the wire frame.  b2b_encode returns total bytes written
 * (0 on overflow).  b2b_parse is strict: magic/version must match, the
 * buffer must be exactly header+len long, and reserved flag bits must be 0. */
int  b2b_encode(const b2b_frame_t* f, uint8_t* buf, int cap);
bool b2b_parse(const uint8_t* buf, int n, b2b_frame_t* out);
/** True for any packet in the reserved "SB" namespace, regardless of version.
 *  Callers must route these to b2b_parse rather than treating unknown versions
 *  as another protocol sharing the carrier. */
bool b2b_is_namespaced(const uint8_t* buf, int n);

/* Length of the authenticated application body after removing the fixed CMAC
 * trailer. Returns 0 for malformed frames. */
uint8_t b2b_authenticated_body_len(const b2b_frame_t* frame);

/*
 * Compute/verify the common wire-v3 AES-CMAC trailer. The tag binds magic,
 * version, source, message ID, type, exact body length, and body. TTL is the
 * sole excluded header field because each legitimate relay decrements it.
 */
bool b2b_auth_tag(const uint8_t key[16], const b2b_frame_t* frame,
                  uint8_t out[B2B_AUTH_TAG_LEN]);
bool b2b_auth_verify(const uint8_t key[16], const b2b_frame_t* frame);

/* Ingest a heard frame. now_rtc_sec is the raw nominal RTC epoch in seconds
 * (used only through wrap-safe deltas). Queue-refused frames return
 * B2B_BLOCKED and are NOT marked seen, so a later re-beacon retries them. */
b2b_result_t b2b_ingest(
    b2b_t* b, const b2b_frame_t* f, uint32_t now_rtc_sec);

/* Verify every queued frame. For a crumb, advance every saturating sample age
 * by the time spent in the local queue and renew the shared-fleet CMAC without
 * changing origin, message ID, or TTL. Non-crumb frames remain byte-identical.
 * The input is committed only on success, and queued_rtc_sec becomes the
 * supplied raw RTC epoch. */
bool b2b_refresh_authenticated_age(
    const uint8_t key[16], b2b_frame_t* frame, uint32_t now_rtc_sec);

/* Peek at the frame b2b_next_forward would pop, so the caller can compute its
 * REAL time-on-air before charging (frame ToA varies ~3x with length).
 * Returns NULL when the queue is empty. */
const b2b_frame_t* b2b_peek_forward(const b2b_t* b);

/* Pop the next frame to re-emit if the airtime budget covers toa_ms; charges
 * the budget on success.  Returns false when the queue is empty or the budget
 * refuses (stats.airtime_block; frames stay queued for a later pass). */
bool b2b_next_forward(b2b_t* b, b2b_frame_t* out, uint32_t toa_ms);

/* Production forward path: before charging airtime or popping the queue,
 * advance authenticated crumb age to now_min and renew its CMAC. A corrupted
 * queued crumb is dropped fail-closed without charging airtime. */
bool b2b_next_forward_fresh(
    b2b_t* b, b2b_frame_t* out, uint32_t toa_ms,
    const uint8_t key[16], uint32_t now_rtc_sec);

/* Return a popped frame after a failed TX or an aborted window: refunds the
 * charge and re-queues the frame (dropped only if the queue refilled). */
void b2b_refund(b2b_t* b, const b2b_frame_t* f, uint32_t toa_ms);

/* Build one of our own frames to originate (crumbs or a command).  Validates
 * the payload with the same shape rules ingest applies, so a frame our own
 * peers would reject as malformed is never handed to the radio; returns false
 * (and burns no msg_id) on a shape violation.  Loop protection for echoes is
 * the src==self guard in b2b_ingest; nothing is written to the seen ring. */
bool b2b_make(b2b_t* b, b2b_type_t type, const uint8_t* payload, uint8_t len,
              b2b_frame_t* out);

/* Crumb pack/unpack (6 bytes each). */
void b2b_crumb_pack(const b2b_crumb_t* c, uint8_t out[6]);
void b2b_crumb_unpack(const uint8_t in[6], b2b_crumb_t* c);

#endif
