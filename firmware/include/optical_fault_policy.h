#pragma once

#include <stdint.h>

/* Consume one bounded fast retry without permitting an 8-bit wrap to reopen
 * the retry loop. Returning false means the caller must resume its normal
 * degraded primary cadence instead of continuing the short fault cadence. */
static inline bool optical_fault_consume_fast_retry(
    uint8_t* retries, uint8_t maximum_retries) {
    if (!retries || maximum_retries == 0u || *retries >= maximum_retries) {
        return false;
    }
    (*retries)++;
    return true;
}
