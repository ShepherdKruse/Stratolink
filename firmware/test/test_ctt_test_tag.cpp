#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "ctt_test_tag.h"

int main(void) {
    uint8_t frame[5] = {};
    const uint8_t reference[5] = {0x78, 0x55, 0x4C, 0x33, 0x58};
    assert(ctt_test_tag_encode(0x3256Eu, frame));
    assert(memcmp(frame, reference, sizeof(frame)) == 0);
    assert(ctt_test_tag_crc8(frame, 4) == 0x58u);

    assert(ctt_test_tag_encode(0, frame));
    for (uint8_t byte : frame) assert(byte == 0);

    assert(ctt_test_tag_encode(0xFFFFFu, frame));
    assert(frame[0] == 0xFF && frame[1] == 0xFF &&
           frame[2] == 0xFF && frame[3] == 0xFF);
    assert(frame[4] == ctt_test_tag_crc8(frame, 4));

    assert(!ctt_test_tag_encode(0x100000u, frame));
    assert(!ctt_test_tag_encode(1, nullptr));
    assert(ctt_test_tag_crc8(nullptr, 4) == 0);

    puts("CTT test-tag encoder: reference, bounds, dictionary, and CRC passed");
    return 0;
}
