#include "region_manager.h"
#include <limits.h>

/* All comparisons use the raw e7 representation so exact-degree
 * boundaries (lat=70°, lon=-30°, etc) decide correctly — dividing by
 * 10⁷ first would truncate toward zero and miss "just past the edge"
 * positions like 70.0001°N or -30.0001°E. */
#define DEG_E7(d) ((int32_t)((d) * 10000000))

lora_region_id_t region_for_latlon(int32_t lat_e7, int32_t lon_e7) {
    /* A corrupt-but-"valid" PVT must never select a transmit plan. */
    if (lat_e7 < -DEG_E7(90) || lat_e7 > DEG_E7(90) ||
        lon_e7 < -DEG_E7(180) || lon_e7 > DEG_E7(180)) {
        return LORA_REGION_SILENT;
    }

    /* Polar: above |70°| the only LoRaWAN coverage is Svalbard
     * (a handful of EU868 gateways) — not worth a special case.  Stay
     * silent rather than risk an off-plan emission. */
    if (lat_e7 >  DEG_E7(70))  return LORA_REGION_SILENT;
    if (lat_e7 < -DEG_E7(70))  return LORA_REGION_SILENT;

    /* Americas.
     *
     * North and Central America use US915 throughout the expected northern
     * circumnavigation corridor.  South America cannot be split safely with a
     * latitude or longitude threshold: neighbouring countries alternate
     * between US915 (for example Peru, Paraguay, Uruguay and Venezuela) and
     * AU915 (for example Brazil, Argentina, Chile and Ecuador).  A coarse
     * geofence previously selected AU915 everywhere at/below 12 N, which was
     * knowingly wrong in several countries.  Stay silent there until the
     * flight image contains reviewed country polygons and credentials for
     * every selected plan. */
    if (lon_e7 < -DEG_E7(30)) {
        return (lat_e7 > DEG_E7(12)) ? LORA_REGION_US915
                                     : LORA_REGION_SILENT;
    }

    /* Russia uses RU864, which is not implemented by this image.  A plain
     * longitude split used to classify western Russia as EU868 and Siberia
     * as AS923.  Both are off-plan.  These deliberately conservative boxes
     * cover mainland Russia, its southern edge, and Kaliningrad; neighbouring
     * unsupported territory may also be silenced at the borders. */
    const bool russian_mainland =
        (lat_e7 >= DEG_E7(55) && lon_e7 >= DEG_E7(27)) ||
        (lat_e7 >= DEG_E7(41) && lon_e7 >= DEG_E7(30));
    const bool kaliningrad =
        lat_e7 >= DEG_E7(54) && lat_e7 <= DEG_E7(56) &&
        lon_e7 >= DEG_E7(19) && lon_e7 <= DEG_E7(23);
    if (russian_mainland || kaliningrad) return LORA_REGION_SILENT;

    /* Europe / Africa / Middle East.  TTN routes everything in this band to
     * its eu1 cluster on EU868 (per TTN docs, South Africa is on EU868 too —
     * NOT AU915).  The RU864 carve-out above must precede this coarse split. */
    if (lon_e7 < DEG_E7(60)) return LORA_REGION_EU868;

    /* India (IN865), central/northern Asia with no substantiated plan in this
     * image, and South Korea (KR920) are not AS923.  Fail closed across the
     * northern flight corridor rather than using a nearby-looking band. */
    if (lat_e7 >= DEG_E7(25) && lat_e7 <= DEG_E7(55) &&
        lon_e7 >= DEG_E7(60) && lon_e7 <= DEG_E7(132)) {
        return LORA_REGION_SILENT;
    }
    if (lat_e7 >= DEG_E7(6) && lat_e7 < DEG_E7(25) &&
        lon_e7 >= DEG_E7(68) && lon_e7 <= DEG_E7(98)) {
        return LORA_REGION_SILENT;
    }

    /* China uses CN470 (470-510 MHz) — totally out of band for the
     * 900 MHz monopole.  Transmitting AS923 / AU915 frequencies inside
     * Chinese borders lands in licensed GSM / mobile spectrum.  Bbox
     * tightened to lat 22-50, lon 73-123 so Hong Kong (22.3°N) and
     * Shanghai (121°E) stay silent while Vietnam (Hanoi 21°N) can reach
     * AS923. Korea and Japan fall through this particular box only to be
     * rejected by their plan-specific checks above/below. */
    if (lat_e7 >= DEG_E7(22) && lat_e7 <= DEG_E7(50) &&
        lon_e7 >= DEG_E7(73) && lon_e7 <= DEG_E7(123)) {
        return LORA_REGION_SILENT;
    }

    /* Japan uses AS923-1 but requires LBT.  LoRa CAD is not equivalent to the
     * required energy-detect LBT, so this image does not claim compliance.
     * South Korea is included in the west edge and is KR920 regardless. */
    if (lat_e7 >= DEG_E7(30) && lat_e7 <= DEG_E7(46) &&
        lon_e7 >= DEG_E7(124) && lon_e7 <= DEG_E7(146)) {
        return LORA_REGION_SILENT;
    }

    /* The Philippines' published plan is not the AS923 plan implemented here,
     * and Papua New Guinea has no substantiated plan in the launch record. */
    if (lat_e7 >= DEG_E7(4) && lat_e7 <= DEG_E7(22) &&
        lon_e7 >= DEG_E7(116) && lon_e7 <= DEG_E7(127)) {
        return LORA_REGION_SILENT;
    }
    if (lat_e7 >= -DEG_E7(11) && lat_e7 <= DEG_E7(0) &&
        lon_e7 >= DEG_E7(140) && lon_e7 <= DEG_E7(160)) {
        return LORA_REGION_SILENT;
    }

    /* Australia and New Zealand use AU915. Indonesia instead belongs to an
     * Asian plan; TTN's current AS_923_925 plan and this device's registered
     * AS_920_923 plan share the 923.2/923.4 MHz default channels implemented
     * by LORA_AS923. Do not sweep it into AU915 by hemisphere. */
    if (lat_e7 <= -DEG_E7(10) && lon_e7 >= DEG_E7(110)) {
        return LORA_REGION_AU915;
    }

    /* Default east-of-+60° = AS923 common channels for supported Southeast
     * Asian plans and the western Pacific. Known incompatible land zones
     * above have already failed closed. */
    return LORA_REGION_AS923;
}

