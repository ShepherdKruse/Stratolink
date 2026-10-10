/**
 * Stratolink region-switching + session-persistence stress test.
 *
 * Drives the firmware's runtime LoRaWAN region logic without needing a
 * real GPS fix or live gateway: feeds synthetic (lat_e7, lon_e7) pairs
 * into the geofence + region switcher, validates state transitions,
 * exercises TAMP-backed session save/load, and prints a PASS/FAIL log
 * over Serial1 @ 115200 8N1.
 *
 * Flash:    pio run -e region_test -t upload    (J-Link on J20)
 * Read out: USB-UART on J4 header (same wiring as power_test)
 * Revert:   pio run -e stratolink -t upload
 *
 * What it checks (run-once at boot, then loops the summary):
 *   1. region_for_latlon over the same 90-ish cases the host test covers
 *   2. lorawan_set_region transitions clear _joined + fCntUp
 *   3. lorawan_set_region(same) is idempotent (no state churn)
 *   4. SILENT region rejects lorawan_join + lorawan_send_uplink
 *   5. TAMP save → clear → load round-trip preserves the session
 *   6. lorawan_export_session / lorawan_import_session round-trip
 *
 * Each test logs "[PASS]" or "[FAIL: reason]"; final summary lists
 * pass/fail counts and re-prints every 10 s so you can catch the
 * output mid-stream.
 */
#include <Arduino.h>
#include <string.h>
#include "stratolink_pins.h"
#include "lorawan.h"
#include "region_manager.h"
#include "power_manager.h"
#include "stm32wlxx_hal.h"   /* for TAMP / PWR / RCC direct access */
#if __has_include("secrets.h")
#include "secrets.h"          /* per-region LORAWAN_DEV_EUI_* for test 12 */
#endif
/* Same backward-compat shim as lorawan.cpp: older single-EUI secrets
 * fall back to the legacy LORAWAN_DEV_EUI for US, empty for others. */
#ifndef LORAWAN_DEV_EUI_US
#define LORAWAN_DEV_EUI_US LORAWAN_DEV_EUI
#endif
#ifndef LORAWAN_DEV_EUI_EU
#define LORAWAN_DEV_EUI_EU ""
#endif
#ifndef LORAWAN_DEV_EUI_AS
#define LORAWAN_DEV_EUI_AS ""
#endif
#ifndef LORAWAN_DEV_EUI_AU
#define LORAWAN_DEV_EUI_AU ""
#endif

#define PRINT       Serial1
#define BAUD        115200

/* ========== SRAM scratchpad for J-Link-only readout ==========
 *
 * Mirrors the Serial1 PASS/FAIL stream into a known global so that
 * J-Link can halt the MCU and dump results without needing a UART
 * adapter wired up.  Layout is fixed (magic + counts + log) so the
 * host-side parser doesn't depend on the .elf symbol table — the
 * J-Link script reads the address looked up via arm-none-eabi-nm at
 * build time. */
#define SCRATCH_MAGIC_DONE    0xC0FFEEAAu

typedef struct {
    uint32_t magic;        /* set to SCRATCH_MAGIC_DONE after all tests run */
    uint32_t total;
    uint32_t passed;
    uint32_t failed;
    uint32_t log_len;
    char     log[3072];
} __attribute__((aligned(4))) test_scratch_t;

/* `used` keeps the linker from GC'ing it; volatile keeps writes
 * observable to J-Link reads. */
volatile test_scratch_t test_scratch __attribute__((used));

static void scratch_append(const char* s) {
    while (*s && test_scratch.log_len < sizeof(test_scratch.log) - 1) {
        test_scratch.log[test_scratch.log_len++] = *s++;
    }
}

#define LOG_OK(s)   do { \
    PRINT.print("[PASS] "); PRINT.println(s); \
    scratch_append("[PASS] "); scratch_append(s); scratch_append("\n"); \
    pass_count++; \
} while(0)
#define LOG_FAIL(s) do { \
    PRINT.print("[FAIL] "); PRINT.println(s); \
    scratch_append("[FAIL] "); scratch_append(s); scratch_append("\n"); \
    fail_count++; \
} while(0)

#define E7(d) ((int32_t)((d) * 10000000))

static int pass_count = 0;
static int fail_count = 0;

static const char* region_name(lora_region_id_t r) {
    switch (r) {
        case LORA_REGION_US915:  return "US915";
        case LORA_REGION_EU868:  return "EU868";
        case LORA_REGION_AS923:  return "AS923";
        case LORA_REGION_AU915:  return "AU915";
        case LORA_REGION_SILENT: return "SILENT";
        default:                 return "?";
    }
}

struct GeoCase {
    const char*       name;
    int32_t           lat_e7;
    int32_t           lon_e7;
    lora_region_id_t  expected;
};

/* Trimmed jet-stream sweep — full coverage is in test/test_region.cpp
 * for the host build.  Here we sanity-check the cases that exercise
 * each return path of the geofence. */
