#include "gps_pvt_validation.h"

bool gps_pvt_to_wire_fix(const gps_pvt_values_t* pvt, gps_wire_fix_t* out) {
    if (!pvt || !out) return false;
    if (pvt->lat_e7 < -900000000 || pvt->lat_e7 > 900000000 ||
        pvt->lon_e7 < -1800000000 || pvt->lon_e7 > 1800000000 ||
        pvt->altitude_mm < -500000 || pvt->altitude_mm > 60000000 ||
        pvt->ground_speed_mm_s < 0 ||
        pvt->ground_speed_mm_s > 500000 ||
        pvt->heading_e5 < 0 || pvt->heading_e5 >= 36000000 ||
        pvt->satellites < 4 || pvt->satellites > 64) {
        return false;
    }

    gps_wire_fix_t converted = {};
    converted.lat_e7 = pvt->lat_e7;
    converted.lon_e7 = pvt->lon_e7;
    converted.altitude_m = pvt->altitude_mm / 1000;
    converted.speed_cm_s =
        (uint16_t)(pvt->ground_speed_mm_s / 10);
    converted.heading_cdeg =
        (uint16_t)(pvt->heading_e5 / 1000);
    converted.satellites = pvt->satellites;
    *out = converted;
    return true;
}
