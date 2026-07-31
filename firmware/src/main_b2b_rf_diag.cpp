/**
 * NOT FLIGHT FIRMWARE: bounded two-node B2B RF integration diagnostic.
 *
 * Role 1 originates one authenticated position crumb after a 65-second age
 * delay, then runs the production LongFast/B2B service window for 20 seconds.
 * Role 2 starts first, listens for 150 seconds through that same production
 * path, then snapshots the authenticated frame queued for its fPort-12 tunnel.
 *
 * Both roles use the public diagnostic-only key and identities supplied by
 * b2b_rf_diag_config.h. No LoRaWAN join or uplink is attempted.
 */
#ifndef B2B_RF_DIAG_BUILD
#error "main_b2b_rf_diag.cpp is diagnostic-only"
#endif

#include <Arduino.h>

#include "b2b.h"
#include "lorawan.h"
#include "power_adc.h"
#include "power_manager.h"

static constexpr uint32_t B2B_RF_TX_AGE_DELAY_MS = 65000u;
static constexpr uint32_t B2B_RF_TX_WINDOW_MS = 20000u;
static constexpr uint32_t B2B_RF_RX_WINDOW_MS = 150000u;
static constexpr int32_t B2B_RF_LAT_E7 = 377749000;
static constexpr int32_t B2B_RF_LON_E7 = -1224194000;
static constexpr int32_t B2B_RF_ALT_M = 12345;

struct __attribute__((packed)) B2BRfDiagState {
    uint32_t magic;             // "BRF1"
    uint32_t uptime_ms;
    uint32_t window_ms;
    uint8_t role;
    uint8_t radio_init_ok;
    uint8_t complete;
    uint8_t pending_count;
    uint8_t frame_valid;
    uint8_t frame_type;
    uint8_t frame_ttl;
    uint8_t frame_msg_id;
    uint16_t frame_src;
    int16_t crumb_lat_cd;
    int16_t crumb_lon_cd;
    uint8_t crumb_alt_hm;
    uint8_t crumb_age_min;
    uint8_t wire_len;
    uint8_t reserved[3];
    uint8_t wire[B2B_FRAME_MAX];
};

__attribute__((used)) volatile B2BRfDiagState b2b_rf_diag_state = {};

static void snapshot_receiver_result(void) {
    uint8_t wire[B2B_FRAME_MAX] = {};
    uint8_t len = 0;
    b2b_rf_diag_state.pending_count =
        lorawan_b2b_pending_uplink_count();
    if (!lorawan_b2b_peek_pending_uplink(wire, sizeof(wire), &len)) return;

    b2b_frame_t frame = {};
    if (!b2b_parse(wire, len, &frame)) return;
    b2b_rf_diag_state.frame_valid = 1;
    b2b_rf_diag_state.frame_type = frame.type;
    b2b_rf_diag_state.frame_ttl = frame.ttl;
    b2b_rf_diag_state.frame_msg_id = frame.msg_id;
    b2b_rf_diag_state.frame_src = frame.src;
    b2b_rf_diag_state.wire_len = len;
    for (uint8_t i = 0; i < len; ++i) {
        b2b_rf_diag_state.wire[i] = wire[i];
    }

    if (frame.type == B2B_TYPE_CRUMB &&
        b2b_authenticated_body_len(&frame) >= B2B_CRUMB_LEN) {
        b2b_crumb_t crumb = {};
        b2b_crumb_unpack(frame.payload, &crumb);
        b2b_rf_diag_state.crumb_lat_cd = crumb.lat_cd;
        b2b_rf_diag_state.crumb_lon_cd = crumb.lon_cd;
        b2b_rf_diag_state.crumb_alt_hm = crumb.alt_hm;
        b2b_rf_diag_state.crumb_age_min = crumb.age_min;
    }
}

void setup() {
    b2b_rf_diag_state.magic = 0x42524631u;
    b2b_rf_diag_state.role = B2B_RF_DIAG_ROLE;
    power_adc_init();
    power_manager_init();
    b2b_rf_diag_state.radio_init_ok = lorawan_init() ? 1u : 0u;
    if (!b2b_rf_diag_state.radio_init_ok) {
        b2b_rf_diag_state.complete = 1;
        return;
    }

#if B2B_RF_DIAG_ROLE == 1
    lorawan_b2b_set_local_crumb(
        B2B_RF_LAT_E7, B2B_RF_LON_E7, B2B_RF_ALT_M);
    for (uint32_t elapsed = 0; elapsed < B2B_RF_TX_AGE_DELAY_MS;
         elapsed += 1000u) {
        power_manager_kick_watchdog();
        delay(1000);
    }
    b2b_rf_diag_state.window_ms =
        lorawan_relay_window(B2B_RF_TX_WINDOW_MS, 0u, false);
#else
    b2b_rf_diag_state.window_ms =
        lorawan_relay_window(B2B_RF_RX_WINDOW_MS, 0u, false);
    snapshot_receiver_result();
#endif
    b2b_rf_diag_state.complete = 1;
}

void loop() {
    b2b_rf_diag_state.uptime_ms = millis();
    power_manager_kick_watchdog();
    delay(1000);
}