static const GeoCase GEO_CASES[] = {
    /* US915 */
    { "New York",     E7(40.71),  E7(-74.0),   LORA_REGION_US915 },
    { "Mexico City",  E7(19.43),  E7(-99.13),  LORA_REGION_US915 },
    { "Honolulu",     E7(21.31),  E7(-157.86), LORA_REGION_US915 },
    /* Mixed-plan South America fails closed; AU915 only in ANZ. */
    { "Sao Paulo",    E7(-23.55), E7(-46.63),  LORA_REGION_SILENT },
    { "Buenos Aires", E7(-34.61), E7(-58.38),  LORA_REGION_SILENT },
    { "Sydney",       E7(-33.87), E7(151.21),  LORA_REGION_AU915 },
    /* EU868 */
    { "London",       E7(51.51),  E7(-0.13),   LORA_REGION_EU868 },
    { "Cape Town",    E7(-33.92), E7(18.42),   LORA_REGION_EU868 },
    { "Moscow",       E7(55.75),  E7(37.62),   LORA_REGION_SILENT },
    /* AS923 */
    { "Singapore",    E7(1.35),   E7(103.82),  LORA_REGION_AS923 },
    /* SILENT (Japan LBT, China, unsupported corridors, polar) */
    { "Tokyo",        E7(35.68),  E7(139.69),  LORA_REGION_SILENT },
    { "Seoul",        E7(37.57),  E7(126.98),  LORA_REGION_SILENT },
    { "Beijing",      E7(39.90),  E7(116.40),  LORA_REGION_SILENT },
    { "Shanghai",     E7(31.23),  E7(121.47),  LORA_REGION_SILENT },
    { "North Pole",   E7(85.0),   E7(0.0),     LORA_REGION_SILENT },
    /* Exact-boundary cases that previously truncated wrong */
    { "lat 70.0001",  700001000,  0,           LORA_REGION_SILENT },
    { "lon -30.0001",E7(35.0),   -300001000,  LORA_REGION_US915 },
    { "lon -170.001",E7(40.0),   -1700001000, LORA_REGION_US915 },
    { "lat 12.0001", 120001000,  E7(-60.0),   LORA_REGION_US915 },
};

static void test_geofence(void) {
    PRINT.println("\n=== 1. region_for_latlon geofence ===");
    for (size_t i = 0; i < sizeof(GEO_CASES)/sizeof(GEO_CASES[0]); i++) {
        const GeoCase& c = GEO_CASES[i];
        lora_region_id_t got = region_for_latlon(c.lat_e7, c.lon_e7);
        char buf[128];
        snprintf(buf, sizeof(buf), "%-14s exp=%s got=%s",
                 c.name, region_name(c.expected), region_name(got));
        if (got == c.expected) LOG_OK(buf); else LOG_FAIL(buf);
    }
}

static void test_set_region_transitions(void) {
    PRINT.println("\n=== 2. lorawan_set_region transitions ===");
    lora_region_id_t order[] = {
        LORA_REGION_US915, LORA_REGION_EU868, LORA_REGION_AS923,
        LORA_REGION_AU915, LORA_REGION_SILENT, LORA_REGION_US915
    };
    for (size_t i = 0; i < sizeof(order)/sizeof(order[0]); i++) {
        lorawan_set_region(order[i]);
        lora_region_id_t got = lorawan_current_region();
        char buf[64];
        snprintf(buf, sizeof(buf), "set %s -> current %s",
                 region_name(order[i]), region_name(got));
        if (got == order[i]) LOG_OK(buf); else LOG_FAIL(buf);
    }
}

static void test_set_region_idempotent(void) {
    PRINT.println("\n=== 3. set_region idempotency ===");
    lorawan_set_region(LORA_REGION_EU868);
    lora_region_id_t before = lorawan_current_region();
    /* Calling twice with the same id must not churn internal state.
     * We can't directly read _joined, but we can re-call and expect
     * the region to remain stable. */
    lorawan_set_region(LORA_REGION_EU868);
    lora_region_id_t after = lorawan_current_region();
    if (before == after && after == LORA_REGION_EU868) {
        LOG_OK("EU868 set twice -> stable");
    } else {
        LOG_FAIL("EU868 set twice -> drifted");
    }
}

static void test_silent_blocks_tx(void) {
    PRINT.println("\n=== 4. SILENT region blocks join + uplink ===");
    lorawan_set_region(LORA_REGION_SILENT);
    bool joined = lorawan_join(1000);  /* short timeout, should bail immediately */
    if (!joined) LOG_OK("join rejected in SILENT");
    else         LOG_FAIL("join accepted in SILENT (should have been rejected)");

    uint8_t dummy[8] = {0};
    bool sent = lorawan_send_uplink(dummy, sizeof(dummy));
    if (!sent) LOG_OK("send_uplink rejected in SILENT");
    else       LOG_FAIL("send_uplink accepted in SILENT (should have been rejected)");
}

