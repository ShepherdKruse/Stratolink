#ifndef COMMAND_SEQUENCE_STORE_H
#define COMMAND_SEQUENCE_STORE_H

#include <stdbool.h>
#include <stdint.h>

/* One-word, corruption-detecting representation used in a retained STM32WL
 * TAMP backup register. The sequence and its complement make every one-bit
 * corruption fail closed instead of changing replay order. */
uint32_t command_sequence_record_encode(uint8_t sequence);
bool command_sequence_record_decode(uint32_t record, uint8_t* sequence);

/* v2 retained command state. Persist the bounded public-relay behavior beside
 * the replay sequence so a warm reset cannot acknowledge relay-off while
 * silently reverting the actual relay to on. The byte CRC detects every
 * one-bit corruption and the new tag rejects legacy sequence-only records. */
uint32_t command_state_record_encode(uint8_t sequence, bool relay_enabled);
bool command_state_record_decode(uint32_t record, uint8_t* sequence,
                                 bool* relay_enabled);

#endif
