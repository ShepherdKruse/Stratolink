#include "gps_ublox.h"
#include "stratolink_pins.h"
#include "config.h"
#include "power_manager.h"
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
    return gnss.setDynamicModel((dynModel)GPS_DYNMODEL_AIRBORNE_4G);
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

    /* Wake the module from software-backup (UBX-RXM-PMREQ with UARTRX
     * wakeup source).  The SparkFun library's checkUblox()/getLatitude()
     * are passive UART reads — they don't generate the TX activity the
     * module needs to wake.  Push a couple of dummy bytes onto the UART
     * to trigger wake, then wait for the module's UART RX handler to
     * come up before we start polling.  ~10 ms is conservative against
     * u-blox MAX-M10S spec (~2 ms wake-up). */
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.flush();
    delay(10);

    uint32_t deadline = millis() + timeout_ms;
    uint32_t last_kick = millis();
    while (millis() < deadline) {
        gnss.checkUblox();
        fill_fix_from_gnss(&last_fix);
        if (last_fix.valid) {
            *fix = last_fix;
            return true;
        }
        /* Refresh IWDG every ~5 s so a long no-fix poll can't outlast
         * the watchdog's 32.7 s timeout.  IWDG init lives in
         * power_manager_init(); we just pet it from here too. */
        if (millis() - last_kick >= 5000) {
            power_manager_kick_watchdog();
            last_kick = millis();
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

void gps_ublox_sleep(void) {
    /* UBX-RXM-PMREQ with duration=0 + UART-RX wake source = indefinite
     * software-backup until the MCU sends UART activity.  ~15 µA in
     * backup vs ~25 mA in continuous mode — the difference between
     * "supercap dies in 2 min" and "lasts hours". */
    (void)gnss.powerOffWithInterrupt(0, VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, false, 0);
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

void gps_ublox_sleep(void) {
    /* No-op when GNSS is compiled out. */
}

#endif /* GNSS_ENABLE */