static void test_session_tamp_roundtrip(void) {
    PRINT.println("\n=== 5. TAMP session save/load round-trip ===");
    /* Stamp a known session, save, clear, then load and compare. */
    lorawan_session_t s = {0};
    s.region_id = LORA_REGION_EU868;
    s.devAddr   = 0xDEADBEEF;
    s.fCntUp    = 0x12345678;
    s.fCntDown  = 0x87654321;
    s.rxDelaySec = 5;
    for (int i = 0; i < 4; i++) {
        s.nwkSKey[i] = 0xA1A2A3A4u + i;
        s.appSKey[i] = 0xB1B2B3B4u + i;
    }
    power_manager_save_session(&s);

    lorawan_session_t r = {0};
    bool ok = power_manager_load_session(&r);
    if (!ok)                              LOG_FAIL("load returned false after save");
    else if (r.region_id != s.region_id)  LOG_FAIL("region_id mismatch");
    else if (r.devAddr   != s.devAddr)    LOG_FAIL("devAddr mismatch");
    else if (r.fCntUp    != s.fCntUp)     LOG_FAIL("fCntUp mismatch");
    else if (r.fCntDown  != s.fCntDown)   LOG_FAIL("fCntDown mismatch");
    else if (r.rxDelaySec != s.rxDelaySec) LOG_FAIL("RxDelay mismatch");
    else if (memcmp(r.nwkSKey, s.nwkSKey, sizeof(s.nwkSKey))) LOG_FAIL("nwkSKey mismatch");
    else if (memcmp(r.appSKey, s.appSKey, sizeof(s.appSKey))) LOG_FAIL("appSKey mismatch");
    else                                  LOG_OK("save -> load preserves all fields");

    bool lease_saved = power_manager_save_region_lease(1777u);
    uint32_t lease_age = 0;
    if (lease_saved && power_manager_load_region_lease(&lease_age) &&
        lease_age == 1777u) {
        LOG_OK("region lease save -> load preserves age");
    } else {
        LOG_FAIL("region lease save/load mismatch");
    }

    /* Clear and re-load — must return false (magic zeroed). */
    bool clear_saved = power_manager_clear_session();
    lorawan_session_t z = {0};
    bool empty = power_manager_load_session(&z);
    if (!empty) LOG_OK("clear -> load returns false");
    else        LOG_FAIL("clear -> load still returned true");
    if (clear_saved && !power_manager_load_region_lease(&lease_age)) {
        LOG_OK("session clear also invalidates region lease");
    } else {
        LOG_FAIL("session clear left a stale region lease");
    }
}

static void test_export_import_session(void) {
    PRINT.println("\n=== 6. lorawan_export_session / import_session ===");
    /* Build a synthetic session, import it, export, compare. */
    lorawan_session_t in = {0};
    in.region_id = LORA_REGION_AS923;
    in.devAddr   = 0xCAFEF00D;
    in.fCntUp    = 42;
    in.fCntDown  = 17;
    in.rxDelaySec = 7;
    for (int i = 0; i < 4; i++) {
        in.nwkSKey[i] = 0xC0FFEE00u + i;
        in.appSKey[i] = 0xFEEDFACEu + i;
    }
    if (!lorawan_import_session(&in)) {
        LOG_FAIL("import rejected valid session");
        return;
    }
    if (lorawan_current_region() != LORA_REGION_AS923) {
        LOG_FAIL("import didn't switch region");
        return;
    }

    lorawan_session_t out = {0};
    lorawan_export_session(&out);
    if (out.region_id != LORA_REGION_AS923)               LOG_FAIL("export region_id");
    else if (out.devAddr  != in.devAddr)                  LOG_FAIL("export devAddr");
    else if (out.fCntUp   != in.fCntUp)                   LOG_FAIL("export fCntUp");
    else if (out.fCntDown != in.fCntDown)                 LOG_FAIL("export fCntDown");
    else if (out.rxDelaySec != in.rxDelaySec)             LOG_FAIL("export RxDelay");
    else if (memcmp(out.nwkSKey, in.nwkSKey, sizeof(in.nwkSKey))) LOG_FAIL("export nwkSKey");
    else if (memcmp(out.appSKey, in.appSKey, sizeof(in.appSKey))) LOG_FAIL("export appSKey");
    else                                                  LOG_OK("import -> export round-trip");

    /* Reject obviously-invalid: out-of-range region_id. */
    lorawan_session_t bad = in;
    bad.region_id = 99;
    if (!lorawan_import_session(&bad)) LOG_OK("import rejects out-of-range region_id");
    else                               LOG_FAIL("import accepted region_id=99");

    bad = in;
    bad.rxDelaySec = 0;
    if (!lorawan_import_session(&bad)) LOG_OK("import rejects RxDelay=0");
    else                               LOG_FAIL("import accepted RxDelay=0");
    bad.rxDelaySec = 16;
    if (!lorawan_import_session(&bad)) LOG_OK("import rejects RxDelay=16");
    else                               LOG_FAIL("import accepted RxDelay=16");
}

/* ========== Trajectory integration test ==========
 *
 * Walks a simulated jet-stream circumnavigation through every
 * regulatory zone the firmware can encounter, calling the same code
 * path that main.cpp loop() runs after a real GPS fix:
 *
 *   region = region_for_latlon(lat, lon)
 *   lorawan_set_region(region)
 *
 * At each step, verifies:
 *   1. region_for_latlon picks the expected region
 *   2. lorawan_current_region() reflects the switch
 *   3. If region changed from prev step: _joined flipped from true to
 *      false AND fCntUp was reset to 0
 *   4. If region didn't change: _joined and fCntUp persisted
 *
 * Setting _joined=true before each switch is done via lorawan_import
 * _session — we don't actually need a real LoRaWAN gateway for this
 * test, the import sets the internal session state synthetically.
 */
