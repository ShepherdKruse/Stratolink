#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "b2b.h"
#include "ctt_event.h"
#include "telemetry.h"

static void emit(const char* name, int port, const uint8_t* bytes, int size) {
    printf("{\"name\":\"%s\",\"fPort\":%d,\"bytes\":[", name, port);
    for (int i = 0; i < size; ++i) printf("%s%u", i ? "," : "", bytes[i]);
    puts("]}");
}

static void emit_b2b(const char* name, b2b_type_t type,
                     const uint8_t* body, uint8_t size) {
    // Public regression key; never a fleet credential.
    const uint8_t key[16] = {0, 1, 2, 3, 4, 5, 6, 7,
                             8, 9, 10, 11, 12, 13, 14, 15};
    b2b_frame_t frame = {};
    frame.src = 2;
    frame.msg_id = 7;
    frame.ttl = 3;
    frame.type = type;
    frame.len = size + B2B_AUTH_TAG_LEN;
    memcpy(frame.payload, body, size);
    assert(b2b_auth_tag(key, &frame, frame.payload + size));
    assert(b2b_auth_verify(key, &frame));
    uint8_t wire[B2B_FRAME_MAX] = {};
    int length = b2b_encode(&frame, wire, sizeof(wire));
    assert(length > 0);
    emit(name, 12, wire, length);
}

int main() {
    telemetry_input_t input;
    telemetry_input_init(&input);
    input.lat_e7 = 374500000;
    input.lon_e7 = -1224200000;
    input.altitude_m = 18000;
    input.gps_speed_cm_s = 1234;
    input.gps_heading_cd = 9000;
    input.gps_satellites = 12;
    input.temperature_dc = -123;
    input.pressure_ch = 10127;
    input.solar_mv = 5123;
    input.battery_mv = 4660;
    input.accel_x_cm_s2 = -123;
    input.accel_y_cm_s2 = 0;
    input.accel_z_cm_s2 = 981;
    input.uv_index = 5;
    input.ambient_lux = 23456;
    input.acoustic_valid = 1;
    input.acoustic_event = 1;
    input.power_tier = 2;
    input.reset_cause = 5;
    input.boot_count = 17;
    input.fix_age_min = 291;
    input.server_proof_count_mod8 = 5;
    input.server_qualified_miss_streak = 2;
    input.server_recovery_parity = 1;
    input.command_ack_valid = 1;
    input.last_command_seq = 42;
    input.relay_enabled = 1;
    input.relay_fwd_delta = 6;
    input.ctt_tags_delta = 11;
    uint8_t wire[TELEMETRY_PAYLOAD_SIZE];
    telemetry_pack(&input, wire);
    emit("primary_v3", 1, wire, sizeof(wire));

    telemetry_input_init(&input);
    input.fix_age_min = TELEMETRY_FIX_AGE_INPUT_NONE;
    input.power_tier = 4;
    input.server_proof_count_mod8 = 7;
    input.server_qualified_miss_streak = 3;
    input.server_recovery_parity = 1;
    telemetry_pack(&input, wire);
    emit("primary_nogps", 1, wire, sizeof(wire));

    ctt_detection_t detection = {};
    detection.id_raw = 0x807F00FFu;
    detection.id_motus = 0xABCDEu;
    detection.rssi_best = -109;
    detection.hits = 7;
    detection.motus_valid = 1;
    detection.queued_min = 100;
    uint8_t ctt[CTT_EVENT_PAYLOAD_SIZE];
    ctt_event_pack(&detection, 100 + 0x1234, ctt);
    emit("ctt_v2", 11, ctt, sizeof(ctt));
    detection.motus_valid = 0;
    ctt_event_pack(&detection, 70100, ctt);
    emit("ctt_saturated", 11, ctt, sizeof(ctt));

    b2b_crumb_t crumb = {3745, -12242, 180, 3};
    uint8_t crumbs[6 * B2B_CRUMB_LEN];
    for (unsigned i = 0; i < 6; ++i) {
        b2b_crumb_pack(&crumb, crumbs + i * B2B_CRUMB_LEN);
    }
    emit_b2b("b2b_crumb", B2B_TYPE_CRUMB, crumbs, B2B_CRUMB_LEN);
    emit_b2b("b2b_six_crumbs", B2B_TYPE_CRUMB, crumbs, sizeof(crumbs));
    const uint8_t command[] = {0, 1, 2, 42, 1};
    emit_b2b("b2b_command", B2B_TYPE_COMMAND, command, sizeof(command));
    const uint8_t ack[] = {0, 7, 42};
    emit_b2b("b2b_ack", B2B_TYPE_ACK, ack, sizeof(ack));
}
