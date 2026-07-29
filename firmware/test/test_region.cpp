/* Host-compilable stress test for region_for_latlon().
 *
 * Build:   g++ -std=c++17 -Wall -I ../include test/test_region.cpp \
 *              src/region_manager.cpp -o /tmp/test_region
 * Run:     /tmp/test_region
 *
 * Covers: every implemented regional plan, every coarse longitude
 * boundary, every special-case carve-out (unsupported Asia, polar,
 * wraparound), and a stress sweep along a typical jet-stream parallel.
 * Exits 0 on all-pass, 1 on any fail.
 *
 * The geofence is intentionally conservative — see region_manager.cpp.
 */
#include "region_manager.h"
#include <cstdio>
#include <cstdint>
#include <cstring>

#define E7(d) ((int32_t)((d) * 10000000))

struct TC {
    const char*       name;
    int32_t           lat_e7;
    int32_t           lon_e7;
    lora_region_id_t  expected;
};

static const char* region_name(lora_region_id_t r) {
    switch (r) {
        case LORA_REGION_US915:  return "US915";
        case LORA_REGION_EU868:  return "EU868";
        case LORA_REGION_AS923:  return "AS923";
        case LORA_REGION_AU915:  return "AU915";
        case LORA_REGION_SILENT: return "SILENT";
        default:                 return "??";
    }
}

