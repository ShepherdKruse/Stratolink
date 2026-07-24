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

/** Non-consuming peek at the freefall wake flag, for long-running windows
 *  (relay) that must yield promptly without eating the flag main.cpp
 *  consumes at the top of the cycle. */
bool power_manager_freefall_pending(void);

/** Chatter latch: while on, INT1 wakes are swallowed inside sleep instead
 *  of aborting the chunk loop, so a stuck/chattering pin cannot collapse
 *  the TX cadence.  Driven by main.cpp's accel-confirmed spurious-wake
 *  streak (3 spurious to latch, 16 clean scheduled wakes to re-arm). */
void power_manager_suppress_freefall_wake(bool on);

/** Refresh the independent watchdog. Must be called at least every ~33 s
 *  or the chip will reboot. IWDG keeps running in Stop on this chip
 *  (FLASH IWDG_STOP option bit = 1), so long sleeps are chunked with a
 *  refresh between chunks. */
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