uint32_t region_fix_age_advance(uint32_t age_sec, uint32_t elapsed_sec) {
    if (UINT32_MAX - age_sec < elapsed_sec) return UINT32_MAX;
    return age_sec + elapsed_sec;
}

bool region_fix_age_allows_tx(uint32_t age_sec) {
    /* The lease is expired at the deadline, not one second after it. */
    return age_sec < REGION_FIX_MAX_AGE_SEC;
}

uint32_t region_fix_remaining_tx_ms(uint32_t age_sec) {
    if (age_sec >= REGION_FIX_MAX_AGE_SEC) return 0u;
    uint32_t remaining_sec = REGION_FIX_MAX_AGE_SEC - age_sec;
    if (remaining_sec <= REGION_TX_DEADLINE_GUARD_SEC) return 0u;
    return (remaining_sec - REGION_TX_DEADLINE_GUARD_SEC) * 1000u;
}

uint32_t region_sleep_age_charge_sec(uint32_t nominal_sleep_sec) {
    /* ceil(nominal * configured/min), with 64-bit intermediate so any caller
     * value is safe and a corrupt duration fails closed at UINT32_MAX. */
    uint64_t scaled = (uint64_t)nominal_sleep_sec *
                      (uint64_t)REGION_RTC_CONFIGURED_LSI_HZ;
    scaled += (uint64_t)REGION_RTC_MIN_LSI_HZ - 1u;
    scaled /= (uint64_t)REGION_RTC_MIN_LSI_HZ;
    return scaled > UINT32_MAX ? UINT32_MAX : (uint32_t)scaled;
}
