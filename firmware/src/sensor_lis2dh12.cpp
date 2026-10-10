#include "sensor_lis2dh12.h"
#include "lis2dh12_conversion.h"
#include "stratolink_pins.h"
#include <Wire.h>

#define LIS2DH12_REG_CTRL1    0x20
#define LIS2DH12_REG_CTRL2    0x21
#define LIS2DH12_REG_CTRL3    0x22
#define LIS2DH12_REG_CTRL4    0x23
#define LIS2DH12_REG_CTRL5    0x24
#define LIS2DH12_REG_WHO_AM_I 0x0F
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
#define LIS2DH12_CTRL4_BDU    (1 << 7)
#define LIS2DH12_WHO_AM_I_VAL 0x33
/* INT1_CFG bits. AOI (bit 7) MUST be set for true freefall: it means
 * "AND of the per-axis low-events" — INT1 fires only when |X|<T AND
 * |Y|<T AND |Z|<T (i.e. the device is genuinely weightless on all
 * three axes).  Leaving AOI=0 yields OR logic, which fires whenever
 * ANY axis is below threshold — i.e. continuously while the board
 * sits flat (|X|≈0, |Y|≈0) or hangs upright (one horizontal axis ≈0).
 * That bug burst-modes the chip constantly during rest. */
#define LIS2DH12_INT1_CFG_AOI  (1 << 7)
#define LIS2DH12_INT1_CFG_XLIE (1 << 0)
#define LIS2DH12_INT1_CFG_YLIE (1 << 2)
#define LIS2DH12_INT1_CFG_ZLIE (1 << 4)

static uint8_t i2c_addr = I2C_ADDR_ACCEL;
static bool freefall_configured = false;
/* J-Link-readable: post-boot full configuration repairs. */
static volatile uint32_t s_lis2dh12_reconfig_attempts = 0;

static bool read_reg(uint8_t reg, uint8_t* value) {
    if (!value) return false;
    Wire.beginTransmission(i2c_addr);
    Wire.write(reg);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 1) != 1) return false;
    *value = (uint8_t)Wire.read();
    return true;
}

static bool freefall_config_matches(void) {
    uint8_t who = 0;
    uint8_t ctrl1 = 0;
    uint8_t ctrl2 = 0;
    uint8_t ctrl3 = 0;
    uint8_t ctrl4 = 0;
    uint8_t ctrl5 = 0;
    uint8_t threshold = 0;
    uint8_t duration = 0;
    uint8_t config = 0;
    return read_reg(LIS2DH12_REG_WHO_AM_I, &who) &&
           read_reg(LIS2DH12_REG_CTRL1, &ctrl1) &&
           read_reg(LIS2DH12_REG_CTRL2, &ctrl2) &&
           read_reg(LIS2DH12_REG_CTRL3, &ctrl3) &&
           read_reg(LIS2DH12_REG_CTRL4, &ctrl4) &&
           read_reg(LIS2DH12_REG_CTRL5, &ctrl5) &&
           read_reg(LIS2DH12_REG_INT1_THS, &threshold) &&
           read_reg(LIS2DH12_REG_INT1_DUR, &duration) &&
           read_reg(LIS2DH12_REG_INT1_CFG, &config) &&
           who == LIS2DH12_WHO_AM_I_VAL &&
           ctrl1 == (LIS2DH12_CTRL1_ODR_100HZ | LIS2DH12_CTRL1_LPEN |
                     LIS2DH12_CTRL1_XEN | LIS2DH12_CTRL1_YEN |
                     LIS2DH12_CTRL1_ZEN) &&
           ctrl2 == 0 &&
           ctrl3 == LIS2DH12_CTRL3_I1_IA1 &&
           ctrl4 == LIS2DH12_CTRL4_BDU &&
           ctrl5 == 0 &&
           threshold == (uint8_t)ACCEL_FREEFALL_THRESHOLD &&
           duration == (uint8_t)ACCEL_FREEFALL_DURATION &&
           config == (LIS2DH12_INT1_CFG_AOI |
                      LIS2DH12_INT1_CFG_XLIE |
                      LIS2DH12_INT1_CFG_YLIE |
                      LIS2DH12_INT1_CFG_ZLIE);
}

