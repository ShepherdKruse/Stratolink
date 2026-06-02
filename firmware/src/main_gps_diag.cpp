/* GPS continuous-acquisition diagnostic (board bring-up / antenna check).
 *
 * Runs the u-blox MAX-M10S FLAT OUT, never sleeps it, no 30 s/cycle cap,  * and exposes live state in a RAM struct read over J-Link. Purpose: tell apart
 *   (a) "GPS antenna/RF dead"        -> gd.siv stays 0 forever, even running continuously
 *   (b) "module not talking"         -> gd.init_ok == 0
 *   (c) "fine, the 30 s budget was too short indoors" -> gd.siv climbs given continuous time
 *
 * Read with J-Link:  mem32 <addr of gd> 11   (addr from `arm-none-eabi-nm`)
 * Field order matches the struct below.
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

/* Live diagnostics block, contiguous so one J-Link mem32 read grabs it all.
 * magic = 0x6D107A61 marks the struct in a RAM dump. */
typedef struct {
    uint32_t magic;
    uint32_t init_ok;    /* gnss.begin() succeeded -> module answers UBX */
    uint32_t loops;      /* loop() iterations (proves we're running) */
    uint32_t pvt_count;  /* fresh PVT messages received */
    int32_t  siv;        /* satellites tracked */
    int32_t  fix_type;   /* 0 none, 2 = 2D, 3 = 3D */
    int32_t  fix_ok;     /* gnssFixOK flag */
    int32_t  lat_e7;
    int32_t  lon_e7;
    uint32_t itow;       /* GPS time-of-week (ms) of last fresh PVT */
    uint32_t uptime_s;
} gps_diag_t;

volatile gps_diag_t gd = { 0x6D107A61, 0, 0, 0, -1, -1, -1, 0, 0, 0, 0 };

static bool set_airborne_4g(void) {
#if defined(DYN_MODEL_AIRBORNE_4G)
    return gnss.setDynamicModel(DYN_MODEL_AIRBORNE_4G);
#else
    return gnss.setDynamicModel((dynModel)GPS_DYNMODEL_AIRBORNE_4G);
#endif
}

void setup() {
    GPS_SERIAL.begin(GPS_BAUD);
    /* Nudge the module out of any software-backup left by the previous
     * firmware (UART activity is the wake trigger). */
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.flush();
    delay(100);

    bool ok = gnss.begin(GPS_SERIAL);
    gd.init_ok = ok ? 1u : 0u;
    if (ok) {
        (void)set_airborne_4g();
    }
}

void loop() {
    if (gnss.getPVT()) {            /* true only on a *fresh* PVT */
        gd.pvt_count++;
        gd.itow = gnss.getTimeOfWeek();
    }
    gnss.checkUblox();
    gd.siv      = (int32_t)gnss.getSIV();
    gd.fix_type = (int32_t)gnss.getFixType();
    gd.fix_ok   = gnss.getGnssFixOk() ? 1 : 0;
    gd.lat_e7   = gnss.getLatitude();
    gd.lon_e7   = gnss.getLongitude();
    gd.uptime_s = millis() / 1000u;
    gd.loops++;
    delay(200);
}
