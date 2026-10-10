#include <assert.h>
#include <stdio.h>

#include "ctt_decode.h"

int main(void) {
    /* Reference motus-test-tags / CTT vector: raw tag 0x78554C33 followed
     * by its CRC-8 0x58. Dictionary indices are 14,11,9,6 in little-endian
     * 5-bit-group order, yielding Motus ID 0x3256E. */
    const uint8_t reference[5] = {0x78, 0x55, 0x4C, 0x33, 0x58};
    ctt_frame_t frame = {};
    assert(ctt_decode(reference, &frame));
    assert(frame.crc_ok);
    assert(frame.motus_valid);
    assert(frame.id_raw == 0x78554C33u);
    assert(frame.id_motus == 0x3256Eu);

    /* All-zero is also a valid dictionary/CRC codeword and proves the
     * boundary ID does not get confused with an invalid dictionary result. */
    const uint8_t zero[5] = {0, 0, 0, 0, 0};
    assert(ctt_decode(zero, &frame));
    assert(frame.motus_valid && frame.id_motus == 0);

    uint8_t corrupt[5] = {0x78, 0x55, 0x4C, 0x33, 0x59};
    assert(!ctt_decode(corrupt, &frame));
    assert(!ctt_decode(nullptr, &frame));
    assert(!ctt_decode(reference, nullptr));

    puts("CTT decoder: reference CRC/raw/dictionary/Motus-ID cases passed");
    return 0;
}
