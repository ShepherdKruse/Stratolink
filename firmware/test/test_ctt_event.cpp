#include <assert.h>
#include <stdio.h>

#include "ctt_event.h"

int main(void) {
    ctt_detection_t detection = {};
    detection.id_raw = 0x807F00FFu;
    detection.id_motus = 0xABCDEu;
    detection.rssi_best = -109;
    detection.hits = 7;
    detection.motus_valid = 1;
    detection.window_idx = 0x1234;
    detection.queued_min = 100;

    uint8_t out[CTT_EVENT_PAYLOAD_SIZE] = {};
    ctt_event_pack(&detection, detection.queued_min + 0x1234u, out);
    const uint8_t expected[] = {
        0x43, 0x54, 0x02, 0x01,
        0x80, 0x7F, 0x00, 0xFF,
        0x00, 0x0A, 0xBC, 0xDE,
        0xFF, 0x93, 0x07, 0x12, 0x34,
    };
    for (unsigned i = 0; i < sizeof(expected); i++) assert(out[i] == expected[i]);

    detection.motus_valid = 0;
    ctt_event_pack(&detection, detection.queued_min + 0x1234u, out);
    assert(out[3] == 0);
    assert(out[8] == 0 && out[9] == 0 && out[10] == 0 && out[11] == 0);

    ctt_event_pack(&detection, detection.queued_min + 70000u, out);
    assert(out[15] == 0xFF && out[16] == 0xFF);

    detection.queued_min = UINT32_MAX - 4u;
    ctt_event_pack(&detection, 5u, out);
    assert(out[15] == 0 && out[16] == 10);

    puts("CTT event payload: age, saturation, wrap, and invalid-Motus cases passed");
    return 0;
}
