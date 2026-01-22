#ifndef REGION_MANAGER_H
#define REGION_MANAGER_H

#include <Arduino.h>

class RegionManager {
public:
    static void init();
    static void setRegion(uint8_t region);
    static uint8_t getRegion();
};

#endif // REGION_MANAGER_H
