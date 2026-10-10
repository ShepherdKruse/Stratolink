#include "telemetry.h"

static void write_be16(uint8_t* p, uint16_t v) {
    p[0] = (uint8_t)(v >> 8);
    p[1] = (uint8_t)(v & 0xFF);
}

static void write_be32(uint8_t* p, int32_t v) {
    p[0] = (uint8_t)((uint32_t)v >> 24);
    p[1] = (uint8_t)((uint32_t)v >> 16);
    p[2] = (uint8_t)((uint32_t)v >> 8);
    p[3] = (uint8_t)((uint32_t)v & 0xFF);
}

void telemetry_input_init(telemetry_input_t* out) {
    if (!out) return;
    *out = {};
    out->temperature_dc = TELEMETRY_TEMP_INVALID_DC;
    out->pressure_ch = TELEMETRY_PRESSURE_INVALID_CH;
    out->accel_x_cm_s2 = TELEMETRY_ACCEL_INVALID_CMS2;
    out->accel_y_cm_s2 = TELEMETRY_ACCEL_INVALID_CMS2;
    out->accel_z_cm_s2 = TELEMETRY_ACCEL_INVALID_CMS2;
    out->uv_index = TELEMETRY_UV_INVALID;
    out->ambient_lux = TELEMETRY_LUX_INVALID;
}

void telemetry_pack(const telemetry_input_t* in, uint8_t* out) {
    if (!in || !out) return;

    write_be32(out + 0,  in->lat_e7);
    write_be32(out + 4,  in->lon_e7);
    write_be32(out + 8,  in->altitude_m);
    write_be16(out + 12, (uint16_t)in->temperature_dc);
    write_be16(out + 14, in->pressure_ch);
    write_be16(out + 16, in->solar_mv);
    write_be16(out + 18, in->battery_mv);
    write_be16(out + 20, in->gps_speed_cm_s);
    write_be16(out + 22, in->gps_heading_cd);
    out[24] = in->gps_satellites;
    write_be16(out + 25, (uint16_t)in->accel_x_cm_s2);
    write_be16(out + 27, (uint16_t)in->accel_y_cm_s2);
    write_be16(out + 29, (uint16_t)in->accel_z_cm_s2);
    out[31] = in->uv_index;
    write_be16(out + 32, in->ambient_lux);
    /* v2 status byte: the existing lower-nibble codes 0..9 remain
     * (power_tier * 2 + acoustic event). Codes 10..14 use five formerly
     * invalid combinations to represent acoustic-unavailable for power tiers
     * 0..4. Code 15 remains invalid. This makes a skipped/failed capture
     * distinguishable from quiet without changing the 40-byte packet or any
     * established valid-v2 wire value. Reset cause stays in [6:4] and command
     * ACK validity in [7]. */
    uint8_t power = in->power_tier <= 4u ? in->power_tier : 4u;
    uint8_t reset = in->reset_cause <= 6u ? in->reset_cause : 0u;
    uint8_t acoustic_power = in->acoustic_valid
        ? (uint8_t)((power << 1) | (in->acoustic_event ? 1u : 0u))
        : (uint8_t)(10u + power);
    out[34] = (uint8_t)(acoustic_power | (reset << 4) |
                        (in->command_ack_valid ? 0x80u : 0u));
    out[35] = in->boot_count;
    write_be16(out + 36, in->fix_age_min);
    out[38] = in->command_ack_valid ? in->last_command_seq : 0u;
    uint8_t relay_delta = in->relay_fwd_delta > 7u ? 7u : in->relay_fwd_delta;
    uint8_t ctt_delta = in->ctt_tags_delta > 15u ? 15u : in->ctt_tags_delta;
    out[39] = (uint8_t)((in->relay_enabled ? 0x80u : 0u) |
                        (relay_delta << 4) | ctt_delta);
}
