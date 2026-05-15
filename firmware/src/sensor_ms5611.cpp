#include "sensor_ms5611.h"
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

static bool read_prom(void) {
    for (int i = 0; i < 6; i++) {
        Wire.beginTransmission(i2c_addr);
        Wire.write(MS5611_PROM_BASE + (uint8_t)((i + 1) * 2));
        if (Wire.endTransmission() != 0) return false;
        if (Wire.requestFrom((int)i2c_addr, 2) != 2) return false;
        uint16_t v = (uint16_t)Wire.read() << 8 | Wire.read();
        switch (i) {
            case 0: C1 = v; break;
            case 1: C2 = v; break;
            case 2: C3 = v; break;
            case 3: C4 = v; break;
            case 4: C5 = v; break;
            case 5: C6 = v; break;
        }
    }

    /* Defensive: a factory-programmed MS5611 has six non-zero,
     * non-saturated calibration constants.  A sensor that responded
     * to RESET but failed PROM read silently leaves C1..C6 either all
     * 0x0000 (no I2C bytes shifted in) or all 0xFFFF (bus held high
     * on NACK), both of which would still parse but yield garbage
     * pressure readings.  Reject both sentinels. */
    if ((C1 | C2 | C3 | C4 | C5 | C6) == 0) return false;
    if ((C1 & C2 & C3 & C4 & C5 & C6) == 0xFFFF) return false;

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
    *adc = (uint32_t)Wire.read() << 16 | (uint32_t)Wire.read() << 8 | Wire.read();
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
    if (!prom_valid) return false;

    uint32_t D1, D2;
    if (!cmd_adc(MS5611_CMD_D1_OSR4096, &D1)) return false;
    if (!cmd_adc(MS5611_CMD_D2_OSR4096, &D2)) return false;
    /* D1/D2 are 24-bit conversion results.  A literal 0 means the
     * ADC register hadn't latched yet (short delay, VDD glitch, I2C
     * race) — feeding 0 into the calibration math produces garbage,
     * so treat as a transient failure. */
    if (D1 == 0 || D2 == 0) return false;

    /* Standard MS5611-01BA03 first-order compensation (datasheet
     * §"Pressure and Temperature Calculation Flow").  All
     * intermediates promoted to int64 to avoid the well-known
     * overflow in (C4 * dT) and (D1 * SENS) on 32-bit math. */
    int32_t dT   = (int32_t)D2 - ((int32_t)C5 << 8);
    int32_t TEMP = 2000 + (int32_t)(((int64_t)dT * (int64_t)C6) >> 23);
    int64_t OFF  = ((int64_t)C2 << 16) + (((int64_t)C4 * (int64_t)dT) >> 7);
    int64_t SENS = ((int64_t)C1 << 15) + (((int64_t)C3 * (int64_t)dT) >> 8);

    /* Second-order temperature compensation.  Datasheet specifies two
     * piecewise corrections, BOTH of which must be applied — the
     * second branch (TEMP < -15 °C) was missing before, which broke
     * pressure accuracy at stratospheric temperatures (the stratopause
     * routinely hits -60 °C). */
    if (TEMP < 2000) {
        int64_t dT2  = (int64_t)(TEMP - 2000);
        int32_t T2   = (int32_t)(((int64_t)dT * (int64_t)dT) >> 31);
        int64_t OFF2  = (5 * (dT2 * dT2)) >> 1;
        int64_t SENS2 = OFF2 >> 1;
        if (TEMP < -1500) {
            int64_t dT15 = (int64_t)(TEMP + 1500);
            int64_t add  = dT15 * dT15;
            OFF2  += 7 * add;
            SENS2 += (11 * add) >> 1;
        }
        TEMP -= T2;
        OFF  -= OFF2;
        SENS -= SENS2;
    }

    /* Datasheet pressure formula returns P in units of 0.01 mbar
     * (= 0.01 hPa) — i.e. P = 100009 means 1000.09 mbar.  Range on
     * Earth: ~80 (0.8 hPa, ~50 km altitude) to ~110000 (1100 hPa,
     * deep low / hyperbaric).  Negative values are physically
     * impossible and indicate a math/sensor fault; clamp to zero. */
    int64_t P_centi = (((int64_t)D1 * SENS) >> 21) - OFF;
    int32_t P = (int32_t)(P_centi >> 15);
    if (P < 0) P = 0;

    /* Telemetry field is 0.1 hPa per LSB (see telemetry.h
     * pressure_ch).  Convert 0.01 hPa → 0.1 hPa by dividing by 10
     * (NOT multiplying — a previous bug here wrapped real ~987 hPa
     * readings down to ~370 hPa via uint16 overflow).  Saturate to
     * UINT16_MAX (= 6553.5 hPa, impossible on Earth) rather than
     * wrapping, so any future calibration fault fails loudly instead
     * of silently roll-over. */
    uint32_t P_deci = ((uint32_t)P + 5) / 10;  /* round-to-nearest */
    if (P_deci > 0xFFFFu) P_deci = 0xFFFFu;
    *pressure_ch = (uint16_t)P_deci;
    return true;
}

bool sensor_ms5611_read_temp_centidegrees(int16_t* temperature_cd) {
    if (!temperature_cd) return false;
    if (!prom_valid) return false;

    uint32_t D2;
    if (!cmd_adc(MS5611_CMD_D2_OSR4096, &D2)) return false;
    if (D2 == 0) return false;

    int32_t dT   = (int32_t)D2 - ((int32_t)C5 << 8);
    int32_t TEMP = 2000 + (int32_t)(((int64_t)dT * (int64_t)C6) >> 23);

    /* Apply T2 second-order correction so this fallback temperature
     * source agrees with TMP117 across the full flight envelope. */
    if (TEMP < 2000) {
        int32_t T2 = (int32_t)(((int64_t)dT * (int64_t)dT) >> 31);
        TEMP -= T2;
    }

    /* TEMP is in 0.01 °C (centidegrees, range -4000..+8500 per
     * datasheet).  Telemetry field is 0.1 °C per LSB, so divide by
     * 10 with round-to-nearest.  Range fits int16 (-400..+850). */
    int32_t out = (TEMP + (TEMP >= 0 ? 5 : -5)) / 10;
    if (out >  INT16_MAX) out = INT16_MAX;
    if (out <  INT16_MIN) out = INT16_MIN;
    *temperature_cd = (int16_t)out;
    return true;
}
