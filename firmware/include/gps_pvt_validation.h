#ifndef GPS_PVT_VALIDATION_H
#define GPS_PVT_VALIDATION_H

#include <stdbool.h>
#include <stdint.h>

/*
 * Values copied from one checksum-valid UBX-NAV-PVT before they are admitted
 * to telemetry, regional selection, or the B2B crumb service.
 */
typedef struct {
    int32_t lat_e7;
    int32_t lon_e7;
    int32_t altitude_mm;
    int32_t ground_speed_mm_s;
    int32_t heading_e5;
    uint8_t satellites;
} gps_pvt_values_t;

/* The bounded representation shared by telemetry v1 and v2. */
typedef struct {
    int32_t lat_e7;
    int32_t lon_e7;
    int32_t altitude_m;
    uint16_t speed_cm_s;
    uint16_t heading_cdeg;
    uint8_t satellites;
} gps_wire_fix_t;

/*
 * Validate and convert a fresh PVT atomically. The receiver's fixOK flag and
 * epoch freshness are necessary but not sufficient: an impossible yet
 * checksum-valid field must never contaminate telemetry, select a frequency
 * plan, or enter a B2B crumb.
 *
 * Limits match the public telemetry contract and the physical mission:
 * latitude/longitude are geographic bounds, altitude is -500..60,000 m,
 * ground speed is 0..500 m/s, heading is [0,360) degrees, and at least four
 * satellites are required. Output is unchanged on rejection.
 */
bool gps_pvt_to_wire_fix(const gps_pvt_values_t* pvt, gps_wire_fix_t* out);

#endif /* GPS_PVT_VALIDATION_H */
