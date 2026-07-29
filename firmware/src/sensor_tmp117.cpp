#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "stratolink_pins.h"
#include "tmp117_conversion.h"
#include <Wire.h>

#define TMP117_REG_TEMP   0x00
#define TMP117_REG_CONFIG 0x01
#define TMP117_ONE_SHOT    (3u << 10)

static uint8_t i2c_addr = I2C_ADDR_TEMP;
static bool tmp117_present = false;
/* J-Link-readable: post-boot attempts to recover a TMP117 that was absent or
 * stopped acknowledging. The MS5611 fallback remains available meanwhile. */
static volatile uint32_t s_tmp117_reinit_attempts = 0;
/* J-Link-readable source attribution. Plausible aggregate telemetry cannot
 * otherwise distinguish a real TMP117 sample from the MS5611 fallback. */
static volatile uint32_t s_tmp117_direct_reads = 0;
static volatile uint32_t s_tmp117_fallback_reads = 0;
static volatile uint32_t s_tmp117_poweron_sentinels = 0;

bool sensor_tmp117_init(void) {
    Wire.beginTransmission(i2c_addr);
    tmp117_present = (Wire.endTransmission() == 0);
    return tmp117_present;
}

bool sensor_tmp117_read_decidegrees(int16_t* temperature_dc) {
    if (!temperature_dc) return false;

    /* A cold-start I2C NACK must not make the TMP117 absent for the entire
     * flight. Retry once on each scheduled sensor cycle; this is a tiny bus
     * transaction at the 20-30 minute normal cadence. */
    if (!tmp117_present) {
        s_tmp117_reinit_attempts++;
        (void)sensor_tmp117_init();
    }

    // If TMP117 is available, read from it directly.
    if (tmp117_present) {
        Wire.beginTransmission(i2c_addr);
        Wire.write(TMP117_REG_CONFIG);
        Wire.write((uint8_t)(TMP117_ONE_SHOT >> 8));
        Wire.write((uint8_t)(TMP117_ONE_SHOT & 0xFF));
        if (Wire.endTransmission() != 0) {
            tmp117_present = false;
            goto fallback;
        }

        delay(TMP117_ONESHOT_CONVERSION_MS);

        Wire.beginTransmission(i2c_addr);
        Wire.write(TMP117_REG_TEMP);
        if (Wire.endTransmission() != 0) {
            tmp117_present = false;
            goto fallback;
        }
        if (Wire.requestFrom((int)i2c_addr, 2) != 2) {
            tmp117_present = false;
            goto fallback;
        }

        uint8_t hi = (uint8_t)Wire.read();
        uint8_t lo = (uint8_t)Wire.read();
        int16_t raw = (int16_t)((uint16_t)hi << 8 | lo);
        if (!tmp117_raw_to_decidegrees(raw, temperature_dc)) {
            /* 0x8000 is the documented power-on value before a completed
             * conversion. Retry sensor detection next cycle and use the
             * independent pressure-sensor temperature channel now. */
            if (raw == INT16_MIN) s_tmp117_poweron_sentinels++;
            tmp117_present = false;
            goto fallback;
        }
        s_tmp117_direct_reads++;
        return true;
    }

fallback:
    // Fall back to MS5611 internal temperature sensor.
    {
        bool ok = sensor_ms5611_read_temp_decidegrees(temperature_dc);
        if (ok) s_tmp117_fallback_reads++;
        return ok;
    }
}
