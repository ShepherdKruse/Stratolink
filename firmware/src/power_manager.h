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

/** Refresh the independent watchdog. Must be called within 30.84 s at the
 *  datasheet-maximum LSI frequency (32.768 s typical) or the chip reboots.
 *  IWDG keeps running in Stop on this chip
 *  (FLASH IWDG_STOP option bit = 1), so long sleeps are chunked with a
 *  refresh between chunks. */
void power_manager_kick_watchdog(void);

/**
 * Return a coarse monotonic mission clock in seconds. On flight hardware this
 * is the LSI-backed RTC, which continues through STOP1; the epoch itself is
 * arbitrary and callers must use unsigned differences only.
 */
uint32_t power_manager_monotonic_seconds(void);

/**
 * LoRaWAN session persistence via STM32WL TAMP backup registers.
 * The STM32WLE5's 20 x 32-bit TAMP_BKPxR survive software reset, STOP1/STOP2, and
 * standby as long as VDD is present — which is the same lifetime as
 * the supercap.  Lost on a deep brown-out (VSTOR < BQ25570 cold-start
 * threshold ~1.8 V), which is the same point at which the MCU itself
 * dies, so the lifetime is consistent.
 *
 * Save after every successful join. The uplink path reserves and saves the
 * next fCntUp before RF, because LoRaWAN servers tolerate skipped counters but
 * reject a repeated counter after reset as a replay. Load on cold boot before
 * attempting a join; if the stored session is valid, skip the join entirely.
 */
bool power_manager_load_session(lorawan_session_t* s);
/** Atomically save and read back the complete retained session. Returns false
 *  if backup-domain access or any word/CRC/commit-marker write did not stick. */
bool power_manager_save_session(const lorawan_session_t* s);
/** Invalidate retained session and region lease with bounded retries/readback. */
bool power_manager_clear_session(void);

/**
 * Persist the age of the GNSS-backed RF-region decision independently from
 * the LoRaWAN session. A packed tag, age, and complemented check reject
 * missing or bit-corrupted state. This prevents a watchdog/software reset from
 * renewing an already-stale region lease merely because the old session
 * survived.
 */
bool power_manager_load_region_lease(uint32_t* age_sec);
/** Commit the packed lease record and read back/decode the complete word. */
bool power_manager_save_region_lease(uint32_t age_sec);

/**
 * Increment and return a packed retained boot counter in TAMP_BKP19R.
 * This word is outside the session record. The counter survives reset and
 * STOP while VDD is present and reinitializes after a true backup-domain loss.
 */
uint32_t power_manager_record_boot(void);

/**
 * Retain the next balloon-to-balloon origin message ID across watchdog,
 * software, and warm brownout resets. The packed TAMP word includes the byte
 * and its complement; load fails closed on missing or corrupt state.
 */
bool power_manager_load_b2b_msg_id(uint8_t* next_id);
bool power_manager_save_b2b_msg_id(uint8_t next_id);

/**
 * Retain the last applied application-command sequence across watchdog,
 * software, and warm-brownout resets. Save is a durable reservation: command
 * dispatch must fail closed unless the value reads back exactly.
 */
bool power_manager_load_command_state(uint8_t* sequence, bool* relay_enabled);
bool power_manager_save_command_state(uint8_t sequence, bool relay_enabled);

#endif
