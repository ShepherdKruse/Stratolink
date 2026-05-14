#include "sensors.h"
#include "stratolink_pins.h"
#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "sensor_lis2dh12.h"
#include "sensor_ltr390.h"
#include <Wire.h>

bool sensors_init(void) {
#if defined(PIN_I2C_SDA) && defined(PIN_I2C_SCL) && defined(ARDUINO_ARCH_STM32)
    Wire.setSDA(PIN_I2C_SDA);
    Wire.setSCL(PIN_I2C_SCL);
#endif
    Wire.begin();

    // TMP117 may be absent (DSBGA-6 soldering issues). Do not block
    // MS5611 or LIS2DH12 if it fails — sensor_tmp117 will fall back
    // to the MS5611 internal temperature sensor automatically.
    (void)sensor_tmp117_init();

    bool ok = true;
    if (!sensor_ms5611_init()) ok = false;
    if (!sensor_lis2dh12_init()) ok = false;
    if (!sensor_ltr390_init()) ok = false;
    return ok;
}
