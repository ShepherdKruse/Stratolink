#include "sensors.h"
#include "stratolink_pins.h"
#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "sensor_lis2dh12.h"
#include "sensor_ltr390.h"
#include <Wire.h>

/* J-Link-readable evidence that the all-sensors-failed containment path ran. */
static volatile uint32_t s_sensor_i2c_bus_recoveries = 0;

static bool init_with_retries(bool (*init_fn)(void)) {
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        if (init_fn()) return true;
        delay(20);
    }
    return false;
}

static void begin_i2c_bus(void) {
#if defined(PIN_I2C_SDA) && defined(PIN_I2C_SCL) && defined(ARDUINO_ARCH_STM32)
    Wire.setSDA(PIN_I2C_SDA);
    Wire.setSCL(PIN_I2C_SCL);
#endif
    Wire.begin();
}

bool sensors_init(void) {
    begin_i2c_bus();

    // TMP117 may be absent (DSBGA-6 soldering issues). Do not block
    // MS5611 or LIS2DH12 if it fails — sensor_tmp117 will fall back
    // to the MS5611 internal temperature sensor automatically.
    (void)init_with_retries(sensor_tmp117_init);

    bool ok = true;
    /* A single cold-boot I2C NACK must not disable a sensor until recovery or
     * end the freefall path for the entire flight. These init routines are
     * idempotent; later per-cycle reads retry or fully reinitialize after
     * transient transport/configuration failures. */
    if (!init_with_retries(sensor_ms5611_init)) ok = false;
    if (!init_with_retries(sensor_lis2dh12_init)) ok = false;
    if (!init_with_retries(sensor_ltr390_init)) ok = false;
    return ok;
}

void sensors_recover_i2c_bus(void) {
    /* STM32duino bounds each transfer at I2C_TIMEOUT_TICK (100 ms), so a
     * stuck slave cannot wedge the watchdog forever.  It does not, however,
     * reset a HAL handle left BUSY after that timeout. Wire.begin() performs
     * the framework's bounded 20-clock bus recovery before reinitializing I2C.
     * Callers bound this to the all-sensors-failed retry and the LTR390's
     * active-state containment paths. */
    s_sensor_i2c_bus_recoveries++;
    Wire.end();
    delay(1);
    begin_i2c_bus();
}
