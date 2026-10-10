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
    assert(be16(unavailable_wire + 36) == TELEMETRY_V3_WORD_MARKER);

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
    in.fix_age_min = 0x0123;
    in.server_proof_count_mod8 = 5;
    in.server_qualified_miss_streak = 2;
    in.server_recovery_parity = 1;
    in.relay_fwd_delta = 6;
    in.ctt_tags_delta = 11;
    uint8_t out[TELEMETRY_PAYLOAD_SIZE] = {};
    telemetry_pack(&in, out);
    assert(out[34] == (uint8_t)(1u | (3u << 1) | (5u << 4) | 0x80u));
    assert(out[35] == 0x42);
    assert(be16(out + 36) == 0xDB23u);
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

    /* Fix age saturates without ever becoming the no-fix sentinel. Modular
     * inputs and the miss streak are bounded at their exact wire widths. */
    in.fix_age_min = 999u;
    in.server_proof_count_mod8 = 15u;
    in.server_qualified_miss_streak = 99u;
    in.server_recovery_parity = 0u;
    telemetry_pack(&in, out);
    assert(be16(out + 36) == 0xFDFEu);

    in.fix_age_min = TELEMETRY_FIX_AGE_INPUT_NONE;
    in.server_proof_count_mod8 = 7u;
    in.server_qualified_miss_streak = 3u;
    in.server_recovery_parity = 1u;
    telemetry_pack(&in, out);
    assert(be16(out + 36) == 0xEFFFu); /* canonical, never legacy 0xFFFF */

    in.server_qualified_miss_streak = 2u;
    telemetry_pack(&in, out);
    assert(be16(out + 36) == 0xFBFFu);

    /* Exhaust the complete representable v3 state space. Every new frame is
     * marked and avoids the frozen legacy sentinel; only the documented sole
     * collision changes proof residue 7 to its canonical residue 6. */
    for (uint8_t proof = 0; proof < 8u; ++proof) {
        for (uint8_t misses = 0; misses < 4u; ++misses) {
            for (uint8_t recovery = 0; recovery < 2u; ++recovery) {
                for (uint16_t age = 0; age <= 511u; ++age) {
                    in.server_proof_count_mod8 = proof;
                    in.server_qualified_miss_streak = misses;
                    in.server_recovery_parity = recovery;
                    in.fix_age_min = age == 511u
                        ? TELEMETRY_FIX_AGE_INPUT_NONE : age;
                    telemetry_pack(&in, out);
                    uint16_t word = be16(out + 36);
                    assert((word & TELEMETRY_V3_WORD_MARKER) != 0u);
                    assert(word != UINT16_MAX);
                    assert(((word >> 10) & 3u) == misses);
                    assert(((word >> 9) & 1u) == recovery);
                    assert((word & 0x01FFu) == age);
                    uint8_t expected_proof =
                        proof == 7u && misses == 3u && recovery == 1u &&
                            age == 511u ? 6u : proof;
                    assert(((word >> 12) & 7u) == expected_proof);
                }
            }
        }
    }
    puts("40-byte observability v3 payload packing passed");
    return 0;
}
