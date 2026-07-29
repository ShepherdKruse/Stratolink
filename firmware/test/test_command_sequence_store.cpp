#include <assert.h>
#include <stdio.h>

#include "command_sequence_store.h"

int main(void) {
    const uint8_t cases[] = {0, 1, 42, 127, 128, 254, 255};
    for (uint8_t value : cases) {
        uint32_t record = command_sequence_record_encode(value);
        uint8_t decoded = 0;
        assert(command_sequence_record_decode(record, &decoded));
        assert(decoded == value);
        for (uint8_t bit = 0; bit < 32; ++bit) {
            assert(!command_sequence_record_decode(
                record ^ ((uint32_t)1u << bit), &decoded));
        }
    }
    assert(!command_sequence_record_decode(0, nullptr));

    for (uint8_t value : cases) {
        for (uint8_t relay = 0; relay <= 1; ++relay) {
            uint32_t record = command_state_record_encode(value, relay != 0);
            uint8_t decoded = 0;
            bool decoded_relay = false;
            assert(command_state_record_decode(
                record, &decoded, &decoded_relay));
            assert(decoded == value);
            assert(decoded_relay == (relay != 0));
            for (uint8_t bit = 0; bit < 32; ++bit) {
                assert(!command_state_record_decode(
                    record ^ ((uint32_t)1u << bit), &decoded,
                    &decoded_relay));
            }
        }
    }
    assert(!command_state_record_decode(0, nullptr, nullptr));
    puts("command state record: round-trip and all one-bit corruptions passed");
    return 0;
}
