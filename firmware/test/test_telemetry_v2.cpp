#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "telemetry.h"

static uint16_t be16(const uint8_t* p) {
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

int main(void) {
    assert(TELEMETRY_PAYLOAD_SIZE == 40);
    telemetry_input_t unavailable;
    telemetry_input_init(&unavailable);
    assert(unavailable.lat_e7 == 0 && unavailable.lon_e7 == 0);
    assert(unavailable.gps_satellites == 0);
    assert(unavailable.temperature_dc == TELEMETRY_TEMP_INVALID_DC);
    assert(unavailable.pressure_ch == TELEMETRY_PRESSURE_INVALID_CH);
    assert(unavailable.accel_x_cm_s2 == TELEMETRY_ACCEL_INVALID_CMS2);
    assert(unavailable.accel_y_cm_s2 == TELEMETRY_ACCEL_INVALID_CMS2);
    assert(unavailable.accel_z_cm_s2 == TELEMETRY_ACCEL_INVALID_CMS2);
    assert(unavailable.uv_index == TELEMETRY_UV_INVALID);
    assert(unavailable.ambient_lux == TELEMETRY_LUX_INVALID);
    assert(unavailable.acoustic_valid == 0);
    uint8_t unavailable_wire[TELEMETRY_PAYLOAD_SIZE] = {};
    telemetry_pack(&unavailable, unavailable_wire);
    assert((int16_t)be16(unavailable_wire + 12) == INT16_MIN);
    assert(be16(unavailable_wire + 14) == 0xFFFEu);
    assert((int16_t)be16(unavailable_wire + 25) == INT16_MIN);
    assert((int16_t)be16(unavailable_wire + 27) == INT16_MIN);
    assert((int16_t)be16(unavailable_wire + 29) == INT16_MIN);
    assert(unavailable_wire[31] == 0xFEu);
    assert(be16(unavailable_wire + 32) == 0xFFFEu);
    assert((unavailable_wire[34] & 0x0Fu) == 10u);

    telemetry_input_t in;
    telemetry_input_init(&in);
    in.acoustic_event = 1;
    in.acoustic_valid = 1;
    in.power_tier = 3;
    in.reset_cause = 5;
    in.command_ack_valid = 1;
    in.last_command_seq = 0xA6;
    in.relay_enabled = 1;
    in.boot_count = 0x42;
    in.fix_age_min = 0x1234;
    in.relay_fwd_delta = 6;
    in.ctt_tags_delta = 11;
    uint8_t out[TELEMETRY_PAYLOAD_SIZE] = {};
    telemetry_pack(&in, out);
    assert(out[34] == (uint8_t)(1u | (3u << 1) | (5u << 4) | 0x80u));
    assert(out[35] == 0x42);
    assert(be16(out + 36) == 0x1234);
    assert(out[38] == 0xA6);
    assert(out[39] == (uint8_t)(0x80u | (6u << 4) | 11u));

    /* All five power tiers have an explicit acoustic-unavailable code while
     * preserving reset and command-ACK fields. */
    in.acoustic_valid = 0;
    in.power_tier = 3;
    telemetry_pack(&in, out);
    assert(out[34] == (uint8_t)(13u | (5u << 4) | 0x80u));

    /* Invalid caller state clamps fail-closed; a missing command ACK never
     * leaks a stale sequence, and activity deltas saturate in their nibbles. */
    in.acoustic_event = 7;
    in.acoustic_valid = 1;
    in.power_tier = 99;
    in.reset_cause = 7;
    in.command_ack_valid = 0;
    in.last_command_seq = 0xFF;
    in.relay_enabled = 0;
    in.relay_fwd_delta = 255;
    in.ctt_tags_delta = 255;
    telemetry_pack(&in, out);
    assert(out[34] == (uint8_t)(1u | (4u << 1)));
    assert(out[38] == 0);
    assert(out[39] == 0x7F);
    puts("40-byte observability payload packing passed");
    return 0;
}