struct trajectory_step_t {
    int32_t           lat_e7;
    int32_t           lon_e7;
    lora_region_id_t  expected_region;
    const char*       name;
};

static const trajectory_step_t TRAJECTORY[] = {
    /* Jet-stream circumnav at lat 40°N going eastbound — every step
     * a balloon would actually pass over during a real flight. */
    { E7(40.7), E7(-74.0),  LORA_REGION_US915,  "NYC start"            },
    { E7(40.0), E7(-100.0), LORA_REGION_US915,  "Kansas"               },
    { E7(40.0), E7(-60.0),  LORA_REGION_US915,  "Atlantic 60W"         },
    { E7(40.0), E7(-40.0),  LORA_REGION_US915,  "Atlantic 40W"         },
    { E7(40.0), E7(-31.0),  LORA_REGION_US915,  "Just west of bdry"    },
    { E7(40.0), E7(-29.0),  LORA_REGION_EU868,  "EU CROSS"             },
    { E7(40.0), E7(0.0),    LORA_REGION_EU868,  "Prime Meridian"       },
    { E7(40.0), E7(30.0),   LORA_REGION_EU868,  "Black Sea"            },
    { E7(40.0), E7(50.0),   LORA_REGION_EU868,  "Caspian"              },
    { E7(40.0), E7(59.0),   LORA_REGION_EU868,  "Just W of EU/AS bdry" },
    { E7(40.0), E7(61.0),   LORA_REGION_SILENT, "Unsupported Asia"     },
    { E7(40.0), E7(75.0),   LORA_REGION_SILENT, "China bbox W"         },
    { E7(40.0), E7(110.0),  LORA_REGION_SILENT, "Mongolia (CN bbox)"   },
    { E7(40.0), E7(120.0),  LORA_REGION_SILENT, "Shanghai-lat (CN)"    },
    { E7(40.0), E7(124.0),  LORA_REGION_SILENT, "Korea KR920"          },
    { E7(40.0), E7(140.0),  LORA_REGION_SILENT, "Japan LBT"            },
    { E7(40.0), E7(170.0),  LORA_REGION_AS923,  "Mid-Pacific"          },
    /* Cross antimeridian going east into Americas */
    { E7(40.0), E7(-170.0), LORA_REGION_US915,  "Aleutians US side"    },
    { E7(40.0), E7(-160.0), LORA_REGION_US915,  "East Pacific"         },
    { E7(40.7), E7(-74.0),  LORA_REGION_US915,  "Back to NYC"          },
    /* Throw in southern hemisphere edge cases */
    { E7(-23.5),E7(-46.6),  LORA_REGION_SILENT, "Sao Paulo (mixed SA)" },
    { E7(-33.9),E7(151.2),  LORA_REGION_AU915,  "Sydney"               },
};

/* Build a synthetic joined-session for a given region.  Import sets
 * _joined=true and fCntUp=42 internally; we use it as the "before"
 * state so we can observe set_region's invalidation. */
static void prime_joined_state(lora_region_id_t region, uint32_t fcnt) {
    lorawan_session_t s = {0};
    s.region_id = (uint32_t)region;
    s.devAddr   = 0xABCDEF01u;
    s.fCntUp    = fcnt;
    s.rxDelaySec = 5;
    for (int i = 0; i < 4; i++) {
        s.nwkSKey[i] = 0xAAAA0000u + i;
        s.appSKey[i] = 0xBBBB0000u + i;
    }
    (void)lorawan_import_session(&s);
}

