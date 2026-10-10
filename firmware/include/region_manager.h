#ifndef REGION_MANAGER_H
#define REGION_MANAGER_H

#include <stdint.h>
#include <stdbool.h>
#include "lorawan.h"  /* for lora_region_id_t */

/* A frequency-plan decision must not live forever after GNSS goes stale.
 * Thirty minutes bounds travel to ~150 km even at an extreme 300 km/h while
 * still tolerating several ordinary no-fix cycles. */
#define REGION_FIX_MAX_AGE_SEC 1800u
/* Leave one complete whole-second guard between the end of any long auxiliary
 * TX window and lease expiry. The relay itself additionally reserves packet
 * airtime plus a 100 ms close guard before its caller-owned deadline. */
#define REGION_TX_DEADLINE_GUARD_SEC 1u

/* A reset can interrupt a cycle before its measured active time is committed.
 * Reserve five minutes from every retained lease immediately after the IWDG
 * is armed and before any external-peripheral initialization. This exceeds a
 * complete bounded setup/active exchange, makes repeated resets age the lease
 * rather than freeze it, and is intentionally conservative: a fresh PVT
 * replaces the charged age with zero. */
#define REGION_RESET_UNACCOUNTED_CHARGE_SEC 300u
static_assert(REGION_RESET_UNACCOUNTED_CHARGE_SEC > 0u &&
              REGION_RESET_UNACCOUNTED_CHARGE_SEC < REGION_FIX_MAX_AGE_SEC,
              "reset lease charge must be positive and fail closed before expiry");

/* STM32WLE5 LSI is 32 kHz nominal but only guaranteed down to 29.5 kHz over
 * the full voltage/temperature range. The RTC prescalers are configured for
 * 32 kHz, so a requested STOP interval can take 32/29.5 times as long in real
 * wall time. Retained RF authorization must charge that worst case. */
#define REGION_RTC_CONFIGURED_LSI_HZ 32000u
#define REGION_RTC_MIN_LSI_HZ        29500u

/**
 * Map (lat_e7, lon_e7) → LoRaWAN regional frequency plan.
 *
 * Conservative geofence for the four plans implemented by this image:
 *   North/Central Americas (lon −180°..−30°, lat > 12°): US915
 *   EU/Africa/ME (lon −30°..+60°): EU868
 *   substantiated Southeast Asia / west Pacific: AS923 common channels
 *   Australia/NZ: AU915
 *   Polar (|lat| > 70°): SILENT — no TTN coverage anyway
 *
 * Known incompatible, mixed-plan, or unimplemented zones fail closed:
 * South America, CN470, IN865, KR920, Japan's LBT-constrained AS923
 * operation, RU864 Russia, the Philippines, PNG, and the unsupported
 * central/northern Asia corridor.
 *
 * This is an RF safety control, not a legal opinion. Country boundaries and
 * airborne operation still require a launch-specific regulatory review.
 */
lora_region_id_t region_for_latlon(int32_t lat_e7, int32_t lon_e7);

/** Saturating age accumulator used across long sleeps and burst cycles. */
uint32_t region_fix_age_advance(uint32_t age_sec, uint32_t elapsed_sec);

/** True strictly before the GNSS-backed frequency-plan lease deadline. */
bool region_fix_age_allows_tx(uint32_t age_sec);

/**
 * Safe duration for a long transmitting service opened at the supplied
 * conservative whole-second age. Returns zero at/near expiry and leaves the
 * guard above for call/setup latency. Every TX path also demands a nonzero
 * result so its final sub-second frame cannot start on the expiry second.
 */
uint32_t region_fix_remaining_tx_ms(uint32_t age_sec);

/**
 * Convert a nominal RTC-backed STOP duration to a conservative real-wall-time
 * lease charge using the STM32WLE5 datasheet minimum LSI frequency. Saturates
 * on overflow. This is intentionally separate from ordinary awake time,
 * which is measured by the run clock through millis().
 */
uint32_t region_sleep_age_charge_sec(uint32_t nominal_sleep_sec);

#endif /* REGION_MANAGER_H */
