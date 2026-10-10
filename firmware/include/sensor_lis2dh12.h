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
 * Call after init when using STOP1 sleep so INT1 can wake the MCU.
 */
bool sensor_lis2dh12_enable_freefall_int1(void);

/**
 * Read INT1_SRC. Returns true only when its aggregate IA bit reports that the
 * configured all-axis freefall condition is active; individual per-axis low
 * status bits are not sufficient.
 */
bool sensor_lis2dh12_clear_and_read_int1_src(void);

/**
 * Read acceleration and report whether magnitude is above the ±0.5 g
 * freefall-clear threshold. Returns false on an I2C/read failure so callers
 * can distinguish "confirmed low-g" from "sensor unavailable".
 */
bool sensor_lis2dh12_get_freefall_cleared(bool* cleared);

/**
 * Convenience used by the bounded burst state machine. Returns true only for
 * a successful ~1 g measurement. A read failure is unknown, not evidence of
 * landing; BURST_MAX_CYCLES contains a persistent sensor fault.
 */
bool sensor_lis2dh12_is_freefall_cleared(void);

#endif /* SENSOR_LIS2DH12_H */
