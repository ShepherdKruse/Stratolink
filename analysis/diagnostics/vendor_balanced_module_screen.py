#!/usr/bin/env python3
"""Screen vendor-balanced stores against the current lower mission model.

This is an architecture comparison, not a BOM substitution or qualification.
The module specifications are transcribed from CAP-XX HY Series Datasheet
Revision 3.1 (May 2021).  The mission calculation reuses the source-bound
StratoLink energy model, including all of that model's documented omissions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mission_energy_store_sizing_audit as mission


ROOT = Path(__file__).resolve().parents[2]
DATASHEET_URL = (
    "https://www.cap-xx.com/wp-content/uploads/2021/05/"
    "CAP-XX-HY-Series-Datasheet.pdf"
)
SLEEP_UPPER_UA = 35.0
DIVIDER_TOP_MOHM = (7.32, 7.50)

# The final character is A for the manufacturer's integrated active balancer.
# Datasheet IL max already includes the active-balance configuration, so it
# replaces (rather than adds to) the separate capacitor-leakage/balancer terms
# used by the board-C5 comparison.
MODULES = (
    {
        "part": "HY25R51122V255RA",
        "nominal_capacitance_f": 2.5,
        "minimum_capacitance_f": 2.25,
        "capacitance_tolerance": "+30/-10%",
        "active_configuration_leakage_max_ua_72h": 21.0,
        "esr_max_1khz_mohm": 140.0,
        "dimensions_mm": [11.0, 22.0, 22.0],
    },
    {
        "part": "HY25R51122V355RA",
        "nominal_capacitance_f": 3.5,
        "minimum_capacitance_f": 3.15,
        "capacitance_tolerance": "+30/-10%",
        "active_configuration_leakage_max_ua_72h": 26.0,
        "esr_max_1khz_mohm": 120.0,
        "dimensions_mm": [11.0, 22.0, 22.0],
    },
    {
        "part": "HY25R51127V505RA",
        "nominal_capacitance_f": 5.0,
        "minimum_capacitance_f": 4.5,
        "capacitance_tolerance": "+30/-10%",
        "active_configuration_leakage_max_ua_72h": 31.0,
        "esr_max_1khz_mohm": 110.0,
        "dimensions_mm": [11.0, 22.0, 27.0],
    },
)


def record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build_screen() -> dict[str, object]:
    base = mission.build_audit(
        mission.DEFAULT_NIGHT_RESERVE,
        mission.DEFAULT_BALANCE,
        mission.DEFAULT_AIRTIME,
        mission.DEFAULT_DARKNESS,
    )
    inputs = base["inputs"]
    energies = inputs["active_lower_screen_j_per_cycle"]
    gates = inputs["voltage_gates_v"]
    cadence = inputs["cadence_s"]
    darkness = inputs["darkness_hours"]
    duration_keys = ("launch_night", "first_30_days", "first_90_days")

    rows: list[dict[str, object]] = []
    for module in MODULES:
        divider_rows: list[dict[str, object]] = []
        base_current_ua = (
            SLEEP_UPPER_UA
            + float(module["active_configuration_leakage_max_ua_72h"])
        )
        common = {
            "floor_v": inputs["floor_v_is_conservative_reported_plateau_not_bor"],
            "base_current_ua": base_current_ua,
            "full_threshold_v": gates["full_cadence"],
            "gps_floor_v": gates["gps"],
            "class_a_floor_v": gates["class_a"],
            "tx_floor_v": gates["tx"],
            "full_cadence_s": cadence["full"],
            "reduced_cadence_s": cadence["reduced_or_lower"],
            "gps_energy_j": energies["hot_gnss_plus_mcu_typical"],
            "tx_energy_j": energies["primary_tx_typical"],
            "class_a_energy_j": energies["empty_class_a_radio_rx_typical"],
        }
        for top_mohm in DIVIDER_TOP_MOHM:
            start_v = mission.lower_screen_ceiling_v(top_mohm)
            survival = mission.discharge_simulation(
                float(module["minimum_capacitance_f"]),
                start_v=start_v,
                duration_h=None,
                **common,
            )
            required = {
                key: mission.required_capacitance_f(
                    float(darkness[key]), start_v=start_v, **common
                )
                for key in duration_keys
            }
            minimum_f = float(module["minimum_capacitance_f"])
            divider_rows.append(
                {
                    "top_mohm": top_mohm,
                    "tolerance_lower_start_v": round(start_v, 6),
                    "minimum_part_survival_hours": round(
                        float(survival["elapsed_hours"]), 3
                    ),
                    "lower_bound_required_capacitance_f": {
                        key: round(value, 3) for key, value in required.items()
                    },
                    "minimum_part_covers_lower_screen": {
                        key: minimum_f >= value for key, value in required.items()
                    },
                }
            )
        rows.append(
            {
                **module,
                "rated_stack_voltage_v": 5.5,
                "temperature_range_c": [-40, 85],
                "continuous_current_screen_ua": base_current_ua,
                "divider_screens": divider_rows,
            }
        )

    return {
        "passed": False,
        "status": "REFERENCE_ARCHITECTURES_REQUIRE_PROCUREMENT_AND_FULL_HIL",
        "scope": (
            "vendor-integrated active-balance module comparison against the "
            "existing incomplete lower mission-energy screen"
        ),
        "vendor_source": {
            "manufacturer": "CAP-XX",
            "document": "HY Series Datasheet Revision 3.1, May 2021",
            "url": DATASHEET_URL,
            "note": (
                "Specifications are manually transcribed; obtain current "
                "manufacturer confirmation and incoming inspection before use."
            ),
        },
        "model_provenance": {
            "mission_model": record(Path(mission.__file__).resolve()),
            "night_reserve": record(mission.DEFAULT_NIGHT_RESERVE),
            "balance_screen": record(mission.DEFAULT_BALANCE),
            "airtime_screen": record(mission.DEFAULT_AIRTIME),
            "friday_darkness": record(mission.DEFAULT_DARKNESS),
        },
        "modules": rows,
        "interpretation": (
            "The 2.5 F active module clears only launch night in this lower "
            "screen. The 3.5 F module clears launch and the first-30-day "
            "geometric nights but not the 90-day night. The 5 F module clears "
            "all three numerical lower screens. None is qualified: the model "
            "still omits measured final-image cycle energy, cold/aging, "
            "weather, sag, actual BOR, and reserve, and none fits the existing "
            "C5 land pattern."
        ),
        "hard_stops": [
            "not footprint-compatible with the current C5 land pattern",
            "availability and exact suffix not verified",
            "mass, mounting, wiring, strain relief, and antenna interaction not reviewed",
            "BQ25570 divider still requires voltage-safe rework and measurement",
            "no exact-module charge/dark/cold/BOR/recovery HIL",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    result = build_screen()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite vendor-module evidence: {args.output}")
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not result["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
