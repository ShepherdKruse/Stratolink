#ifndef SENSOR_LIS2DH12_H
#define SENSOR_LIS2DH12_H

#include <stdint.h>
#include <stdbool.h>

/**
 * LIS2DH12 accelerometer (I2C).
 * Read X, Y, Z in 0.01 m/s² (centim/s²). ±2g range assumed.
 */
bool sensor_lis2dh12_read_accel_cm_s2(int16_t* ax, int16_t* ay, int16_t* az);

/**
 * Initialize: power on, 1 Hz ODR for low power. Call after I2C begin.
 */
bool sensor_lis2dh12_init(void);

/**
 * Enable freefall detection on INT1 (PA8). Uses 100 Hz ODR and board.h threshold/duration.
 * Call after init when using STOP2 sleep so INT1 can wake the MCU.
 */
bool sensor_lis2dh12_enable_freefall_int1(void);

/**
 * Read and clear INT1_SRC. Returns true if freefall (or movement) interrupt was active.
 */
bool sensor_lis2dh12_clear_and_read_int1_src(void);

/**
 * Return true if acceleration magnitude is above threshold (e.g. back to ~1g, freefall cleared).
 * Uses current accel read; ±0.5g threshold.
 */
bool sensor_lis2dh12_is_freefall_cleared(void);

#endif /* SENSOR_LIS2DH12_H */
