#ifndef MIC_ACOUSTIC_H
#define MIC_ACOUSTIC_H

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    uint32_t attempts;
    uint32_t captures;
    uint32_t capture_failures;
    uint32_t events;
    uint32_t last_variance_x16;
    uint32_t noise_floor_x16;
} mic_acoustic_diag_t;

bool mic_acoustic_init(void);
bool mic_acoustic_detect(uint8_t* acoustic_event);

#endif /* MIC_ACOUSTIC_H */
