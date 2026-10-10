#!/usr/bin/env python3
"""Regression checks for the fail-closed balanced-module comparison."""

import json
from pathlib import Path
import tempfile

from vendor_balanced_module_screen import build_screen


def main() -> None:
    # Synthetic engineering inputs; no measured flight evidence is embedded.
    inputs = {
        "active_lower_screen_j_per_cycle": {
            "hot_gnss_plus_mcu_typical": 0.271764705882,
            "primary_tx_typical": 0.056,
            "empty_class_a_radio_rx_typical": 0.037154,
        },
        "voltage_gates_v": {"full_cadence": 4.5, "gps": 3.6, "class_a": 3.5, "tx": 3.0},
        "cadence_s": {"full": 1200, "reduced_or_lower": 1200},
        "darkness_hours": {"launch_night": 9.5, "first_30_days": 10.5, "first_90_days": 12.5},
        "floor_v_is_conservative_reported_plateau_not_bor": 3.32,
    }
    with tempfile.TemporaryDirectory(prefix="vendor-screen-input-") as raw:
        report = Path(raw) / "synthetic-mission.json"
        report.write_text(json.dumps({"inputs": inputs}), encoding="utf-8")
        result = build_screen(report)
    assert result["model_provenance"]["mission_audit"]["sha256"]
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
        assert covers["launch_night"] is False
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
