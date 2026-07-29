#!/usr/bin/env python3
"""Lower-bound energy-store sizing for the planned StratoLink-2 mission.

The existing night-reserve audit intentionally excludes active work. This
audit adds only the already-source-bound typical hot-GNSS, primary-TX, and
mandatory empty Class-A RX energy. It still excludes sensors, MCU current in
shallow WFI, joins/retries, auxiliary RF, cold, aging, cloud, attitude, ESR,
conversion variation, and shutdown/recovery failures. Its required
capacitances are therefore lower bounds, never flight ratings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from class_a_energy_audit import build_audit as build_class_a_audit
from supercap_charge_ceiling_audit import (
    BOTTOM_VALUE_MOHM,
    BQ25570_OPERATING_MAX_C,
    BQ25570_OPERATING_MIN_C,
    DIVIDER_REFERENCE_TEMP_C,
    DIVIDER_TCR_PPM_PER_C,
    DIVIDER_TOLERANCE,
    THRESHOLD_ACCURACY,
    SUPERCAP_MAX_CAPACITANCE_F,
    SUPERCAP_MIN_CAPACITANCE_F,
    SUPERCAP_NOMINAL_CAPACITANCE_F,
    ceiling_v,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NIGHT_RESERVE = (
    ROOT / "analysis/diagnostics/logs/stratolink2_supercap_night_reserve_20260726.json"
)
DEFAULT_BALANCE = (
    ROOT / "analysis/diagnostics/logs/stratolink2_supercap_balance_20260726.json"
)
DEFAULT_AIRTIME = (
    ROOT / "analysis/diagnostics/logs/stratolink2_regional_airtime_20260726.json"
)
DEFAULT_DARKNESS = (
    ROOT / "analysis/diagnostics/logs/stratolink2_friday_darkness_envelope_20260727.json"
)
CONFIG = ROOT / "firmware/include/config.h"
PINS = ROOT / "firmware/include/stratolink_pins.h"
LEGACY_POWER_MODEL = ROOT / "analysis/power/relay_power_budget.py"

RAIL_V = 3.3
CONVERTER_EFFICIENCY = 0.85
SELECTED_TOP_MOHM = (7.32, 7.50)
EXTRA_DURATION_HOURS = (12.0, 16.0)


def record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def source_number(text: str, pattern: str, label: str) -> float:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing source-bound {label}")
    return float(match.group(1))


def lower_screen_ceiling_v(top_mohm: float) -> float:
    """Opposite ratio/threshold/TCR corner from the existing upper screen."""
    temperature_delta_c = max(
        abs(BQ25570_OPERATING_MIN_C - DIVIDER_REFERENCE_TEMP_C),
        abs(BQ25570_OPERATING_MAX_C - DIVIDER_REFERENCE_TEMP_C),
    )
    return ceiling_v(
        top_mohm,
        BOTTOM_VALUE_MOHM,
        -DIVIDER_TOLERANCE,
        -THRESHOLD_ACCURACY,
        -DIVIDER_TCR_PPM_PER_C,
        temperature_delta_c,
    )


def discharge_simulation(
    capacitance_f: float,
    start_v: float,
    floor_v: float,
    duration_h: float | None,
    base_current_ua: float,
    full_threshold_v: float,
    gps_floor_v: float,
    class_a_floor_v: float,
    tx_floor_v: float,
    full_cadence_s: int,
    reduced_cadence_s: int,
    gps_energy_j: float,
    tx_energy_j: float,
    class_a_energy_j: float,
) -> dict[str, object]:
    values = (
        capacitance_f,
        start_v,
        floor_v,
        base_current_ua,
        full_threshold_v,
        gps_floor_v,
        class_a_floor_v,
        tx_floor_v,
        gps_energy_j,
        tx_energy_j,
        class_a_energy_j,
    )
    if any(value <= 0.0 for value in values):
        raise ValueError("energy simulation inputs must be positive")
    if not start_v > full_threshold_v > gps_floor_v > class_a_floor_v > floor_v:
        raise ValueError("energy simulation voltage ordering is invalid")
    if not class_a_floor_v > tx_floor_v:
        raise ValueError("Class-A floor must exceed the TX floor")
    if full_cadence_s <= 0 or reduced_cadence_s <= 0:
        raise ValueError("cadences must be positive")
    if duration_h is not None and duration_h <= 0.0:
        raise ValueError("duration must be positive")

    target_s = None if duration_h is None else duration_h * 3600.0
    energy_j = 0.5 * capacitance_f * start_v**2
    floor_energy_j = 0.5 * capacitance_f * floor_v**2
    elapsed_s = 0.0
    next_cycle_s = 0.0  # worst phase: darkness starts immediately before a cycle
    counts = {"cycles": 0, "gps": 0, "tx": 0, "class_a": 0}

    while energy_j > floor_energy_j:
        if target_s is not None and elapsed_s >= target_s:
            break
        voltage_v = (2.0 * energy_j / capacitance_f) ** 0.5
        if elapsed_s >= next_cycle_s - 1e-9:
            counts["cycles"] += 1
            if voltage_v >= gps_floor_v:
                energy_j -= gps_energy_j
                counts["gps"] += 1
                if energy_j <= floor_energy_j:
                    break
                voltage_v = (2.0 * energy_j / capacitance_f) ** 0.5
            if voltage_v >= tx_floor_v:
                energy_j -= tx_energy_j
                counts["tx"] += 1
                if energy_j <= floor_energy_j:
                    break
                voltage_v = (2.0 * energy_j / capacitance_f) ** 0.5
            if voltage_v >= class_a_floor_v:
                energy_j -= class_a_energy_j
                counts["class_a"] += 1
                if energy_j <= floor_energy_j:
                    break
                voltage_v = (2.0 * energy_j / capacitance_f) ** 0.5
            cadence_s = (
                full_cadence_s
                if voltage_v >= full_threshold_v
                else reduced_cadence_s
            )
            next_cycle_s = elapsed_s + cadence_s

        voltage_v = (2.0 * energy_j / capacitance_f) ** 0.5
        seconds_to_floor = (
            capacitance_f * (voltage_v - floor_v) / (base_current_ua * 1e-6)
        )
        step_s = min(next_cycle_s - elapsed_s, seconds_to_floor)
        if target_s is not None:
            step_s = min(step_s, target_s - elapsed_s)
        if step_s <= 0.0:
            raise RuntimeError("energy simulation did not advance")
        voltage_v -= base_current_ua * 1e-6 * step_s / capacitance_f
        energy_j = 0.5 * capacitance_f * voltage_v**2
        elapsed_s += step_s

    survived = target_s is not None and elapsed_s >= target_s - 1e-6
    end_v = max(floor_v, (2.0 * max(energy_j, 0.0) / capacitance_f) ** 0.5)
    return {
        "survived_target": survived,
        "elapsed_hours": elapsed_s / 3600.0,
        "end_v": end_v,
        **counts,
    }


def required_capacitance_f(duration_h: float, **inputs: object) -> float:
    low_f = 0.01
    high_f = 16.0
    for _ in range(80):
        midpoint_f = (low_f + high_f) / 2.0
        result = discharge_simulation(
            midpoint_f, duration_h=duration_h, **inputs
        )
        if result["survived_target"]:
            high_f = midpoint_f
        else:
            low_f = midpoint_f
    return high_f


def build_audit(
    night_reserve_path: Path,
    balance_path: Path,
    airtime_path: Path,
    darkness_path: Path,
) -> dict[str, object]:
    night_reserve = json.loads(night_reserve_path.read_text(encoding="utf-8"))
    balance = json.loads(balance_path.read_text(encoding="utf-8"))
    airtime = json.loads(airtime_path.read_text(encoding="utf-8"))
    darkness = json.loads(darkness_path.read_text(encoding="utf-8"))
    config = CONFIG.read_text(encoding="utf-8")
    pins = PINS.read_text(encoding="utf-8")
    power_model = LEGACY_POWER_MODEL.read_text(encoding="utf-8")

    if night_reserve.get("passed") is not False or darkness.get("passed") is not False:
        raise ValueError("expected fail-closed darkness inputs")
    if airtime.get("passed") is not True:
        raise ValueError("regional airtime input did not pass")

    night_inputs = night_reserve["inputs"]
    sleep_values = night_inputs.get("conservative_legacy_sleep_screen_ua")
    if sleep_values is None:
        # Accept immutable evidence generated before the input was renamed.
        # The numeric screen is unchanged; only its provenance label was
        # corrected after the exact v15 STOP1 measurement.
        sleep_values = night_inputs.get(
            "documented_ppk2_jlink_attached_sleep_upper_bound_ua"
        )
    if not isinstance(sleep_values, list) or not sleep_values:
        raise ValueError("night-reserve sleep-current screen is missing")
    sleep_ua = max(float(value) for value in sleep_values)
    leakage_ua = float(night_reserve["inputs"]["supercap_leakage_max_ua"])
    balance_ua = float(
        balance["active_tlv8801_reference_not_yet_designed_or_qualified"]
        ["screening_circuit_overhead_ua_excluding_cap_leakage"]
    )
    base_current_ua = sleep_ua + leakage_ua + balance_ua
    evidence_minimum_capacitance_f = float(
        night_reserve["inputs"]["supercap_min_capacitance_f"]
    )
    if evidence_minimum_capacitance_f != SUPERCAP_MIN_CAPACITANCE_F:
        raise ValueError("minimum-capacitance evidence drifted")
    specified_capacitance_f = {
        "minimum": SUPERCAP_MIN_CAPACITANCE_F,
        "nominal": SUPERCAP_NOMINAL_CAPACITANCE_F,
        "maximum": SUPERCAP_MAX_CAPACITANCE_F,
    }
    floor_v = float(
        night_reserve["inputs"]["conservative_flight3_reported_plateau_floor_v"]
    )

    full_cadence_s = int(
        source_number(
            config, r"#define SLEEP_INTERVAL_FULL_SEC\s+([0-9]+)", "FULL cadence"
        )
    )
    reduced_cadence_s = int(
        source_number(
            config,
            r"#define SLEEP_INTERVAL_REDUCED_SEC\s+([0-9]+)",
            "REDUCED cadence",
        )
    )
    full_threshold_v = source_number(
        pins, r"#define POWER_TIER_FULL_V\s+([0-9.]+)f", "FULL threshold"
    )
    class_a_floor_v = source_number(
        pins, r"#define POWER_TIER_REDUCED_V\s+([0-9.]+)f", "REDUCED threshold"
    )
    gps_floor_v = source_number(
        config, r"#define GPS_ACQ_FLOOR_MV\s+([0-9]+)u", "GPS floor"
    ) / 1000.0
    tx_floor_v = 3.0  # independently re-read at every RF boundary in main.cpp

    current_match = re.search(
        r"I_GPS, I_MCU\s*=\s*([0-9.]+),\s*([0-9.]+)", power_model
    )
    tx_match = re.search(
        r"I_RX, I_TX14\s*=\s*([0-9.]+),\s*([0-9.]+)", power_model
    )
    hot_match = re.search(r"T_GPS_HOT, TOA_SF9\s*=\s*([0-9.]+),", power_model)
    if current_match is None or tx_match is None or hot_match is None:
        raise ValueError("legacy current-model constants drifted")
    gps_a = float(current_match.group(1))
    mcu_active_a = float(current_match.group(2))
    tx_a = float(tx_match.group(2))
    hot_s = float(hot_match.group(1))
    primary_s = float(airtime["airtime"]["primary_ms"]) / 1000.0
    class_a_energy_j = float(
        build_class_a_audit()["energy_screen"]
        ["actual_empty_radio_rx_typical_j_per_cycle"]
    )
    gps_energy_j = (gps_a + mcu_active_a) * RAIL_V / CONVERTER_EFFICIENCY * hot_s
    tx_energy_j = tx_a * RAIL_V / CONVERTER_EFFICIENCY * primary_s

    darkness_hours = {
        "launch_night": float(darkness["geometric_darkness"]["launch_night"]["hours"]),
        "historical_flight3_longest": 9.674,
        "first_30_days": float(
            darkness["geometric_darkness"]["longest_first_30_days"]["hours"]
        ),
        "first_90_days": float(
            darkness["geometric_darkness"]["longest_modeled"]["hours"]
        ),
        "twelve_hour_screen": EXTRA_DURATION_HOURS[0],
        "sixteen_hour_screen": EXTRA_DURATION_HOURS[1],
    }

    common = {
        "floor_v": floor_v,
        "base_current_ua": base_current_ua,
        "full_threshold_v": full_threshold_v,
        "gps_floor_v": gps_floor_v,
        "class_a_floor_v": class_a_floor_v,
        "tx_floor_v": tx_floor_v,
        "full_cadence_s": full_cadence_s,
        "reduced_cadence_s": reduced_cadence_s,
        "gps_energy_j": gps_energy_j,
        "tx_energy_j": tx_energy_j,
        "class_a_energy_j": class_a_energy_j,
    }

    rows: list[dict[str, object]] = []
    reserve_rows = {float(row["top_mohm"]): row for row in night_reserve["divider_options"]}
    for top_mohm in SELECTED_TOP_MOHM:
        nominal_v = float(reserve_rows[top_mohm]["nominal_ceiling_v"])
        lower_v = lower_screen_ceiling_v(top_mohm)
        cases: dict[str, object] = {}
        for case_name, start_v in (
            ("full_tolerance_lower_charge_screen", lower_v),
            ("nominal_charge_reference", nominal_v),
        ):
            specified_results = {
                label: discharge_simulation(
                    capacitance_f,
                    start_v=start_v,
                    duration_h=None,
                    **common,
                )
                for label, capacitance_f in specified_capacitance_f.items()
            }
            minimum_result = specified_results["minimum"]
            required = {
                label: required_capacitance_f(
                    duration_h, start_v=start_v, **common
                )
                for label, duration_h in darkness_hours.items()
            }
            cases[case_name] = {
                "start_v": round(start_v, 6),
                "minimum_part_survival_hours": round(
                    float(minimum_result["elapsed_hours"]), 3
                ),
                "specified_part_survival_hours": {
                    label: round(float(result["elapsed_hours"]), 3)
                    for label, result in specified_results.items()
                },
                "specified_maximum_part_covers_launch_night": (
                    float(specified_results["maximum"]["elapsed_hours"])
                    >= darkness_hours["launch_night"]
                ),
                "minimum_part_cycle_counts": {
                    key: minimum_result[key]
                    for key in ("cycles", "gps", "tx", "class_a")
                },
                "lower_bound_required_capacitance_f": {
                    key: round(value, 3) for key, value in required.items()
                },
            }
        rows.append({"top_mohm": top_mohm, "cases": cases})

    return {
        "passed": False,
        "status": "BLOCKED_SPECIFIED_PART_RANGE_FAILS_ACTIVE_DARKNESS_SCREEN",
        "scope": (
            "tier-aware lower engineering screen using typical hot-GNSS, "
            "primary-TX, and empty Class-A RX energy; not an endurance model "
            "or part recommendation"
        ),
        "provenance": {
            "night_reserve": record(night_reserve_path),
            "balance_screen": record(balance_path),
            "airtime_screen": record(airtime_path),
            "friday_darkness": record(darkness_path),
            "firmware_config": record(CONFIG),
            "firmware_tier_pins": record(PINS),
            "legacy_current_model": record(LEGACY_POWER_MODEL),
        },
        "inputs": {
            "specified_part_capacitance_f": specified_capacitance_f,
            "floor_v_is_conservative_reported_plateau_not_bor": floor_v,
            "continuous_current_ua": {
                "measured_jlink_attached_sleep_upper": sleep_ua,
                "room_cap_leakage_limit": leakage_ua,
                "unqualified_tlv8801_screening_overhead": balance_ua,
                "total": round(base_current_ua, 6),
            },
            "active_lower_screen_j_per_cycle": {
                "hot_gnss_plus_mcu_typical": round(gps_energy_j, 9),
                "primary_tx_typical": round(tx_energy_j, 9),
                "empty_class_a_radio_rx_typical": round(class_a_energy_j, 9),
                "sum_when_all_three_run": round(
                    gps_energy_j + tx_energy_j + class_a_energy_j, 9
                ),
            },
            "cadence_s": {"full": full_cadence_s, "reduced_or_lower": reduced_cadence_s},
            "voltage_gates_v": {
                "full_cadence": full_threshold_v,
                "gps": gps_floor_v,
                "class_a": class_a_floor_v,
                "tx": tx_floor_v,
            },
            "darkness_hours": darkness_hours,
            "phase_assumption": "darkness begins immediately before an active cycle",
        },
        "divider_sizing": rows,
        "omitted_loads_and_uncertainties": [
            "sensor and microphone energy",
            "MCU current during shallow-WFI Class-A waits",
            "GNSS shutdown, recovery, cold starts, and failed acquisitions",
            "OTAA joins, retries, auxiliary uplinks, Meshtastic, CTT, and B2B",
            "cold capacitance/ESR/leakage, aging, and converter variation",
            "cloud, attitude, frost, trajectory, load-step sag, and actual BOR",
            "energy required to preserve explicit reserve above the accounting floor",
        ],
        "interpretation": (
            "The full specified 0.8-1.2 F part range is materially smaller than "
            "even this lower active-work screen. Required-capacitance results cannot select a "
            "part: every active current is a typical or incomplete engineering "
            "input and the balancer itself is not designed or qualified. They "
            "only prove that baseline-current runtime substantially overstates "
            "mission endurance and that a nominal 1 F architecture has no "
            "credible Friday qualification path."
        ),
        "required_resolution": (
            "Measure complete exact-image cycle energy and fitted-cap behavior, "
            "then size a voltage-safe balanced store above the measured worst-"
            "case requirement with explicit seasonal, weather, cold, aging, "
            "sag, and BOR reserve."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--night-reserve", type=Path, default=DEFAULT_NIGHT_RESERVE)
    parser.add_argument("--balance", type=Path, default=DEFAULT_BALANCE)
    parser.add_argument("--airtime", type=Path, default=DEFAULT_AIRTIME)
    parser.add_argument("--darkness", type=Path, default=DEFAULT_DARKNESS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    result = build_audit(args.night_reserve, args.balance, args.airtime, args.darkness)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite energy sizing evidence: {args.output}")
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not result["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
