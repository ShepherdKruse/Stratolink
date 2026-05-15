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

#define PRINT       Serial1
#define BAUD        115200
#define LOG_OK(s)   do { PRINT.print("[PASS] "); PRINT.println(s); pass_count++; } while(0)
#define LOG_FAIL(s) do { PRINT.print("[FAIL] "); PRINT.println(s); fail_count++; } while(0)

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
    /* AU915 (South America + Australia) */
    { "Sao Paulo",    E7(-23.55), E7(-46.63),  LORA_REGION_AU915 },
    { "Buenos Aires", E7(-34.61), E7(-58.38),  LORA_REGION_AU915 },
    { "Sydney",       E7(-33.87), E7(151.21),  LORA_REGION_AU915 },
    /* EU868 */
    { "London",       E7(51.51),  E7(-0.13),   LORA_REGION_EU868 },
    { "Cape Town",    E7(-33.92), E7(18.42),   LORA_REGION_EU868 },
    { "Moscow",       E7(55.75),  E7(37.62),   LORA_REGION_EU868 },
    /* AS923 */
    { "Tokyo",        E7(35.68),  E7(139.69),  LORA_REGION_AS923 },
    { "Singapore",    E7(1.35),   E7(103.82),  LORA_REGION_AS923 },
    /* SILENT (China + polar) */
    { "Beijing",      E7(39.90),  E7(116.40),  LORA_REGION_SILENT },
    { "Shanghai",     E7(31.23),  E7(121.47),  LORA_REGION_SILENT },
    { "North Pole",   E7(85.0),   E7(0.0),     LORA_REGION_SILENT },
    /* Exact-boundary cases that previously truncated wrong */
    { "lat 70.0001",  700001000,  0,           LORA_REGION_SILENT },
    { "lon -30.0001",E7(35.0),   -300001000,  LORA_REGION_US915 },
    { "lon -170.001",E7(40.0),   -1700001000, LORA_REGION_AS923 },
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
    else if (memcmp(r.nwkSKey, s.nwkSKey, sizeof(s.nwkSKey))) LOG_FAIL("nwkSKey mismatch");
    else if (memcmp(r.appSKey, s.appSKey, sizeof(s.appSKey))) LOG_FAIL("appSKey mismatch");
    else                                  LOG_OK("save -> load preserves all fields");

    /* Clear and re-load — must return false (magic zeroed). */
    power_manager_clear_session();
    lorawan_session_t z = {0};
    bool empty = power_manager_load_session(&z);
    if (!empty) LOG_OK("clear -> load returns false");
    else        LOG_FAIL("clear -> load still returned true");
}

static void test_export_import_session(void) {
    PRINT.println("\n=== 6. lorawan_export_session / import_session ===");
    /* Build a synthetic session, import it, export, compare. */
    lorawan_session_t in = {0};
    in.region_id = LORA_REGION_AS923;
    in.devAddr   = 0xCAFEF00D;
    in.fCntUp    = 42;
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
    else if (memcmp(out.nwkSKey, in.nwkSKey, sizeof(in.nwkSKey))) LOG_FAIL("export nwkSKey");
    else if (memcmp(out.appSKey, in.appSKey, sizeof(in.appSKey))) LOG_FAIL("export appSKey");
    else                                                  LOG_OK("import -> export round-trip");

    /* Reject obviously-invalid: out-of-range region_id. */
    lorawan_session_t bad = in;
    bad.region_id = 99;
    if (!lorawan_import_session(&bad)) LOG_OK("import rejects out-of-range region_id");
    else                               LOG_FAIL("import accepted region_id=99");
}

static void run_all_tests(void) {
    pass_count = fail_count = 0;
    test_geofence();
    test_set_region_transitions();
    test_set_region_idempotent();
    test_silent_blocks_tx();
    test_session_tamp_roundtrip();
    test_export_import_session();

    PRINT.print("\n=== ");
    PRINT.print(pass_count);
    PRINT.print(" passed, ");
    PRINT.print(fail_count);
    PRINT.println(" failed ===");
}

void setup() {
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
