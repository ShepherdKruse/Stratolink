#ifndef CTT_QUEUE_H
#define CTT_QUEUE_H

#include "lorawan.h"

/* Pure, bounded queue/ring policy for CTT detections. Keeping this independent
 * of the radio driver makes saturation and repeat aggregation testable on the
 * host. The queue is intentionally RAM-only: an unconfirmed LoRaWAN event has
 * no end-to-end acknowledgement with which to make retained exactly-once
 * delivery safe across reset. */
typedef struct {
    ctt_detection_t log[CTT_LOG_N];
    ctt_detection_t pending[CTT_LOG_N];
    uint8_t log_n;
    uint8_t log_next;
    uint8_t pending_head;
    uint8_t pending_tail;
    uint8_t pending_n;
} ctt_queue_t;

typedef enum {
    CTT_QUEUE_REPEAT = 0,
    CTT_QUEUE_NEW_QUEUED = 1,
    CTT_QUEUE_NEW_DROPPED = 2,
} ctt_queue_result_t;

void ctt_queue_init(ctt_queue_t* queue);
uint8_t ctt_queue_get_log(const ctt_queue_t* queue, ctt_detection_t* out);
bool ctt_queue_peek(const ctt_queue_t* queue, ctt_detection_t* out);
void ctt_queue_ack(ctt_queue_t* queue);
uint8_t ctt_queue_count(const ctt_queue_t* queue);

/* Record one checksum-valid beep. Repeats of the same raw id/window update
 * hits and best RSSI but are never admitted twice, even if the independent
 * debug ring has wrapped while the original event remains pending. */
ctt_queue_result_t ctt_queue_record(
    ctt_queue_t* queue, const ctt_detection_t* detection);

#endif
