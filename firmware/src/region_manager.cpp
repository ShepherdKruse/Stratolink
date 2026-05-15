#include "region_manager.h"

/* All comparisons use the raw e7 representation so exact-degree
 * boundaries (lat=70°, lon=-30°, etc) decide correctly — dividing by
 * 10⁷ first would truncate toward zero and miss "just past the edge"
 * positions like 70.0001°N or -30.0001°E. */
#define DEG_E7(d) ((int32_t)((d) * 10000000))

lora_region_id_t region_for_latlon(int32_t lat_e7, int32_t lon_e7) {
    /* Polar: above |70°| the only LoRaWAN coverage is Svalbard
     * (a handful of EU868 gateways) — not worth a special case.  Stay
     * silent rather than risk an off-plan emission. */
    if (lat_e7 >  DEG_E7(70))  return LORA_REGION_SILENT;
    if (lat_e7 < -DEG_E7(70))  return LORA_REGION_SILENT;

    /* Far-east Russia + Aleutians sit in the wraparound between +180°
     * and -170°.  Map to AS923 (closest band-compatible plan; the
     * actual RU864/JP920 nuances don't matter without local gateways). */
    if (lon_e7 < -DEG_E7(170)) return LORA_REGION_AS923;

    /* Americas. */
    if (lon_e7 < -DEG_E7(30)) {
        /* TTN's official assignment per country (validated 2026-05):
         *   US, Canada, Mexico, Caribbean, north Colombia/Venezuela:
         *       US915
         *   Brazil, Argentina, Chile, Uruguay, Paraguay, south Bolivia:
         *       AU915
         * Split at lat 12° puts most US915-aligned countries north and
         * AU915-aligned south.  Peru/Bolivia/south-Venezuela are
         * officially US915 but their TTN gateway density is near zero
         * — accept the mis-classification to avoid a per-country
         * lookup table. */
        return (lat_e7 > DEG_E7(12)) ? LORA_REGION_US915 : LORA_REGION_AU915;
    }

    /* Europe / Africa / Middle East / west Russia.  TTN routes
     * everything in this band to its eu1 cluster on EU868 (per TTN
     * docs, South Africa is on EU868 too — NOT AU915). */
    if (lon_e7 < DEG_E7(60)) return LORA_REGION_EU868;

    /* China uses CN470 (470-510 MHz) — totally out of band for the
     * 900 MHz monopole.  Transmitting AS923 / AU915 frequencies inside
     * Chinese borders lands in licensed GSM / mobile spectrum.  Bbox
     * tightened to lat 22-50, lon 73-123 so Hong Kong (22.3°N) and
     * Shanghai (121°E) stay silent while Vietnam (Hanoi 21°N), Korea
     * (Seoul 127°E), and Japan (Osaka 135.5°E) correctly fall through
     * to AS923. */
    if (lat_e7 >= DEG_E7(22) && lat_e7 <= DEG_E7(50) &&
        lon_e7 >= DEG_E7(73) && lon_e7 <= DEG_E7(123)) {
        return LORA_REGION_SILENT;
    }

    /* East-of-+60° splits at ~+10° lat: southern hemisphere = AU915
     * (Australia, NZ).  Indonesia (officially AS923-2 at 921 MHz)
     * straddles this line; AU915 channels overlap AS923-2 spectrum
     * close enough to reach gateways either way. */
    if (lat_e7 < DEG_E7(10) && lon_e7 >= DEG_E7(110)) return LORA_REGION_AU915;

    /* Default east-of-+60° = AS923-1: Japan, SE Asia.  India (IN865
     * at 865 MHz) and Korea (KR920) overlap here imperfectly — we
     * accept marginal coverage there rather than carry two more
     * region tables for sub-1%-of-flight zones. */
    return LORA_REGION_AS923;
}
