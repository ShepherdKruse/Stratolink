#include "mic_noise_ema.h"

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>

int main() {
    assert(mic_noise_ema_update(16u, 0u, 4u) == 15u);
    assert(mic_noise_ema_update(16u, 15u, 4u) == 16u);
    assert(mic_noise_ema_update(16u, 16u, 4u) == 16u);
    assert(mic_noise_ema_update(16u, 32u, 4u) == 17u);
    assert(mic_noise_ema_update(1u, 0u, 4u) == 1u);
    assert(mic_noise_ema_update(100u, 25u, 0u) == 25u);
    assert(mic_noise_ema_update(100u, 0u, 0u) == 1u);
    assert(mic_noise_ema_update(1u, UINT32_MAX, 4u) == 268435456u);
    assert(mic_noise_ema_update(UINT32_MAX, 0u, 4u) == 4026531840u);
    assert(mic_noise_ema_update(16u, 32u, 255u) ==
           mic_noise_ema_update(16u, 32u, 31u));

    uint32_t state = 0x6D2B79F5u;
    for (uint32_t trial = 0; trial < 200000u; ++trial) {
        state = state * 1664525u + 1013904223u;
        const uint32_t floor_sq = state;
        state = state * 1664525u + 1013904223u;
        const uint32_t sample_sq = state;
        const uint32_t updated =
            mic_noise_ema_update(floor_sq, sample_sq, 4u);
        const uint32_t lower =
            floor_sq < sample_sq ? floor_sq : sample_sq;
        const uint32_t upper =
            floor_sq > sample_sq ? floor_sq : sample_sq;
        assert(updated >= (lower == 0u ? 1u : lower));
        assert(updated <= (upper == 0u ? 1u : upper));
    }

    uint32_t converging = 10000u;
    for (uint32_t i = 0; i < 256u; ++i) {
        const uint32_t next =
            mic_noise_ema_update(converging, 100u, 4u);
        assert(next <= converging);
        assert(next >= 100u);
        converging = next;
    }
    assert(converging <= 115u);

    std::puts("Microphone noise EMA boundaries and 200k properties passed");
    return 0;
}