static const TC CASES[] = {
    /* === US915 (North America + Caribbean + north S.A.) === */
    { "New York City",          E7(40.71),  E7(-74.0),   LORA_REGION_US915 },
    { "Chicago",                E7(41.88),  E7(-87.63),  LORA_REGION_US915 },
    { "Los Angeles",            E7(34.05),  E7(-118.24), LORA_REGION_US915 },
    { "Mexico City",            E7(19.43),  E7(-99.13),  LORA_REGION_US915 },
    { "Miami",                  E7(25.76),  E7(-80.19),  LORA_REGION_US915 },
    { "Havana (Cuba)",          E7(23.13),  E7(-82.39),  LORA_REGION_US915 },
    { "Honolulu",               E7(21.31),  E7(-157.86), LORA_REGION_US915 },
    { "Anchorage",              E7(61.22),  E7(-149.90), LORA_REGION_US915 },
    { "Vancouver",              E7(49.28),  E7(-123.12), LORA_REGION_US915 },
    { "Caracas (Venezuela)",    E7(10.48),  E7(-66.90),  LORA_REGION_SILENT },

    /* === Mixed-plan South America: fail closed without country polygons === */
    { "Sao Paulo",              E7(-23.55), E7(-46.63),  LORA_REGION_SILENT },
    { "Rio de Janeiro",         E7(-22.91), E7(-43.17),  LORA_REGION_SILENT },
    { "Buenos Aires",           E7(-34.61), E7(-58.38),  LORA_REGION_SILENT },
    { "Santiago Chile",         E7(-33.45), E7(-70.67),  LORA_REGION_SILENT },
    { "Lima Peru",              E7(-12.05), E7(-77.04),  LORA_REGION_SILENT },
    { "Bogota (north of 12)",   E7(15.0),   E7(-72.0),   LORA_REGION_US915 },
    /* ^^ above lat 12 = US915 ✓ */
    { "N. Brazil (Roraima)",    E7(5.0),    E7(-60.0),   LORA_REGION_SILENT },
    { "Sydney",                 E7(-33.87), E7(151.21),  LORA_REGION_AU915 },
    { "Melbourne",              E7(-37.81), E7(144.96),  LORA_REGION_AU915 },
    { "Auckland NZ",            E7(-36.85), E7(174.76),  LORA_REGION_AU915 },
    { "Bali (AS923-2)",         E7(-8.65),  E7(115.22),  LORA_REGION_AS923 },

    /* === EU868 (Europe + Africa + Middle East) === */
    { "London",                 E7(51.51),  E7(-0.13),   LORA_REGION_EU868 },
    { "Paris",                  E7(48.86),  E7(2.35),    LORA_REGION_EU868 },
    { "Berlin",                 E7(52.52),  E7(13.41),   LORA_REGION_EU868 },
    { "Reykjavik",              E7(64.13),  E7(-21.94),  LORA_REGION_EU868 },
    { "Cairo",                  E7(30.04),  E7(31.24),   LORA_REGION_EU868 },
    { "Nairobi",                E7(-1.29),  E7(36.82),   LORA_REGION_EU868 },
    { "Johannesburg",           E7(-26.20), E7(28.04),   LORA_REGION_EU868 },
    { "Cape Town",              E7(-33.92), E7(18.42),   LORA_REGION_EU868 },
    { "Warsaw",                 E7(52.23),  E7(21.01),   LORA_REGION_EU868 },
    { "Helsinki",               E7(60.17),  E7(24.94),   LORA_REGION_EU868 },
    { "Bucharest",              E7(44.43),  E7(26.10),   LORA_REGION_EU868 },
    { "Istanbul",               E7(41.01),  E7(28.98),   LORA_REGION_EU868 },
    { "Tehran",                 E7(35.69),  E7(51.39),   LORA_REGION_EU868 },

    /* === AS923 (Japan + SE Asia) === */
    { "Singapore",              E7(1.35),   E7(103.82),  LORA_REGION_AS923 },
    { "Bangkok",                E7(13.75),  E7(100.50),  LORA_REGION_AS923 },
    { "Hanoi",                  E7(21.03),  E7(105.85),  LORA_REGION_AS923 },
    { "Jakarta (lon<110)",      E7(-6.21),  E7(106.85),  LORA_REGION_AS923 },

    /* === SILENT (unimplemented/incompatible plans + polar) === */
    { "Tokyo (LBT required)",   E7(35.68),  E7(139.69),  LORA_REGION_SILENT },
    { "Osaka (LBT required)",   E7(34.69),  E7(135.50),  LORA_REGION_SILENT },
    { "Seoul (KR920)",          E7(37.57),  E7(126.98),  LORA_REGION_SILENT },
    { "Mumbai (IN865)",         E7(19.08),  E7(72.88),   LORA_REGION_SILENT },
    { "Manila (unsupported)",   E7(14.60),  E7(120.98),  LORA_REGION_SILENT },
    { "Port Moresby PNG",       E7(-9.44),  E7(147.18),  LORA_REGION_SILENT },
    { "Beijing",                E7(39.90),  E7(116.40),  LORA_REGION_SILENT },
    { "Shanghai",               E7(31.23),  E7(121.47),  LORA_REGION_SILENT },
    { "Hong Kong",              E7(22.30),  E7(114.17),  LORA_REGION_SILENT },
    { "Taipei (in CN bbox)",    E7(25.03),  E7(121.57),  LORA_REGION_SILENT },
    { "Urumqi (West China)",    E7(43.83),  E7(87.61),   LORA_REGION_SILENT },
    { "Moscow (RU864)",         E7(55.75),  E7(37.62),   LORA_REGION_SILENT },
    { "St Petersburg (RU864)",  E7(59.93),  E7(30.34),   LORA_REGION_SILENT },
    { "Kaliningrad (RU864)",    E7(54.71),  E7(20.51),   LORA_REGION_SILENT },
    { "Sochi (RU864)",          E7(43.60),  E7(39.73),   LORA_REGION_SILENT },
    { "Yekaterinburg (RU864)",  E7(56.84),  E7(60.61),   LORA_REGION_SILENT },
    { "Novosibirsk (RU864)",    E7(55.03),  E7(82.92),   LORA_REGION_SILENT },
    { "Yakutsk (RU864)",        E7(62.03),  E7(129.73),  LORA_REGION_SILENT },
    { "Vladivostok (RU864)",    E7(43.12),  E7(131.89),  LORA_REGION_SILENT },
    { "North Pole",             E7(85.0),   E7(0.0),     LORA_REGION_SILENT },
    { "Svalbard 78N",           E7(78.0),   E7(15.0),    LORA_REGION_SILENT },
    { "McMurdo Antarctica",     E7(-77.85), E7(166.67),  LORA_REGION_SILENT },

    /* === Boundary cases (exact lon/lat values) === */
    { "Atlantic boundary -30",  E7(35.0),   E7(-30.0),   LORA_REGION_EU868 },  /* lon<-30 false */
    { "Atlantic just W of -30", E7(35.0),   E7(-30.0001),LORA_REGION_US915 },
    { "Atlantic just E of -30", E7(35.0),   E7(-29.9999),LORA_REGION_EU868 },
    { "Iran boundary lon 60",   E7(30.0),   E7(60.0),    LORA_REGION_SILENT },
    { "Just W of 60",           E7(30.0),   E7(59.9999), LORA_REGION_EU868 },
    { "Polar boundary +70",     E7(70.0),   E7(0.0),     LORA_REGION_EU868 },  /* lat>70 false */
    { "Just N of +70",          E7(70.0001),E7(0.0),     LORA_REGION_SILENT },
    { "Polar boundary -70",     E7(-70.0),  E7(0.0),     LORA_REGION_EU868 },  /* lat<-70 false */
    { "Just S of -70",          E7(-70.0001),E7(0.0),    LORA_REGION_SILENT },
    { "Date line -170",         E7(40.0),   E7(-170.0),  LORA_REGION_US915 },  /* lon<-170 false */
    { "Date line wraparound",   E7(40.0),   E7(-170.0001),LORA_REGION_US915 },
    { "Americas lat-12 line",   E7(12.0),   E7(-60.0),   LORA_REGION_SILENT }, /* lat>12 false */
    { "Just N of 12",           E7(12.0001),E7(-60.0),   LORA_REGION_US915 },
    { "China bbox west edge",   E7(40.0),   E7(73.0),    LORA_REGION_SILENT },
    { "China bbox just west",   E7(40.0),   E7(72.9999), LORA_REGION_SILENT },
    { "China bbox east edge",   E7(40.0),   E7(123.0),   LORA_REGION_SILENT },
    { "China bbox just east",   E7(40.0),   E7(123.0001),LORA_REGION_SILENT },
    { "China bbox north edge",  E7(50.0),   E7(110.0),   LORA_REGION_SILENT },
    { "China bbox just north",  E7(50.0001),E7(110.0),   LORA_REGION_SILENT },
    { "China bbox south edge",  E7(22.0),   E7(110.0),   LORA_REGION_SILENT },
    { "China bbox just south",  E7(21.9999),E7(110.0),   LORA_REGION_AS923 },
    { "AU lon boundary 110",    E7(-5.0),   E7(110.0),   LORA_REGION_AS923 },
    { "AU just W of 110",       E7(-5.0),   E7(109.9999),LORA_REGION_AS923 },
    { "Philippines carve-out",  E7(10.0),   E7(120.0),   LORA_REGION_SILENT },
    { "AU just S of 10",        E7(9.9999), E7(120.0),   LORA_REGION_SILENT },

    /* === Jet-stream circumnav sweep at lat 40°N === */
    { "Jet 40N -160 (Pacific)", E7(40),     E7(-160),    LORA_REGION_US915 },
    { "Jet 40N -120 (US W)",    E7(40),     E7(-120),    LORA_REGION_US915 },
    { "Jet 40N -70 (US E)",     E7(40),     E7(-70),     LORA_REGION_US915 },
    { "Jet 40N -50 (Atl mid)",  E7(40),     E7(-50),     LORA_REGION_US915 },
    { "Jet 40N -10 (W EU)",     E7(40),     E7(-10),     LORA_REGION_EU868 },
    { "Jet 40N 20 (EU)",        E7(40),     E7(20),      LORA_REGION_EU868 },
    { "Jet 40N 50 (Caspian)",   E7(40),     E7(50),      LORA_REGION_EU868 },
    { "Jet 40N 75 (Kyrgyzstan)",E7(40),     E7(75),      LORA_REGION_SILENT },  /* in CN bbox */
    { "Jet 40N 110 (Mongolia)", E7(40),     E7(110),     LORA_REGION_SILENT },
    { "Jet 40N 140 (Japan)",    E7(40),     E7(140),     LORA_REGION_SILENT },
    { "Jet 40N 170 (Pacific)",  E7(40),     E7(170),     LORA_REGION_AS923 },

    /* === Jet-stream sweep at lat 30°S (typical southern hem track) === */
    { "Jet -30S -70 (Chile)",   E7(-30),    E7(-70),     LORA_REGION_SILENT },
    { "Jet -30S -50 (Argentina)",E7(-30),   E7(-50),     LORA_REGION_SILENT },
    { "Jet -30S 20 (S Africa)", E7(-30),    E7(20),      LORA_REGION_EU868 },
    { "Jet -30S 130 (Australia)",E7(-30),   E7(130),     LORA_REGION_AU915 },
    { "Jet -30S 175 (NZ E)",    E7(-30),    E7(175),     LORA_REGION_AU915 },

    /* === Corrupt coordinate fail-closed === */
    { "Invalid latitude north", E7(90.0001),E7(0),         LORA_REGION_SILENT },
    { "Invalid latitude south", E7(-90.0001),E7(0),        LORA_REGION_SILENT },
    { "Invalid longitude east", E7(0),      E7(180.0001),  LORA_REGION_SILENT },
    { "Invalid longitude west", E7(0),      E7(-180.0001), LORA_REGION_SILENT },
};

