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

void telemetry_pack(const telemetry_input_t* in, uint8_t* out) {
    if (!in || !out) return;

    write_be32(out + 0,  in->lat_e7);
    write_be32(out + 4,  in->lon_e7);
    write_be32(out + 8,  in->altitude_m);
    write_be16(out + 12, (uint16_t)in->temperature_cd);
    write_be16(out + 14, in->pressure_ch);
    write_be16(out + 16, in->solar_mv);
    write_be16(out + 18, in->battery_mv);
    write_be16(out + 20, in->gps_speed_cm_s);
    write_be16(out + 22, in->gps_heading_cd);
    out[24] = in->gps_satellites;
    write_be16(out + 25, (uint16_t)in->accel_x_cm_s2);
    write_be16(out + 27, (uint16_t)in->accel_y_cm_s2);
    write_be16(out + 29, (uint16_t)in->accel_z_cm_s2);
    write_be16(out + 31, (uint16_t)in->gyro_x_cd_s);
    write_be16(out + 33, (uint16_t)in->gyro_y_cd_s);
    write_be16(out + 35, (uint16_t)in->gyro_z_cd_s);
    out[37] = in->acoustic_event;
}
