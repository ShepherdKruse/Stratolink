#ifndef B2B_ID_STORE_H
#define B2B_ID_STORE_H

#include <stdint.h>
#include <stdbool.h>

/* Pure encoding for the one-word retained next-origin-ID record. */
uint32_t b2b_id_record_encode(uint8_t next_id);
bool b2b_id_record_decode(uint32_t record, uint8_t* next_id);

#endif
