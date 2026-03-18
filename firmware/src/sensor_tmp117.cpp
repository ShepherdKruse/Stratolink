#include "sensor_tmp117.h"
#include "board.h"
#include <Wire.h>

#define TMP117_REG_TEMP   0x00
#define TMP117_REG_CONFIG 0x01
#define TMP117_ONE_SHOT    (3u << 13)

static uint8_t i2c_addr = I2C_ADDR_TEMP;

bool sensor_tmp117_init(void) {
    Wire.beginTransmission(i2c_addr);
    return Wire.endTransmission() == 0;
}

bool sensor_tmp117_read_centidegrees(int16_t* temperature_cd) {
    if (!temperature_cd) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(TMP117_REG_CONFIG);
    Wire.write((uint8_t)(TMP117_ONE_SHOT >> 8));
    Wire.write((uint8_t)(TMP117_ONE_SHOT & 0xFF));
    if (Wire.endTransmission() != 0) return false;

    delay(TMP117_ONESHOT_CONVERSION_MS);

    Wire.beginTransmission(i2c_addr);
    Wire.write(TMP117_REG_TEMP);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 2) != 2) return false;

    uint8_t hi = Wire.read();
    uint8_t lo = Wire.read();
    int16_t raw = (int16_t)((uint16_t)hi << 8 | lo);
    *temperature_cd = (int16_t)((int32_t)raw * 10 / 128);
    return true;
}
