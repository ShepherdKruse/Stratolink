#!/usr/bin/env python3
"""Regressions for the exact supercap charge-ceiling source audit."""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile

from supercap_charge_ceiling_audit import (
    ROOT,
    audit,
    ceiling_v,
    screen_divider_option,
    stored_energy_j,
)


def main() -> None:
    current = audit()
    assert not current["passed"]
    assert current["status"] == "blocked_pending_safer_divider_or_exact_assembly_bound"
    calculated = current["calculated"]
    assert calculated["divider_sum_mohm"] == 12.47
    assert calculated["nominal_ceiling_v"] == 5.363282
    assert calculated["one_pct_ratio_only_upper_v"] == 5.434964
    assert calculated["conservative_screening_upper_v"] == 5.543664
    assert calculated["room_temperature_screening_margin_to_5v5_v"] == -0.043664
    assert calculated["operating_temperature_delta_c"] == 65.0
    assert calculated["full_operating_temperature_screening_upper_v"] == 5.591979
    assert calculated["full_operating_temperature_screening_margin_to_5v5_v"] == -0.091979
    history = current["historical_flight3"]
    assert history["maximum_v"] == 5.412
    assert round(history["maximum_margin_to_5v5_v"], 3) == 0.088
    assert current["gates"]["divider_sum_within_ti_11_to_15Mohm_recommendation"]
    assert current["gates"]["flight3_observed_ceiling_below_5v5"]
    assert not current["gates"]["bom_resistors_meet_ti_0v1pct_accuracy_condition"]
    assert not current["gates"]["room_temperature_screening_upper_below_5v5"]
    assert not current["gates"]["full_operating_temperature_screening_upper_below_5v5"]

    # A materially lower ratio can clear the same conservative mathematical
    # screen; this is not a component recommendation or a board qualification.
    assert ceiling_v(7.68, 4.22, 0.01, 0.02, 100.0, 65.0) < 5.5
    assert round(stored_energy_j(0.8, 5.199846, 3.32), 6) == 6.406399
    options = current["divider_tradeoff_screen"]
    assert [row["top_mohm"] for row in options] == [8.06, 7.87, 7.68, 7.5, 7.32, 7.15]
    assert not options[0]["screening_upper_below_5v5"]
    assert options[1]["screening_upper_below_5v5"]
    assert options[1]["minimum_energy_to_3v32_at_0v8F_j"] == 6.406399
    assert options[2]["screening_upper_below_5v5"]
    assert screen_divider_option(7.87) == options[1]
    reference = current["reference_rework_candidate"]
    assert reference["part"] == "CRCW04027M50FKED"
    assert reference["approval_state"] == "comparison_baseline_not_preferred_or_qualified"
    assert reference["source_screen"] == options[3]
    assert reference["source_screen"]["full_temperature_screening_upper_v"] == 5.251917
    assert reference["source_screen"]["full_temperature_screening_margin_to_5v5_v"] == 0.248083
    assert not options[2]["initial_cell_match_screen_below_2v75"]
    assert options[2]["worst_initial_cell_v_at_full_temperature_upper"] == 2.773436
    assert reference["source_screen"]["initial_cell_match_screen_below_2v75"]
    assert reference["source_screen"]["worst_initial_cell_v_at_full_temperature_upper"] == 2.730997
    assert reference["source_screen"]["worst_initial_cell_margin_to_2v75_v"] == 0.019003
    safer = current["safer_margin_prototype_candidate"]
    assert safer["primary_part"] == "CRCW04027M32FKED"
    assert safer["alternate_part"] == "RC0402FR-077M32L"
    assert safer["approval_state"] == "source_screened_pending_manufacturer_review_and_hil"
    assert safer["source_screen"] == options[4]
    assert safer["source_screen"]["full_temperature_screening_upper_v"] == 5.170302
    assert safer["source_screen"]["worst_initial_cell_margin_to_2v75_v"] == 0.061443
    assert safer["headroom_gain_vs_7v50_reference_v"] == 0.04244
    assert options[5]["worst_initial_cell_margin_to_2v75_v"] == 0.101525
    cap = current["exact_parts"]["supercap"]
    assert cap["capacitance_f"] == {"min": 0.8, "typ": 1.0, "max": 1.2}
    assert cap["esr_max_mohm_at_1khz"] == 50.0
    assert current["datasheet_limits"]["recommended_divider_sum_mohm"] == {
        "min": 11.0,
        "nominal": 13.0,
        "max": 15.0,
    }
    assert current["datasheet_limits"]["ti_evm_design_screen_resistor_tolerance_pct"] == 1.0
    assert current["sources"]["bq25570_evm_user_guide"].endswith("sluuaa7a.pdf")
    assert "+/-1% resistor tolerance" in current["sources"]["bq25570_evm_methodology"]
    assert current["sources"]["safer_margin_top_resistor_datasheet"].endswith("dcrcwe3.pdf")

    with tempfile.TemporaryDirectory(prefix="stratolink-charge-ceiling-") as raw:
        root = Path(raw)
        for relative in (
            "hardware/gerbers/production_files/BOM-stratolink.csv",
            "hardware/pcb/stratolink.kicad_pcb",
            "analysis/power/flight_power.csv",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        bom = root / "hardware/gerbers/production_files/BOM-stratolink.csv"
        bom.write_text(
            bom.read_text(encoding="utf-8").replace("C2091474", "C_UNKNOWN", 1),
            encoding="utf-8",
        )
        try:
            audit(root)
        except ValueError as exc:
            assert "R2 BOM drift" in str(exc)
        else:
            raise AssertionError("charge-ceiling audit accepted an unknown divider part")

    with tempfile.TemporaryDirectory(prefix="stratolink-charge-observation-") as raw:
        path = Path(raw) / "ttn.jsonl"
        rows = [
            {
                "event": "ttn_uplink",
                "f_cnt": 65,
                "received_at": "2026-07-25T18:39:24Z",
                "telemetry": {"vstor_mv": 4630, "solar_mv": 3150, "ambient_lux": 2865},
            },
            {
                "event": "ttn_uplink",
                "f_cnt": 66,
                "received_at": "2026-07-25T19:00:14Z",
                "telemetry": {"vstor_mv": 5396, "solar_mv": 5174, "ambient_lux": 65535},
            },
        ]
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        observed = audit(ttn_path=path)
        exact = observed["exact_payload_soak"]
        assert exact["rows"] == 2
        assert exact["maximum_v"] == 5.396
        assert round(exact["maximum_margin_to_5v5_v"], 3) == 0.104
        assert exact["maximum_f_cnt"] == 66
        assert observed["gates"]["exact_payload_observed_ceiling_below_5v5"]

    print(
        "PASS: exact divider/topology/history are bound, TI's EVM 1% design "
        "method is explicit, and the current 5.5 V design fails closed"
    )


if __name__ == "__main__":
    main()
