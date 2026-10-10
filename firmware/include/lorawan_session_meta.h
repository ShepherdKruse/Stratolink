#ifndef LORAWAN_SESSION_META_H
#define LORAWAN_SESSION_META_H

#include <stdbool.h>
#include <stdint.h>

#include "lorawan_liveness.h"

/* The retained session has no spare TAMP word. RECEIVE_DELAY1 needs only its
 * specified low nibble, so the CRC-protected rxDelaySec word also carries the
 * compact server-liveness state. A marker distinguishes current records from
 * legacy v3 sessions whose high bits were all zero. */
#define LORAWAN_SESSION_RX_DELAY_MASK       0x0000000Fu
#define LORAWAN_SESSION_LIVENESS_COUNT_MASK 0x000001F0u
#define LORAWAN_SESSION_LIVENESS_MISS_MASK  0x00000600u
#define LORAWAN_SESSION_LIVENESS_PENDING    0x00000800u
#define LORAWAN_SESSION_LIVENESS_MARKER     0x00001000u
#define LORAWAN_SESSION_SERVER_PROVEN       0x00002000u
#define LORAWAN_SESSION_INITIAL_PROBE_TRIED 0x00004000u
#define LORAWAN_SESSION_META_ALLOWED_MASK   0x00007FFFu

typedef struct {
    uint8_t rx_delay_sec;
    lorawan_liveness_state_t liveness;
    bool legacy_without_liveness;
} lorawan_session_meta_t;

static inline bool lorawan_session_meta_encode(
    uint8_t rx_delay_sec,
    const lorawan_liveness_state_t* liveness,
    uint32_t* encoded) {
    if (!encoded || rx_delay_sec < 1u || rx_delay_sec > 15u ||
        !lorawan_liveness_state_valid(liveness)) {
        return false;
    }
    uint32_t word = (uint32_t)rx_delay_sec |
        ((uint32_t)liveness->countdown << 4) |
        ((uint32_t)liveness->qualified_miss_streak << 9) |
        (liveness->probe_pending ? LORAWAN_SESSION_LIVENESS_PENDING : 0u) |
        (liveness->server_proven ? LORAWAN_SESSION_SERVER_PROVEN : 0u) |
        (liveness->initial_probe_attempted
             ? LORAWAN_SESSION_INITIAL_PROBE_TRIED : 0u) |
        LORAWAN_SESSION_LIVENESS_MARKER;
    if ((word & ~LORAWAN_SESSION_META_ALLOWED_MASK) != 0u) return false;
    *encoded = word;
    return true;
}

static inline bool lorawan_session_meta_decode(
    uint32_t encoded,
    lorawan_session_meta_t* out) {
    if (!out || (encoded & ~LORAWAN_SESSION_META_ALLOWED_MASK) != 0u) {
        return false;
    }
    uint8_t rx_delay_sec =
        (uint8_t)(encoded & LORAWAN_SESSION_RX_DELAY_MASK);
    if (rx_delay_sec < 1u || rx_delay_sec > 15u) return false;

    lorawan_session_meta_t decoded = {};
    decoded.rx_delay_sec = rx_delay_sec;
    uint32_t high = encoded & ~LORAWAN_SESSION_RX_DELAY_MASK;
    if (high == 0u) {
        /* Exact backward compatibility for every valid legacy session-v3
         * RECEIVE_DELAY1 value. It carries no authenticated server proof, so
         * import normalization schedules one prompt eligible probe. */
        lorawan_liveness_begin_session(&decoded.liveness);
        decoded.legacy_without_liveness = true;
        *out = decoded;
        return true;
    }
    if ((encoded & LORAWAN_SESSION_LIVENESS_MARKER) == 0u) return false;

    decoded.liveness.countdown = (uint8_t)(
        (encoded & LORAWAN_SESSION_LIVENESS_COUNT_MASK) >> 4);
    decoded.liveness.qualified_miss_streak = (uint8_t)(
        (encoded & LORAWAN_SESSION_LIVENESS_MISS_MASK) >> 9);
    decoded.liveness.probe_pending =
        (encoded & LORAWAN_SESSION_LIVENESS_PENDING) != 0u;
    decoded.liveness.server_proven =
        (encoded & LORAWAN_SESSION_SERVER_PROVEN) != 0u;
    decoded.liveness.initial_probe_attempted =
        (encoded & LORAWAN_SESSION_INITIAL_PROBE_TRIED) != 0u;
    if (!lorawan_liveness_state_valid(&decoded.liveness)) return false;
    *out = decoded;
    return true;
}

#endif /* LORAWAN_SESSION_META_H */
