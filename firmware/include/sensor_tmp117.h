#ifndef SENSOR_TMP117_H
#define SENSOR_TMP117_H

#include <stdint.h>
#include <stdbool.h>

/**
 * TMP117 temperature sensor (I2C).
 * One-shot mode: trigger conversion, wait TMP117_ONESHOT_CONVERSION_MS, read.
 * Result in centidegrees (0.1 °C). Returns true on success.
 */
bool sensor_tmp117_read_centidegrees(int16_t* temperature_cd);

/**
 * Initialize / detect TMP117. Call after I2C begin.
 */
bool sensor_tmp117_init(void);

#endif /* SENSOR_TMP117_H */