static void test_trajectory(void) {
    PRINT.println("\n=== 7. Trajectory: fake-GPS-driven region switching ===");

    lora_region_id_t prev_region = LORA_REGION_COUNT;

    for (size_t i = 0; i < sizeof(TRAJECTORY)/sizeof(TRAJECTORY[0]); i++) {
        const trajectory_step_t& step = TRAJECTORY[i];

        /* Step 1: geofence picks expected region. */
        lora_region_id_t geo = region_for_latlon(step.lat_e7, step.lon_e7);

        /* Pre-arm a joined session in the previous region so we can
         * observe set_region's invalidation when crossing a boundary.
         * Skip on the very first step (no prev) and skip if the new
         * region is SILENT (import rejects SILENT). */
        if (prev_region != LORA_REGION_COUNT && prev_region != LORA_REGION_SILENT) {
            prime_joined_state(prev_region, /*fcnt=*/100);
        }
        bool was_joined = lorawan_joined();
        uint32_t was_fcnt;
        {
            lorawan_session_t pre; lorawan_export_session(&pre);
            was_fcnt = pre.fCntUp;
        }

        /* Step 2: call set_region as main.cpp loop() would. */
        lorawan_set_region(geo);

        /* Step 3: verify state. */
        lora_region_id_t now = lorawan_current_region();
        bool joined_now = lorawan_joined();
        uint32_t fcnt_now;
        {
            lorawan_session_t post; lorawan_export_session(&post);
            fcnt_now = post.fCntUp;
        }

        bool ok = true;
        char buf[160];
        if (geo != step.expected_region) {
            snprintf(buf, sizeof(buf), "%-22s geofence wrong: exp=%s got=%s",
                     step.name, region_name(step.expected_region), region_name(geo));
            ok = false;
        } else if (now != step.expected_region) {
            snprintf(buf, sizeof(buf), "%-22s set_region didn't take: exp=%s got=%s",
                     step.name, region_name(step.expected_region), region_name(now));
            ok = false;
        } else if (prev_region != LORA_REGION_COUNT
                   && prev_region != LORA_REGION_SILENT
                   && geo != prev_region) {
            /* Boundary crossing: session should have been invalidated. */
            if (was_joined && joined_now) {
                snprintf(buf, sizeof(buf), "%-22s set_region didn't clear _joined on %s->%s",
                         step.name, region_name(prev_region), region_name(geo));
                ok = false;
            } else if (was_fcnt != 0 && fcnt_now != 0) {
                snprintf(buf, sizeof(buf), "%-22s fCntUp not reset on %s->%s (was %lu now %lu)",
                         step.name, region_name(prev_region), region_name(geo),
                         (unsigned long)was_fcnt, (unsigned long)fcnt_now);
                ok = false;
            } else {
                snprintf(buf, sizeof(buf), "%-22s %s->%s session cleared OK",
                         step.name, region_name(prev_region), region_name(geo));
            }
        } else {
            snprintf(buf, sizeof(buf), "%-22s stays %s",
                     step.name, region_name(geo));
        }
        if (ok) LOG_OK(buf); else LOG_FAIL(buf);

        prev_region = geo;
    }
}

/* ========== Boundary thrash ==========
 *
 * Stresses the radio reconfiguration path inside lorawan_set_region by
 * doing many rapid alternations between two regions.  If anything in
 * the SX1262 reconfiguration accumulates bad state (stuck SPI, missed
 * standby, frequency commit failure), 50+ iterations will surface it
 * where a single switch wouldn't. */
static void test_boundary_thrash(void) {
    PRINT.println("\n=== 8. Boundary thrash: rapid alternations ===");

    /* Strategy: at each iteration pick the OPPOSITE of the current
     * region.  Guarantees every set_region call is a real transition
     * (not a same-region idempotent no-op), so invalidation is
     * observable on every iteration. */

    /* (a) US915 <-> EU868 across the Atlantic mid-ocean boundary */
    int bad = 0;
    lorawan_set_region(LORA_REGION_EU868);  /* known start, opposite of first switch */
    for (int i = 0; i < 50; i++) {
        lora_region_id_t before = lorawan_current_region();
        prime_joined_state(before, (uint32_t)(i + 1) * 10);
        /* Force a real transition: target whichever region we're NOT in. */
        lora_region_id_t want = (before == LORA_REGION_US915)
                                 ? LORA_REGION_EU868 : LORA_REGION_US915;
        int32_t lon = (want == LORA_REGION_EU868) ? E7(-29.0) : E7(-31.0);
        lora_region_id_t geo = region_for_latlon(E7(40.0), lon);
        lorawan_set_region(geo);
        if (geo != want)                       bad |= 1;
        if (lorawan_current_region() != want)  bad |= 2;
        if (lorawan_joined())                  bad |= 4;  /* must be cleared */
        lorawan_session_t post; lorawan_export_session(&post);
        if (post.fCntUp != 0)                  bad |= 8;
    }
    char buf[120];
    if (bad == 0) {
        LOG_OK("50x US<->EU forced-transition crossings: state clean");
    } else {
        snprintf(buf, sizeof(buf), "50x US<->EU thrash failure bitmap=0x%X", bad);
        LOG_FAIL(buf);
    }

    /* (b) AS923 <-> SILENT across the China bbox west edge (lon 73).
     * SILENT branch in set_region uses a different early-return path. */
    bad = 0;
    lorawan_set_region(LORA_REGION_AS923);  /* known start */
    for (int i = 0; i < 50; i++) {
        lora_region_id_t before = lorawan_current_region();
        if (before != LORA_REGION_SILENT) prime_joined_state(before, (uint32_t)(i + 1) * 10);
        lora_region_id_t want = (before == LORA_REGION_AS923)
                                 ? LORA_REGION_SILENT : LORA_REGION_AS923;
        int32_t lon = (want == LORA_REGION_SILENT) ? E7(75.0) : E7(70.0);
        lora_region_id_t geo = region_for_latlon(E7(40.0), lon);
        lorawan_set_region(geo);
        if (geo != want)                       bad |= 1;
        if (lorawan_current_region() != want)  bad |= 2;
        lorawan_session_t post; lorawan_export_session(&post);
        if (post.fCntUp != 0)                  bad |= 4;
    }
    if (bad == 0) {
        LOG_OK("50x AS<->SILENT forced-transition crossings: state clean");
    } else {
        snprintf(buf, sizeof(buf), "50x AS<->SILENT thrash failure bitmap=0x%X", bad);
        LOG_FAIL(buf);
    }
}

