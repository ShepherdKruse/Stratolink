#include "lorawan_counter.h"
#include <limits.h>

bool lorawan_fcntdown_reconstruct(uint32_t next_expected,
                                 uint16_t on_air_low,
                                 uint32_t* accepted_counter) {
    if (!accepted_counter) return false;

    uint32_t candidate;
    if (next_expected == 0) {
        candidate = on_air_low;
    } else {
        uint16_t diff =
            (uint16_t)(on_air_low - (uint16_t)(next_expected & 0xFFFFu));
        if (diff >= 0x8000u ||
            (uint32_t)diff > UINT32_MAX - next_expected) {
            return false;
        }
        candidate = next_expected + diff;
    }

    /* The retained state stores candidate + 1. Never wrap that durable replay
     * guard back to the fresh-session sentinel. */
    if (candidate == UINT32_MAX) return false;
    *accepted_counter = candidate;
    return true;
}
