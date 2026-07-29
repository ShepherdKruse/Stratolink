#ifndef SENSOR_MS5611_H
#define SENSOR_MS5611_H

#include <stdint.h>
#include <stdbool.h>

/**
 * MS5611-01BA03 barometer (I2C).
 *
 * Pressure: returned in 0.1 hPa per LSB (uint16, range 0..6553.5 hPa,
 * covers Earth's 0.8 hPa stratopause minimum through 1100 hPa surface
 * maximum).  Function name keeps the legacy "centihpa" suffix for
 * source-compat with payload spec v1 (telemetry.h pressure_ch); the
 * actual on-wire field is decihectopascals — see telemetry.h.
 *
 * Temperature: returned in 0.1 °C per LSB (int16, range -400..+850
 * representing -40.0 °C..+85.0 °C, the MS5611 spec range).  Includes
 * the T2 second-order correction so it tracks TMP117 down to
 * stratospheric temperatures.
 *
 * Both functions return true on success.  A return of false means
 * either uninitialised PROM, I2C bus error, or an ADC sample that
 * hadn't latched yet — caller should leave the previous value in the
 * telemetry struct rather than transmit garbage.
 */
bool sensor_ms5611_read_pressure_centihpa(uint16_t* pressure_ch);

/**
 * Read MS5611 internal temperature (fallback / redundancy for TMP117).
 * Units and error semantics identical to the pressure read above.
 */
bool sensor_ms5611_read_temp_decidegrees(int16_t* temperature_dc);

/**
 * Initialize: reset and read PROM. Call after I2C begin.
 */
bool sensor_ms5611_init(void);

#endif /* SENSOR_MS5611_H */
