#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <stdint.h>

/** Payload size in bytes (matches webhook parser). v2 uses the complete
 * 36-40-byte SF9 symbol group: five diagnostic bytes cost the same airtime as
 * adding only one byte to the legacy 35-byte packet. */
#define TELEMETRY_PAYLOAD_SIZE 40

/* In-band unavailable sentinels. These values are outside each qualified
 * sensor's output range; UV/lux conversion deliberately skips the reserved
 * code so genuine full-scale saturation remains UINT8_MAX/UINT16_MAX. */
#define TELEMETRY_TEMP_INVALID_DC     INT16_MIN
#define TELEMETRY_PRESSURE_INVALID_CH ((uint16_t)0xFFFEu)
#define TELEMETRY_ACCEL_INVALID_CMS2  INT16_MIN
#define TELEMETRY_UV_INVALID          ((uint8_t)0xFEu)
#define TELEMETRY_LUX_INVALID         ((uint16_t)0xFFFEu)

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
    int16_t temperature_dc;   /* 0.1 degC; INT16_MIN unavailable */
    uint16_t pressure_ch;     /* 0.1 hPa; 0xFFFE unavailable */

    /* Power */
    uint16_t solar_mv;
    uint16_t battery_mv;      /* VSTOR */

    /* MEMS (LIS2DH12 accel only - no gyroscope on this board) */
    int16_t accel_x_cm_s2;    /* 0.01 m/s^2; INT16_MIN unavailable */
    int16_t accel_y_cm_s2;
    int16_t accel_z_cm_s2;

    /* UV / Ambient Light (LTR-390UV-01) */
    uint8_t uv_index;         /* integer UVI; 0xFE unavailable, 0xFF saturated */
    uint16_t ambient_lux;     /* lux; 0xFFFE unavailable, 0xFFFF saturated */

    /* Acoustic (mic broadband-energy detector - DC-blocked variance vs adaptive
     * noise floor; NOT an FFT. See firmware/src/mic_acoustic.cpp). */
    uint8_t acoustic_event;   /* 0 = quiet, 1 = energy > 4x adaptive noise floor */
    uint8_t acoustic_valid;   /* capture completed; false encodes unavailable */

    /* Flight observability (wire v2). These make the known reset/GNSS and
     * auxiliary-radio failure modes remotely distinguishable. */
    uint8_t power_tier;       /* 0 FULL .. 4 CRITICAL */
    uint8_t reset_cause;      /* reset_cause_code_t, 0..6 */
    uint8_t command_ack_valid;/* last_command_seq is meaningful */
    uint8_t last_command_seq; /* last durably applied fPort-10 sequence */
    uint8_t relay_enabled;    /* retained public-Meshtastic policy */
    uint8_t boot_count;       /* retained boot count, low byte */
    uint16_t fix_age_min;     /* since last real fix; 0xFFFF = none this boot */
    uint8_t relay_fwd_delta;  /* since last successful primary; saturates at 7 */
    uint8_t ctt_tags_delta;   /* since last successful primary; saturates at 15 */
} telemetry_input_t;

/** Initialize a cycle packet to atomic NOGPS plus explicit unavailable
 * sensor sentinels. Successful drivers overwrite only their own fields. */
void telemetry_input_init(telemetry_input_t* out);

/**
 * Pack telemetry into a 40-byte big-endian payload for LoRaWAN uplink.
 * out must point to at least TELEMETRY_PAYLOAD_SIZE bytes.
 */
void telemetry_pack(const telemetry_input_t* in, uint8_t* out);

#endif /* TELEMETRY_H */
