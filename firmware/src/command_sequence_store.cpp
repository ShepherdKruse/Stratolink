#include "command_sequence_store.h"

#define COMMAND_SEQUENCE_TAG 0x5343u /* "SC" */
#define COMMAND_STATE_TAG 0xD7u

static uint8_t crc8(const uint8_t* bytes, uint8_t n) {
    uint8_t crc = 0;
    while (n--) {
        crc ^= *bytes++;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (uint8_t)((crc & 0x80u) ? (crc << 1) ^ 0x07u : crc << 1);
        }
    }
    return crc;
}

uint32_t command_sequence_record_encode(uint8_t sequence) {
    return ((uint32_t)COMMAND_SEQUENCE_TAG << 16) |
           ((uint32_t)sequence << 8) |
           (uint8_t)~sequence;
}

bool command_sequence_record_decode(uint32_t record, uint8_t* sequence) {
    if ((uint16_t)(record >> 16) != COMMAND_SEQUENCE_TAG) return false;
    uint8_t value = (uint8_t)(record >> 8);
    if ((uint8_t)record != (uint8_t)~value) return false;
    if (sequence) *sequence = value;
    return true;
}

uint32_t command_state_record_encode(uint8_t sequence, bool relay_enabled) {
    uint8_t bytes[3] = {
        COMMAND_STATE_TAG,
        sequence,
        (uint8_t)(relay_enabled ? 1u : 0u),
    };
    return ((uint32_t)bytes[0] << 24) |
           ((uint32_t)bytes[1] << 16) |
           ((uint32_t)bytes[2] << 8) |
           crc8(bytes, sizeof(bytes));
}

bool command_state_record_decode(uint32_t record, uint8_t* sequence,
                                 bool* relay_enabled) {
    uint8_t bytes[3] = {
        (uint8_t)(record >> 24),
        (uint8_t)(record >> 16),
        (uint8_t)(record >> 8),
    };
    if (bytes[0] != COMMAND_STATE_TAG || bytes[2] > 1u ||
        (uint8_t)record != crc8(bytes, sizeof(bytes))) return false;
    if (sequence) *sequence = bytes[1];
    if (relay_enabled) *relay_enabled = bytes[2] != 0;
    return true;
}
