#ifndef GPS_UBLOX_H
#define GPS_UBLOX_H

#include <stdint.h>
#include <stdbool.h>

/** Result of a GPS fix (units match telemetry payload). */
typedef struct {
    int32_t lat_e7;           /* latitude  * 1e7 */
    int32_t lon_e7;           /* longitude * 1e7 */
    int32_t altitude_m;       /* meters */
    uint16_t speed_cm_s;      /* 0.01 m/s */
    uint16_t heading_cd;      /* 0.01 deg, 0-36000 */
    uint8_t satellites;
    bool valid;               /* true if fix is usable */
} gps_fix_t;

/**
 * Observable GNSS state at the MCU sleep boundary.
 *
 * RESET_HELD means the MCU is actively driving the MAX-M10S RESET_N input
 * low. It is electrical containment, but it is not an energy qualification:
 * the board's reset-held current must still be measured on the exact
 * assembly. UNCONTAINED is deliberately zero so an uninitialized or corrupt
 * RAM value fails closed.
 */
typedef enum {
    GPS_QUIESCENCE_UNCONTAINED = 0,
    GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY = 1,
    GPS_QUIESCENCE_RESET_HELD = 2,
    GPS_QUIESCENCE_NOT_PRESENT = 3,
} gps_quiescence_result_t;

/** Result of deliberately opening RESET_N containment for an acquisition. */
typedef enum {
    GPS_RECOVERY_ALREADY_RELEASED = 0,
    GPS_RECOVERY_RESET_RELEASED = 1,
    GPS_RECOVERY_BLOCKED_LOW_RAIL = 2,
    GPS_RECOVERY_REINIT_FAILED_RESET_HELD = 3,
    GPS_RECOVERY_NOT_PRESENT = 4,
} gps_recovery_result_t;

/** Public, copy-safe subset of the J-Link-readable containment counters. */
typedef struct {
    uint32_t confirmed_software_standby;
    uint32_t early_reset_hold_entries;
    uint32_t reset_hold_entries;
    uint32_t reset_hold_reuses;
    uint32_t reset_release_attempts;
    uint32_t reset_release_denied_low_rail;
    uint32_t reset_release_failures;
    uint32_t current_state;
} gps_containment_diag_t;

/**
 * Assert RESET_N at the first executable point in setup().
 *
 * This minimizes (but cannot eliminate) the interval in which an MCU reset's
 * GPIO defaults let R18 deassert the receiver reset. It does not classify the
 * event as a terminal PMREQ failure. gps_ublox_init() respects this hold and
 * releases it only through the 4.4 V-gated recovery path.
 */
void gps_ublox_assert_reset_early(void);

/**
 * Initialize GPS UART and GNSS.
 * Call once from setup(). Uses GPS_SERIAL (Serial1) at GPS_BAUD.
 */
bool gps_ublox_init(void);

/**
 * Send UBX-CFG-NAVSPG DYNMODEL = 8 (Airborne <4g).
 * CRITICAL for stratospheric flight (required after every power-on).
 */
bool gps_ublox_set_airborne_4g(void);

/**
 * Poll for a fix until we get valid position or timeout_ms expires.
 * With explicit extension enabled, an ordinary 30 s call may continue up to
 * 180 s total from entry for cold acquisition or later reacquisition while
 * the receiver makes progress and the loaded rail permits it. Other budgets
 * (including 10 s burst) never extend. Every attempt requalifies independently;
 * live voltage supervision does not establish stored or daily energy margin.
 * Returns true if fix.valid, false on timeout or error.
 */
bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms,
                       bool allow_cold_extension = false);

/**
 * Record that a whole acquisition cycle was power-gated before get_fix().
 * The next acquisition must establish a new two-PVT freshness proof rather
 * than compare iTOW across an arbitrarily long unobserved interval.
 */
void gps_ublox_note_power_skip(void);

/**
 * Get last known fix without blocking (e.g. after get_fix succeeded).
 */
void gps_ublox_get_last_fix(gps_fix_t* fix);

/**
 * Quiesce the u-blox MAX-M10S before MCU sleep.
 *
 * The preferred result is CONFIRMED_SOFTWARE_STANDBY. If the bounded PMREQ
 * confirmation/recovery ladder fails, this function asserts PA0 RESET_N and
 * deliberately leaves it driven low, returning RESET_HELD. It must never
 * return UNCONTAINED after a terminal PMREQ failure.
 */
gps_quiescence_result_t gps_ublox_quiesce(void);

/** Return the current locally commanded/confirmed containment state. */
gps_quiescence_result_t gps_ublox_current_quiescence(void);

/**
 * Prepare a receiver held in RESET_N containment for a new acquisition.
 *
 * RESET_N is released only when the same conservative rail policy used for a
 * cold recovery reset permits it. The UART command path is then reinitialized;
 * on failure RESET_N is asserted again before this function returns. Callers
 * must treat BLOCKED_LOW_RAIL and REINIT_FAILED_RESET_HELD as a power-gated
 * NOGPS cycle and must not attempt to wake the receiver by UART.
 */
gps_recovery_result_t gps_ublox_prepare_acquisition(void);

/** Copy containment diagnostics; a null output is ignored. */
void gps_ublox_get_containment_diag(gps_containment_diag_t* diag);

/**
 * Compatibility wrapper for call sites not yet migrated to the explicit
 * result. It returns true only for confirmed software standby (or a build in
 * which GNSS is not present). RESET_HELD deliberately returns false so legacy
 * callers keep optional loads suppressed; the receiver nevertheless remains
 * physically held in reset.
 *
 * The current data sheet specifies about 46 µA at V_IO plus 0.12 µA at VCC
 * in standby, versus mA-class acquisition/tracking.
 * MUST be called before MCU STOP1 entry — without it the GPS keeps
 * tracking through sleep and drains the supercap at 25 mA, brown-
 * outing the chip in ~2 minutes of cap-only operation.
 *
 * V_BCKP is tied to VCC on this board, so RTC + almanac/ephemeris
 * are retained — next get_fix() can hot-start (~5 s TTFF).
 *
 * Wake source: UART RX activity from the MCU.  The next get_fix()
 * call sends UBX queries which wake the module implicitly.
 *
 * New code must use gps_ublox_quiesce() and retain the distinction between
 * confirmed standby, RESET_N-held containment, and an uncontained receiver.
 */
bool gps_ublox_sleep(void);

#endif /* GPS_UBLOX_H */
