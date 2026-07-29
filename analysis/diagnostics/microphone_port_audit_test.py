#!/usr/bin/env python3
"""Regression checks for the exact T3902 acoustic-port audit."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import microphone_port_audit as microphone


def main() -> None:
    report = microphone.audit()
    assert report["status"] == "PARTIAL_PHYSICAL_AND_EXACT_IMAGE_HIL_REQUIRED"
    assert not report["passed"]
    assert report["geometry_screen_passed"]
    assert report["bom"] == microphone.EXPECTED_BOM
    geometry = report["geometry"]
    assert geometry["footprint_uuid"] == microphone.MK1_FOOTPRINT_UUID
    assert geometry["acoustic_hole"] == {
        "center_mm": [0.0, 0.71],
        "drill_diameter_mm": 0.5,
        "npth": True,
    }
    assert geometry["signal_pad_size_mm"] == [0.725, 0.522]
    assert geometry["all_four_signal_pad_sizes_equal"]
    assert round(geometry["ground_ring"]["outer_diameter_mm"], 3) == 1.626
    assert round(geometry["ground_ring"]["inner_diameter_mm"], 3) == 1.024
    assert geometry["paste"]["polygon_count"] == 8
    assert geometry["paste"]["signal_polygon_count"] == 4
    assert geometry["paste"]["ground_ring_polygon_count"] == 4
    assert geometry["paste"]["all_four_signal_pad_sizes_equal"]
    assert [round(value, 3) for value in geometry["paste"]["signal_pad_size_mm"]] == [0.625, 0.422]
    assert round(geometry["paste"]["ground_ring_outer_diameter_mm"], 3) == 1.626
    assert round(geometry["paste"]["ground_ring_inner_diameter_mm"], 3) == 1.124
    assert round(geometry["paste"]["clearance_beyond_hole_edge_mm"], 3) == 0.312
    assert round(geometry["mask"]["opening_diameter_mm"], 3) == 1.725
    assert report["historical_drc_finding"]["type"] == "solder_mask_bridge"
    assert report["historical_drc_finding"]["severity"] == "error"
    gates = report["gates"]
    assert gates["pcb_hole_within_manufacturer_range"]
    assert gates["paste_stencil_matches_manufacturer_nominal"]
    assert gates["paste_geometry_clears_acoustic_bore"]
    assert not gates["clean_current_pcb_drc"]
    assert not gates["physical_port_unblocked_verified"]
    assert not gates["exact_image_controlled_acoustic_response_verified"]

    with tempfile.TemporaryDirectory(prefix="stratolink-mic-port-") as raw:
        directory = Path(raw)
        board = directory / "board.kicad_pcb"
        bom = directory / "bom.csv"
        drc = directory / "drc.json"
        shutil.copy2(microphone.DEFAULT_BOARD, board)
        shutil.copy2(microphone.DEFAULT_BOM, bom)
        shutil.copy2(microphone.DEFAULT_DRC, drc)
        board.write_text(
            board.read_text(encoding="utf-8").replace(
                '(pad "" np_thru_hole circle\n\t\t\t(at 0 0.71)\n\t\t\t(size 0.5 0.5)\n\t\t\t(drill 0.5)',
                '(pad "" np_thru_hole circle\n\t\t\t(at 0 0.71)\n\t\t\t(size 0.4 0.4)\n\t\t\t(drill 0.4)',
                1,
            ),
            encoding="utf-8",
        )
        narrowed = microphone.audit(board, bom, drc)
        assert not narrowed["gates"]["pcb_hole_within_manufacturer_range"]
        assert not narrowed["geometry_screen_passed"]

    with tempfile.TemporaryDirectory(prefix="stratolink-mic-bom-") as raw:
        directory = Path(raw)
        bom = directory / "bom.csv"
        shutil.copy2(microphone.DEFAULT_BOM, bom)
        bom.write_text(
            bom.read_text(encoding="utf-8").replace("C3171752", "C_UNKNOWN", 1),
            encoding="utf-8",
        )
        try:
            microphone.audit(bom_path=bom)
        except ValueError as exc:
            assert "MK1 BOM drift" in str(exc)
        else:
            raise AssertionError("microphone audit accepted an unknown MK1 BOM part")

    print("PASS: exact T3902 geometry is source-bound and physical/HIL gates fail closed")


if __name__ == "__main__":
    main()
