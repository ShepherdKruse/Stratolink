#include "sensors.h"
#include "board.h"
#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "sensor_lis2dh12.h"
#include <Wire.h>

bool sensors_init(void) {
#if defined(PIN_I2C_SDA) && defined(PIN_I2C_SCL) && defined(ARDUINO_ARCH_STM32)
    Wire.setSDA(PIN_I2C_SDA);
    Wire.setSCL(PIN_I2C_SCL);
#endif
    Wire.begin();

    if (!sensor_tmp117_init()) return false;
    if (!sensor_ms5611_init()) return false;
    if (!sensor_lis2dh12_init()) return false;
    return true;
}
