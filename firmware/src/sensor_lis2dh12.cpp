#include "sensor_lis2dh12.h"
#include "stratolink_pins.h"
#include <Wire.h>

#define LIS2DH12_REG_CTRL1    0x20
#define LIS2DH12_REG_CTRL3    0x22
#define LIS2DH12_REG_INT1_CFG 0x30
#define LIS2DH12_REG_INT1_SRC 0x31
#define LIS2DH12_REG_INT1_THS 0x32
#define LIS2DH12_REG_INT1_DUR 0x33
#define LIS2DH12_REG_OUT_X_L  0x28

#define LIS2DH12_CTRL1_LPEN   (1 << 3)
#define LIS2DH12_CTRL1_ODR_1HZ  (1 << 4)
#define LIS2DH12_CTRL1_ODR_100HZ (5 << 4)
#define LIS2DH12_CTRL1_XEN    (1 << 0)
#define LIS2DH12_CTRL1_YEN    (1 << 1)
#define LIS2DH12_CTRL1_ZEN    (1 << 2)
#define LIS2DH12_CTRL3_I1_IA1 (1 << 6)
#define LIS2DH12_INT1_CFG_XLIE (1 << 0)
#define LIS2DH12_INT1_CFG_YLIE (1 << 2)
#define LIS2DH12_INT1_CFG_ZLIE (1 << 4)

static uint8_t i2c_addr = I2C_ADDR_ACCEL;

bool sensor_lis2dh12_init(void) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL1);
    Wire.write(LIS2DH12_CTRL1_ODR_1HZ | LIS2DH12_CTRL1_LPEN | LIS2DH12_CTRL1_XEN | LIS2DH12_CTRL1_YEN | LIS2DH12_CTRL1_ZEN);
    return Wire.endTransmission() == 0;
}

bool sensor_lis2dh12_read_accel_cm_s2(int16_t* ax, int16_t* ay, int16_t* az) {
    if (!ax || !ay || !az) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_OUT_X_L | 0x80);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 6) != 6) return false;

    int16_t x = (int16_t)((uint16_t)Wire.read() | (uint16_t)Wire.read() << 8);
    int16_t y = (int16_t)((uint16_t)Wire.read() | (uint16_t)Wire.read() << 8);
    int16_t z = (int16_t)((uint16_t)Wire.read() | (uint16_t)Wire.read() << 8);

    x >>= 4;
    y >>= 4;
    z >>= 4;
    *ax = (int16_t)((int32_t)x * 96 / 100);
    *ay = (int16_t)((int32_t)y * 96 / 100);
    *az = (int16_t)((int32_t)z * 96 / 100);
    return true;
}

bool sensor_lis2dh12_enable_freefall_int1(void) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL1);
    Wire.write(LIS2DH12_CTRL1_ODR_100HZ | LIS2DH12_CTRL1_LPEN | LIS2DH12_CTRL1_XEN | LIS2DH12_CTRL1_YEN | LIS2DH12_CTRL1_ZEN);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL3);
    Wire.write(LIS2DH12_CTRL3_I1_IA1);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_INT1_THS);
    Wire.write((uint8_t)ACCEL_FREEFALL_THRESHOLD);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_INT1_DUR);
    Wire.write((uint8_t)ACCEL_FREEFALL_DURATION);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_INT1_CFG);
    Wire.write(LIS2DH12_INT1_CFG_XLIE | LIS2DH12_INT1_CFG_YLIE | LIS2DH12_INT1_CFG_ZLIE);
    return Wire.endTransmission() == 0;
}

bool sensor_lis2dh12_clear_and_read_int1_src(void) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_INT1_SRC);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 1) != 1) return false;
    return (Wire.read() & 0x3F) != 0;
}

bool sensor_lis2dh12_is_freefall_cleared(void) {
    int16_t ax, ay, az;
    if (!sensor_lis2dh12_read_accel_cm_s2(&ax, &ay, &az)) return true;
    int32_t mag_sq = (int32_t)ax * ax + (int32_t)ay * ay + (int32_t)az * az;
    return mag_sq >= 240000u;
}
