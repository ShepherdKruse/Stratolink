#ifndef POWER_MANAGER_H
#define POWER_MANAGER_H

#include <Arduino.h>

class PowerManager {
public:
    static void init();
    static void enterSleepMode(uint32_t durationMs);
    static void wakeFromSleep();
    static bool isLowBattery();
};

#endif // POWER_MANAGER_H
