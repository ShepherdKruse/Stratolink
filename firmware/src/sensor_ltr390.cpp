#include "sensor_ltr390.h"
#include "ltr390_conversion.h"
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
#define LTR390_SW_RESET          0x10
#define LTR390_ENABLE            0x02
#define LTR390_MODE_UVS          0x08
#define LTR390_MODE_ALS          0x00
#define LTR390_STATUS_DATA_RDY   0x08

/* 18-bit resolution, 100 ms integration, 100 ms rate */
#define LTR390_MEAS_RATE_VAL     0x22
/* Gain 18x (UVS).  ALS drops to 1x per-read, see read_ambient_lux. */
#define LTR390_GAIN_VAL          0x04
#define LTR390_GAIN_1X           0x00

static uint8_t i2c_addr = I2C_ADDR_UV;
static bool ltr390_present = false;
/* Set only after a successful command can have enabled the measurement engine;
 * clear only after MAIN_CTRL standby reads back. This distinguishes an absent
 * sensor from one this boot may have left drawing active current. */
static bool ltr390_active_possible = false;
/* J-Link-readable: post-boot attempts to recover an absent/faulted LTR390. */
static volatile uint32_t s_ltr390_reinit_attempts = 0;
static volatile uint32_t s_ltr390_quiesce_failures = 0;
static volatile uint32_t s_ltr390_soft_reset_recoveries = 0;

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
    *val = (uint8_t)Wire.read();
    return true;
}

static bool read_data_20bit(uint8_t base_reg, uint32_t* data) {
    Wire.beginTransmission(i2c_addr);
    Wire.write(base_reg);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 3) != 3) return false;
    uint8_t d0 = (uint8_t)Wire.read();
    uint8_t d1 = (uint8_t)Wire.read();
    uint8_t d2 = (uint8_t)Wire.read();
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

static bool standby_readback(void) {
    uint8_t control = 0xFFu;
    return write_reg(LTR390_REG_MAIN_CTRL, 0x00) &&
           read_reg(LTR390_REG_MAIN_CTRL, &control) && control == 0x00u;
}

static bool reset_to_standby_readback(void) {
    /* MAIN_CTRL bit 4 resets the part. The upstream Linux driver notes that
     * the chip may NACK the reset transaction itself, so ignore that status,
     * wait its 1-2 ms recovery interval, and trust only a subsequent exact
     * default-register readback. */
    (void)write_reg(LTR390_REG_MAIN_CTRL, LTR390_SW_RESET);
    delay(2);
    uint8_t control = 0xFFu;
    return read_reg(LTR390_REG_MAIN_CTRL, &control) && control == 0x00u;
}

bool sensor_ltr390_quiesce(void) {
    if (!ltr390_active_possible) return true;
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        if (standby_readback()) {
            ltr390_active_possible = false;
            return true;
        }
        delay(10);
    }
    if (reset_to_standby_readback()) {
        ltr390_active_possible = false;
        /* Software reset also restores gain/configuration defaults. Force the
         * next measurement through sensor_ltr390_init() before reuse. */
        ltr390_present = false;
        if (s_ltr390_soft_reset_recoveries != UINT32_MAX) {
            s_ltr390_soft_reset_recoveries++;
        }
        return true;
    }
    if (s_ltr390_quiesce_failures != UINT32_MAX) {
        s_ltr390_quiesce_failures++;
    }
    ltr390_present = false;
    return false;
}

bool sensor_ltr390_init(void) {
    ltr390_present = false;
    uint8_t id;
    if (!read_reg(LTR390_REG_PART_ID, &id)) return false;
    if ((id >> 4) != (LTR390_PART_ID_VAL >> 4)) return false;

    /* The MCU may have reset while a preceding measurement was active. Once
     * WHO_AM_I proves the part is present, treat its power state as unknown
     * until an explicit standby command reads back. */
    ltr390_active_possible = true;
    if (!sensor_ltr390_quiesce()) return false;

    if (!write_reg(LTR390_REG_MEAS_RATE, LTR390_MEAS_RATE_VAL)) return false;
    if (!write_reg(LTR390_REG_GAIN, LTR390_GAIN_VAL)) return false;

    ltr390_present = true;
    return true;
}

bool sensor_ltr390_read_uv_index(uint8_t* uv_index) {
    if (!uv_index) return false;
    if (!ltr390_present) {
        s_ltr390_reinit_attempts++;
        if (!sensor_ltr390_init()) return false;
    }

    ltr390_active_possible = true;
    if (!write_reg(LTR390_REG_MAIN_CTRL, LTR390_MODE_UVS | LTR390_ENABLE)) {
        /* A bus-level failure does not prove the device rejected the enable
         * byte. Treat its state as active/unknown and demand standby. */
        (void)sensor_ltr390_quiesce();
        ltr390_present = false;
        return false;
    }
    if (!wait_data_ready()) {
        (void)sensor_ltr390_quiesce();
        ltr390_present = false;
        return false;
    }

    uint32_t raw;
    if (!read_data_20bit(LTR390_REG_UVS_DATA_0, &raw)) {
        (void)sensor_ltr390_quiesce();
        ltr390_present = false;
        return false;
    }

    /* Standby after read */
    if (!sensor_ltr390_quiesce()) {
        ltr390_present = false;
        return false;
    }

    *uv_index = ltr390_uv_index_from_raw(raw);
    return true;
}

bool sensor_ltr390_read_ambient_lux(uint16_t* lux) {
    if (!lux) return false;
    if (!ltr390_present) {
        s_ltr390_reinit_attempts++;
        if (!sensor_ltr390_init()) return false;
    }

    /* ALS at gain 1x: at the UVS gain (18x, 18-bit) full scale is only
     * ~8.7 klux and daylight at altitude (30-120 klux) rails the ADC,
     * pegging ambient_lux for the whole flight day.  Gain 1x gives
     * ~157 klux full scale.  Restore the UVS gain after the read. */
    if (!write_reg(LTR390_REG_GAIN, LTR390_GAIN_1X)) {
        ltr390_present = false;
        return false;
    }
    ltr390_active_possible = true;
    if (!write_reg(LTR390_REG_MAIN_CTRL, LTR390_MODE_ALS | LTR390_ENABLE)) {
        (void)sensor_ltr390_quiesce();
        ltr390_present = false;
        return false;
    }
    bool ready = wait_data_ready();
    uint32_t raw = 0;
    bool ok = ready && read_data_20bit(LTR390_REG_ALS_DATA_0, &raw);

    bool standby_ok = sensor_ltr390_quiesce();
    bool gain_ok = write_reg(LTR390_REG_GAIN, LTR390_GAIN_VAL);
    if (!ok || !standby_ok || !gain_ok) {
        ltr390_present = false;
        return false;
    }

    /* Lux = 0.6 * raw / (gain * int_time_100ms). gain=1, int=1 (100ms) */
    *lux = ltr390_lux_from_raw_1x_18bit(raw);
    return true;
}
