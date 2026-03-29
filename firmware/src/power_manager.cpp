#include "power_manager.h"
#include "config.h"
#include "stratolink_pins.h"
#include "power_adc.h"
#include <Arduino.h>

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
#include <STM32LowPower.h>
#endif

static bool inited = false;
static volatile bool s_burst_wake = false;

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
static void freefall_wake_callback(void) {
    s_burst_wake = true;
}
#endif

void power_manager_init(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    LowPower.begin();
    inited = true;
#endif
}

void power_manager_attach_freefall_wakeup(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        pinMode(PIN_ACCEL_INT1, INPUT_PULLUP);
        LowPower.attachInterruptWakeup(PIN_ACCEL_INT1, freefall_wake_callback, RISING, DEEP_SLEEP_MODE);
    }
#endif
}

bool power_manager_did_wake_from_freefall(void) {
    bool v = s_burst_wake;
    s_burst_wake = false;
    return v;
}

void power_manager_sleep_ms(uint32_t durationMs) {
    if (durationMs == 0) return;

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        LowPower.deepSleep(durationMs);
        return;
    }
#endif
    delay(durationMs);
}

bool power_manager_is_low_battery(void) {
    return power_adc_get_tier() == POWER_TIER_CRITICAL;
}
