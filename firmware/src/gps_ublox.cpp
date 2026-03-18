#include "gps_ublox.h"
#include "board.h"
#include "config.h"
#include <Arduino.h>

#if defined(GNSS_ENABLE) && GNSS_ENABLE

#if __has_include(<SparkFun_u-blox_GNSS_v3.h>)
#include <SparkFun_u-blox_GNSS_v3.h>
static SFE_UBLOX_GNSS_SERIAL gnss;
#else
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
static SFE_UBLOX_GNSS gnss;
#endif

static gps_fix_t last_fix;

bool gps_ublox_init(void) {
    GPS_SERIAL.begin(GPS_BAUD);
    bool ok = gnss.begin(GPS_SERIAL);
    if (ok) {
        (void)gps_ublox_set_airborne_4g();
    }
    last_fix.valid = false;
    return ok;
}

bool gps_ublox_set_airborne_4g(void) {
#if defined(DYN_MODEL_AIRBORNE_4G)
    return gnss.setDynamicModel(DYN_MODEL_AIRBORNE_4G);
#else
    return gnss.setDynamicModel((uint8_t)GPS_DYNMODEL_AIRBORNE_4G);
#endif
}

static void fill_fix_from_gnss(gps_fix_t* fix) {
    if (!fix) return;
    fix->lat_e7       = gnss.getLatitude();
    fix->lon_e7      = gnss.getLongitude();
    fix->altitude_m  = gnss.getAltitude() / 1000;
    int32_t speed_mm_s = gnss.getGroundSpeed();
    fix->speed_cm_s  = (uint16_t)(speed_mm_s / 10);
    int32_t head = gnss.getHeading();
    if (head < 0) head += 3600000;
    fix->heading_cd  = (uint16_t)((head / 100) % 36000);
    fix->satellites  = (uint8_t)gnss.getSIV();
    fix->valid       = gnss.getGnssFixOk() && fix->satellites >= 4;
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms) {
    if (!fix) return false;
    uint32_t deadline = millis() + timeout_ms;
    while (millis() < deadline) {
        gnss.checkUblox();
        fill_fix_from_gnss(&last_fix);
        if (last_fix.valid) {
            *fix = last_fix;
            return true;
        }
        delay(100);
    }
    *fix = last_fix;
    fix->valid = false;
    return false;
}

void gps_ublox_get_last_fix(gps_fix_t* fix) {
    if (fix) *fix = last_fix;
}

#else

bool gps_ublox_init(void) {
    last_fix.valid = false;
    return true;
}

bool gps_ublox_set_airborne_4g(void) {
    return true;
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms) {
    (void)timeout_ms;
    if (fix) {
        fix->valid = false;
        *fix = last_fix;
    }
    return false;
}

void gps_ublox_get_last_fix(gps_fix_t* fix) {
    if (fix) *fix = last_fix;
}

#endif /* GNSS_ENABLE */
