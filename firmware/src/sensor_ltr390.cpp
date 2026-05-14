#include "sensor_ltr390.h"
#include "stratolink_pins.h"
#include <Wire.h>

#define LTR390_REG_MAIN_CTRL     0x00
#define LTR390_REG_MEAS_RATE     0x04
#define LTR390_REG_GAIN          0x05
#define LTR390_REG_PART_ID       0x06
#define LTR390_REG_MAIN_STATUS   0x07
#define LTR390_REG_ALS_DATA_0    0x0D
#define LTR390_REG_UVS_DATA_0    0x10

#define LTR390_PART_ID_VAL       0xB2
#define LTR390_ENABLE            0x02
#define LTR390_MODE_UVS          0x08
#define LTR390_MODE_ALS          0x00
#define LTR390_STATUS_DATA_RDY   0x08

/* 18-bit resolution, 100 ms integration, 100 ms rate */
#define LTR390_MEAS_RATE_VAL     0x22
/* Gain 18x */
#define LTR390_GAIN_VAL          0x04

/* UV sensitivity at gain=18x, res=18bit: ~2300 counts per UV index 1 */
#define LTR390_UV_SENSITIVITY    2300

static uint8_t i2c_addr = I2C_ADDR_UV;
static bool ltr390_present = false;

static bool write_reg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(reg);
    Wire.write(val);
    return Wire.endTransmission() == 0;
}

static bool read_reg(uint8_t reg, uint8_t* val) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(reg);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 1) != 1) return false;
    *val = Wire.read();
    return true;
}

static bool read_data_20bit(uint8_t base_reg, uint32_t* data) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(base_reg);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 3) != 3) return false;
    uint8_t d0 = Wire.read();
    uint8_t d1 = Wire.read();
    uint8_t d2 = Wire.read();
    *data = (uint32_t)d0 | ((uint32_t)d1 << 8) | ((uint32_t)(d2 & 0x0F) << 16);
    return true;
}

static bool wait_data_ready(void) {
    for (int i = 0; i < 20; i++) {
        uint8_t status;
        if (read_reg(LTR390_REG_MAIN_STATUS, &status) && (status & LTR390_STATUS_DATA_RDY))
            return true;
        delay(10);
    }
    return false;
}

bool sensor_ltr390_init(void) {
    uint8_t id;
    if (!read_reg(LTR390_REG_PART_ID, &id)) return false;
    if ((id >> 4) != (LTR390_PART_ID_VAL >> 4)) return false;

    if (!write_reg(LTR390_REG_MEAS_RATE, LTR390_MEAS_RATE_VAL)) return false;
    if (!write_reg(LTR390_REG_GAIN, LTR390_GAIN_VAL)) return false;

    ltr390_present = true;
    return true;
}

bool sensor_ltr390_read_uv_index(uint8_t* uv_index) {
    if (!uv_index || !ltr390_present) return false;

    if (!write_reg(LTR390_REG_MAIN_CTRL, LTR390_MODE_UVS | LTR390_ENABLE)) return false;
    if (!wait_data_ready()) return false;

    uint32_t raw;
    if (!read_data_20bit(LTR390_REG_UVS_DATA_0, &raw)) return false;

    /* Standby after read */
    (void)write_reg(LTR390_REG_MAIN_CTRL, 0x00);

    *uv_index = (uint8_t)(raw / LTR390_UV_SENSITIVITY);
    return true;
}

bool sensor_ltr390_read_ambient_lux(uint16_t* lux) {
    if (!lux || !ltr390_present) return false;

    if (!write_reg(LTR390_REG_MAIN_CTRL, LTR390_MODE_ALS | LTR390_ENABLE)) return false;
    if (!wait_data_ready()) return false;

    uint32_t raw;
    if (!read_data_20bit(LTR390_REG_ALS_DATA_0, &raw)) return false;

    (void)write_reg(LTR390_REG_MAIN_CTRL, 0x00);

    /* Lux = 0.6 * raw / (gain * int_time_100ms). gain=18, int=1 (100ms) */
    uint32_t lux_val = (raw * 6) / (18 * 10);
    *lux = (lux_val > 65535) ? 65535 : (uint16_t)lux_val;
    return true;
}
