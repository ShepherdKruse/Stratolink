#ifndef SENSOR_MS5611_H
#define SENSOR_MS5611_H

#include <stdint.h>
#include <stdbool.h>

/**
 * MS5611 barometer (I2C).
 * Read pressure in 0.1 hPa (centihectopascals). Optional internal temp in 0.1 °C.
 * Returns true on success.
 */
bool sensor_ms5611_read_pressure_centihpa(uint16_t* pressure_ch);

/**
 * Optional: read internal temperature in centidegrees (for compensation / redundancy).
 */
bool sensor_ms5611_read_temp_centidegrees(int16_t* temperature_cd);

/**
 * Initialize: reset and read PROM. Call after I2C begin.
 */
bool sensor_ms5611_init(void);

#endif /* SENSOR_MS5611_H */