int main(void) {
    int pass = 0, fail = 0;
    for (size_t i = 0; i < sizeof(CASES)/sizeof(CASES[0]); i++) {
        const TC& tc = CASES[i];
        lora_region_id_t got = region_for_latlon(tc.lat_e7, tc.lon_e7);
        bool ok = (got == tc.expected);
        std::printf("[%s] %-28s lat=%+7.2f lon=%+8.2f  exp=%-7s got=%-7s\n",
                    ok ? "PASS" : "FAIL", tc.name,
                    (double)tc.lat_e7 / 1e7, (double)tc.lon_e7 / 1e7,
                    region_name(tc.expected), region_name(got));
        if (ok) pass++; else fail++;
    }
    std::printf("\n=== %d passed, %d failed (%zu total) ===\n",
                pass, fail, sizeof(CASES)/sizeof(CASES[0]));

    struct AgeCase {
        uint32_t age;
        uint32_t elapsed;
        uint32_t expected;
        bool tx_expected;
    };
    static const AgeCase AGE_CASES[] = {
        { 0u, 0u, 0u, true },
        { 0u, REGION_FIX_MAX_AGE_SEC - 1u,
          REGION_FIX_MAX_AGE_SEC - 1u, true },
        { 0u, REGION_FIX_MAX_AGE_SEC, REGION_FIX_MAX_AGE_SEC, false },
        { REGION_FIX_MAX_AGE_SEC, 1u, REGION_FIX_MAX_AGE_SEC + 1u, false },
        { UINT32_MAX - 4u, 5u, UINT32_MAX, false },
        { UINT32_MAX - 4u, 6u, UINT32_MAX, false },
    };
    for (const AgeCase& tc : AGE_CASES) {
        uint32_t got = region_fix_age_advance(tc.age, tc.elapsed);
        bool tx = region_fix_age_allows_tx(got);
        if (got == tc.expected && tx == tc.tx_expected) {
            pass++;
        } else {
            fail++;
            std::printf("[FAIL] age=%lu + %lu => %lu (expected %lu), tx=%d\n",
                        (unsigned long)tc.age, (unsigned long)tc.elapsed,
                        (unsigned long)got, (unsigned long)tc.expected, tx);
        }
    }
    struct BudgetCase {
        uint32_t age;
        uint32_t expected_ms;
    };
    static const BudgetCase BUDGET_CASES[] = {
        { 0u, (REGION_FIX_MAX_AGE_SEC - REGION_TX_DEADLINE_GUARD_SEC) * 1000u },
        { REGION_FIX_MAX_AGE_SEC - 2u, 1000u },
        { REGION_FIX_MAX_AGE_SEC - 1u, 0u },
        { REGION_FIX_MAX_AGE_SEC, 0u },
        { UINT32_MAX, 0u },
    };
    for (const BudgetCase& tc : BUDGET_CASES) {
        uint32_t got = region_fix_remaining_tx_ms(tc.age);
        if (got == tc.expected_ms) {
            pass++;
        } else {
            fail++;
            std::printf("[FAIL] age=%lu => budget=%lu ms (expected %lu)\n",
                        (unsigned long)tc.age, (unsigned long)got,
                        (unsigned long)tc.expected_ms);
        }
    }
    struct SleepChargeCase {
        uint32_t nominal_sec;
        uint32_t expected_sec;
    };
    static const SleepChargeCase SLEEP_CHARGE_CASES[] = {
        { 0u, 0u },
        { 1u, 2u },
        { 10u, 11u },
        { 1200u, 1302u },
        { 1800u, 1953u },
        { UINT32_MAX, UINT32_MAX },
    };
    for (const SleepChargeCase& tc : SLEEP_CHARGE_CASES) {
        uint32_t got = region_sleep_age_charge_sec(tc.nominal_sec);
        if (got == tc.expected_sec) {
            pass++;
        } else {
            fail++;
            std::printf("[FAIL] nominal sleep=%lu => lease charge=%lu s "
                        "(expected %lu)\n",
                        (unsigned long)tc.nominal_sec, (unsigned long)got,
                        (unsigned long)tc.expected_sec);
        }
    }
    std::printf("=== region + freshness: %d passed, %d failed ===\n",
                pass, fail);
    return fail == 0 ? 0 : 1;
}
