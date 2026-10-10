#include "ctt_queue.h"

#include <assert.h>
#include <stdio.h>

static ctt_detection_t detection(uint32_t id, uint16_t window,
                                 int16_t rssi = -90) {
    ctt_detection_t value = {};
    value.id_raw = id;
    value.id_motus = id & 0xFFFFFu;
    value.rssi_best = rssi;
    value.hits = 1;
    value.motus_valid = 1;
    value.window_idx = window;
    return value;
}

int main() {
    ctt_queue_t queue;
    ctt_queue_init(&queue);
    assert(ctt_queue_count(&queue) == 0);
    assert(!ctt_queue_peek(&queue, nullptr));

    ctt_detection_t first = detection(0x78554C33u, 7, -92);
    assert(ctt_queue_record(&queue, &first) == CTT_QUEUE_NEW_QUEUED);
    assert(ctt_queue_count(&queue) == 1);

    ctt_detection_t repeat = detection(first.id_raw, 7, -61);
    assert(ctt_queue_record(&queue, &repeat) == CTT_QUEUE_REPEAT);
    ctt_detection_t peeked = {};
    assert(ctt_queue_peek(&queue, &peeked));
    assert(peeked.hits == 2 && peeked.rssi_best == -61);

    ctt_queue_ack(&queue);
    assert(ctt_queue_count(&queue) == 0);
    assert(ctt_queue_record(&queue, &repeat) == CTT_QUEUE_REPEAT);
    assert(ctt_queue_count(&queue) == 0);

    /* Exact former duplicate path: fill both structures with X then A then
     * fourteen others. Two queue-full detections overwrite the debug-ring
     * copies of X and A. Drain only X, leaving A pending with free capacity.
     * A repeat must update A in place, never occupy that capacity twice. */
    ctt_queue_init(&queue);
    ctt_detection_t x = detection(1, 20);
    ctt_detection_t a = detection(2, 20, -88);
    assert(ctt_queue_record(&queue, &x) == CTT_QUEUE_NEW_QUEUED);
    assert(ctt_queue_record(&queue, &a) == CTT_QUEUE_NEW_QUEUED);
    for (uint32_t id = 3; id <= 16; ++id) {
        ctt_detection_t item = detection(id, 20);
        assert(ctt_queue_record(&queue, &item) == CTT_QUEUE_NEW_QUEUED);
    }
    assert(ctt_queue_count(&queue) == CTT_LOG_N);
    ctt_detection_t drop1 = detection(17, 20);
    ctt_detection_t drop2 = detection(18, 20);
    assert(ctt_queue_record(&queue, &drop1) == CTT_QUEUE_NEW_DROPPED);
    assert(ctt_queue_record(&queue, &drop2) == CTT_QUEUE_NEW_DROPPED);
    ctt_queue_ack(&queue);  // X only; A remains pending.
    assert(ctt_queue_count(&queue) == CTT_LOG_N - 1);

    ctt_detection_t a_repeat = detection(2, 20, -42);
    assert(ctt_queue_record(&queue, &a_repeat) == CTT_QUEUE_REPEAT);
    assert(ctt_queue_count(&queue) == CTT_LOG_N - 1);
    assert(ctt_queue_peek(&queue, &peeked));
    assert(peeked.id_raw == 2 && peeked.hits == 2 && peeked.rssi_best == -42);

    uint8_t a_pending_copies = 0;
    while (ctt_queue_peek(&queue, &peeked)) {
        if (peeked.id_raw == 2 && peeked.window_idx == 20) a_pending_copies++;
        ctt_queue_ack(&queue);
    }
    assert(a_pending_copies == 1);

    /* Saturation is explicit, hits saturate, and null inputs fail closed. */
    ctt_queue_init(&queue);
    ctt_detection_t saturated = detection(42, 21);
    saturated.hits = 255;
    assert(ctt_queue_record(&queue, &saturated) == CTT_QUEUE_NEW_QUEUED);
    assert(ctt_queue_record(&queue, &saturated) == CTT_QUEUE_REPEAT);
    assert(ctt_queue_peek(&queue, &peeked) && peeked.hits == 255);
    assert(ctt_queue_record(nullptr, &saturated) == CTT_QUEUE_NEW_DROPPED);
    assert(ctt_queue_record(&queue, nullptr) == CTT_QUEUE_NEW_DROPPED);

    puts("CTT queue: aggregation, saturation, drop, and ring-wrap dedup passed");
    return 0;
}
