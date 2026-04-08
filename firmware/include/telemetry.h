#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <stdint.h>

/** Payload size in bytes (matches webhook parser). */
#define TELEMETRY_PAYLOAD_SIZE 35

/**
 * All inputs for one telemetry packet.
 * Units match the payload spec (see firmware-architecture-and-payload-plan.md).
 */
typedef struct {
    /* GPS (required for position) */
    int32_t lat_e7;           /* latitude  * 1e7 */
    int32_t lon_e7;           /* longitude * 1e7 */
    int32_t altitude_m;       /* meters */
    uint16_t gps_speed_cm_s;  /* 0.01 m/s */
    uint16_t gps_heading_cd;   /* 0.01 deg */
    uint8_t gps_satellites;

    /* Environmental */
    int16_t temperature_cd;   /* 0.1 °C */
    uint16_t pressure_ch;     /* 0.1 hPa */

    /* Power */
    uint16_t solar_mv;
    uint16_t battery_mv;      /* VSTOR */

    /* MEMS (LIS2DH12 accel only — no gyroscope on this board) */
    int16_t accel_x_cm_s2;    /* 0.01 m/s² */
    int16_t accel_y_cm_s2;
    int16_t accel_z_cm_s2;

    /* UV / Ambient Light (LTR-390UV-01) */
    uint8_t uv_index;         /* integer UV index (0–15+) */
    uint16_t ambient_lux;     /* lux (0–65535) */

    /* Acoustic (mic FFT change detection) */
    uint8_t acoustic_event;   /* 0 = no event, non-zero = spectral change */
} telemetry_input_t;

/**
 * Pack telemetry into a 38-byte big-endian payload for LoRaWAN uplink.
 * out must point to at least TELEMETRY_PAYLOAD_SIZE bytes.
 */
void telemetry_pack(const telemetry_input_t* in, uint8_t* out);

#endif /* TELEMETRY_H */