/* ========== Random walk ==========
 *
 * Visit each region in a deterministic pseudo-random order and verify
 * lorawan_current_region tracks the requested region every step.
 * Different stress profile than thrash — exercises every possible
 * transition (X→Y for every X,Y pair) rather than just one pair. */
static void test_random_walk(void) {
    PRINT.println("\n=== 9. Random walk through all regions ===");
    /* xorshift32 with seed 1 — fully reproducible. */
    uint32_t s = 1u;
    int bad = 0;
    for (int i = 0; i < 100; i++) {
        s ^= s << 13; s ^= s >> 17; s ^= s << 5;
        lora_region_id_t target = (lora_region_id_t)(s % 5);  /* 0..4 incl SILENT */
        lorawan_set_region(target);
        if (lorawan_current_region() != target) bad++;
    }
    char buf[80];
    if (bad == 0) {
        LOG_OK("100x pseudo-random region transitions: all tracked");
    } else {
        snprintf(buf, sizeof(buf), "random walk: %d/100 mismatched", bad);
        LOG_FAIL(buf);
    }
}

/* ========== Multi-session save/load ==========
 *
 * Save three different sessions in sequence; after each save, the load
 * must return that session, not a stale one.  Catches any case where
 * TAMP isn't fully overwritten by the save path (partial writes,
 * caching, stale-residue bugs). */
static void test_multi_save_load(void) {
    PRINT.println("\n=== 10. Multi-cycle save/load (write-A, write-B, write-C) ===");
    struct { lora_region_id_t r; uint32_t addr; uint32_t fcnt; uint32_t key0; const char* tag; } cases[] = {
        { LORA_REGION_US915, 0x11111111u, 0x00000001u, 0xA1111111u, "A US915 fcnt=1" },
        { LORA_REGION_EU868, 0x22222222u, 0x00000002u, 0xA2222222u, "B EU868 fcnt=2" },
        { LORA_REGION_AS923, 0x33333333u, 0xDEADBEEFu, 0xA3333333u, "C AS923 fcnt=DEADBEEF" },
    };
    for (size_t i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        lorawan_session_t w = {0};
        w.region_id = cases[i].r;
        w.devAddr   = cases[i].addr;
        w.fCntUp    = cases[i].fcnt;
        w.rxDelaySec = 5;
        for (int j = 0; j < 4; j++) { w.nwkSKey[j] = cases[i].key0 + j; w.appSKey[j] = cases[i].key0 + 0x10 + j; }
        power_manager_save_session(&w);
        lorawan_session_t r = {0};
        bool ok = power_manager_load_session(&r);
        char buf[100];
        if (!ok) {
            snprintf(buf, sizeof(buf), "%-30s load returned false", cases[i].tag);
            LOG_FAIL(buf);
            continue;
        }
        bool match = (r.region_id == w.region_id && r.devAddr == w.devAddr &&
                      r.fCntUp == w.fCntUp && r.nwkSKey[0] == w.nwkSKey[0]);
        if (match) {
            snprintf(buf, sizeof(buf), "%-30s save/load round-trip", cases[i].tag);
            LOG_OK(buf);
        } else {
            snprintf(buf, sizeof(buf), "%-30s stale data: got fcnt=0x%08lX addr=0x%08lX",
                     cases[i].tag, (unsigned long)r.fCntUp, (unsigned long)r.devAddr);
            LOG_FAIL(buf);
        }
    }
    (void)power_manager_clear_session();  /* clean up */
}

/* ========== Session persistence across NVIC_SystemReset ==========
 *
 * The flight firmware's TX-fail auto-reset path calls NVIC_SystemReset
 * after 5 consecutive failures (main.cpp tx_fail_streak >= 5).  After
 * that reset, setup() runs power_manager_load_session and is supposed
 * to find the saved session in TAMP, skip the join, and continue from
 * the last fCntUp.  Bench-proving this end-to-end requires actually
 * triggering NVIC_SystemReset mid-test.
 *
 * Two-phase strategy:
 *   Phase 1 (first boot): stamp a known session, mark BKP16R, reset.
 *   Phase 2 (post-reset): detect marker, load session, compare every
 *                          field, clear marker, then continue normal
 *                          tests.
 *
 * Inter-phase signal temporarily uses TAMP_BKP16R (immediately after the
 * 15-word session struct at BKP0R..BKP14R and its production CRC32 at
 * BKP15R). In the flight image BKP16R stores command state, BKP17R the B2B
 * origin ID, BKP18R the packed region lease, and BKP19R the packed boot
 * counter. This diagnostic does not dispatch commands, and clears its marker
 * before continuing. test_scratch is zeroed across reset (it is in BSS), so
 * phase-2 results are what J-Link sees in the dump. */
#define RESET_TEST_MARKER       0xDEADBEEFu

