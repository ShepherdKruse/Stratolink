#include "b2b_id_store.h"

#define B2B_ID_RECORD_TAG 0xB2B20000u

uint32_t b2b_id_record_encode(uint8_t next_id) {
    return B2B_ID_RECORD_TAG |
           ((uint32_t)(uint8_t)~next_id << 8) |
           next_id;
}

bool b2b_id_record_decode(uint32_t record, uint8_t* next_id) {
    if (!next_id || (record & 0xFFFF0000u) != B2B_ID_RECORD_TAG) return false;
    uint8_t value = (uint8_t)record;
    uint8_t check = (uint8_t)(record >> 8);
    if (check != (uint8_t)~value) return false;
    *next_id = value;
    return true;
}
