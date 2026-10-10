/* GPS I2C WEDGE-PROBE diagnostic v2  (board #2, J-Link RAM read)
 *
 * WHY: on the current PCB the GPS EXTINT is tied to GND, so the robust u-blox
 * hardware wake is unavailable, UART-RX is the only software wake, and the
 * intermittent "wedge" (module stops answering UART after a software-backup nap)
 * can only be RECOVERED, not prevented. A PA0 RESET_N un-stick clears the GPS
 * BBR -> cold start (~46% of the 1F supercap; see analysis/power/gps_start_power).
 * The GPS is ALSO on the shared I2C bus at 0x42 (DDC). v1 proved the DDC ACKs even
 * in confirmed backup but delivered NO nav data (avail=0, output never enabled),
 * and I2C did NOT wake the module. v2 enables I2C UBX output and actively POLLS a
 * PVT over I2C, to answer "can I2C hand us a FIX when UART is down?" (the real
 * recovery question), and bulletproofs the backup confound by verifying NMEA is on.
 *
 * Each cycle (mirrors the real GPS cycle from gps_ublox.cpp):
 *   1. Wake over UART (0xFF nudge + airborne) and poll a FRESH PVT, wedge detector.
 *   2. Probe DDC raw (ACK? bytes-available?) AND poll a PVT over I2C (data path).
 *   3. Confirm NMEA streams on UART while awake (validates the backup check).
 *   4. UART software-backup (UBX-RXM-PMREQ).
 *   5. Confirm it slept (passive NMEA watch), then re-probe I2C (ACK + PVT poll)
 *      twice, then check whether the I2C traffic woke it.
 *
 * KEY READOUTS (read `ip` over J-Link):
 *   i2c_present / i2c_init_ok        -> DDC wired + command/response path works
 *   i2c_pvt_ok                       -> can we read a fix over I2C while awake
 *   nmea_on                          -> 1 validates backup_confirmed (NMEA really on)
 *   backup_confirmed & i2c_ack_backup-> DDC ACKs in true backup (liveness survives)
 *   i2c_pvt_in_backup                -> PVT over I2C in backup? (expect 0, core asleep)
 *   woke_by_i2c_backup               -> did I2C traffic wake it (alt wake path?)
 *   i2c_alive_during_uart_wedge      -> UART silent but I2C answered (needs a natural wedge to hit)
 *
 * READ:  arm-none-eabi-nm .pio/build/gps_iprobe/firmware.elf | grep ' ip$'
 *        JLinkExe -device STM32WLE5CC -if SWD -speed 4000 -autoconnect 1
 *          mem32 <addr> 24            (24 words = 96 bytes)
 *
 * Bench-only diag, no watchdog.
 */
#include <Arduino.h>
#include <Wire.h>
#include "stratolink_pins.h"
#include "config.h"

#if __has_include(<SparkFun_u-blox_GNSS_v3.h>)
#include <SparkFun_u-blox_GNSS_v3.h>
static SFE_UBLOX_GNSS_SERIAL gnss;        /* primary: UART */
static SFE_UBLOX_GNSS        gnss_i2c;    /* secondary: DDC / I2C poll path */
#else
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
static SFE_UBLOX_GNSS gnss;
static SFE_UBLOX_GNSS gnss_i2c;
#endif

#define SLEEP_MS         15000   /* short backup between cycles to compress runtime */
#define POLL_TIMEOUT_MS  30000   /* matches the firmware's 30 s UART GPS window */

