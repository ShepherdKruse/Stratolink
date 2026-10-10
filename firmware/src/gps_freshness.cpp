#include "gps_freshness.h"

#define GPS_WEEK_MS 604800000u

void gps_freshness_reset(gps_freshness_t* state) {
    if (!state) return;
    state->itow_ms = 0;
    state->anchored = false;
}

bool gps_freshness_observe(gps_freshness_t* state, uint32_t itow_ms) {
    if (!state || itow_ms >= GPS_WEEK_MS) return false;

    if (!state->anchored) {
        state->itow_ms = itow_ms;
        state->anchored = true;
        return false;
    }

    uint32_t delta = itow_ms >= state->itow_ms
        ? itow_ms - state->itow_ms
        : GPS_WEEK_MS - state->itow_ms + itow_ms;
    /* Modular half-range ordering: zero is cached/repeated; a delta larger
     * than half a GPS week is a small move BACKWARD represented modulo one
     * week, while exactly half a week has no unique forward direction. Reject
     * both cases. Do not update the anchor on rejection, so one corrupt PVT
     * cannot make the next stale epoch look fresh. Legitimate long periods
     * without observing PVT are handled by resetting the anchor at the
     * power-gated skip boundary. */
    if (delta == 0 || delta >= GPS_WEEK_MS / 2u) return false;

    state->itow_ms = itow_ms;
    return true;
}

bool gps_recovery_due(bool anchor_available, uint32_t now_ms,
                      uint32_t last_epoch_progress_ms,
                      uint32_t last_pvt_ms) {
    bool frozen = anchor_available &&
        now_ms - last_epoch_progress_ms >= GPS_FROZEN_EPOCH_RESET_MS;
    bool silent =
        now_ms - last_pvt_ms >= GPS_PVT_SILENCE_RESET_MS;
    return frozen || silent;
}

bool gps_stale_ladder_step(bool navigation_progressed,
                           bool reset_already_attempted,
                           uint8_t threshold,
                           uint8_t* streak) {
    if (!streak || threshold == 0u) return false;
    if (navigation_progressed || reset_already_attempted) {
        *streak = 0u;
        return false;
    }
    if (*streak < UINT8_MAX) ++*streak;
    if (*streak < threshold) return false;
    *streak = 0u;
    return true;
}
