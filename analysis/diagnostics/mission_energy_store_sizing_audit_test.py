#!/usr/bin/env python3
"""Adversarial checks for mission energy-store lower-bound sizing."""

from __future__ import annotations

from mission_energy_store_sizing_audit import (
    DEFAULT_AIRTIME,
    DEFAULT_BALANCE,
    DEFAULT_DARKNESS,
    DEFAULT_NIGHT_RESERVE,
    build_audit,
    discharge_simulation,
)


def main() -> None:
    audit = build_audit(
        DEFAULT_NIGHT_RESERVE, DEFAULT_BALANCE, DEFAULT_AIRTIME, DEFAULT_DARKNESS
    )
    assert audit["passed"] is False
    assert audit["status"] == "BLOCKED_SPECIFIED_PART_RANGE_FAILS_ACTIVE_DARKNESS_SCREEN"
    rows = {row["top_mohm"]: row for row in audit["divider_sizing"]}
    assert set(rows) == {7.32, 7.5}

    safer = rows[7.32]["cases"]["full_tolerance_lower_charge_screen"]
    reference = rows[7.5]["cases"]["full_tolerance_lower_charge_screen"]
    assert 3.4 < safer["minimum_part_survival_hours"] < 3.6
    assert 3.7 < reference["minimum_part_survival_hours"] < 3.9
    assert safer["specified_part_survival_hours"]["minimum"] == safer[
        "minimum_part_survival_hours"
    ]
    assert 5.7 < safer["specified_part_survival_hours"]["maximum"] < 5.9
    assert 5.8 < reference["specified_part_survival_hours"]["maximum"] < 6.1
    assert safer["specified_maximum_part_covers_launch_night"] is False
    assert reference["specified_maximum_part_covers_launch_night"] is False
    assert safer["lower_bound_required_capacitance_f"]["launch_night"] > 1.8
    assert safer["lower_bound_required_capacitance_f"]["first_90_days"] > 2.7
    assert reference["lower_bound_required_capacitance_f"]["launch_night"] > 1.7
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
        "reduced_cadence_s": 1800,
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