typedef struct {
    uint32_t magic;                     /* 0x49324350 "I2CP" */
    uint32_t init_ok;                   /* UART gnss.begin() ok at boot */
    uint32_t i2c_init_ok;               /* I2C gnss_i2c.begin() ok (DDC cmd/response works) */
    uint32_t cycle;
    /* --- UART side: the wedge detector --- */
    uint32_t uart_resp;                 /* 1 = fresh PVT (advanced iTOW) over UART */
    uint32_t consec_uart_silent;        /* consecutive UART-silent cycles (the wedge) */
    uint32_t max_consec_uart_silent;
    uint32_t wedge_cycles_seen;
    uint32_t itow;
    uint32_t nmea_on;                   /* awake module streams NMEA on UART (validates backup chk) */
    /* --- I2C side: AWAKE --- */
    uint32_t i2c_present;               /* sticky: 0x42 ACKed at least once */
    uint32_t i2c_ack_awake;             /* ACK while awake */
    int32_t  i2c_avail_awake;           /* DDC bytes-available; -1 = no ACK / 0xFFFF idle */
    uint32_t i2c_stream_awake;          /* saw UBX 0xB562 / NMEA '$' in stream */
    uint32_t i2c_pvt_ok;                /* got a PVT polled over I2C while awake */
    uint32_t i2c_pvt_itow;              /* iTOW of the I2C-polled PVT */
    /* --- I2C side: IN-BACKUP --- */
    uint32_t backup_confirmed;          /* UART went silent after PMREQ (really asleep) */
    uint32_t i2c_ack_backup;            /* ACK ~1.5 s into backup */
    int32_t  i2c_avail_backup;
    uint32_t i2c_ack_backup_late;       /* still ACKing ~2.5 s into backup */
    uint32_t i2c_pvt_in_backup;         /* PVT poll over I2C succeeded in backup? (expect 0) */
    uint32_t woke_by_i2c_backup;        /* module streaming again after the I2C probe */
    /* --- the payoff --- */
    uint32_t i2c_alive_during_uart_wedge; /* UART silent AND I2C answered */
    uint32_t uptime_s;
} ip_t;

volatile ip_t ip = { 0x49324350, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                     0, 0, -1, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0 };

static void set_airborne_4g(void) {
#if defined(DYN_MODEL_AIRBORNE_4G)
    gnss.setDynamicModel(DYN_MODEL_AIRBORNE_4G);
#else
    gnss.setDynamicModel((dynModel)GPS_DYNMODEL_AIRBORNE_4G);
#endif
}

/* Passively check (READ ONLY, no UART TX, which would be an armed wake edge)
 * whether the module is emitting its default ~1 Hz NMEA stream on UART. */
static bool uart_is_streaming(uint32_t win_ms) {
    while (GPS_SERIAL.available()) (void)GPS_SERIAL.read();
    uint32_t d = millis() + win_ms;
    while ((int32_t)(d - millis()) > 0) {
        if (GPS_SERIAL.available()) return true;
        delay(10);
    }
    return false;
}

/* Raw u-blox DDC liveness probe, just Wire, can't perturb the library state. */
static void i2c_probe(bool* ack, int32_t* avail, bool* stream) {
    *ack = false; *avail = -1; *stream = false;

    Wire.beginTransmission((uint8_t)GPS_I2C_ADDR);
    if (Wire.endTransmission() != 0) return;
    *ack = true;

    Wire.beginTransmission((uint8_t)GPS_I2C_ADDR);
    Wire.write((uint8_t)0xFD);
    if (Wire.endTransmission(false) != 0) return;
    if (Wire.requestFrom((uint8_t)GPS_I2C_ADDR, (uint8_t)2) != 2) return;
    uint16_t hi = (uint16_t)Wire.read();
    uint16_t lo = (uint16_t)Wire.read();
    uint16_t n  = (uint16_t)((hi << 8) | lo);
    if (n == 0xFFFF) { *avail = -1; return; }
    *avail = (int32_t)n;
    if (n == 0) return;

    uint8_t want = n > 32 ? 32 : (uint8_t)n;
    Wire.beginTransmission((uint8_t)GPS_I2C_ADDR);
    Wire.write((uint8_t)0xFF);
    if (Wire.endTransmission(false) != 0) return;
    uint8_t got = Wire.requestFrom((uint8_t)GPS_I2C_ADDR, want);
    uint8_t prev = 0;
    for (uint8_t i = 0; i < got; i++) {
        uint8_t b = (uint8_t)Wire.read();
        if (b == 0xB5 || b == (uint8_t)'$' || (prev == 0xB5 && b == 0x62)) *stream = true;
        prev = b;
    }
}

