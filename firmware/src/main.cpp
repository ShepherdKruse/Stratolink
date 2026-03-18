/**
 * Stratolink firmware — Phase 1–4.
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
#include "board.h"
#include "telemetry.h"
#include "power_adc.h"
#include "gps_ublox.h"
#include "lorawan.h"
#include "power_manager.h"
#include "sensors.h"
#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "sensor_lis2dh12.h"

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

void setup() {
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
    if (!lorawan_join(60000)) {
        LOG("LoRaWAN join failed");
    }

    if (!sensors_init()) {
        LOG("Sensors init failed");
    }

    (void)sensor_lis2dh12_enable_freefall_int1();
    power_manager_init();
    power_manager_attach_freefall_wakeup();

    last_gps_fix.valid = false;
    LOG("Setup done");
}

void loop() {
    if (power_manager_did_wake_from_freefall()) {
        burst_mode = true;
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
        } else {
            gps_ublox_get_last_fix(&last_gps_fix);
            if (last_gps_fix.valid) {
                ti.lat_e7         = last_gps_fix.lat_e7;
                ti.lon_e7         = last_gps_fix.lon_e7;
                ti.altitude_m     = last_gps_fix.altitude_m;
                ti.gps_speed_cm_s = last_gps_fix.speed_cm_s;
                ti.gps_heading_cd = last_gps_fix.heading_cd;
                ti.gps_satellites = last_gps_fix.satellites;
            }
        }
    }

    if (power_adc_should_read_sensors()) {
        (void)sensor_tmp117_read_centidegrees(&ti.temperature_cd);
        (void)sensor_ms5611_read_pressure_centihpa(&ti.pressure_ch);
        (void)sensor_lis2dh12_read_accel_cm_s2(&ti.accel_x_cm_s2, &ti.accel_y_cm_s2, &ti.accel_z_cm_s2);
    }
    ti.gyro_x_cd_s   = ti.gyro_y_cd_s = ti.gyro_z_cd_s = 0;
    ti.acoustic_event = 0;

    telemetry_pack(&ti, tx_payload);

    if (power_adc_can_tx() && lorawan_joined()) {
        if (lorawan_send_uplink(tx_payload, TELEMETRY_PAYLOAD_SIZE)) {
            LOG("TX OK");
        }
    }

    if (burst_mode && sensor_lis2dh12_is_freefall_cleared()) {
        burst_mode = false;
    }

    uint32_t sleep_sec = burst_mode ? (uint32_t)BURST_SLEEP_SEC : power_adc_get_sleep_interval_sec(tier);
    power_manager_sleep_ms(sleep_sec * 1000);
}
