#ifndef REGION_MANAGER_H
#define REGION_MANAGER_H

#include <stdint.h>
#include "lorawan.h"  /* for lora_region_id_t */

/**
 * Map (lat_e7, lon_e7) → LoRaWAN regional frequency plan.
 *
 * Longitude-band geofence.  Boundaries are approximate but cover the
 * regulator zones a jet-stream circumnavigation crosses:
 *   Americas  (lon −170°..−30°): US915
 *   EU/Africa/ME (lon −30°..+60°): EU868
 *   Asia (lon +60°..+180° and lat ≥ 0°): AS923
 *   Australasia (lon +60°..+180° and lat < 0°): AU915
 *   Polar (|lat| > 70°): SILENT — no TTN coverage anyway
 *
 * IN865 (India) and KR920 (Korea) overlap our AS923 zone — we transmit
 * on AS923 frequencies (~923 MHz) which is off-plan in both countries
 * but practically silent (~zero TTN gateways).  CN470 is out of band
 * for the 83 mm monopole; we never enter China cleanly.
 *
 * The geofence is intentionally coarse: at jet-stream speed (~150 km/h)
 * the balloon covers ~1° longitude every 6 min, so the worst-case
 * "wrong region for one cycle at the boundary" is one 5-minute uplink
 * that either reaches a foreign gateway (rare) or goes into the air.
 */
lora_region_id_t region_for_latlon(int32_t lat_e7, int32_t lon_e7);

#endif /* REGION_MANAGER_H */