static void backup_access_unlock(void) {
    SET_BIT(RCC->APB1ENR1, RCC_APB1ENR1_RTCAPBEN);
    (void)READ_BIT(RCC->APB1ENR1, RCC_APB1ENR1_RTCAPBEN);
    SET_BIT(PWR->CR1, PWR_CR1_DBP);
}
static uint32_t test_marker_read(void) {
    backup_access_unlock();
    return (&TAMP->BKP0R)[16];
}
static void test_marker_write(uint32_t v) {
    backup_access_unlock();
    (&TAMP->BKP0R)[16] = v;
}

static void test_persist_phase2(void) {
    PRINT.println("\n=== 11. Persist across NVIC_SystemReset (PHASE 2 post-reset) ===");
    scratch_append("[INFO] phase 2: post-NVIC_SystemReset boot\n");

    lorawan_session_t s = {0};
    bool ok = power_manager_load_session(&s);
    if (!ok)                                  { LOG_FAIL("phase2: load_session returned false"); return; }
    if (s.region_id != LORA_REGION_EU868)     { LOG_FAIL("phase2: region_id mismatch"); return; }
    if (s.devAddr   != 0xAABBCCDDu)           { LOG_FAIL("phase2: devAddr mismatch"); return; }
    if (s.fCntUp    != 0x12345678u)           { LOG_FAIL("phase2: fCntUp mismatch"); return; }
    if (s.fCntDown  != 0x13579BDFu)           { LOG_FAIL("phase2: fCntDown mismatch"); return; }
    if (s.rxDelaySec != 5u)                    { LOG_FAIL("phase2: RxDelay mismatch"); return; }
    for (int i = 0; i < 4; i++) {
        if (s.nwkSKey[i] != 0xCAFE0000u + i)  { LOG_FAIL("phase2: nwkSKey mismatch"); return; }
        if (s.appSKey[i] != 0xF00D0000u + i)  { LOG_FAIL("phase2: appSKey mismatch"); return; }
    }
    uint32_t lease_age = 0;
    if (!power_manager_load_region_lease(&lease_age) || lease_age != 1799u) {
        LOG_FAIL("phase2: region lease age did not survive reset");
        return;
    }
    LOG_OK("session + region lease preserved across NVIC_SystemReset");

    /* Clean up: clear marker + session so subsequent boots don't loop. */
    test_marker_write(0);
    (void)power_manager_clear_session();
}

static void test_persist_phase1_and_reset(void) {
    PRINT.println("\n=== 11. Persist across NVIC_SystemReset (PHASE 1) ===");
    scratch_append("[INFO] phase 1: stamping session + marker, calling NVIC_SystemReset\n");

    lorawan_session_t s = {0};
    s.region_id = LORA_REGION_EU868;
    s.devAddr   = 0xAABBCCDDu;
    s.fCntUp    = 0x12345678u;
    s.fCntDown  = 0x13579BDFu;
    s.rxDelaySec = 5;
    for (int i = 0; i < 4; i++) { s.nwkSKey[i] = 0xCAFE0000u + i; s.appSKey[i] = 0xF00D0000u + i; }
    power_manager_save_session(&s);
    if (!power_manager_save_region_lease(1799u)) {
        LOG_FAIL("phase1: region lease write/readback failed");
        return;
    }
    test_marker_write(RESET_TEST_MARKER);

    /* Finalize scratchpad with phase-1 results in case the reset
     * doesn't fire — J-Link dump will at least show how far we got. */
    test_scratch.passed = pass_count;
    test_scratch.failed = fail_count;
    test_scratch.total  = pass_count + fail_count;
    test_scratch.magic  = SCRATCH_MAGIC_DONE;

    delay(50);    /* let any pending UART drain */
    NVIC_SystemReset();
    /* unreachable */
    while (1) { }
}

/* ========== Per-region credentials switching ==========
 *
 * After lorawan_set_region(X), the firmware must have loaded the
 * (DevEUI, AppKey) pair flashed in secrets.h for region X.  If the
 * region's secret is empty, lorawan_creds_loaded() returns false and
 * lorawan_join short-circuits — i.e., we silently skip OTAA in that
 * region rather than transmitting bogus identities. */
static int hex_nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
static void test_hex_to_bytes(const char* hex, uint8_t* out, size_t n) {
    for (size_t i = 0; i < n; i++) {
        int h = hex_nibble(hex[2*i]);
        int l = hex_nibble(hex[2*i + 1]);
        out[i] = (uint8_t)(((h < 0 ? 0 : h) << 4) | (l < 0 ? 0 : l));
    }
}

