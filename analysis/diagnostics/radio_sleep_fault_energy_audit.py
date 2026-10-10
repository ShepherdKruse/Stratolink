#!/usr/bin/env python3
"""Quantify the reserve exposed by an unquiesced SX1262 idle interval."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LORAWAN = ROOT / "firmware/src/lorawan.cpp"
CONFIG = ROOT / "firmware/include/config.h"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def macro_seconds(source: str, name: str) -> int:
    match = re.search(rf"^#define\s+{name}\s+(\d+)\s*$", source, re.MULTILINE)
    if not match:
        raise SystemExit(f"missing integer macro {name}")
    return int(match.group(1))


def usable_cap_energy_j(capacitance_f: float, high_v: float, low_v: float) -> float:
    return 0.5 * capacitance_f * (high_v * high_v - low_v * low_v)


def unquiesced_energy_j(
    seconds: int, radio_v: float = 3.3, standby_a: float = 0.0006,
    efficiency: float = 0.85,
) -> float:
    return radio_v * standby_a * seconds / efficiency


def build_report() -> dict[str, object]:
    source = LORAWAN.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    start = source.index("void lorawan_sleep(void)")
    end = source.index("/* ========== Meshtastic open-relay", start)
    sleep = source[start:end]
    contained = (
        "if (!radio_ready) return;" not in sleep
        and "if (!lorawan_init() ||" in sleep
        and "(retry_state = radio->sleep(true)) != RADIOLIB_ERR_NONE" in sleep
        and "NVIC_SystemReset();" in sleep
    )
    if not contained:
        raise SystemExit("radio sleep containment is absent or incomplete")

    intervals = {
        name: macro_seconds(config, name)
        for name in (
            "SLEEP_INTERVAL_FULL_SEC",
            "SLEEP_INTERVAL_REDUCED_SEC",
            "SLEEP_INTERVAL_NO_GPS_SEC",
            "SLEEP_INTERVAL_EMERGENCY_SEC",
        )
    }
    min_cap_energy = usable_cap_energy_j(0.8, 4.66, 3.32)
    nominal_cap_energy = usable_cap_energy_j(1.0, 4.66, 3.32)
    exposure = {}
    for name, seconds in intervals.items():
        energy = unquiesced_energy_j(seconds)
        exposure[name] = {
            "seconds": seconds,
            "unquiesced_radio_energy_j": round(energy, 6),
            "fraction_minimum_cap_reserve": round(energy / min_cap_energy, 6),
            "fraction_nominal_cap_reserve": round(energy / nominal_cap_energy, 6),
        }

    return {
        "audit": "radio_sleep_fault_energy",
        "scope": (
            "Analytic screen using the documented SX1262 STDBY_RC current; "
            "not a substitute for final-assembly PPK2 measurement."
        ),
        "assumptions": {
            "radio_supply_v": 3.3,
            "standby_rc_a": 0.0006,
            "converter_efficiency": 0.85,
            "vstor_start_v": 4.66,
            "conservative_endpoint_v": 3.32,
            "minimum_capacitance_f": 0.8,
            "nominal_capacitance_f": 1.0,
        },
        "reserve": {
            "minimum_capacitance_j": round(min_cap_energy, 6),
            "nominal_capacitance_j": round(nominal_cap_energy, 6),
        },
        "sleep_intervals": exposure,
        "source_gate": {
            "contained": contained,
            "contract": "confirmed radio sleep or bounded reinit then reset",
            "lorawan_cpp_sha256": sha256(LORAWAN),
            "config_h_sha256": sha256(CONFIG),
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
