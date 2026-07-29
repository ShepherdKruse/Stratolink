#!/usr/bin/env python3
"""Screen darkness reserve for the exact planned supercapacitor.

This intentionally does not claim a flight-energy qualification. It combines
the 0.8 F datasheet minimum, a deliberately conservative legacy 33-35 uA
screen above the newer measured STOP1 result, and the datasheet 5.5 V / 23 C /
120 h leakage limit. GPS, sensing, TX, watchdog wake
chunks, temperature, aging, converter behavior, and load-step sag are excluded,
so the reported baseline-only runtimes are a warning screen, not endurance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from supercap_charge_ceiling_audit import (
    CAPXX_DATASHEET,
    CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V,
    SCREENING_TOP_OPTIONS_MOHM,
    REFERENCE_TOP_PART,
    REFERENCE_TOP_VALUE_MOHM,
    SAFER_MARGIN_TOP_ALTERNATE_PART,
    SAFER_MARGIN_TOP_PART,
    SAFER_MARGIN_TOP_VALUE_MOHM,
    SUPERCAP_MIN_CAPACITANCE_F,
    TOP_VALUE_MOHM,
    screen_divider_option,
)


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_DOCUMENTATION = ROOT / "firmware/DOCUMENTATION.md"
SLEEP_CURRENT_RANGE_UA = (33.0, 35.0)
SUPERCAP_LEAKAGE_MAX_UA = 6.0
SUPERCAP_LEAKAGE_CONDITION = "5.5 V, 23 C, after 120 h"
TARGET_DARK_HOURS = (9.0, 12.0, 16.0)


def constant_current_runtime_hours(
    capacitance_f: float,
    ceiling_v: float,
    floor_v: float,
    current_ua: float,
) -> float:
    if capacitance_f <= 0 or ceiling_v <= floor_v or current_ua <= 0:
        raise ValueError("invalid darkness-runtime inputs")
    return capacitance_f * (ceiling_v - floor_v) / (current_ua * 1e-6) / 3600.0


def option_row(top_mohm: float) -> dict[str, object]:
    divider = screen_divider_option(top_mohm)
    ceiling = float(divider["nominal_ceiling_v"])
    sleep_best = min(SLEEP_CURRENT_RANGE_UA)
    sleep_worst = max(SLEEP_CURRENT_RANGE_UA)
    best_case = constant_current_runtime_hours(
        SUPERCAP_MIN_CAPACITANCE_F,
        ceiling,
        CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V,
        sleep_best,
    )
    room_leakage_screen = constant_current_runtime_hours(
        SUPERCAP_MIN_CAPACITANCE_F,
        ceiling,
        CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V,
        sleep_worst + SUPERCAP_LEAKAGE_MAX_UA,
    )
    return {
        "top_mohm": top_mohm,
        "source_bound_candidate_parts": (
            [REFERENCE_TOP_PART]
            if top_mohm == REFERENCE_TOP_VALUE_MOHM
            else [SAFER_MARGIN_TOP_PART, SAFER_MARGIN_TOP_ALTERNATE_PART]
            if top_mohm == SAFER_MARGIN_TOP_VALUE_MOHM
            else []
        ),
        "candidate_role": (
            "comparison_reference"
            if top_mohm == REFERENCE_TOP_VALUE_MOHM
            else "safer_margin_prototype_candidate"
            if top_mohm == SAFER_MARGIN_TOP_VALUE_MOHM
            else None
        ),
        "nominal_ceiling_v": ceiling,
        "minimum_capacitance_f": SUPERCAP_MIN_CAPACITANCE_F,
        "conservative_flight3_reported_plateau_floor_v": (
            CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V
        ),
        "baseline_only_runtime_h": {
            "33uA_no_cap_leakage": round(best_case, 3),
            "35uA_plus_6uA_room_leakage": round(room_leakage_screen, 3),
        },
        "baseline_only_target_screen": {
            f"{int(hours)}h_at_35uA_plus_6uA": room_leakage_screen >= hours
            for hours in TARGET_DARK_HOURS
        },
        "overvoltage_screen_clears_5v5": divider[
            "screening_upper_below_5v5"
        ],
    }


def build_audit() -> dict[str, object]:
    docs = FIRMWARE_DOCUMENTATION.read_text(encoding="utf-8")
    required_claim = "6.688 µA"
    if required_claim not in docs:
        raise AssertionError("documented PPK2 sleep-current evidence drifted")

    rows = [
        option_row(value)
        for value in (TOP_VALUE_MOHM, *SCREENING_TOP_OPTIONS_MOHM)
    ]
    return {
        "status": "BLOCKED_PENDING_EXACT_FITTED_CAP_DARKNESS_HIL",
        "passed": False,
        "scope": (
            "baseline-only constant-current screen; not a cycle-energy model "
            "or a flight-endurance qualification"
        ),
        "sources": {
            "supercap_datasheet": CAPXX_DATASHEET,
            "measured_sleep_current_claim": str(FIRMWARE_DOCUMENTATION.relative_to(ROOT)),
        },
        "inputs": {
            "supercap_min_capacitance_f": SUPERCAP_MIN_CAPACITANCE_F,
            "supercap_leakage_max_ua": SUPERCAP_LEAKAGE_MAX_UA,
            "supercap_leakage_condition": SUPERCAP_LEAKAGE_CONDITION,
            "conservative_legacy_sleep_screen_ua": list(SLEEP_CURRENT_RANGE_UA),
            "conservative_flight3_reported_plateau_floor_v": (
                CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V
            ),
        },
        "divider_options": rows,
        "interpretation": (
            "Even before GPS, sensors, LoRa TX/RX, watchdog wake chunks, cold, "
            "aging, and load-step sag are charged to the budget, none of the "
            "screened ceilings reaches 12 h at the 0.8 F capacitance limit when "
            "the documented 35 uA J-Link-attached sleep upper bound and the "
            "6 uA room-temperature leakage limit are combined. A lower divider "
            "can resolve the 5.5 V "
            "screen but further reduces darkness reserve. The 7.50 Mohm "
            f"{REFERENCE_TOP_PART} comparison reference clears both the "
            "total-voltage and initial-cell-match screens, yet its minimum-cap "
            "baseline is only 9.326 h at 35+6 uA before balancer overhead and "
            "its cell headroom is only 19 mV. The 7.32 Mohm safer-margin "
            f"candidate ({SAFER_MARGIN_TOP_PART} or "
            f"{SAFER_MARGIN_TOP_ALTERNATE_PART}) increases that cell headroom "
            "to 61 mV while reducing the same baseline to 8.907 h. Neither is "
            "qualified. "
            "The live 16 h PPK2 "
            "soak proves powered runtime, not supercapacitor endurance."
        ),
        "required_hil": (
            "Fit the exact flight capacitor only after the charge-ceiling risk "
            "is controlled. Measure capacitance and ESR, then run a dark discharge "
            "from the verified ceiling through real candidate GPS/sensor/TX cycles "
            "to tier crossings, below the 3.32 V historical reported plateau, "
            "actual BOR, and sunrise recovery, including cold repeats."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    result = build_audit()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite night-reserve evidence: {args.output}")
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not result["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
