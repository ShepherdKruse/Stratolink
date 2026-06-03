/**
 * Stratolink firmware, Phase 1, 4.
 * Normal: tier → GPS/sensors → pack → TX → sleep. Burst: on LIS2DH12 freefall (INT1/PA8) wake, rapid beacon until freefall clears.
 */
#include <Arduino.h>
#include "config.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#define LORAWAN_DEV_EUI ""
#define LORAWAN_APP_EUI ""
#define LORAWAN_APP_KEY ""
#endif
#include "stratolink_pins.h"
#include "telemetry.h"
#include "power_adc.h"
#include "gps_ublox.h"
#include "lorawan.h"
#include "power_manager.h"
#include "sensors.h"
#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "sensor_lis2dh12.h"
#include "sensor_ltr390.h"
#include "mic_acoustic.h"
#include "region_manager.h"

#ifndef BURST_GPS_TIMEOUT_MS
#define BURST_GPS_TIMEOUT_MS 10000
#endif
#ifndef BURST_SLEEP_SEC
#define BURST_SLEEP_SEC 10
#endif

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
#define LOG(x) Serial.println(x)
#else
#define LOG(x) ((void)0)
#endif

static uint8_t tx_payload[TELEMETRY_PAYLOAD_SIZE];
static gps_fix_t last_gps_fix;
static bool burst_mode = false;
static uint16_t burst_cycles = 0;    /* cycles spent in the current burst (runaway cap) */
static uint8_t burst_cooldown = 0;   /* normal cycles to ignore freefall re-trigger after a capped burst */
static uint8_t tx_fail_streak = 0;  /* consecutive TX failures; 5 → reset */

/* Reset-cause snapshot. RAM-only diagnostic; read via J-Link.
 * Captured before RMVF clear so each new boot writes the precise cause. */
volatile uint32_t boot_reset_cause = 0;

void setup() {
    boot_reset_cause = RCC->CSR;
    RCC->CSR |= RCC_CSR_RMVF;     /* clear flags so the next reset is unambiguous */

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
    Serial.begin(DEBUG_SERIAL_BAUD);
    LOG("Stratolink Firmware Starting");
#endif

    power_adc_init();
    if (!gps_ublox_init()) {
        LOG("GPS init failed");
    } else {
        (void)gps_ublox_set_airborne_4g();
    }
    if (!lorawan_init()) {
        LOG("LoRaWAN init failed");
    }
    /* Try to restore the previous OTAA session from TAMP backup regs
     * before attempting a fresh join.  A successful restore preserves
     * region + DevAddr + FCntUp across reset (TX-fail auto-reset,
     * brown-out, freefall-wake, etc.), avoiding a join airtime hit and
     * an FCnt-anti-replay collision on the next uplink.  TAMP survives
     * STOP/standby but not full power loss, so a deep brown-out
     * (VSTOR < 1.8 V cold-start) still triggers a fresh join, which
     * is what we want for a real cold boot. */
    {
        lorawan_session_t s;
        if (power_manager_load_session(&s) && lorawan_import_session(&s)) {
            LOG("LoRaWAN session restored from TAMP");
        } else if (!lorawan_join(60000)) {
            LOG("LoRaWAN join failed");
        } else {
            lorawan_session_t out; lorawan_export_session(&out);
            power_manager_save_session(&out);
        }
    }

    if (!sensors_init()) {
        LOG("Sensors init failed");
    }

    (void)mic_acoustic_init();
    (void)sensor_lis2dh12_enable_freefall_int1();
    power_manager_init();
    power_manager_attach_freefall_wakeup();

    last_gps_fix.valid = false;
    LOG("Setup done");
}

