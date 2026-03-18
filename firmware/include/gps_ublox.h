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
 * Get last known fix without blocking (e.g. after get_fix succeeded).
 */
void gps_ublox_get_last_fix(gps_fix_t* fix);

#endif /* GPS_UBLOX_H */
