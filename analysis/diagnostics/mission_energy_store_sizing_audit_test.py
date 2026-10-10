#!/usr/bin/env python3
"""Adversarial checks for mission energy-store lower-bound sizing."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from mission_energy_store_sizing_audit import (
    build_audit,
    discharge_simulation,
)


def synthetic_audit() -> dict[str, object]:
    """Exercise source binding with synthetic inputs, not flight measurements."""
    inputs = {
        "night": {
            "passed": False,
            "inputs": {
                "conservative_legacy_sleep_screen_ua": [33, 35],
                "supercap_leakage_max_ua": 6,
                "supercap_min_capacitance_f": 0.8,
                "conservative_flight3_reported_plateau_floor_v": 3.32,
            },
            "divider_options": [
                {"top_mohm": 7.32, "nominal_ceiling_v": 4.9634},
                {"top_mohm": 7.50, "nominal_ceiling_v": 5.0409},
            ],
        },
        "balance": {"active_tlv8801_reference_not_yet_designed_or_qualified": {
            "screening_circuit_overhead_ua_excluding_cap_leakage": 1,
        }},
        "airtime": {"passed": True, "airtime": {"primary_ms": 308}},
        "darkness": {"passed": False, "geometric_darkness": {
            "launch_night": {"hours": 9.5},
            "longest_first_30_days": {"hours": 10.5},
            "longest_modeled": {"hours": 12.5},
        }},
    }
    with tempfile.TemporaryDirectory(prefix="mission-screen-input-") as raw:
        root = Path(raw)
        paths = []
        for name, payload in inputs.items():
            path = root / f"synthetic-{name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths.append(path)
        model = root / "synthetic-current-model.py"
        model.write_text(
            "I_GPS, I_MCU = 0.030, 0.005\n"
            "I_RX, I_TX14 = 0.0055, 0.044\n"
            "T_GPS_HOT, TOA_SF9 = 2.0, 0.308\n", encoding="utf-8",
        )
        return build_audit(*paths, power_model_path=model)


def main() -> None:
    audit = synthetic_audit()
    assert audit["passed"] is False
    assert audit["status"] == "BLOCKED_SPECIFIED_PART_RANGE_FAILS_ACTIVE_DARKNESS_SCREEN"
    assert audit["provenance"]["legacy_current_model"]["path"] == "synthetic-current-model.py"
    assert audit["inputs"]["continuous_current_ua"]["total"] == 42.0
    assert abs(audit["inputs"]["active_lower_screen_j_per_cycle"]
               ["hot_gnss_plus_mcu_typical"] - 0.271764706) < 1e-9
    rows = {row["top_mohm"]: row for row in audit["divider_sizing"]}
    assert set(rows) == {7.32, 7.5}

    safer = rows[7.32]["cases"]["full_tolerance_lower_charge_screen"]
    reference = rows[7.5]["cases"]["full_tolerance_lower_charge_screen"]
    # A higher starting voltage can enable another GNSS cycle, so survival
    # time is not strictly monotone across these two discrete duty schedules.
    assert 3.1 < safer["minimum_part_survival_hours"] < 3.4
    assert 3.1 < reference["minimum_part_survival_hours"] < 3.4
    assert safer["specified_part_survival_hours"]["minimum"] == safer[
        "minimum_part_survival_hours"
    ]
    assert safer["minimum_part_survival_hours"] < safer["specified_part_survival_hours"]["maximum"]
    assert reference["minimum_part_survival_hours"] < reference["specified_part_survival_hours"]["maximum"]
    assert safer["specified_maximum_part_covers_launch_night"] is False
    assert reference["specified_maximum_part_covers_launch_night"] is False
    assert safer["lower_bound_required_capacitance_f"]["launch_night"] > 2.1
    assert (
        safer["lower_bound_required_capacitance_f"]["first_90_days"]
        > safer["lower_bound_required_capacitance_f"]["first_30_days"]
        > safer["lower_bound_required_capacitance_f"]["launch_night"]
    )
    assert reference["lower_bound_required_capacitance_f"]["launch_night"] > 2.0
    assert (
        safer["lower_bound_required_capacitance_f"]["sixteen_hour_screen"]
        > safer["lower_bound_required_capacitance_f"]["launch_night"]
    )
    assert (
        safer["minimum_part_survival_hours"]
        < rows[7.32]["cases"]["nominal_charge_reference"]
        ["minimum_part_survival_hours"]
    )

    common = {
        "capacitance_f": 0.8,
        "start_v": 4.8,
        "floor_v": 3.32,
        "duration_h": 1.0,
        "base_current_ua": 42.0,
        "full_threshold_v": 4.5,
        "gps_floor_v": 3.6,
        "class_a_floor_v": 3.5,
        "tx_floor_v": 3.0,
        "full_cadence_s": 1200,
        "reduced_cadence_s": 1200,
        "gps_energy_j": 0.27,
        "tx_energy_j": 0.056,
        "class_a_energy_j": 0.037,
    }
    assert discharge_simulation(**common)["survived_target"] is True
    for key, bad in (
        ("capacitance_f", 0.0),
        ("start_v", 3.0),
        ("duration_h", 0.0),
        ("full_cadence_s", 0),
    ):
        case = dict(common)
        case[key] = bad
        try:
            discharge_simulation(**case)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid {key} must fail closed")

    print("PASS: tier-aware mission energy-store sizing fails closed")


if __name__ == "__main__":
    main()
