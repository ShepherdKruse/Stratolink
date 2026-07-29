#!/usr/bin/env python3
"""Regressions for the exact C5 balance-terminal audit."""

from pathlib import Path
import shutil
import tempfile

from supercap_balance_audit import ROOT, audit
from supercap_charge_ceiling_audit import footprint_blocks


def main() -> None:
    current = audit()
    assert not current["passed"]
    assert current["status"] == "BLOCKED_UNCONNECTED_SUPERCAP_BALANCE_TERMINAL"
    topology = current["exact_topology"]
    assert topology["part"] == "DMF4B5R5G105M3DTA0"
    assert topology["balance_pad_net"] is None
    assert not current["gates"]["balance_terminal_connected_to_a_balance_network"]
    passive = current["passive_reference_rejected_for_energy"]
    assert passive["candidate_total_ceiling_v"] == 5.040711
    assert passive["added_current_ua"] == 252.03555
    assert passive["minimum_cap_baseline_runtime_h_at_35_plus_6_plus_passive_ua"] == 1.305
    active = current["active_tlv8801_reference_not_yet_designed_or_qualified"]
    assert active["opamp_candidate"] == "TLV8801DBVT"
    assert active["reference_resistor_candidate_each"] == "MCA1206MD1005BP100"
    assert active["modeled_circuit_overhead_ua_excluding_cap_leakage"] == 0.732036
    assert active["screening_circuit_overhead_ua_excluding_cap_leakage"] == 0.952036
    assert active[
        "minimum_cap_baseline_runtime_h_at_35_plus_6_plus_active_overhead_ua"
    ] == 9.163
    assert active[
        "minimum_cap_screening_runtime_h_at_35_plus_6_plus_active_overhead_ua"
    ] == 9.115
    assert active["worst_reference_fraction_with_tolerance_and_tcr"] == 0.501312498
    assert active["balanced_cell_upper_v_including_max_opamp_offset"] == 2.637352
    assert active["balanced_cell_margin_to_2v75_v"] == 0.112648
    assert active[
        "initial_4pct_mismatch_correction_demand_ma_at_full_upper"
    ] == 4.77447
    assert active["opamp_typical_output_current_ma"] == 4.7
    ald = current["active_ald910025_sab_not_yet_designed_or_qualified"]
    assert ald["part"] == "ALD910025SALI"
    assert ald["threshold_v_at_1ua_25c"] == {
        "minimum": 2.48,
        "typical": 2.5,
        "maximum": 2.52,
    }
    assert ald["cold_rating_margin_c"] == -2.1
    assert ald["balanced_cell_upper_v_from_25c_max_channel_offset"] == 2.635958
    assert ald["balanced_cell_margin_to_2v75_v_at_25c_max_channel_offset"] == 0.114042
    assert ald["worst_initial_4pct_cells_at_full_upper"]["high_cell_v"] == 2.730997
    assert ald["worst_initial_4pct_cells_at_full_upper"]["low_cell_v"] == 2.52092
    assert ald[
        "typical_25c_6ua_leakage_mismatch_equilibrium_with_20mv_offset"
    ] == {
        "nominal_total_v": 5.040711,
        "nominal_high_cell_v": 2.59964,
        "nominal_low_cell_v": 2.441071,
        "full_screen_total_v": 5.251917,
        "full_screen_high_cell_v": 2.647378,
        "full_screen_low_cell_v": 2.604539,
        "full_screen_high_cell_margin_to_2v75_v": 0.102622,
    }
    assert not current["gates"][
        "individual_cell_leakage_characterized_against_selected_balancer"
    ]
    assert not current["gates"][
        "active_balancer_flight_temperature_envelope_qualified"
    ]
    assert not current["gates"][
        "active_balancer_reverse_discharge_transient_path_qualified"
    ]
    assert not current["gates"]["active_balancer_exact_part_procured_and_verified"]
    assert not current["gates"][
        "initial_mismatch_correction_current_has_specified_minimum_margin"
    ]
    assert current["cell_match_screen"] == {
        "manufacturer_matching": "+/-4% between the two cells",
        "cell_rated_v": 2.75,
        "reference_7v50_divider_full_upper_v": 5.251917,
        "worst_initial_cell_v": 2.730997,
        "margin_v": 0.019003,
        "passed": True,
    }
    sensitivity = current["divider_architecture_sensitivity"]["options"]
    assert [row["top_mohm"] for row in sensitivity] == [7.5, 7.32, 7.15]
    assert sensitivity[0]["tlv8801"][
        "initial_4pct_mismatch_correction_demand_ma"
    ] == 4.77447
    assert sensitivity[1]["tlv8801"] == {
        "minimum_cap_screening_runtime_h": 8.705,
        "balanced_cell_margin_to_2v75_v": 0.153563,
        "initial_4pct_mismatch_correction_demand_ma": 4.700275,
        "demand_minus_typical_output_current_ma": 0.000275,
        "current_limit_boundary": (
            "TI specifies 4.7 mA only as typical short-circuit current; "
            "no minimum correction-current guarantee is available"
        ),
    }
    assert sensitivity[1]["ald910025_typical_only"] == {
        "minimum_cap_25c_runtime_h_with_min_25c_threshold": 8.895,
        "initial_high_cell_v": 2.688557,
        "initial_low_cell_v": 2.481745,
        "initial_net_equalizing_current_ua": 54.041622,
        "full_screen_6ua_mismatch_equilibrium_high_cell_v": 2.617271,
        "full_screen_6ua_mismatch_equilibrium_low_cell_v": 2.553031,
        "full_screen_6ua_mismatch_equilibrium_margin_to_2v75_v": 0.132729,
        "boundary": (
            "current curve and temperature coefficients are typical-only; "
            "these values rank candidates but cannot qualify correction time"
        ),
    }
    assert sensitivity[2]["tlv8801"][
        "initial_4pct_mismatch_correction_demand_ma"
    ] == 4.630201
    assert sensitivity[2]["ald910025_typical_only"][
        "initial_net_equalizing_current_ua"
    ] == 25.068659

    with tempfile.TemporaryDirectory(prefix="stratolink-cap-balance-") as raw:
        root = Path(raw)
        relative = Path("hardware/pcb/stratolink.kicad_pcb")
        destination = root / relative
        destination.parent.mkdir(parents=True)
        shutil.copy2(ROOT / relative, destination)
        text = destination.read_text(encoding="utf-8")
        c5 = footprint_blocks(text)["C5"]
        connected_c5 = c5.replace(
            '(pad "3" smd rect',
            '(pad "3" smd rect\n\t\t(net 999 "BALANCE_TEST")',
            1,
        )
        text = text.replace(c5, connected_c5, 1)
        destination.write_text(text, encoding="utf-8")
        mutated = audit(root)
        assert mutated["gates"]["balance_terminal_connected_to_a_balance_network"]
        assert not mutated["passed"]
        assert not mutated["gates"][
            "manufacturer_balance_requirement_resolved_for_exact_application"
        ]

    print("PASS: exact unconnected C5 balance terminal fails closed")


if __name__ == "__main__":
    main()
