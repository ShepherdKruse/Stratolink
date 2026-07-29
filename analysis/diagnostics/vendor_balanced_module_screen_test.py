#!/usr/bin/env python3
"""Regression checks for the fail-closed balanced-module comparison."""

from vendor_balanced_module_screen import build_screen


def main() -> None:
    result = build_screen()
    assert result["passed"] is False
    assert result["status"] == "REFERENCE_ARCHITECTURES_REQUIRE_PROCUREMENT_AND_FULL_HIL"
    modules = {row["nominal_capacitance_f"]: row for row in result["modules"]}
    assert set(modules) == {2.5, 3.5, 5.0}

    for module in modules.values():
        assert module["continuous_current_screen_ua"] == (
            35.0 + module["active_configuration_leakage_max_ua_72h"]
        )
        assert len(module["divider_screens"]) == 2

    for divider in modules[2.5]["divider_screens"]:
        covers = divider["minimum_part_covers_lower_screen"]
        assert covers["launch_night"] is True
        assert covers["first_30_days"] is False
        assert covers["first_90_days"] is False

    for divider in modules[3.5]["divider_screens"]:
        covers = divider["minimum_part_covers_lower_screen"]
        assert covers["launch_night"] is True
        assert covers["first_30_days"] is True
        assert covers["first_90_days"] is False

    for divider in modules[5.0]["divider_screens"]:
        assert all(divider["minimum_part_covers_lower_screen"].values())

    assert "not footprint-compatible" in result["hard_stops"][0]
    print("PASS: vendor-balanced module screen remains numerical and fail-closed")


if __name__ == "__main__":
    main()
