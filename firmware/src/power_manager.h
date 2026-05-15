#ifndef POWER_MANAGER_H
#define POWER_MANAGER_H

#include <stdint.h>
#include <stdbool.h>
#include "lorawan.h"   /* for lorawan_session_t */

void power_manager_init(void);
void power_manager_sleep_ms(uint32_t durationMs);
bool power_manager_is_low_battery(void);

/** Call once after sensors init to allow wake from LIS2DH12 INT1 (PA8) in deep sleep. */
void power_manager_attach_freefall_wakeup(void);

/** Returns true if last wake was from freefall (INT1). Clears the flag. */
bool power_manager_did_wake_from_freefall(void);

/** Refresh the independent watchdog. Must be called at least every ~33 s
 *  while in run mode or the chip will reboot. IWDG is frozen in STOP. */
void power_manager_kick_watchdog(void);

/**
 * LoRaWAN session persistence via STM32WL TAMP backup registers.
 * The 32× 32-bit TAMP_BKPxR survive software reset, STOP1/STOP2, and
 * standby as long as VDD is present — which is the same lifetime as
 * the supercap.  Lost on a deep brown-out (VSTOR < BQ25570 cold-start
 * threshold ~1.8 V), which is the same point at which the MCU itself
 * dies, so the lifetime is consistent.
 *
 * Save after every successful join and every successful uplink (the
 * latter to persist fCntUp — LoRaWAN servers reject any repeated FCnt
 * as a replay).  Load on cold boot before attempting a join; if the
 * stored session is valid, skip the join entirely.
 */
bool power_manager_load_session(lorawan_session_t* s);
void power_manager_save_session(const lorawan_session_t* s);
void power_manager_clear_session(void);

#endif
