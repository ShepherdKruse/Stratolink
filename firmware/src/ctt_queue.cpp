#include "ctt_queue.h"

#include <string.h>

static void aggregate(ctt_detection_t* current,
                      const ctt_detection_t* observation) {
    if (current->hits < 255u) current->hits++;
    if (observation->rssi_best > current->rssi_best) {
        current->rssi_best = observation->rssi_best;
    }
}

static int16_t find_log(const ctt_queue_t* queue, uint32_t id_raw,
                        uint16_t window_idx) {
    for (uint8_t i = 0; i < queue->log_n; ++i) {
        if (queue->log[i].id_raw == id_raw &&
            queue->log[i].window_idx == window_idx) {
            return (int16_t)i;
        }
    }
    return -1;
}

static int16_t find_pending(const ctt_queue_t* queue, uint32_t id_raw,
                            uint16_t window_idx) {
    uint8_t slot = queue->pending_head;
    for (uint8_t i = 0; i < queue->pending_n; ++i) {
        if (queue->pending[slot].id_raw == id_raw &&
            queue->pending[slot].window_idx == window_idx) {
            return (int16_t)slot;
        }
        slot = (uint8_t)((slot + 1u) % CTT_LOG_N);
    }
    return -1;
}

static void write_log(ctt_queue_t* queue, const ctt_detection_t* detection) {
    uint8_t slot;
    if (queue->log_n < CTT_LOG_N) {
        slot = queue->log_n++;
    } else {
        slot = queue->log_next;
        queue->log_next = (uint8_t)((queue->log_next + 1u) % CTT_LOG_N);
    }
    queue->log[slot] = *detection;
}

void ctt_queue_init(ctt_queue_t* queue) {
    if (queue) memset(queue, 0, sizeof(*queue));
}

uint8_t ctt_queue_get_log(const ctt_queue_t* queue, ctt_detection_t* out) {
    if (!queue) return 0;
    if (out) memcpy(out, queue->log, sizeof(queue->log));
    return queue->log_n;
}

bool ctt_queue_peek(const ctt_queue_t* queue, ctt_detection_t* out) {
    if (!queue || !out || queue->pending_n == 0) return false;
    *out = queue->pending[queue->pending_head];
    return true;
}

void ctt_queue_ack(ctt_queue_t* queue) {
    if (!queue || queue->pending_n == 0) return;
    queue->pending_head =
        (uint8_t)((queue->pending_head + 1u) % CTT_LOG_N);
    queue->pending_n--;
}

uint8_t ctt_queue_count(const ctt_queue_t* queue) {
    return queue ? queue->pending_n : 0;
}

ctt_queue_result_t ctt_queue_record(
    ctt_queue_t* queue, const ctt_detection_t* detection) {
    if (!queue || !detection) return CTT_QUEUE_NEW_DROPPED;

    int16_t pending_index = find_pending(
        queue, detection->id_raw, detection->window_idx);
    int16_t log_index = find_log(
        queue, detection->id_raw, detection->window_idx);

    if (pending_index >= 0) {
        ctt_detection_t* pending = &queue->pending[pending_index];
        aggregate(pending, detection);
        if (log_index >= 0) {
            aggregate(&queue->log[log_index], detection);
        } else {
            /* The debug ring may wrap independently of the transactional
             * queue. Re-materialize its newest aggregate without admitting a
             * second pending copy of the same event. */
            write_log(queue, pending);
        }
        return CTT_QUEUE_REPEAT;
    }

    if (log_index >= 0) {
        /* The event was already transmitted during this same listen window.
         * Keep its diagnostics current but do not emit a second uplink. */
        aggregate(&queue->log[log_index], detection);
        return CTT_QUEUE_REPEAT;
    }

    write_log(queue, detection);
    if (queue->pending_n >= CTT_LOG_N) return CTT_QUEUE_NEW_DROPPED;

    queue->pending[queue->pending_tail] = *detection;
    queue->pending_tail =
        (uint8_t)((queue->pending_tail + 1u) % CTT_LOG_N);
    queue->pending_n++;
    return CTT_QUEUE_NEW_QUEUED;
}
