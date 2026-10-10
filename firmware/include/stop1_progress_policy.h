#pragma once

#include <stdint.h>

/* Pure policy for repeated STOP1 entries which return with negligible
 * retained-RTC progress. A chattering wake every few milliseconds is not zero
 * elapsed, but allowing it to reset the streak can cause hundreds of thousands
 * of high-overhead entries during one cadence. Require either one second or
 * the complete requested short residue to count as meaningful progress.
 * Eight short wakes first suppress external INT1; eight more with INT1 already
 * suppressed prove that masking the expected noisy source did not restore
 * progress, so the caller must leave STOP1 and finish in a watchdog-bounded
 * shallow-sleep fallback. Saturation prevents an 8-bit wrap from reopening the
 * live-lock during a persistent fault. */
static constexpr uint32_t STOP1_MIN_MEANINGFUL_PROGRESS_MS = 1000u;
static constexpr uint8_t STOP1_MASK_INT1_AFTER_SHORT_WAKES = 8u;
static constexpr uint8_t STOP1_SHALLOW_FALLBACK_AFTER_SHORT_WAKES = 16u;

enum stop1_progress_action_t : uint8_t {
    STOP1_PROGRESS_CONTINUE = 0,
    STOP1_PROGRESS_MASK_INT1,
    STOP1_PROGRESS_SHALLOW_FALLBACK,
};

struct stop1_progress_state_t {
    uint8_t short_progress_wakes;
    bool int1_masked;
};

static inline stop1_progress_action_t stop1_progress_observe(
    stop1_progress_state_t* state, uint32_t elapsed_ms,
    uint32_t requested_ms) {
    if (!state) return STOP1_PROGRESS_SHALLOW_FALLBACK;
    if (requested_ms == 0u) return STOP1_PROGRESS_SHALLOW_FALLBACK;
    uint32_t meaningful_ms =
        requested_ms < STOP1_MIN_MEANINGFUL_PROGRESS_MS
            ? requested_ms : STOP1_MIN_MEANINGFUL_PROGRESS_MS;
    if (elapsed_ms >= meaningful_ms) {
        state->short_progress_wakes = 0u;
        return STOP1_PROGRESS_CONTINUE;
    }
    if (state->short_progress_wakes < UINT8_MAX) {
        state->short_progress_wakes++;
    }
    if (!state->int1_masked &&
        state->short_progress_wakes >= STOP1_MASK_INT1_AFTER_SHORT_WAKES) {
        state->int1_masked = true;
        return STOP1_PROGRESS_MASK_INT1;
    }
    if (state->int1_masked &&
        state->short_progress_wakes >=
            STOP1_SHALLOW_FALLBACK_AFTER_SHORT_WAKES) {
        return STOP1_PROGRESS_SHALLOW_FALLBACK;
    }
    return STOP1_PROGRESS_CONTINUE;
}
