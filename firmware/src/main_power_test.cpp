/**
 * Stratolink power test — BQ25570 + 1F supercap (C5) + solar (J1/J2) bringup.
 *
 * Streams VSTOR (PA10 ADC), +SOLAR (PA15 ADC), VBAT_OK (PB5 digital) and
 * derived power tier over Serial1 @ 115200 8N1. No LoRa, no GPS, no I2C,
 * no STOP2 sleep — the MCU stays awake so you can watch transients live.
 *
 * Flash:      pio run -e power_test -t upload   (J-Link on J20 Tag-Connect)
 * Read out:   USB-UART on J4 header:
 *               J4.1 GND  -> adapter GND
 *               J4.4 TX   -> adapter RX
 *               (J4.5 RX not needed for this test)
 *               open terminal @ 115200 baud
 * Revert:     pio run -e stratolink -t upload
 *
 * Safety: do NOT leave a bench PSU soldered to J4.7 (+3.3V) while the
 * supercap + solar rig is under test. That pad is the BQ25570 buck OUTPUT;
 * back-feeding it fights the regulator and can damage U1. See the procedure
 * notes below.
 */
#include <Arduino.h>
#include "stratolink_pins.h"
#include "power_adc.h"

#define PRINT  Serial1
#define LOOP_INTERVAL_MS 1000

typedef struct {
    uint32_t magic;
    uint32_t loops;
    uint32_t vstor_mv;
    uint32_t solar_mv;
    uint32_t vbat_ok;
    uint32_t tier;
    uint32_t vdda_mv;
    uint32_t vrefint_raw;
    uint32_t vstor_raw;
    uint32_t solar_raw;
} power_test_diag_t;

/* J-Link-readable mirror for a bench without the J4 UART attached. */
volatile power_test_diag_t ptd = {
    0x50575232u, 0, 0, 0, 0, 0, 0, 0, 0, 0
}; /* "PWR2" */

static const char* tier_name(power_tier_t t) {
    switch (t) {
        case POWER_TIER_FULL:      return "FULL";
        case POWER_TIER_REDUCED:   return "REDUCED";
        case POWER_TIER_NO_GPS:    return "NO_GPS";
        case POWER_TIER_EMERGENCY: return "EMERGENCY";
        case POWER_TIER_CRITICAL:  return "CRITICAL";
        default:                   return "?";
    }
}

static power_tier_t tier_from_mv(uint16_t vstor_mv) {
    float vf = (float)vstor_mv / 1000.0f;
    if (vf >= POWER_TIER_FULL_V)      return POWER_TIER_FULL;
    if (vf >= POWER_TIER_REDUCED_V)   return POWER_TIER_REDUCED;
    if (vf >= POWER_TIER_NO_GPS_V)    return POWER_TIER_NO_GPS;
    if (vf >= POWER_TIER_EMERGENCY_V) return POWER_TIER_EMERGENCY;
    return POWER_TIER_CRITICAL;
}

void setup() {
    PRINT.begin(115200);
    uint32_t t0 = millis();
    while (!PRINT && (millis() - t0) < 2000) { /* wait for UART */ }

    PRINT.println();
    PRINT.println(F("# Stratolink power test"));
    PRINT.print  (F("# board=")); PRINT.println(F(BOARD_NAME));
    PRINT.print  (F("# rev=")); PRINT.println(F(BOARD_REVISION));
    PRINT.print  (F("# supercap="));
    PRINT.print  (SUPERCAP_CAPACITANCE_F, 2);
    PRINT.print  (F("F, VBAT_OK rise="));
    PRINT.print  (BQ25570_VBAT_OK_RISE_MV);
    PRINT.print  (F("mV, fall="));
    PRINT.print  (BQ25570_VBAT_OK_FALL_MV);
    PRINT.println(F("mV"));
    PRINT.println(F("# csv: t_ms,vstor_mv,solar_mv,vbat_ok,tier"));

    pinMode(PIN_VBAT_OK, INPUT);
    power_adc_init();
}

void loop() {
    uint32_t t  = millis();
    uint16_t vs = power_adc_read_vSTOR_mv();
    uint16_t so = power_adc_read_solar_mv();
    int      ok = digitalRead(PIN_VBAT_OK);
    power_tier_t tier = tier_from_mv(vs);
    ptd.vstor_mv = vs;
    ptd.solar_mv = so;
    ptd.vbat_ok = (uint32_t)ok;
    ptd.tier = (uint32_t)tier;
    ptd.vdda_mv = power_adc_debug_vdda_mv();
    ptd.vrefint_raw = power_adc_debug_vrefint_raw();
    ptd.vstor_raw = power_adc_debug_vstor_raw();
    ptd.solar_raw = power_adc_debug_solar_raw();
    ptd.loops++;

    PRINT.print(t);       PRINT.print(',');
    PRINT.print(vs);      PRINT.print(',');
    PRINT.print(so);      PRINT.print(',');
    PRINT.print(ok);      PRINT.print(',');
    PRINT.println(tier_name(tier));

    delay(LOOP_INTERVAL_MS);
}
