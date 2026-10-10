#!/usr/bin/env python3
"""Characterize GPS-loss silence using the real regional gate and age policy.

This executes the complete production region_tx_allowed_now helper, not a
replacement Boolean gate. GNSS outcomes and cycle timing are scenario inputs;
this is not MCU/whole-loop emulation or proof of the bench failure's cause.
Two compiled mutants prove that permitting an expired lease or suppressing a
usable lease fails the independently specified sequence assertions.
"""

import os
from pathlib import Path
import subprocess
import tempfile

from short_sleep_region_accounting_test import block


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    source = (ROOT / "firmware/src/main.cpp").read_text()
    gate = block(source, "static bool region_tx_allowed_now(")
    harness = r'''
#include "region_manager.h"
#include <cstdio>
static uint32_t now_ms, region_fix_age_sec;
static bool region_known;
static uint32_t millis() { return now_ms; }
@GATE@
static unsigned failures;
static void check(const char* name, bool actual, bool expected) {
    if (actual != expected) {
        ++failures;
        std::printf("FAIL %s: got=%u expected=%u age=%u known=%u\n",
                    name, actual, expected, region_fix_age_sec, region_known);
    }
}
int main() {
    // Fresh accepted GNSS authority is the initial scenario input.
    region_known = true;
    region_fix_age_sec = 0u;
    now_ms = 0u;
    check("fresh authority transmits", region_tx_allowed_now(0u), true);

    // Thirty seconds active plus a nominal1200s sleep costs30+1302s.
    region_fix_age_sec = region_fix_age_after_sleep(0u, 30000u, 1200000u);
    check("first sleep conservatively charged", region_fix_age_sec == 1332u, true);
    now_ms = 30000u;
    check("first no-fix retains legal telemetry", region_tx_allowed_now(0u), true);
    check("first miss keeps region known", region_known, true);

    region_fix_age_sec = region_fix_age_after_sleep(
        region_fix_age_sec, 30000u, 1200000u);
    check("second sleep conservatively charged", region_fix_age_sec == 2664u, true);
    check("second no-fix suppresses telemetry", region_tx_allowed_now(0u), false);
    check("expiry revokes region-known state", region_known, false);
    now_ms = 0u;
    check("later wake does not restore expired authority", region_tx_allowed_now(0u), false);

    // A genuinely accepted fix renews authority; merely keeping a LoRaWAN
    // session would not do this. No test pretends to acquire a physical fix.
    region_fix_age_sec = 0u;
    region_known = true;
    check("new GNSS authority permits recovery", region_tx_allowed_now(0u), true);

    region_fix_age_sec = 1798u;
    check("two seconds remaining permits short frame", region_tx_allowed_now(0u), true);
    now_ms = 1u;
    check("partial second consumes close guard", region_tx_allowed_now(0u), false);

    region_known = true;
    region_fix_age_sec = 1332u;
    now_ms = 29999u;
    check("millis wrap retains same thirty-second charge",
          region_tx_allowed_now(UINT32_MAX), true);
    std::printf("GPS-loss regional sequence: %u failures\n", failures);
    return failures ? 1 : 0;
}
'''
    old = "region_known = false;\n        return false;"
    assert gate.count(old) == 1
    assert gate.count("return true;") == 1
    variants = {
        "real": gate,
        "allow-expired": gate.replace(old, "region_known = true;\n        return true;"),
        "suppress-valid": gate.replace("return true;", "return false;"),
    }
    with tempfile.TemporaryDirectory(prefix="stratolink-region-sequence-") as tmp:
        for name, variant in variants.items():
            binary = Path(tmp) / name
            subprocess.run([
                os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
                "-Werror", "-pedantic", "-fno-omit-frame-pointer",
                "-fsanitize=address,undefined", "-I", str(ROOT / "firmware/include"),
                "-x", "c++", "-", str(ROOT / "firmware/src/region_manager.cpp"),
                "-o", str(binary),
            ], input=harness.replace("@GATE@", variant), text=True, check=True)
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True,
                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                     "UBSAN_OPTIONS": "halt_on_error=1"},
            )
            if name == "real":
                assert result.returncode == 0, result.stdout + result.stderr
            else:
                expected_failure = ("second no-fix suppresses telemetry"
                                    if name == "allow-expired"
                                    else "fresh authority transmits")
                assert result.returncode == 1, result.stdout + result.stderr
                assert "FAIL " + expected_failure in result.stdout
            assert not result.stderr, result.stderr
            print(name + ": " + result.stdout.strip())
    print("PASS: real regional sequence; both unsafe compiled mutants rejected")


if __name__ == "__main__":
    main()
