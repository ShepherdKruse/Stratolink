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
 * Returns true if fix.valid, false on timeout or error.
 */
bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms);

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
 * Put the u-blox MAX-M10S into SOFTWARE STANDBY mode (UBX-RXM-PMREQ).
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
 * Returns true only after a RAM-only periodic UBX marker becomes silent for
 * more than three marker periods. Returns false after bounded reset/retries;
 * the caller must use a short retry sleep and suppress optional loads.
 */
bool gps_ublox_sleep(void);

#endif /* GPS_UBLOX_H */
