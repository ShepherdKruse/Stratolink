/**
 * CTT listener bench diagnostic. Runs back-to-back ten-minute 434 MHz FSK
 * listen windows on the flight radio path and prints every decoded tag beep, for
 * validating the listener end-to-end against a separate compatible 434 MHz
 * transmitter or real CTT test tag. The connected RTL-SDR is receive-only and
 * cannot provide this stimulus. The exact fitted RAK3172-9-SM-NI is RAK's
 * 9xx-MHz SKU (US915/AU915/KR920/AS923); RAK assigns both EU868 and 434 MHz to
 * different ordering codes. Treat a successful radio setup as control-path
 * evidence only until a compatible tag proves usable end-to-end sensitivity.
 *
 * Build/flash:  pio run -e ctt_diag -t upload
 * Watch:        RTT/serial at 115200; stats also J-Link readable (s_ctt).
 */
#include <Arduino.h>
#include "config.h"
#include "stratolink_pins.h"
#include "lorawan.h"
#include "power_adc.h"
#include "power_manager.h"

/* Longer than the finite four-minute transmitter sequence so every stimulus
 * belongs to one aggregation window and no frame lands in a re-arm gap. */
static constexpr uint32_t CTT_DIAG_WINDOW_MS = 600000u;

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("[ctt_diag] start");
    power_adc_init();
    power_manager_init();          /* IWDG armed; window housekeeping kicks it */
    if (!lorawan_init()) {
        Serial.println("[ctt_diag] radio init FAILED");
    }
}

void loop() {
    /* floor_mv=0: bench supply, no mission to protect.  60 s per window. */
    uint32_t used = lorawan_ctt_window(CTT_DIAG_WINDOW_MS, 0);

    lorawan_ctt_stats_t st;
    lorawan_ctt_get_stats(&st);
    Serial.print("[ctt_diag] window="); Serial.print(st.windows);
    Serial.print(" ms=");               Serial.print(used);
    Serial.print(" frames=");           Serial.print(st.frames_rx);
    Serial.print(" crc_fail=");         Serial.print(st.crc_fail);
    Serial.print(" tags=");             Serial.print(st.tags_seen);
    Serial.print(" last_id=0x");        Serial.print(st.last_id, HEX);
    Serial.print(" last_rssi=");        Serial.println(st.last_rssi);

    ctt_detection_t log[CTT_LOG_N];
    uint8_t n = lorawan_ctt_get_log(log);
    for (uint8_t i = 0; i < n; i++) {
        Serial.print("  tag 0x");      Serial.print(log[i].id_raw, HEX);
        Serial.print(" motus=");       Serial.print(log[i].id_motus);
        Serial.print(log[i].motus_valid ? " (valid)" : " (non-dict)");
        Serial.print(" hits=");        Serial.print(log[i].hits);
        Serial.print(" rssi=");        Serial.print(log[i].rssi_best);
        Serial.print(" win=");         Serial.println(log[i].window_idx);
    }
}
