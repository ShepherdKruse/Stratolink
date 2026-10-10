#!/usr/bin/env python3
"""Execute the flight loop's short-sleep branches against controlled clocks."""

from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def block(source: str, opening: str) -> str:
    start = source.index(opening)
    brace = source.index("{", start)
    depth = 0
    for end in range(brace, len(source)):
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
            if depth == 0:
                return source[start:end + 1]
    raise AssertionError(f"unterminated block: {opening}")


def main() -> None:
    source = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
    spurious = block(source, "if (spurious_freefall_wake) {")
    optical = block(
        source,
        "if (s_optical_quiescence_fault && !freefall_wake && !burst_mode)",
    )
    harness = r'''
#include "config.h"
#include "region_manager.h"
#include "optical_fault_policy.h"
#include <cstdio>
#include <cstdint>

static uint32_t now_ms, region_fix_age_sec, persisted_age, slept_ms;
static unsigned saves;
static bool spurious_freefall_wake = true;
static bool s_optical_quiescence_fault = true;
static bool freefall_wake = false, burst_mode = false;
static uint8_t s_optical_quiet_retries;
static uint32_t millis() { return now_ms; }
static void gps_ublox_quiesce() { now_ms += 1123u; }
void lorawan_sleep() { now_ms += 877u; }
static void sensors_recover_i2c_bus() { now_ms += 450u; }
static bool sensor_ltr390_quiesce() { now_ms += 550u; return false; }
static void persist_region_lease_if_trusted() {
    persisted_age = region_fix_age_sec;
    ++saves;
}
static void power_manager_sleep_ms(uint32_t duration_ms) {
    slept_ms = duration_ms;
}
static void spurious_cycle(uint32_t cycle_started_ms) {
    (void)cycle_started_ms;
    (void)millis();
''' + spurious + r'''
}
static void optical_cycle(uint32_t cycle_started_ms) {
    (void)cycle_started_ms;
''' + optical + r'''
}

int main() {
    struct Case {
        const char* name;
        void (*cycle)(uint32_t);
        uint32_t age, started, now, expected;
    };
    const Case cases[] = {
        {"spurious awake + slow RTC", spurious_cycle, 100u, 0u, 1000u, 169u},
        {"optical awake + slow RTC", optical_cycle, 100u, 0u, 1000u, 170u},
        {"spurious partial awake second", spurious_cycle, 100u, 0u, 1001u, 170u},
        {"optical partial awake second", optical_cycle, 100u, 0u, 1001u, 171u},
        {"spurious millis wrap", spurious_cycle, 100u, UINT32_MAX - 999u, 0u, 169u},
        {"optical millis wrap", optical_cycle, 100u, UINT32_MAX - 999u, 0u, 170u},
        {"spurious maximum awake delta", spurious_cycle, 100u, 0u, UINT32_MAX - 2000u, 4295134u},
        {"optical maximum awake delta", optical_cycle, 100u, 0u, UINT32_MAX - 3000u, 4295134u},
        {"spurious deadline", spurious_cycle, 1731u, 0u, 1000u, 1800u},
        {"optical deadline", optical_cycle, 1730u, 0u, 1000u, 1800u},
        {"spurious saturated age", spurious_cycle, UINT32_MAX - 10u, 0u, 1000u, UINT32_MAX},
        {"optical saturated age", optical_cycle, UINT32_MAX - 10u, 0u, 1000u, UINT32_MAX},
    };
    unsigned failures = 0u;
    for (const Case& tc : cases) {
        region_fix_age_sec = tc.age;
        now_ms = tc.now;
        saves = slept_ms = 0u;
        s_optical_quiet_retries = 0u;
        tc.cycle(tc.started);
        if (region_fix_age_sec != tc.expected || persisted_age != tc.expected ||
            saves != 1u || slept_ms != 60000u ||
            (tc.expected >= 1800u && region_fix_remaining_tx_ms(persisted_age))) {
            std::printf("FAIL %s: age=%u persisted=%u expected=%u saves=%u sleep=%u\n",
                        tc.name, region_fix_age_sec, persisted_age, tc.expected,
                        saves, slept_ms);
            ++failures;
        }
    }
    region_fix_age_sec = 1450u;
    s_optical_quiet_retries = 0u;
    saves = 0u;
    for (unsigned retry = 0u; retry < 5u; ++retry) {
        now_ms = 1000u;
        optical_cycle(0u);
    }
    if (persisted_age != 1800u || saves != 5u || s_optical_quiet_retries != 5u ||
        region_fix_remaining_tx_ms(persisted_age)) {
        std::printf("FAIL optical retries: persisted=%u expected=1800 saves=%u retries=%u\n",
                    persisted_age, saves, s_optical_quiet_retries);
        ++failures;
    }
    std::printf("Short-sleep flight branches: %u failures\n", failures);
    return failures ? 1 : 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="stratolink-short-sleep-") as tmp:
        binary = Path(tmp) / "short_sleep"
        subprocess.run(
            [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
             "-Werror", "-pedantic", "-fno-omit-frame-pointer",
             "-fsanitize=address,undefined", "-I", str(ROOT / "firmware/include"),
             "-x", "c++", "-", str(ROOT / "firmware/src/region_manager.cpp"),
             "-o", str(binary)],
            input=harness, text=True, check=True,
        )
        subprocess.run(
            [str(binary)], check=True,
            env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                 "UBSAN_OPTIONS": "halt_on_error=1"},
        )


if __name__ == "__main__":
    main()