void loop() {
    /* IWDG runs from LSI in run mode (frozen in STOP).  Refresh at the
     * top of every loop so any hang lasting > 33 s reboots the chip. */
    power_manager_kick_watchdog();

    /* Enter burst on a freefall wake, unless we're in the post-cap cooldown.
     * The cooldown re-arms only after BURST_COOLDOWN_CYCLES *consecutive*
     * freefall-free wakes; a freefall wake during cooldown restarts the count,
     * so a persistently stuck/chattering INT1 never re-arms burst (one capped
     * window total).  Always consume the wake flag so it can't accumulate. */
    bool freefall_wake = power_manager_did_wake_from_freefall();
    if (burst_cooldown > 0) {
        burst_cooldown = freefall_wake ? BURST_COOLDOWN_CYCLES : (uint8_t)(burst_cooldown - 1);
    } else if (freefall_wake && !burst_mode) {
        burst_mode = true;
        burst_cycles = 0;
    }

    telemetry_input_t ti = {0};

    power_tier_t tier = power_adc_get_tier();
    ti.battery_mv = power_adc_read_vSTOR_mv();
    ti.solar_mv   = power_adc_read_solar_mv();

    uint32_t gps_timeout_ms = burst_mode ? (uint32_t)BURST_GPS_TIMEOUT_MS : 30000;
    if (power_adc_can_use_gps() || burst_mode) {
        if (gps_ublox_get_fix(&last_gps_fix, gps_timeout_ms)) {
            ti.lat_e7         = last_gps_fix.lat_e7;
            ti.lon_e7         = last_gps_fix.lon_e7;
            ti.altitude_m     = last_gps_fix.altitude_m;
            ti.gps_speed_cm_s = last_gps_fix.speed_cm_s;
            ti.gps_heading_cd = last_gps_fix.heading_cd;
            ti.gps_satellites = last_gps_fix.satellites;
        }
        /* No fresh fix this cycle -> GPS fields stay zero (NOGPS).  We do NOT
         * fall back to the last known fix: a wedged/silent GPS must report
         * NOGPS, never a frozen position re-shipped as valid (the stale-fix
         * bug).  gps_ublox_get_fix() gates on a fresh PVT + advancing iTOW. */
    }

    /* GPS-driven region switch.  If the balloon crossed a regulatory
     * boundary (Atlantic mid-ocean, Persian Gulf, Wallace Line) since
     * the last cycle, lorawan_set_region() invalidates the current
     * session and the re-join logic below picks it up before the next
     * TX.  No-op if region unchanged. */
    if (last_gps_fix.valid) {
        lorawan_set_region(region_for_latlon(last_gps_fix.lat_e7,
                                             last_gps_fix.lon_e7));
    }

    /* IWDG max timeout is 32.7 s.  GPS fix can block up to 30 s, TX +
     * RX1/RX2 windows ~5 s, sensor + mic reads ~1 s, kick the dog
     * between phases so the watchdog only catches genuine hangs. */
    power_manager_kick_watchdog();

    if (power_adc_should_read_sensors()) {
        (void)sensor_tmp117_read_centidegrees(&ti.temperature_cd);
        (void)sensor_ms5611_read_pressure_centihpa(&ti.pressure_ch);
        (void)sensor_lis2dh12_read_accel_cm_s2(&ti.accel_x_cm_s2, &ti.accel_y_cm_s2, &ti.accel_z_cm_s2);
        (void)sensor_ltr390_read_uv_index(&ti.uv_index);
        (void)sensor_ltr390_read_ambient_lux(&ti.ambient_lux);
        (void)mic_acoustic_detect(&ti.acoustic_event);
    }

    telemetry_pack(&ti, tx_payload);
    power_manager_kick_watchdog();

    /* If a previous join attempt failed (cold boot when the gateway was
     * briefly out of range, post-brown-out recovery, etc.) try again
     * before TX.  Short timeout, if it doesn't take here it'll retry on
     * the next wake.  IWDG (32.7 s) bounds this. */
    if (!lorawan_joined() && power_adc_can_tx()) {
        if (lorawan_join(15000)) {
            /* New region → new session.  Persist it so a reset (TX
             * fail, brown-out, freefall) doesn't force another join. */
            lorawan_session_t out; lorawan_export_session(&out);
            power_manager_save_session(&out);
        }
        power_manager_kick_watchdog();
    }

    /* VSTOR floor for uplink TX, mirroring lorawan_join()'s 3.0 V guard.  Below
     * ~3.0 V the buck is in dropout and Vdd droops hard during the +14 dBm/~50 mA
     * peak, worse at SF9 (~308 ms TX, ~3x SF7) where a long uplink can brown out
     * mid-transmit.  Gating HERE (not inside send_uplink) keeps a low-rail cycle a
     * clean skip: it must NOT feed tx_fail_streak, or a stable 2.8-3.0 V dusk rail
     * would log 5 false "failures" and force the very NVIC reset (-> rejoin spiral)
     * this guard exists to avoid. */
    bool vstor_ok_for_tx = power_adc_read_vSTOR_mv() >= 3000;
    if (power_adc_can_tx() && vstor_ok_for_tx && lorawan_joined()) {
        if (lorawan_send_uplink(tx_payload, TELEMETRY_PAYLOAD_SIZE)) {
            tx_fail_streak = 0;
            /* Persist FCntUp so a post-reset boot doesn't replay an
             * already-used counter (LoRaWAN servers reject repeats).
             * TAMP write is ~10 cycles, free in the energy budget. */
            lorawan_session_t out; lorawan_export_session(&out);
            power_manager_save_session(&out);
            LOG("TX OK");
        } else {
            /* TX failed but we believed we were joined.  Most likely the
             * SX1262 latched into a fault state, we observed this once
             * after the cap hit VBAT_OV (5.36 V) at peak sun and the
             * radio went silent for hours despite IWDG kicking and the
             * MCU running.  After N consecutive TX failures, force a
             * full system reset so lorawan_init() can re-init the radio
             * from scratch (radio->begin() runs a full SX1262 reset). */
            tx_fail_streak++;
            if (tx_fail_streak >= 5) {
                NVIC_SystemReset();
            }
        }
    }

    if (burst_mode) {
        burst_cycles++;
        if (sensor_lis2dh12_is_freefall_cleared()) {
            /* Normal exit: payload reached terminal velocity / landed (~1g). */
            burst_mode = false;
        } else if (burst_cycles >= BURST_MAX_CYCLES) {
            /* Runaway guard: freefall never cleared (stuck/chattering INT1).
             * Force-exit and latch the cooldown (re-arm needs consecutive
             * freefall-free wakes, handled at the top of loop()). */
            burst_mode = false;
            burst_cooldown = BURST_COOLDOWN_CYCLES;
        }
    }

    uint32_t sleep_sec = burst_mode ? (uint32_t)BURST_SLEEP_SEC : power_adc_get_sleep_interval_sec(tier);

    /* Quiesce the heavy peripherals before entering MCU STOP1.
     * Without these calls:
     *   - SX1262 sits in STDBY_RC (~600 µA), drains cap + hard-resets MCU on STOP2.
     *   - u-blox MAX-M10S keeps tracking (~25 mA), drains 1F cap in ~2 min.
     * Both must sleep alongside the MCU for night/no-solar survival. */
    lorawan_sleep();
    gps_ublox_sleep();

    power_manager_sleep_ms(sleep_sec * 1000);
}
