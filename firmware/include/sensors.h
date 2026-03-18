#ifndef SENSORS_H
#define SENSORS_H

#include <stdbool.h>

/**
 * Initialize I2C (board pins) and all Phase 2 sensors: TMP117, MS5611, LIS2DH12.
 * Call once from setup() after power_adc_init().
 */
bool sensors_init(void);

#endif /* SENSORS_H */
