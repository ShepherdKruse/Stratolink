#!/usr/bin/env python3
"""Prove why Flight-3's ~3.32 V plateau is not brownout metrology."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
FLIGHT_COMMIT = "c4bd109"
FLIGHT_ADC_PATH = "firmware/src/power_adc.cpp"
CURRENT_ADC_PATH = ROOT / FLIGHT_ADC_PATH
ADC_HEADER_PATH = ROOT / "firmware/include/power_adc.h"
ADC_TEST_PATH = ROOT / "firmware/test/test_power_adc_policy.cpp"
TELEMETRY_PATH = ROOT / "analysis/antenna/data/telemetry_raw.csv"
LAUNCH_UTC = datetime.fromisoformat("2026-05-17T15:00:00+00:00")
TELEMETRY_PLATEAU_MAX_V = 3.35


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def flown_source(root: Path = ROOT) -> str:
    return subprocess.check_output(
        ["git", "show", f"{FLIGHT_COMMIT}:{FLIGHT_ADC_PATH}"],
        cwd=root,
        text=True,
    )


def audit(root: Path = ROOT) -> dict[str, object]:
    old = flown_source(root)
    current = (root / FLIGHT_ADC_PATH).read_text(encoding="utf-8")
    header = (root / ADC_HEADER_PATH.relative_to(ROOT)).read_text(encoding="utf-8")
    policy_test = (root / ADC_TEST_PATH.relative_to(ROOT)).read_text(encoding="utf-8")
    if "#define ADC_VREF_MV_NOMINAL 3300" not in old:
        raise ValueError("flown nominal ADC reference drift")
    if "(void)s_vdda_mv;" not in old:
        raise ValueError("flown source no longer proves cached VREFINT was ignored")
    if "if (channel == ADC_CHANNEL_6) refresh_vdda_mv();" not in current:
        raise ValueError("current VSTOR path no longer refreshes VREFINT")
    if "if (vdda_mv == 0) return 0;" not in current:
        raise ValueError("current invalid-reference path no longer fails closed")
    if "if (HAL_ADCEx_Calibration_Start(&s_hadc) != HAL_OK) return;" not in current:
        raise ValueError("current ADC calibration failure no longer fails closed")
    if current.count("if (!adc_initialized) return 0;") != 2:
        raise ValueError("current VSTOR/solar init-failure guards drifted")
    if "power_adc_vdda_from_vrefint" not in current or \
       "uint32_t measured_mv" not in header:
        raise ValueError("current VREFINT conversion no longer validates before narrowing")
    if "assert(power_adc_vdda_from_vrefint(1200, 10, 3300) == 0);" not in policy_test:
        raise ValueError("pre-narrowing VREFINT alias regression is absent")

    telemetry_path = root / TELEMETRY_PATH.relative_to(ROOT)
    rows: list[dict[str, object]] = []
    with telemetry_path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if not raw["device_id"].startswith("stratolink-3"):
                continue
            if not raw["time"]:
                continue
            time = parse_utc(raw["time"])
            if time < LAUNCH_UTC or not raw["battery_voltage"]:
                continue
            rows.append(
                {
                    "time": time,
                    "device_id": raw["device_id"],
                    "vstor_v": float(raw["battery_voltage"]),
                    "solar_v": float(raw["solar_voltage"]),
                    "temperature_c": float(raw["temperature"]),
                }
            )
    rows.sort(key=lambda row: row["time"])
    plateau = [row for row in rows if row["vstor_v"] <= TELEMETRY_PLATEAU_MAX_V]
    if not plateau:
        raise ValueError("no post-launch low-rail telemetry")

    gaps_after: list[float] = []
    for index, row in enumerate(rows[:-1]):
        if row["vstor_v"] <= TELEMETRY_PLATEAU_MAX_V:
            gaps_after.append(
                (rows[index + 1]["time"] - row["time"]).total_seconds() / 3600.0
            )

    gates = {
        "flown_source_ignored_runtime_vdda_for_conversion": True,
        "current_source_refreshes_runtime_vdda_each_vstor_read": True,
        "current_source_invalid_reference_fails_closed": True,
        "current_source_init_and_calibration_failures_fail_closed": True,
        "current_source_rejects_pre_narrowing_vrefint_alias": True,
        "historical_3v32_is_actual_vstor_or_brownout_metrology": False,
        "exact_final_image_low_rail_adc_tx_reset_hil_passed": False,
    }
    return {
        "passed": all(gates.values()),
        "status": "BLOCKED_HISTORICAL_FLOOR_IS_NOT_BROWNOUT_METROLOGY",
        "flown_source": {
            "commit": FLIGHT_COMMIT,
            "path": FLIGHT_ADC_PATH,
            "conversion": (
                "VSTOR ADC used a fixed 3300 mV reference and explicitly "
                "ignored the cached runtime VREFINT-derived VDDA"
            ),
        },
        "dropout_observability": {
            "equation": (
                "reported_vstor = actual_vstor * 3.3 / runtime_vdda; when "
                "buck-dropout VDDA tracks actual_vstor, the actual_vstor term "
                "largely cancels and telemetry approaches a false plateau"
            ),
            "consequence": (
                "the lowest received value bounds neither actual VSTOR nor MCU "
                "BOR. Gaps and sunrise recovery support a low-energy episode "
                "but cannot distinguish TX sag, reset, sleep cutoff, or coverage"
            ),
        },
        "post_launch_telemetry": {
            "rows": len(rows),
            "plateau_rows_at_or_below_3v35": len(plateau),
            "minimum_reported_v": min(row["vstor_v"] for row in plateau),
            "maximum_reported_v_in_plateau": max(row["vstor_v"] for row in plateau),
            "minimum_temperature_c_in_plateau": min(
                row["temperature_c"] for row in plateau
            ),
            "maximum_following_gap_h": max(gaps_after) if gaps_after else None,
        },
        "current_source_boundary": (
            "the current source refreshes VREFINT immediately before VSTOR, "
            "checks the full-width result before narrowing, and returns zero "
            "on an invalid 1.8-3.6 V VDDA estimate. Host policy tests prove "
            "the former wrap-alias fault and other fail-closed decisions, but "
            "final-image low-rail ADC "
            "accuracy and TX survival still require physical sweep evidence"
        ),
        "modeling_rule": (
            "3.32 V may remain a deliberately conservative accounting floor, "
            "but must be labeled the Flight-3 reported plateau—not a measured "
            "brownout threshold or available-energy endpoint"
        ),
        "required_hil": (
            "After preserving the soak, sweep PPK2 VSTOR downward with the exact "
            "candidate and then the fitted supercap. Simultaneously measure "
            "VSTOR, VOUT/VDDA, ADC telemetry error, reset/boot counters, and "
            "successful join/primary/aux TX through room and cold load steps. "
            "Set TX and tier floors only from the bounded result plus margin"
        ),
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite VSTOR-floor evidence: {args.output}")
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