bool sensor_lis2dh12_init(void) {
    freefall_configured = false;
    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL1);
    Wire.write(LIS2DH12_CTRL1_ODR_1HZ | LIS2DH12_CTRL1_LPEN | LIS2DH12_CTRL1_XEN | LIS2DH12_CTRL1_YEN | LIS2DH12_CTRL1_ZEN);
    return Wire.endTransmission() == 0;
}

bool sensor_lis2dh12_read_accel_cm_s2(int16_t* ax, int16_t* ay, int16_t* az) {
    if (!ax || !ay || !az) return false;
    /* Verify, not merely assume, that a late sensor brownout did not return
     * the part to power-down defaults. Otherwise I2C can succeed while all
     * acceleration registers remain plausible-looking zeros and freefall
     * wake is silently disabled. */
    if (!freefall_configured || !freefall_config_matches()) {
        freefall_configured = false;
        s_lis2dh12_reconfig_attempts++;
        if (!sensor_lis2dh12_enable_freefall_int1()) return false;
    }

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_OUT_X_L | 0x80);
    if (Wire.endTransmission() != 0) {
        freefall_configured = false;
        return false;
    }
    if (Wire.requestFrom((int)i2c_addr, 6) != 6) {
        freefall_configured = false;
        return false;
    }

    /* Low-power mode is 8-bit, left-justified in each 16-bit output pair. */
    (void)Wire.read();
    int8_t x = (int8_t)Wire.read();
    (void)Wire.read();
    int8_t y = (int8_t)Wire.read();
    (void)Wire.read();
    int8_t z = (int8_t)Wire.read();

    *ax = lis2dh12_low_power_to_cm_s2(x);
    *ay = lis2dh12_low_power_to_cm_s2(y);
    *az = lis2dh12_low_power_to_cm_s2(z);
    return true;
}

bool sensor_lis2dh12_enable_freefall_int1(void) {
    freefall_configured = false;
    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL1);
    Wire.write(LIS2DH12_CTRL1_ODR_100HZ | LIS2DH12_CTRL1_LPEN | LIS2DH12_CTRL1_XEN | LIS2DH12_CTRL1_YEN | LIS2DH12_CTRL1_ZEN);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL2);
    Wire.write(0x00);  /* high-pass filter disabled */
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL3);
    Wire.write(LIS2DH12_CTRL3_I1_IA1);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL4);
    /* BDU prevents a 100 Hz update from splitting the six-byte XYZ sample.
     * FS=00 keeps +/-2 g and HR=0 is required with CTRL1.LPEN=1. */
    Wire.write(LIS2DH12_CTRL4_BDU);
    if (Wire.endTransmission() != 0) return false;

    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_CTRL5);
    /* Keep INT1 non-latched: the rising edge wakes STOP1 and the main loop
     * validates current acceleration. A latched source would require an
     * unconditional INT1_SRC read on every wake to avoid a stuck-high pin. */
    Wire.write(0x00);
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
    Wire.write(LIS2DH12_INT1_CFG_AOI
             | LIS2DH12_INT1_CFG_XLIE
             | LIS2DH12_INT1_CFG_YLIE
             | LIS2DH12_INT1_CFG_ZLIE);
    if (Wire.endTransmission() != 0) return false;
    freefall_configured = freefall_config_matches();
    return freefall_configured;
}

bool sensor_lis2dh12_clear_and_read_int1_src(void) {
    if (!freefall_configured || !freefall_config_matches()) {
        freefall_configured = false;
        s_lis2dh12_reconfig_attempts++;
        if (!sensor_lis2dh12_enable_freefall_int1()) return false;
    }
    Wire.beginTransmission(i2c_addr);
    Wire.write(LIS2DH12_REG_INT1_SRC);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((int)i2c_addr, 1) != 1) return false;
    return lis2dh12_int1_active((uint8_t)Wire.read());
}

bool sensor_lis2dh12_get_freefall_cleared(bool* cleared) {
    if (!cleared) return false;
    int16_t ax, ay, az;
    if (!sensor_lis2dh12_read_accel_cm_s2(&ax, &ay, &az)) return false;
    int32_t mag_sq = (int32_t)ax * ax + (int32_t)ay * ay + (int32_t)az * az;
    *cleared = mag_sq >= 240000L;
    return true;
}

bool sensor_lis2dh12_is_freefall_cleared(void) {
    bool cleared = false;
    bool sample_ok = sensor_lis2dh12_get_freefall_cleared(&cleared);
    return lis2dh12_freefall_is_cleared(sample_ok, cleared);
}
