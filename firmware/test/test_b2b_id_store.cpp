#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "b2b_id_store.h"

int main(void) {
    const uint8_t values[] = {0, 1, 0x7F, 0x80, 0xFE, 0xFF};
    for (uint8_t value : values) {
        uint32_t record = b2b_id_record_encode(value);
        uint8_t decoded = 0;
        assert(b2b_id_record_decode(record, &decoded));
        assert(decoded == value);

        /* Every bit participates in either the fixed tag, value, or
         * complement, so every possible retained one-bit corruption fails. */
        for (uint8_t bit = 0; bit < 32; ++bit) {
            decoded = 0xA5;
            assert(!b2b_id_record_decode(record ^ (1u << bit), &decoded));
            assert(decoded == 0xA5);
        }
    }
    assert(!b2b_id_record_decode(b2b_id_record_encode(7), nullptr));
    puts("B2B retained ID: round-trip and all one-bit corruptions passed");
    return 0;
}
