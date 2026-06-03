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
static uint32_t  last_pvt_itow = 0xFFFFFFFFu; /* last accepted PVT's iTOW (freshness anchor).
                                               * Init = an impossible iTOW (> max ~6.048e8 ms/week)
                                               * so the first fix AND the weekly iTOW==0 rollover
                                               * both register as fresh. */
static uint8_t   consecutive_no_fresh = 0; /* no-fresh-fix cycles, drives reset recovery */

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

/* Hardware-reset the u-blox via PIN_GPS_RESET_N (active-low, 10 kΩ pullup R18)
 * to un-stick a module that has WEDGED, stopped answering after a backup-wake.
 * A wedged module ignores the UART, so a UBX soft-reset can't reach it; only
 * the reset line works.  After the pulse, re-sync the library + dyn model. */
static void gps_ublox_reset(void) {
    pinMode(PIN_GPS_RESET_N, OUTPUT);
    digitalWrite(PIN_GPS_RESET_N, LOW);     /* assert reset */
    delay(20);
    pinMode(PIN_GPS_RESET_N, INPUT);        /* release: pullup deasserts reset */
    power_manager_kick_watchdog();
    delay(1000);                            /* let the module cold-boot */
    (void)gnss.begin(GPS_SERIAL);           /* re-sync library state to the fresh module */
    (void)gps_ublox_set_airborne_4g();
    power_manager_kick_watchdog();
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms) {
    if (!fix) return false;

    /* Wake the module from software-backup (UBX-RXM-PMREQ with UARTRX wakeup
     * source).  Passive UART reads don't generate the TX activity the module
     * needs to wake, push a couple of dummy bytes, then give the module's UART
     * RX handler ~10 ms to come up (MAX-M10S spec ~2 ms wake-up). */
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.flush();
    delay(10);

    /* Re-apply AIRBORNE_4G on every wake.  A hot-wake from software-backup keeps
     * its config, but a cold start (brown-out, or the PA0 reset below) reverts to
     * the default "Portable" model (12 km ceiling) and would silently kill fixes
     * at float, so re-assert it each cycle.  Idempotent, ~60 ms.  (NB: not an SEU
     * guard, cosmic-ray upset was quantitatively refuted; see
     * analysis/diagnostics/WAKE_WEDGE_ROOT_CAUSE.md.) */
    (void)gps_ublox_set_airborne_4g();

    /* Accept a fix ONLY when a genuinely FRESH NAV-PVT arrives this cycle:
     *   - gnss.getPVT() returns true only when a NEW PVT was received, AND
     *   - its iTOW advanced (a re-served buffered PVT can't pass), AND
     *   - the fix is OK with >= 4 satellites.
     * We never read the cached position getters on a silent module, so a wedged
     * GPS can no longer have its last fix re-shipped as valid, it reports
     * NOGPS.  (The stale-fix bug: getGnssFixOk()/getLatitude() return the last
     * cached PVT with no freshness check when the module is silent, see
     * GPS_BUG_BOARD2.md and the SparkFun u-blox v3 source.) */
    uint32_t deadline = millis() + timeout_ms;
    uint32_t last_kick = millis();
    bool module_responded = false;          /* did the module answer at all this cycle? */
    while ((int32_t)(deadline - millis()) > 0) {
        if (gnss.getPVT()) {
            module_responded = true;        /* alive, sent a PVT (with or without a fix) */
            uint32_t itow = gnss.getTimeOfWeek();
            if (itow != last_pvt_itow) {            /* genuinely new epoch */
                last_pvt_itow = itow;
                uint8_t siv = (uint8_t)gnss.getSIV();
                if (gnss.getGnssFixOk() && siv >= 4) {
                    last_fix.lat_e7     = gnss.getLatitude();
                    last_fix.lon_e7     = gnss.getLongitude();
                    last_fix.altitude_m = gnss.getAltitude() / 1000;
                    last_fix.speed_cm_s = (uint16_t)(gnss.getGroundSpeed() / 10);
                    int32_t head = gnss.getHeading();
                    if (head < 0) head += 3600000;
                    last_fix.heading_cd = (uint16_t)((head / 100) % 36000);
                    last_fix.satellites = siv;
                    last_fix.valid      = true;
                    consecutive_no_fresh = 0;
                    *fix = last_fix;
                    return true;
                }
            }
        }
        /* Refresh IWDG every ~5 s so a long no-fix poll can't outlast the
         * watchdog's 32.7 s timeout. */
        if (millis() - last_kick >= 5000) {
            power_manager_kick_watchdog();
            last_kick = millis();
        }
        delay(100);
    }

    /* No fresh, usable fix this cycle -> report NOGPS.  Invalidate the cache so
     * nothing downstream can resurrect a stale fix. */
    last_fix.valid  = false;
    fix->valid      = false;
    fix->satellites = 0;

    /* Escalate to a reset ONLY for a truly SILENT (wedged) module.  A module
     * that answered getPVT() but had no usable fix is just acquiring / poor
     * sky, an honest NOGPS, not a wedge, so don't reset it and interrupt a
     * legitimate cold acquisition.  The wedge (flight freezes lasting hours)
     * is specifically "module stopped answering after its backup-wake." */
    if (module_responded) {
        consecutive_no_fresh = 0;
    } else if (++consecutive_no_fresh >= GPS_STALE_RECOVERY_CYCLES) {
        consecutive_no_fresh = 0;
        gps_ublox_reset();
    }
    return false;
}

void gps_ublox_get_last_fix(gps_fix_t* fix) {
    if (fix) *fix = last_fix;
}

void gps_ublox_sleep(void) {
    /* UBX-RXM-PMREQ with duration=0 + UART-RX wake source = indefinite
     * software-backup until the MCU sends UART activity.  ~15 µA in
     * backup vs ~25 mA in continuous mode, the difference between
     * "supercap dies in 2 min" and "lasts hours".
     *
     * maxWait=300 ms: wait for the GPS to ACK the command.  Without
     * this (maxWait=0) the library returns immediately after queuing
     * the UART write; entering STOP1 ~µs later cuts the UART clock
     * mid-frame and the PMREQ never reaches the module, GPS stays in
     * continuous tracking and drains the cap in ~60 s.  Empirically
     * verified post-flash on 2026-05-15. */
    (void)gnss.powerOffWithInterrupt(0,
                                     VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX,
                                     false,
                                     300);
    GPS_SERIAL.flush();  /* belt + suspenders: ensure UART drains */
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