void setup() {
    /* UART GPS (same as the flight firmware) */
    GPS_SERIAL.begin(GPS_BAUD);
    GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.flush();
    delay(100);
    ip.init_ok = gnss.begin(GPS_SERIAL) ? 1u : 0u;
    if (ip.init_ok) set_airborne_4g();

    /* Shared I2C bus, PA11 SDA / PA12 SCL, 4.7k pull-ups (R11/R12) */
    Wire.setSDA(PIN_I2C_SDA);
    Wire.setSCL(PIN_I2C_SCL);
    Wire.begin();
    Wire.setClock(100000);

    /* Secondary GNSS on the DDC. begin() polls UBX-MON-VER over I2C, success means
     * the I2C command/response path works. Enable UBX output on the I2C port so the
     * DDC actually carries nav messages (v1 saw avail=0 because it was never on). */
    ip.i2c_init_ok = gnss_i2c.begin(Wire, (uint8_t)GPS_I2C_ADDR) ? 1u : 0u;
    if (ip.i2c_init_ok) gnss_i2c.setI2COutput(COM_TYPE_UBX);
}

void loop() {
    ip.cycle++;

    /* ---- WAKE via UART (exact firmware sequence) ---- */
    GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.write((uint8_t)0xFF); GPS_SERIAL.flush();
    delay(10);
    set_airborne_4g();

    /* ---- UART poll: fresh PVT? (the wedge detector) ---- */
    uint32_t deadline = millis() + POLL_TIMEOUT_MS;
    bool uart_resp = false;
    while ((int32_t)(deadline - millis()) > 0) {
        if (gnss.getPVT()) {
            uint32_t itow = gnss.getTimeOfWeek();
            if (itow != ip.itow) { ip.itow = itow; uart_resp = true; break; }
        }
        delay(50);
    }

    /* ---- I2C probe WHILE AWAKE: raw liveness + an actual PVT poll ---- */
    bool ack = false; int32_t avail = -1; bool stream = false;
    i2c_probe(&ack, &avail, &stream);
    if (ack) ip.i2c_present = 1u;
    ip.i2c_ack_awake   = ack ? 1u : 0u;
    ip.i2c_avail_awake = avail;
    ip.i2c_stream_awake = stream ? 1u : 0u;

    if (gnss_i2c.getPVT()) { ip.i2c_pvt_ok = 1u; ip.i2c_pvt_itow = gnss_i2c.getTimeOfWeek(); }
    else                   { ip.i2c_pvt_ok = 0u; }

    /* ---- NMEA confound check: a known-awake module, does it stream NMEA on UART?
     * If yes, backup_confirmed (NMEA-absent => asleep) is trustworthy. ---- */
    if (uart_resp) ip.nmea_on = uart_is_streaming(1500) ? 1u : 0u;

    /* ---- wedge bookkeeping + the smoking-gun correlation ---- */
    if (uart_resp) {
        ip.uart_resp = 1u;
        ip.consec_uart_silent = 0u;
    } else {
        ip.uart_resp = 0u;
        ip.consec_uart_silent++;
        if (ip.consec_uart_silent > ip.max_consec_uart_silent)
            ip.max_consec_uart_silent = ip.consec_uart_silent;
        ip.wedge_cycles_seen++;
        if (ack || ip.i2c_pvt_ok) ip.i2c_alive_during_uart_wedge++;  /* UART dead, I2C alive */
    }

    /* ---- SLEEP GPS via UART backup (exact firmware sequence) ---- */
    (void)gnss.powerOffWithInterrupt(0, VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, false, 300);
    GPS_SERIAL.flush();

    /* ---- CONFIRM backup WITHOUT waking it (passive NMEA watch) ---- */
    delay(300);
    ip.backup_confirmed = uart_is_streaming(1200) ? 0u : 1u;

    /* ---- I2C IN BACKUP: raw ACK (x2) + an actual PVT poll ---- */
    bool ba = false; int32_t bav = -1; bool bs = false;
    i2c_probe(&ba, &bav, &bs);
    ip.i2c_ack_backup   = ba ? 1u : 0u;
    ip.i2c_avail_backup = bav;
    ip.i2c_pvt_in_backup = gnss_i2c.getPVT() ? 1u : 0u;   /* expect 0, core asleep */
    delay(1000);
    bool bl = false; int32_t blav = -1; bool bls = false;
    i2c_probe(&bl, &blav, &bls);
    ip.i2c_ack_backup_late = bl ? 1u : 0u;

    /* ---- did the in-backup I2C traffic WAKE the module? ---- */
    ip.woke_by_i2c_backup = uart_is_streaming(300) ? 1u : 0u;

    ip.uptime_s = millis() / 1000u;
    delay(SLEEP_MS);
}
