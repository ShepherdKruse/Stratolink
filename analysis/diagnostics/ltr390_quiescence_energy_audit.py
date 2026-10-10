#!/usr/bin/env python3
"""Source-bound energy screen for an LTR390 left active after I2C failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "firmware/src/sensor_ltr390.cpp"
MAIN = ROOT / "firmware/src/main.cpp"
CONFIG = ROOT / "firmware/include/config.h"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def macro(source: str, name: str) -> int:
    match = re.search(rf"^#define\s+{name}\s+(\d+)(?:u)?\s*$", source, re.MULTILINE)
    if not match:
        raise SystemExit(f"missing integer macro {name}")
    return int(match.group(1))


def energy_j(seconds: int, current_a: float, supply_v: float = 3.3,
             efficiency: float = 0.85) -> float:
    return seconds * current_a * supply_v / efficiency


def build_report() -> dict[str, object]:
    driver = DRIVER.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    source_gate = (
        "static bool standby_readback(void)" in driver
        and "read_reg(LTR390_REG_MAIN_CTRL, &control)" in driver
        and "bool sensor_ltr390_quiesce(void)" in driver
        and "reset_to_standby_readback()" in driver
        and "s_optical_quiescence_fault" in main
        and "SENSOR_QUIESCE_RETRY_SLEEP_MS" in main
        and "SENSOR_QUIESCE_FAST_RETRIES" in main
        and "optical_fault_consume_fast_retry(" in main
        and "&s_optical_quiet_retries" in main
        and main.count("if (!s_optical_quiescence_fault)") >= 3
        and "#define SENSOR_QUIESCE_FAST_RETRIES" in config
    )
    if not source_gate:
        raise SystemExit("LTR390 quiescence containment is absent or incomplete")

    minimum_reserve_j = 0.5 * 0.8 * (4.66**2 - 3.32**2)
    intervals = sorted({
        macro(config, "SLEEP_INTERVAL_FULL_SEC"),
        macro(config, "SLEEP_INTERVAL_REDUCED_SEC"),
        macro(config, "SLEEP_INTERVAL_NO_GPS_SEC"),
        macro(config, "SLEEP_INTERVAL_EMERGENCY_SEC"),
    })
    exposure = []
    for seconds in intervals:
        gross = energy_j(seconds, 200e-6)
        incremental = energy_j(seconds, 190e-6)
        exposure.append({
            "seconds": seconds,
            "gross_active_energy_j": round(gross, 6),
            "increment_over_10ua_standby_j": round(incremental, 6),
            "gross_fraction_minimum_cap_reserve": round(
                gross / minimum_reserve_j, 6
            ),
        })

    return {
        "audit": "ltr390_quiescence_energy",
        "scope": (
            "Analytic screen from Lite-On LTR-390UV-01 Rev. 1.7 maximum "
            "active/standby currents; exact-assembly PPK2 remains required."
        ),
        "manufacturer_source": (
            "https://optoelectronics.liteon.com/upload/download/"
            "DS86-2015-0004/LTR-390UV-01_Final_%20DS_V1.7.PDF"
        ),
        "assumptions": {
            "active_current_max_a": 0.0002,
            "standby_current_max_a": 0.00001,
            "supply_v": 3.3,
            "converter_efficiency": 0.85,
            "minimum_capacitance_f": 0.8,
            "vstor_start_v": 4.66,
            "conservative_endpoint_v": 3.32,
        },
        "minimum_cap_reserve_j": round(minimum_reserve_j, 6),
        "mission_interval_exposure": exposure,
        "recovery_interval_seconds": (
            macro(config, "SENSOR_QUIESCE_RETRY_SLEEP_MS") // 1000
        ),
        "fast_retry_count": macro(config, "SENSOR_QUIESCE_FAST_RETRIES"),
        "source_gate": {
            "contained": source_gate,
            "contract": (
                "read-back-confirmed standby with verified software-reset "
                "fallback and bounded fast quiet retries; a persistent fault "
                "then resumes normal degraded primary GPS/TTN cadence while "
                "optical reads and auxiliary services remain suppressed"
            ),
            "driver_sha256": sha256(DRIVER),
            "main_sha256": sha256(MAIN),
            "config_sha256": sha256(CONFIG),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(build_report(), indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
