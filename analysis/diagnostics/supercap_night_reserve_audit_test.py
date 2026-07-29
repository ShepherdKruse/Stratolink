#!/usr/bin/env python3
"""Regressions for the fitted-supercap darkness warning screen."""

from supercap_night_reserve_audit import (
    build_audit,
    constant_current_runtime_hours,
)


def main() -> None:
    assert round(constant_current_runtime_hours(0.8, 5.2, 3.32, 41), 3) == 10.19
    audit = build_audit()
    assert not audit["passed"]
    assert audit["status"] == "BLOCKED_PENDING_EXACT_FITTED_CAP_DARKNESS_HIL"
    rows = audit["divider_options"]
    assert [row["top_mohm"] for row in rows] == [8.25, 8.06, 7.87, 7.68, 7.5, 7.32, 7.15]
    assert rows[0]["baseline_only_runtime_h"] == {
        "33uA_no_cap_leakage": 13.759,
        "35uA_plus_6uA_room_leakage": 11.075,
    }
    assert rows[2]["baseline_only_runtime_h"] == {
        "33uA_no_cap_leakage": 12.659,
        "35uA_plus_6uA_room_leakage": 10.189,
    }
    assert rows[4]["source_bound_candidate_parts"] == ["CRCW04027M50FKED"]
    assert rows[4]["candidate_role"] == "comparison_reference"
    assert rows[5]["source_bound_candidate_parts"] == [
        "CRCW04027M32FKED",
        "RC0402FR-077M32L",
    ]
    assert rows[5]["candidate_role"] == "safer_margin_prototype_candidate"
    assert rows[3]["source_bound_candidate_parts"] == []
    assert rows[3]["baseline_only_runtime_h"] == {
        "33uA_no_cap_leakage": 12.109,
        "35uA_plus_6uA_room_leakage": 9.746,
    }
    assert rows[4]["baseline_only_runtime_h"] == {
        "33uA_no_cap_leakage": 11.587,
        "35uA_plus_6uA_room_leakage": 9.326,
    }
    assert rows[5]["baseline_only_runtime_h"] == {
        "33uA_no_cap_leakage": 11.066,
        "35uA_plus_6uA_room_leakage": 8.907,
    }
    assert not rows[0]["overvoltage_screen_clears_5v5"]
    assert rows[2]["overvoltage_screen_clears_5v5"]
    assert not any(
        row["baseline_only_target_screen"]["12h_at_35uA_plus_6uA"]
        for row in rows
    )
    print("PASS: minimum-capacitance darkness screen fails closed pending fitted-cap HIL")


if __name__ == "__main__":
    main()
