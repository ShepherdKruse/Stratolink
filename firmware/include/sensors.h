#ifndef SENSORS_H
#define SENSORS_H

#include <stdbool.h>

/**
 * Initialize I2C (board pins) and all Phase 2 sensors: TMP117, MS5611, LIS2DH12.
 * Call once from setup() after power_adc_init().
 */
bool sensors_init(void);

/**
 * Reinitialize the STM32 I2C peripheral and clock a slave-stuck bus free.
 * Use only after every I2C sensor in one scheduled read phase has failed;
 * individual sensor drivers already perform their own bounded retries.
 */
void sensors_recover_i2c_bus(void);

#endif /* SENSORS_H */
