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
 * Frame (LoRaMesher-style, 6-byte header + payload):
 *   [src:2][msg_id:1][ttl:1][flags:1][len:1][payload:len]
 *     src     originating balloon id (0xFFFF reserved for broadcast targets)
 *     msg_id  per-source monotonic counter; dedup key = (src<<8 | msg_id)
 *     ttl     remaining hops.  A frame arriving with ttl 0 is consumed but
 *             never re-emitted; ttl >= 1 forwards with ttl-1 (so ttl 1 goes
 *             out once more as ttl 0).  Default 3 = origin plus three hops.
 *     flags   bits 0-1 type (b2b_type_t); bits 2-7 reserved, must be 0
 *     len     payload length in bytes (0..B2B_PAYLOAD_MAX)
 *
 * Payload by type:
 *   CRUMB    N x 6-byte b2b_crumb_t, len must be a nonzero multiple of 6
 *   COMMAND  the doc-08 command frame [target:2][opcode:1][seq:1][args],
 *            len >= 4; target 0xFFFF = broadcast (delivered AND forwarded)
 *   ACK      [target:2][seq:1] echoing an applied command's seq, len == 3
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

#define B2B_HDR_LEN       6
#define B2B_CRUMB_LEN     6
#define B2B_PAYLOAD_MAX   48          /* fits 8 crumbs; keeps ToA modest at SF9 */
#define B2B_FRAME_MAX     (B2B_HDR_LEN + B2B_PAYLOAD_MAX)
#define B2B_ID_BROADCAST  0xFFFFu
#define B2B_SEEN_N        32          /* recent dedup keys retained */
#define B2B_SEEN_TTL_MIN  240         /* seen entries age out after 4 h; msg_id
                                       * wraps no faster than ~85 h at the
                                       * 20-min cadence, so 4 h is safe by 20x */
#define B2B_FWD_N         8           /* store-and-forward queue depth */
#define B2B_TTL_DEFAULT   3           /* origin + 3 hops of reach */
#define B2B_AIRTIME_CAP_MS 6000       /* max banked credit, ~2 pass-grants; a
                                       * quiet leg must not bank a TX burst */

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
} b2b_frame_t;

typedef struct {
    uint32_t rx;            /* frames ingested */
    uint32_t dup;           /* dropped as duplicates */
    uint32_t fwd;           /* frames handed to the radio for re-emission */
    uint32_t local;         /* delivered to us (incl. broadcast deliveries) */
    uint32_t expired;       /* arrived with ttl 0 */
    uint32_t malformed;     /* header/len/type inconsistencies */
    uint32_t own_echo;      /* our own frames heard back (mesh is working) */
    uint32_t queue_full;    /* ingests refused for queue space (retryable) */
    uint32_t airtime_block; /* radio hand-offs refused by the airtime budget */
    uint32_t airtime_ms;    /* cumulative airtime charged for forwards */
} b2b_stats_t;

/* State handle.  Zero-initialise before first use, or call b2b_reset. */
typedef struct {
    uint16_t self_id;
    uint32_t seen[B2B_SEEN_N];     /* (key<<0 | 0x80000000 valid) */
    uint16_t seen_min[B2B_SEEN_N]; /* coarse insert time, minutes */
    uint8_t  seen_head;
    b2b_frame_t fwd[B2B_FWD_N];
    uint8_t  fwd_head, fwd_tail, fwd_count;
    uint32_t airtime_budget_ms;    /* remaining airtime credit, capped */
    uint8_t  next_msg_id;
    b2b_stats_t stats;
} b2b_t;

void b2b_reset(b2b_t* b, uint16_t self_id);

/* Grant airtime credit for the forwarder (call once per pass with the slice
 * you are willing to spend, e.g. 5% of the window).  Banked credit is capped
 * at B2B_AIRTIME_CAP_MS. */
void b2b_add_airtime(b2b_t* b, uint32_t credit_ms);

/* Serialize/parse the wire frame.  b2b_encode returns total bytes written
 * (0 on overflow).  b2b_parse is strict: the buffer must be exactly
 * header+len long and reserved flag bits must be 0. */
int  b2b_encode(const b2b_frame_t* f, uint8_t* buf, int cap);
bool b2b_parse(const uint8_t* buf, int n, b2b_frame_t* out);

/* Ingest a heard frame.  now_min is a coarse monotonic clock in minutes
 * (any epoch; used only for seen-entry aging).  Queue-refused frames return
 * B2B_BLOCKED and are NOT marked seen, so a later re-beacon retries them. */
b2b_result_t b2b_ingest(b2b_t* b, const b2b_frame_t* f, uint16_t now_min);

/* Pop the next frame to re-emit if the airtime budget covers toa_ms; charges
 * the budget on success.  Returns false when the queue is empty or the budget
 * refuses (stats.airtime_block; frames stay queued for a later pass). */
bool b2b_next_forward(b2b_t* b, b2b_frame_t* out, uint32_t toa_ms);

/* Return a popped frame after a failed TX or an aborted window: refunds the
 * charge and re-queues the frame (dropped only if the queue refilled). */
void b2b_refund(b2b_t* b, const b2b_frame_t* f, uint32_t toa_ms);

/* Build one of our own frames to originate (crumbs or a command).  Loop
 * protection for echoes is the src==self guard in b2b_ingest; nothing is
 * written to the seen ring here. */
void b2b_make(b2b_t* b, b2b_type_t type, const uint8_t* payload, uint8_t len,
              b2b_frame_t* out);

/* Crumb pack/unpack (6 bytes each). */
void b2b_crumb_pack(const b2b_crumb_t* c, uint8_t out[6]);
void b2b_crumb_unpack(const uint8_t in[6], b2b_crumb_t* c);

#endif
