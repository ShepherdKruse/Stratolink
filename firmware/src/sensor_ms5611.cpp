#include "sensor_ms5611.h"
#include "ms5611_compensation.h"
#include "ms5611_crc.h"
#include "stratolink_pins.h"
#include <Wire.h>

#define MS5611_CMD_RESET   0x1E
#define MS5611_CMD_ADC_READ 0x00
#define MS5611_CMD_D1_OSR4096 0x48
#define MS5611_CMD_D2_OSR4096 0x58
#define MS5611_PROM_BASE   0xA0
#define MS5611_CONV_DELAY_MS 10

static uint8_t i2c_addr = I2C_ADDR_BARO;
static uint16_t C1, C2, C3, C4, C5, C6;
static bool prom_valid = false;
/* J-Link-readable: post-boot PROM reloads after a failed cold-start init. */
static volatile uint32_t s_ms5611_reinit_attempts = 0;

static bool read_prom(void) {
    uint16_t prom[8] = {};
    for (int i = 0; i < 8; i++) {
        Wire.beginTransmission(i2c_addr);
        Wire.write(MS5611_PROM_BASE + (uint8_t)(i * 2));
        if (Wire.endTransmission() != 0) return false;
        if (Wire.requestFrom((int)i2c_addr, 2) != 2) return false;
        prom[i] = (uint16_t)Wire.read() << 8 | Wire.read();
    }

    /* Defensive: a factory-programmed MS5611 has six non-zero,
     * non-saturated calibration constants.  A sensor that responded
     * to RESET but failed PROM read silently leaves C1..C6 either all
     * 0x0000 (no I2C bytes shifted in) or all 0xFFFF (bus held high
     * on NACK), both of which would still parse but yield garbage
     * pressure readings.  Reject both sentinels. */
    const uint16_t any = prom[1] | prom[2] | prom[3] |
                         prom[4] | prom[5] | prom[6];
    const uint16_t all = prom[1] & prom[2] & prom[3] &
                         prom[4] & prom[5] & prom[6];
    if (any == 0 || all == 0xFFFF) return false;
    if (!ms5611_prom_crc_valid(prom)) return false;

    /* Commit calibration atomically only after the complete PROM passes
     * transport, sentinel, and CRC validation. */
    C1 = prom[1];
    C2 = prom[2];
    C3 = prom[3];
    C4 = prom[4];
    C5 = prom[5];
    C6 = prom[6];
    prom_valid = true;
    return true;
}

static bool cmd_adc(uint8_t cmd, uint32_t* adc) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(cmd);
    if (Wire.endTransmission() != 0) return false;
    delay(MS5611_CONV_DELAY_MS);
    Wire.beginTransmission(i2c_addr);
    Wire.write(MS5611_CMD_ADC_READ);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 3) != 3) return false;
    *adc = (uint32_t)(uint8_t)Wire.read() << 16 |
           (uint32_t)(uint8_t)Wire.read() << 8 |
           (uint32_t)(uint8_t)Wire.read();
    return true;
}

bool sensor_ms5611_init(void) {
    prom_valid = false;
    Wire.beginTransmission(i2c_addr);
    Wire.write(MS5611_CMD_RESET);
    if (Wire.endTransmission() != 0) return false;
    delay(4);
    return read_prom();
}

bool sensor_ms5611_read_pressure_centihpa(uint16_t* pressure_ch) {
    if (!pressure_ch) return false;
    if (!prom_valid) {
        s_ms5611_reinit_attempts++;
        if (!sensor_ms5611_init()) return false;
    }

    uint32_t D1, D2;
    if (!cmd_adc(MS5611_CMD_D1_OSR4096, &D1)) return false;
    if (!cmd_adc(MS5611_CMD_D2_OSR4096, &D2)) return false;
    /* D1/D2 are 24-bit conversion results.  A literal 0 means the
     * ADC register hadn't latched yet (short delay, VDD glitch, I2C
     * race) — feeding 0 into the calibration math produces garbage,
     * so treat as a transient failure. */
    if (D1 == 0 || D2 == 0) return false;

    const uint16_t coefficients[6] = {C1, C2, C3, C4, C5, C6};
    ms5611_compensated_t compensated = {};
    if (!ms5611_compensate(coefficients, D1, D2, &compensated)) return false;

    /* Telemetry field is 0.1 hPa per LSB (see telemetry.h
     * pressure_ch).  Convert 0.01 hPa → 0.1 hPa by dividing by 10
     * (NOT multiplying — a previous bug here wrapped real ~987 hPa
     * readings down to ~370 hPa via uint16 overflow).  Saturate to
     * UINT16_MAX (= 6553.5 hPa, impossible on Earth) rather than
     * wrapping, so any future calibration fault fails loudly instead
     * of silently roll-over. */
    uint32_t P_deci =
        ((uint32_t)compensated.pressure_centi_hpa + 5) / 10;
    if (P_deci > 0xFFFFu) P_deci = 0xFFFFu;
    *pressure_ch = (uint16_t)P_deci;
    return true;
}

bool sensor_ms5611_read_temp_decidegrees(int16_t* temperature_dc) {
    if (!temperature_dc) return false;
    if (!prom_valid) {
        s_ms5611_reinit_attempts++;
        if (!sensor_ms5611_init()) return false;
    }

    uint32_t D2;
    if (!cmd_adc(MS5611_CMD_D2_OSR4096, &D2)) return false;
    if (D2 == 0) return false;

    /* Pressure is not needed by this call, but using the same pure function
     * keeps temperature and pressure on one exactly tested compensation path. */
    const uint16_t coefficients[6] = {C1, C2, C3, C4, C5, C6};
    ms5611_compensated_t compensated = {};
    if (!ms5611_compensate(coefficients, 1u, D2, &compensated)) return false;

    /* TEMP is in 0.01 °C (centidegrees, range -4000..+8500 per
     * datasheet).  Telemetry field is 0.1 °C per LSB, so divide by
     * 10 with round-to-nearest.  Range fits int16 (-400..+850). */
    const int32_t temp_centi = compensated.temperature_centi_c;
    int32_t out =
        (temp_centi + (temp_centi >= 0 ? 5 : -5)) / 10;
    if (out >  INT16_MAX) out = INT16_MAX;
    if (out <  INT16_MIN) out = INT16_MIN;
    *temperature_dc = (int16_t)out;
    return true;
}
