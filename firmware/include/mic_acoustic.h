#ifndef MIC_ACOUSTIC_H
#define MIC_ACOUSTIC_H

#include <stdint.h>
#include <stdbool.h>

bool mic_acoustic_init(void);
bool mic_acoustic_detect(uint8_t* acoustic_event);

#endif /* MIC_ACOUSTIC_H */
