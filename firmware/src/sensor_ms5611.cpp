#include "sensor_ms5611.h"
#include "board.h"
#include <Wire.h>

#define MS5611_CMD_RESET   0x1E
#define MS5611_CMD_ADC_READ 0x00
#define MS5611_CMD_D1_OSR4096 0x48
#define MS5611_CMD_D2_OSR4096 0x58
#define MS5611_PROM_BASE   0xA0
#define MS5611_CONV_DELAY_MS 10

static uint8_t i2c_addr = I2C_ADDR_BARO;
static uint16_t C1, C2, C3, C4, C5, C6;

static bool read_prom(void) {
    for (int i = 0; i < 6; i++) {
        Wire.beginTransmission(i2c_addr);
        Wire.write(MS5611_PROM_BASE + (uint8_t)(i * 2));
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
    Wire.beginTransmission(i2c_addr);
    Wire.write(MS5611_CMD_RESET);
    if (Wire.endTransmission() != 0) return false;
    delay(4);
    return read_prom();
}

bool sensor_ms5611_read_pressure_centihpa(uint16_t* pressure_ch) {
    if (!pressure_ch) return false;

    uint32_t D1, D2;
    if (!cmd_adc(MS5611_CMD_D1_OSR4096, &D1)) return false;
    if (!cmd_adc(MS5611_CMD_D2_OSR4096, &D2)) return false;

    int32_t dT = (int32_t)D2 - ((int32_t)C5 << 8);
    int32_t TEMP = 2000 + ((int64_t)dT * (int64_t)C6 >> 23);
    int64_t OFF  = ((int64_t)C2 << 16) + ((int64_t)C4 * (int64_t)dT >> 7);
    int64_t SENS = ((int64_t)C1 << 15) + ((int64_t)C3 * (int64_t)dT >> 8);

    if (TEMP < 2000) {
        int32_t T2 = ((int64_t)dT * (int64_t)dT) >> 31;
        int64_t OFF2 = 5 * ((int64_t)(TEMP - 2000) * (int64_t)(TEMP - 2000)) >> 1;
        int64_t SENS2 = OFF2 >> 1;
        TEMP -= T2;
        OFF -= OFF2;
        SENS -= SENS2;
    }

    int32_t P = (int32_t)(((int64_t)D1 * SENS >> 21) - OFF) >> 15);
    if (P < 0) P = 0;
    *pressure_ch = (uint16_t)((uint32_t)P * 10);
    return true;
}

bool sensor_ms5611_read_temp_centidegrees(int16_t* temperature_cd) {
    if (!temperature_cd) return false;

    uint32_t D2;
    if (!cmd_adc(MS5611_CMD_D2_OSR4096, &D2)) return false;

    int32_t dT = (int32_t)D2 - ((int32_t)C5 << 8);
    int32_t TEMP = 2000 + ((int64_t)dT * (int64_t)C6 >> 23);
    *temperature_cd = (int16_t)(TEMP / 10);
    return true;
}
