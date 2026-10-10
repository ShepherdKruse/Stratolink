#!/usr/bin/env python3
"""Execute flight main's GNSS -> authority -> join/primary -> lease sequence.

Catches the liveness bug of requiring existing RF authority before acquiring
GNSS, failure to revoke RF after expiry/persistence failure, and stale-position
publication after a missed fix. The unsafe authority-gated-acquisition mutant
must compile and fail a named recovery assertion before the real sequence runs.

Production blocks are extracted verbatim; real geofencing, lease arithmetic,
record encoding/decoding, and telemetry packing execute. Hardware GNSS results,
ADC tier, persistence success and radio success are controlled boundaries.
This is not the complete loop: setup/reset restore, sensors, freefall handling,
post-primary Class-A/auxiliary processing and physical sleep are outside scope.
An accepted GNSS result is an input, not proof of receiver fix validation. The
test observes primary send admission, not RF delivery or network acceptance.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from short_sleep_region_accounting_test import block


ROOT = Path(__file__).resolve().parents[2]


def harness() -> str:
    main = (ROOT / "firmware/src/main.cpp").read_text()
    acquisition_start = main.index("    uint32_t gps_timeout_ms =")
    acquisition_end = main.index("    /* GPS-driven region switch.", acquisition_start)
    authority_start = main.index("    if (fresh_fix_this_cycle)", acquisition_end)
    authority_end = main.index("    /* A genuine freefall", authority_start)
    join = block(main, "if (!suppress_optional_after_recovery && !burst_mode &&")
    primary_start = main.index("    bool vstor_ok_for_tx =")
    primary_end = main.index("        if (primary_sent)", primary_start)
    primary = main[primary_start:primary_end] + "        (void)primary_sent;\n    }\n"
    accounting_start = main.index("    uint32_t active_sec =", main.index("    uint32_t relay_region_budget_ms ="))
    accounting_end = main.index("#else", accounting_start)
    helpers = "\n".join(block(main, name) for name in (
        "static void persist_region_lease_if_trusted(",
        "static bool region_authority_is_gnss(",
        "static bool region_tx_allowed_now("))
    return r'''
#include "region_manager.h"
#include "tamp_record.h"
#include "gps_ublox.h"
#include "power_adc.h"
#include "telemetry.h"
#include <cstdio>
#include <string>
#include <vector>
#define LOG(...) ((void)0)
#define BURST_GPS_TIMEOUT_MS 10000u
static uint32_t now_ms, region_fix_age_sec, retained_word;
static bool region_known, region_lease_trusted, joined;
static tamp_region_authority_source_t region_authority_source;
static lora_region_id_t region_authority_region, radio_region;
static bool burst_mode, suppress_optional_after_recovery, s_have_fix_this_boot;
static uint32_t s_last_fix_monotonic_sec;
static uint8_t join_retry_skip, join_backoff_exp;
static gps_fix_t last_gps_fix;
static uint8_t tx_payload[TELEMETRY_PAYLOAD_SIZE];
static struct Inputs {
    bool fix = false, save_ok = true, clear_ok = true;
    bool gps_power = true, tx_power = true;
    int32_t latitude = 370000000, longitude = -1220000000;
} in;
static std::vector<std::string> events;
static unsigned failures, checks, joins, sends;
static bool last_allow_cold;
static uint32_t last_gps_budget;
static uint32_t millis() { return now_ms; }
uint32_t power_manager_monotonic_seconds() { return now_ms / 1000u; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }
bool power_adc_can_use_gps() { return in.gps_power; }
bool power_adc_can_tx() { return in.tx_power; }
uint16_t power_adc_read_vSTOR_mv() { return in.tx_power ? 4660u : 2800u; }
power_tier_t power_adc_get_tier() { return POWER_TIER_FULL; }
bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout, bool allow_cold_extension) {
    events.push_back("acquire");
    last_allow_cold = allow_cold_extension;
    last_gps_budget = timeout;
    now_ms += timeout;
    *fix = {};
    if (!in.fix) return false;
    fix->valid = true;
    fix->satellites = 6;
    fix->lat_e7 = in.latitude;
    fix->lon_e7 = in.longitude;
    return true;
}
gps_quiescence_result_t gps_ublox_quiesce() {
    events.push_back("quiesce");
    return GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY;
}
void gps_ublox_note_power_skip() { events.push_back("power-skip"); }
bool lorawan_joined() { return joined; }
lora_region_id_t lorawan_current_region() { return radio_region; }
void lorawan_set_region(lora_region_id_t region) {
    if (region != radio_region) joined = false;
    radio_region = region;
}
bool power_manager_clear_session() {
    events.push_back("clear");
    if (in.clear_ok) retained_word = 0u;
    return in.clear_ok;
}
bool power_manager_save_region_authority(uint32_t age, lora_region_id_t region,
                                       tamp_region_authority_source_t source) {
    events.push_back("authority-save");
    return in.save_ok && tamp_region_lease_record_encode(age, region, source,
                                                        &retained_word);
}
bool lorawan_join(uint32_t timeout) {
    events.push_back("join");
    ++joins;
    if (timeout != 15000u) ++failures;
    joined = true;
    return true;
}
bool lorawan_persist_session() { events.push_back("session-save"); return true; }
bool lorawan_server_probe_due(const lorawan_liveness_qualification_t*) { return false; }
static std::vector<uint8_t> last_payload;
bool lorawan_send_uplink(const uint8_t* bytes, uint8_t size) {
    events.push_back("primary");
    ++sends;
    last_payload.assign(bytes, bytes + size);
    return true;
}
bool lorawan_send_confirmed_uplink(const uint8_t* bytes, uint8_t size,
                                 const lorawan_liveness_qualification_t*) {
    return lorawan_send_uplink(bytes, size);
}
@HELPERS@
static void cycle() {
    events.clear();
    const uint32_t cycle_started_ms = now_ms;
    telemetry_input_t ti;
    telemetry_input_init(&ti);
@ACQUISITION@
@AUTHORITY@
    telemetry_pack(&ti, tx_payload);
@JOIN@
@PRIMARY@
    const uint32_t sleep_sec = 1200u;
    uint32_t relay_region_budget_ms;
@ACCOUNTING@
    (void)relay_region_budget_ms;
    (void)gps_quiescence;
}
static void check(const char* name, bool okay) {
    ++checks;
    if (!okay) { ++failures; std::printf("FAIL %s\n", name); }
}
static bool saw(const char* event) {
    for (const auto& actual : events) if (actual == event) return true;
    return false;
}
static void reset() {
    in = {};
    now_ms = region_fix_age_sec = retained_word = 0u;
    region_known = region_lease_trusted = joined = false;
    region_authority_source = TAMP_REGION_AUTHORITY_GNSS;
    region_authority_region = LORA_REGION_SILENT;
    radio_region = LORA_REGION_US915;
    burst_mode = suppress_optional_after_recovery = s_have_fix_this_boot = false;
    s_last_fix_monotonic_sec = 0u;
    join_retry_skip = join_backoff_exp = 0u;
    last_gps_fix = {};
    joins = sends = 0u;
    last_payload.clear();
}
static bool retained(uint32_t age, tamp_region_authority_source_t source) {
    tamp_region_lease_t value = {};
    return tamp_region_lease_record_decode(retained_word, &value) &&
        value.exact_region && value.region_id == LORA_REGION_US915 &&
        value.source == source && value.age_sec == age;
}
int main() {
    reset();
    cycle();
    check("unknown authority still acquires GNSS", saw("acquire"));
    check("ordinary main caller explicitly permits cold extension", saw("acquire") &&
          last_gps_budget == 30000u && last_allow_cold);
    check("no authority cannot publish itself or transmit", retained_word == 0u &&
          !region_known && !region_lease_trusted && joins == 0u && sends == 0u);
    in.fix = true;
    cycle();
    check("fresh fix restores absent authority and primary", region_known &&
          region_lease_trusted && joins == 1u && sends == 1u);
    check("authority is durable before join and primary", events ==
          std::vector<std::string>{"acquire", "quiesce", "clear", "authority-save",
              "join", "session-save", "primary", "authority-save"});
    check("fresh cycle charges active plus slow-RTC sleep", retained(1332u,
          TAMP_REGION_AUTHORITY_GNSS));
    check("fresh wire has location", last_payload.size() == 40u &&
          (last_payload[0] || last_payload[1] || last_payload[2] || last_payload[3]));

    in.fix = false;
    cycle();
    check("first missed fix retains legal primary", sends == 2u && region_known);
    check("missed fix never resends stale position", last_payload.size() == 40u &&
          last_payload[0] == 0u && last_payload[1] == 0u &&
          last_payload[2] == 0u && last_payload[3] == 0u &&
          last_payload[4] == 0u && last_payload[5] == 0u &&
          last_payload[6] == 0u && last_payload[7] == 0u);
    check("second sleep persists saturated expired age", region_fix_age_sec == 2664u &&
          retained(2047u, TAMP_REGION_AUTHORITY_GNSS));
    cycle();
    check("second missed fix revokes RF but still acquires", saw("acquire") &&
          !region_known && joined && sends == 2u);
    cycle();
    check("expired authority still acquires GNSS", saw("acquire") && sends == 2u);
    in.fix = true;
    cycle();
    check("fresh fix recovers expired retained session", region_known &&
          sends == 3u && joins == 1u && retained(1332u, TAMP_REGION_AUTHORITY_GNSS));

    reset();
    in.gps_power = false;
    in.tx_power = false;
    in.fix = true;
    cycle();
    check("low rail cannot acquire or mint authority", saw("power-skip") &&
          !saw("acquire") && retained_word == 0u && sends == 0u);
    in.gps_power = in.tx_power = true;
    cycle();
    check("power recovery retries acquisition and reaches primary", saw("acquire") &&
          region_known && joins == 1u && sends == 1u);

    reset();
    in.fix = true;
    in.save_ok = false;
    cycle();
    check("failed authority save suppresses join and primary", !region_known &&
          !region_lease_trusted && retained_word == 0u && joins == 0u && sends == 0u);
    in.save_ok = true;
    cycle();
    check("later fresh fix recovers save failure", region_known && sends == 1u);

    reset();
    in.fix = true;
    in.clear_ok = false;
    cycle();
    check("failed old-session clear cannot publish fresh authority", !region_known &&
          !saw("authority-save") && sends == 0u);
    in.clear_ok = true;
    cycle();
    check("unjoined same-region retry recovers clear failure", region_known && sends == 1u);

    reset();
    region_known = region_lease_trusted = true;
    region_authority_source = TAMP_REGION_AUTHORITY_LAUNCH;
    region_authority_region = LORA_REGION_US915;
    join_retry_skip = 2u;
    join_backoff_exp = 2u;
    in.fix = true;
    cycle();
    check("same-region GNSS takeover clears launch join backoff", joins == 1u &&
          sends == 1u && join_retry_skip == 0u &&
          retained(1332u, TAMP_REGION_AUTHORITY_GNSS));

    reset();
    burst_mode = joined = true;
    cycle();
    check("burst main caller forbids cold extension", saw("acquire") &&
          last_gps_budget == 10000u && !last_allow_cold);
    std::printf("main GNSS/region sequence: %u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
'''.replace("@HELPERS@", helpers).replace(
        "@ACQUISITION@", main[acquisition_start:acquisition_end]
    ).replace("@AUTHORITY@", main[authority_start:authority_end]).replace(
        "@JOIN@", join
    ).replace("@PRIMARY@", primary).replace(
        "@ACCOUNTING@", main[accounting_start:accounting_end]
    )


def main() -> None:
    source = harness()
    before = "if (gps_attempted_this_cycle) {"
    assert source.count(before) == 1, "acquisition mutation boundary changed"
    variants = {
        "authority-gates-gnss": source.replace(
            before, "if (gps_attempted_this_cycle && region_known) {"),
        "cold-permission-inverted": source.replace(
            "gps_timeout_ms, !burst_mode", "gps_timeout_ms, burst_mode"),
        "real": source,
    }
    with tempfile.TemporaryDirectory(prefix="stratolink-main-region-") as directory:
        for name, code in variants.items():
            binary = Path(directory) / name
            subprocess.run([
                os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
                "-Werror", "-pedantic", "-fno-omit-frame-pointer",
                "-fsanitize=address,undefined", "-I", str(ROOT / "firmware/include"),
                "-x", "c++", "-", str(ROOT / "firmware/src/region_manager.cpp"),
                str(ROOT / "firmware/src/telemetry.cpp"), "-o", str(binary),
            ], input=code, text=True, check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True,
                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                     "UBSAN_OPTIONS": "halt_on_error=1"})
            assert not result.stderr, result.stderr
            if name == "real":
                assert result.returncode == 0, result.stdout
            elif name == "authority-gates-gnss":
                assert result.returncode == 1, result.stdout
                assert "FAIL unknown authority still acquires GNSS" in result.stdout
                assert "FAIL fresh fix restores absent authority and primary" in result.stdout
            else:
                assert result.returncode == 1, result.stdout
                assert "FAIL ordinary main caller explicitly permits cold extension" in result.stdout
                assert "FAIL burst main caller forbids cold extension" in result.stdout
            print(name + ": " + result.stdout.strip())
    print("PASS: real main sequence; compiled authority-deadlock and inverted-cold-permission mutants rejected")


if __name__ == "__main__":
    main()
