#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "lorawan_counter.h"

static void accepts(uint32_t next_expected, uint16_t low, uint32_t expected) {
    uint32_t actual = 0xA5A5A5A5u;
    assert(lorawan_fcntdown_reconstruct(next_expected, low, &actual));
    assert(actual == expected);
}

static void rejects(uint32_t next_expected, uint16_t low) {
    uint32_t untouched = 0xA5A5A5A5u;
    assert(!lorawan_fcntdown_reconstruct(next_expected, low, &untouched));
    assert(untouched == 0xA5A5A5A5u);
}

int main(void) {
    accepts(0, 0, 0);                       /* first session downlink */
    accepts(0, 0x1234, 0x1234);
    accepts(20, 20, 20);                    /* exact next counter */
    accepts(20, 25, 25);                    /* legal forward gap */
    rejects(20, 19);                        /* duplicate/backward replay */
    rejects(20, (uint16_t)(20 + 0x8000u));  /* ambiguous half-range */
    accepts(0x00010000u, 0, 0x00010000u);   /* 16-bit rollover */
    rejects(0x00010000u, 0xFFFFu);          /* pre-rollover replay */
    accepts(0xFFFFFFFEu, 0xFFFEu, 0xFFFFFFFEu);
    rejects(0xFFFFFFFEu, 0xFFFFu);          /* next value cannot be retained */
    rejects(0xFFFFFFFEu, 0x0000u);          /* addition would wrap */
    assert(!lorawan_fcntdown_reconstruct(1, 1, nullptr));

    puts("LoRaWAN FCntDown: reconstruction/replay/rollover/exhaustion cases passed");
    return 0;
}
