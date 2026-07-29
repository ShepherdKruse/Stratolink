#ifndef GPS_FRESHNESS_H
#define GPS_FRESHNESS_H

#include <stdbool.h>
#include <stdint.h>

/*
 * NAV-PVT epoch freshness guard.
 *
 * The first PVT observed after an MCU or GNSS reset establishes an anchor but
 * is never accepted as fresh. This prevents a still-powered GNSS/library cache
 * from leaking one stale fix after an MCU-only reset. A second, different iTOW
 * proves that the navigation engine is advancing.
 */
typedef struct {
    uint32_t itow_ms;
    bool anchored;
} gps_freshness_t;

void gps_freshness_reset(gps_freshness_t* state);

/*
 * Observe a GPS time-of-week epoch.
 * Returns true only after an anchor exists and the epoch has advanced in
 * modular GPS-week order. Repeated, backward, and out-of-range epochs fail
 * closed without moving the anchor.
 */
bool gps_freshness_observe(gps_freshness_t* state, uint32_t itow_ms);

/* Same-window hardware-reset thresholds. A healthy default 1 Hz NAV engine
 * advances comfortably inside the frozen threshold; lack of any PVT gets a
 * slightly wider UART/startup allowance. */
#define GPS_FROZEN_EPOCH_RESET_MS 3000u
#define GPS_PVT_SILENCE_RESET_MS  5000u

/*
 * Decide whether a bounded in-acquisition GNSS reset is due.
 * Millisecond inputs are unsigned monotonic clock samples; subtraction is
 * wrap-safe. Recovery keys on time since the most recent advancing epoch, not
 * a sticky "advanced at least once" flag: a receiver can advance early and
 * then freeze later inside the same 30-second acquisition.
 */
bool gps_recovery_due(bool anchor_available, uint32_t now_ms,
                      uint32_t last_epoch_progress_ms,
                      uint32_t last_pvt_ms);

/* Advance the slower cross-cycle stale-navigation recovery ladder.
 * Navigation progress or a RESET_N already attempted in this acquisition
 * clears the streak. Otherwise increment it (saturating) and return true only
 * when the threshold is reached; the firing step clears the streak too. */
bool gps_stale_ladder_step(bool navigation_progressed,
                           bool reset_already_attempted,
                           uint8_t threshold,
                           uint8_t* streak);

#endif /* GPS_FRESHNESS_H */