static void test_creds_switch(void) {
    PRINT.println("\n=== 12. Per-region credentials switching ===");

    struct { lora_region_id_t r; const char* eui_hex; const char* tag; } cases[] = {
        { LORA_REGION_US915, LORAWAN_DEV_EUI_US, "US915" },
        { LORA_REGION_EU868, LORAWAN_DEV_EUI_EU, "EU868" },
        { LORA_REGION_AS923, LORAWAN_DEV_EUI_AS, "AS923" },
        { LORA_REGION_AU915, LORAWAN_DEV_EUI_AU, "AU915" },
    };

    char buf[120];
    for (size_t i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        bool secret_present = (cases[i].eui_hex && cases[i].eui_hex[0] != '\0');
        lorawan_set_region(cases[i].r);
        bool creds_now = lorawan_creds_loaded();

        if (secret_present != creds_now) {
            snprintf(buf, sizeof(buf), "%s creds_loaded=%d but secret_present=%d",
                     cases[i].tag, creds_now, secret_present);
            LOG_FAIL(buf);
            continue;
        }

        if (!secret_present) {
            snprintf(buf, sizeof(buf), "%s no secret + no creds (consistent)", cases[i].tag);
            LOG_OK(buf);
            continue;
        }

        /* Both secret present AND creds loaded — verify DevEUI matches. */
        uint8_t got[8], want[8];
        lorawan_get_dev_eui(got);
        test_hex_to_bytes(cases[i].eui_hex, want, 8);
        if (memcmp(got, want, 8) == 0) {
            snprintf(buf, sizeof(buf), "%s DevEUI matches secret (%02X%02X..%02X%02X)",
                     cases[i].tag, got[0], got[1], got[6], got[7]);
            LOG_OK(buf);
        } else {
            snprintf(buf, sizeof(buf), "%s DevEUI mismatch got=%02X%02X..%02X%02X",
                     cases[i].tag, got[0], got[1], got[6], got[7]);
            LOG_FAIL(buf);
        }
    }

    /* SILENT must always have creds_loaded == false. */
    lorawan_set_region(LORA_REGION_SILENT);
    if (!lorawan_creds_loaded()) LOG_OK("SILENT: no creds (as required)");
    else                          LOG_FAIL("SILENT: creds_loaded reports true (must be false)");

    /* lorawan_join with empty-creds region must short-circuit. */
    lorawan_set_region(LORA_REGION_AU915);
    if (!lorawan_creds_loaded()) {
        bool joined = lorawan_join(500);
        if (!joined) LOG_OK("join short-circuits when creds empty");
        else         LOG_FAIL("join attempted with empty creds");
    } else {
        LOG_OK("AU915 has creds, skipping empty-creds short-circuit check");
    }
}

static void run_all_tests(void) {
    pass_count = fail_count = 0;
    test_scratch.magic = 0;       /* clear "done" until tests finish */
    test_scratch.log_len = 0;
    test_scratch.passed = 0;
    test_scratch.failed = 0;
    test_scratch.total = 0;

    /* Phase 2 detection: if the marker is set in TAMP, we just came
     * back from NVIC_SystemReset and must verify the session before
     * any other test mucks with TAMP.  Always run this first. */
    bool is_phase2 = (test_marker_read() == RESET_TEST_MARKER);
    if (is_phase2) test_persist_phase2();

    test_geofence();
    test_set_region_transitions();
    test_set_region_idempotent();
    test_silent_blocks_tx();
    test_session_tamp_roundtrip();
    test_export_import_session();
    test_trajectory();
    test_boundary_thrash();
    test_random_walk();
    test_multi_save_load();
    test_creds_switch();

    PRINT.print("\n=== ");
    PRINT.print(pass_count);
    PRINT.print(" passed, ");
    PRINT.print(fail_count);
    PRINT.println(" failed ===");

    /* Publish results to the scratchpad so J-Link can read them
     * without a UART adapter.  Magic-last ordering means the host can
     * poll for the magic value and know all other fields are stable. */
    test_scratch.passed = pass_count;
    test_scratch.failed = fail_count;
    test_scratch.total  = pass_count + fail_count;
    test_scratch.magic  = SCRATCH_MAGIC_DONE;

    /* If this was phase 1 (cold boot, no marker set), now stamp the
     * session + marker and trigger NVIC_SystemReset.  After reset,
     * setup() runs again, test_persist_phase2 runs first, then all
     * the other tests re-run.  Final J-Link dump shows phase-2
     * scratchpad. */
    if (!is_phase2) test_persist_phase1_and_reset();
}

void setup() {
    /* Two UARTs in play here: Serial1 = USART1 on PB6/PB7 (the J4
     * test header), Serial = LPUART1 on PA2/PA3 (no header, just a
     * BSS sink).  lorawan.cpp's LOG/LOGV writes to Serial; if it
     * isn't begin()'d, the HW UART is idle, the TX IRQ never fires,
     * and HardwareSerial::write busy-waits forever in
     * availableForWrite() once the 64-byte ring buffer fills.  Boot
     * both so neither path can hang on an uninitialised UART. */
    Serial.begin(BAUD);
    Serial1.begin(BAUD);
    delay(500);

    PRINT.println();
    PRINT.println("Stratolink region-switching stress test");
    PRINT.println("=======================================");

    /* lorawan_init() must run before set_region (it pre-arms the
     * SX1262); session funcs work even without init since they only
     * touch C statics + TAMP. */
    bool li = lorawan_init();
    PRINT.print("lorawan_init: ");
    PRINT.println(li ? "OK" : "FAIL (radio not initialized — set_region tests will still run)");

    run_all_tests();
}

void loop() {
    /* Re-print summary every 10 s so it's easy to catch on the UART. */
    delay(10000);
    PRINT.print("\n[summary] ");
    PRINT.print(pass_count);
    PRINT.print(" passed, ");
    PRINT.print(fail_count);
    PRINT.println(" failed");
}
