#ifndef POWER_MANAGER_H
#define POWER_MANAGER_H

#include <stdint.h>
#include <stdbool.h>

void power_manager_init(void);
void power_manager_sleep_ms(uint32_t durationMs);
bool power_manager_is_low_battery(void);

/** Call once after sensors init to allow wake from LIS2DH12 INT1 (PA8) in deep sleep. */
void power_manager_attach_freefall_wakeup(void);

/** Returns true if last wake was from freefall (INT1). Clears the flag. */
bool power_manager_did_wake_from_freefall(void);

#endif
