#include "ctt_event.h"

static void write_be16(uint8_t* out, uint16_t value) {
    out[0] = (uint8_t)(value >> 8);
    out[1] = (uint8_t)value;
}

static void write_be32(uint8_t* out, uint32_t value) {
    out[0] = (uint8_t)(value >> 24);
    out[1] = (uint8_t)(value >> 16);
    out[2] = (uint8_t)(value >> 8);
    out[3] = (uint8_t)value;
}

void ctt_event_pack(const ctt_detection_t* in,
                    uint32_t now_min,
                    uint8_t out[CTT_EVENT_PAYLOAD_SIZE]) {
    if (!in || !out) return;
    out[0] = 'C';
    out[1] = 'T';
    out[2] = CTT_EVENT_VERSION;
    out[3] = in->motus_valid ? 0x01 : 0x00;
    write_be32(out + 4, in->id_raw);
    write_be32(out + 8, in->motus_valid ? in->id_motus : 0);
    write_be16(out + 12, (uint16_t)in->rssi_best);
    out[14] = in->hits;
    uint32_t age_min = now_min - in->queued_min;
    if (age_min > UINT16_MAX) age_min = UINT16_MAX;
    write_be16(out + 15, (uint16_t)age_min);
}
