#include "region_manager.h"

lora_region_id_t region_for_latlon(int32_t lat_e7, int32_t lon_e7) {
    /* Integer-degree comparisons are sufficient (boundaries are coarse
     * and GPS jitter is < 0.001° at altitude). */
    int32_t lat = lat_e7 / 10000000;
    int32_t lon = lon_e7 / 10000000;

    /* Polar regions: above ~70° lat the only LoRaWAN coverage is in
     * Svalbard (a handful of EU868 gateways) — not worth the special
     * case.  Stay silent rather than risk an off-plan emission. */
    if (lat > 70 || lat < -70) return LORA_REGION_SILENT;

    /* Far-east Russia + Aleutians sit in the wraparound between +180°
     * and -170°.  Map to AS923 (closest band-compatible plan; the
     * actual RU864/JP920 nuances don't matter without local gateways). */
    if (lon < -170) return LORA_REGION_AS923;

    /* Main longitude bands. */
    if (lon < -30)  return LORA_REGION_US915;  /* Americas */
    if (lon <  60)  return LORA_REGION_EU868;  /* Europe / Africa / Middle East */

    /* East of +60° splits at the equator: southern hemisphere uses AU915
     * (Australia/NZ), northern hemisphere uses AS923 (Japan, SE Asia).
     * Australia/NZ are the only places with reliable TTN coverage in
     * this whole band, so favour AU915 down to ~+10° latitude as well —
     * captures Indonesia/Papua New Guinea, where AS923-2 nominally
     * applies but TTN coverage is sparse. */
    if (lat < 10 && lon >= 110) return LORA_REGION_AU915;
    return LORA_REGION_AS923;
}
