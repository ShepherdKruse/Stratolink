/* GPS sleep/wake WEDGE diagnostic.
 *
 * Replicates the flight firmware's GPS cycle exactly, wake (UART nudge +
 * re-apply airborne model) -> poll for a fresh PVT -> sleep (UBX-RXM-PMREQ
 * software-backup) -> repeat, and measures, per cycle, whether the module
 * ANSWERS after its nap. The flight STALE bug is an intermittent failure to
 * wake/answer (data ruled out temp/power/altitude/runtime), so `consec_no_resp`
 * climbing IS that wedge, caught live over J-Link.
 *
 * Responsive = a fresh PVT with an ADVANCED iTOW arrives within the window.
 * Wedged     = iTOW frozen / no PVT for the whole 30 s window (exactly the
 *              condition under which the real firmware ships its stale cache).
 *
 * SLEEP_MS is shortened to cycle fast (compress the flight's ~2.4 h-to-first-
 * wedge into minutes); set to 300000 to match the FULL-tier 5-min backup.
 *
 * Read with J-Link:  mem32 <addr of gw> 14   (addr from arm-none-eabi-nm)
 */
#include <Arduino.h>
#include "stratolink_pins.h"
#include "config.h"

#if __has_include(<SparkFun_u-blox_GNSS_v3.h>)
#include <SparkFun_u-blox_GNSS_v3.h>
static SFE_UBLOX_GNSS_SERIAL gnss;
#else
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
static SFE_UBLOX_GNSS gnss;
#endif

#define SLEEP_MS         15000   /* GPS backup duration between cycles (fast cycling) */
#define POLL_TIMEOUT_MS  30000   /* matches firmware's 30 s GPS window */

typedef struct {
    uint32_t magic;              /* 0x57414B45 "WAKE" */
    uint32_t init_ok;            /* gnss.begin() ok at boot */
    uint32_t cycle;              /* sleep/wake cycles completed */
    uint32_t wake_resp;          /* 1 = module answered (iTOW advanced) this cycle */
    uint32_t got_fix;            /* 1 = fixType >= 3 this cycle */
    uint32_t consec_no_resp;     /* consecutive cycles module did NOT answer (the wedge) */
    uint32_t max_consec_no_resp; /* worst streak so far */
    uint32_t total_no_resp;      /* total no-answer cycles */
    int32_t  siv;
    int32_t  fix_type;
    uint32_t itow;
    uint32_t wake_latency_ms;    /* wake -> first fresh PVT (POLL_TIMEOUT if wedged) */
    int32_t  lat_e7;
    uint32_t uptime_s;
} gw_t;

volatile gw_t gw = { 0x57414B45, 0, 0, 0, 0, 0, 0, 0, -1, -1, 0, 0, 0, 0 };

static void set_airborne_4g(void) {
#if defined(DYN_MODEL_AIRBORNE_4G)
    gnss.setDynamicModel(DYN_MODEL_AIRBORNE_4G);
#else
    gnss.setDynamicModel((dynModel)GPS_DYNMODEL_AIRBORNE_4G);
#endif
}

void setup() {
    GPS_SERIAL.begin(GPS_BAUD);
    GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.flush();
    delay(100);
    gw.init_ok = gnss.begin(GPS_SERIAL) ? 1u : 0u;
    if (gw.init_ok) set_airborne_4g();
}

void loop() {
    gw.cycle++;

    /* ---- WAKE (exact firmware sequence from gps_ublox_get_fix) ---- */
    GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.flush();
    delay(10);
    set_airborne_4g();

    /* ---- POLL: did the module answer with a *fresh* PVT? ---- */
    uint32_t t0 = millis();
    uint32_t deadline = t0 + POLL_TIMEOUT_MS;
    bool responded = false;
    while ((int32_t)(deadline - millis()) > 0) {
        if (gnss.getPVT()) {
            uint32_t itow = gnss.getTimeOfWeek();
            if (itow != gw.itow) {           /* iTOW advanced => module alive & answering */
                gw.itow = itow;
                gw.siv = (int32_t)gnss.getSIV();
                gw.fix_type = (int32_t)gnss.getFixType();
                gw.lat_e7 = gnss.getLatitude();
                gw.wake_latency_ms = millis() - t0;
                responded = true;
                break;
            }
        }
        delay(50);
    }

    if (responded) {
        gw.wake_resp = 1;
        gw.got_fix = (gw.fix_type >= 3) ? 1u : 0u;
        gw.consec_no_resp = 0;
    } else {
        gw.wake_resp = 0;
        gw.got_fix = 0;
        gw.consec_no_resp++;
        gw.total_no_resp++;
        if (gw.consec_no_resp > gw.max_consec_no_resp) gw.max_consec_no_resp = gw.consec_no_resp;
        gw.wake_latency_ms = POLL_TIMEOUT_MS;
    }
    gw.uptime_s = millis() / 1000u;

    /* ---- SLEEP GPS (exact firmware sequence from gps_ublox_sleep) ---- */
    (void)gnss.powerOffWithInterrupt(0, VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, false, 300);
    GPS_SERIAL.flush();
    delay(SLEEP_MS);
}
