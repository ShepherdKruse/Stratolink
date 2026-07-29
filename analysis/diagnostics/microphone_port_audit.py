#!/usr/bin/env python3
"""Audit the exact StratoLink T3902 acoustic-port PCB geometry.

This is deliberately a design-file screen, not microphone qualification.  It
binds the production BOM and the *embedded* MK1 footprint in the current PCB to
the T3902 manufacturer's landing-pattern and acoustic-hole guidance.  Physical
port blockage, solder wicking, frequency response, and detector selectivity
remain HIL gates.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD = ROOT / "hardware" / "pcb" / "stratolink.kicad_pcb"
DEFAULT_BOM = ROOT / "hardware" / "gerbers" / "production_files" / "BOM-stratolink.csv"
DEFAULT_DRC = ROOT / "hardware" / "pcb" / "drc-final.json"

T3902_SOURCE = {
    "manufacturer": "TDK InvenSense",
    "part": "T3902",
    "datasheet": "https://invensense.tdk.com/wp-content/uploads/2020/05/DS-000357-T3902-v1.0.pdf",
    "product_page": "https://www.invensense.tdk.com/en-us/products/t3902",
    "datasheet_document": "DS-000357 revision 1.0, page 18, figures 14-15",
    "recommended_pcb_acoustic_hole_mm": {"min": 0.5, "max": 1.0},
    "package_sound_port_diameter_mm": 0.375,
    "signal_pad_size_mm": [0.725, 0.522],
    "ground_ring_outer_diameter_mm": 1.625,
    "ground_ring_inner_diameter_mm": 1.025,
    "suggested_paste_signal_pad_size_mm": [0.625, 0.422],
    "suggested_ground_paste_outer_diameter_mm": 1.625,
    "suggested_ground_paste_inner_diameter_mm": 1.125,
    "assembly_note": "Do not apply solder paste to the sound hole.",
}

EXPECTED_BOM = {
    "Comment": "T3902",
    "Designator": "MK1",
    "Footprint": "MIC_T3902",
    "LCSC": "C3171752",
}

MK1_FOOTPRINT_UUID = "a200ef55-36d6-4844-bc4d-465bfee3424f"
MASK_APERTURE_UUID = "b23feb49-8f0f-4574-9e2e-318902ace596"
HISTORICAL_GND_TRACK_UUID = "29a1de5e-c2c8-4e27-bbc7-a8acaa3e6468"


def balanced_block(text: str, start: int) -> str:
    """Return the balanced parenthesized block beginning at *start*."""

    if start < 0 or text[start] != "(":
        raise ValueError("balanced block start not found")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("unterminated parenthesized block")


def find_unique_block(text: str, marker: str) -> str:
    positions = [match.start() for match in re.finditer(re.escape(marker), text)]
    if len(positions) != 1:
        raise ValueError(f"expected one {marker!r} block; found {len(positions)}")
    return balanced_block(text, positions[0])


def child_blocks(text: str, marker: str) -> list[str]:
    return [balanced_block(text, match.start()) for match in re.finditer(re.escape(marker), text)]


def first_pair(pattern: str, text: str, label: str) -> tuple[float, float]:
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f"missing {label}")
    return float(match.group(1)), float(match.group(2))


def first_number(pattern: str, text: str, label: str) -> float:
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f"missing {label}")
    return float(match.group(1))


def point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polygon_distance_to_point(points: list[tuple[float, float]], point: tuple[float, float]) -> float:
    if len(points) < 3:
        raise ValueError("paste polygon has fewer than three vertices")
    return min(
        point_segment_distance(point, points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def parse_bom(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    matches = [row for row in rows if row.get("Designator") == "MK1"]
    if len(matches) != 1:
        raise ValueError(f"expected one MK1 BOM row; found {len(matches)}")
    row = matches[0]
    for field, expected in EXPECTED_BOM.items():
        actual = row.get(field) or (row.get("LCSC Part #") if field == "LCSC" else None)
        if actual != expected:
            raise ValueError(f"MK1 BOM drift: {field}={actual!r}, expected {expected!r}")
    return EXPECTED_BOM.copy()


def parse_pad(footprint: str, pad_name: str) -> dict[str, object]:
    marker = f'(pad "{pad_name}" smd'
    block = find_unique_block(footprint, marker)
    at = first_pair(r"\(at\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", block, f"pad {pad_name} position")
    size = first_pair(r"\(size\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", block, f"pad {pad_name} size")
    return {"at_mm": list(at), "size_mm": list(size), "block": block}


def parse_geometry(board_path: Path) -> dict[str, object]:
    board = board_path.read_text(encoding="utf-8")
    footprint = find_unique_block(board, '(footprint "lib:MIC_T3902"')
    if f'(uuid "{MK1_FOOTPRINT_UUID}")' not in footprint:
        raise ValueError("MK1 footprint UUID drift")

    hole = find_unique_block(footprint, '(pad "" np_thru_hole circle')
    hole_at = first_pair(r"\(at\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", hole, "acoustic-hole position")
    hole_size = first_pair(r"\(size\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", hole, "acoustic-hole size")
    drill = first_number(r"\(drill\s+([-+0-9.eE]+)\)", hole, "acoustic-hole drill")
    if abs(hole_size[0] - hole_size[1]) > 1e-9 or abs(hole_size[0] - drill) > 1e-9:
        raise ValueError("MK1 acoustic bore is not one circular NPTH drill")

    signal_pads = {name: parse_pad(footprint, name) for name in ("1", "2", "4", "5")}
    ground_pads = {name: parse_pad(footprint, name) for name in ("3_1", "3_2")}
    copper_points: list[tuple[float, float]] = []
    for pad in ground_pads.values():
        offset_x, offset_y = pad["at_mm"]
        for x, y in re.findall(r"\(xy\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", str(pad["block"])):
            copper_points.append((float(x) + float(offset_x), float(y) + float(offset_y)))
    copper_radii = [math.hypot(x - hole_at[0], y - hole_at[1]) for x, y in copper_points]
    if not copper_radii:
        raise ValueError("MK1 custom GND-ring geometry missing")

    paste_polygons: list[list[tuple[float, float]]] = []
    for block in child_blocks(footprint, "(fp_poly"):
        if '(layer "F.Paste")' not in block:
            continue
        points = [(float(x), float(y)) for x, y in re.findall(
            r"\(xy\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", block
        )]
        paste_polygons.append(points)
    if not paste_polygons:
        raise ValueError("MK1 has no explicit F.Paste polygons")
    signal_paste = [points for points in paste_polygons if len(points) == 4]
    ground_paste = [points for points in paste_polygons if len(points) > 4]
    if len(signal_paste) != 4 or len(ground_paste) != 4:
        raise ValueError(
            "expected four MK1 signal-paste and four ground-ring polygons"
        )
    signal_paste_sizes = [
        (
            max(x for x, _ in points) - min(x for x, _ in points),
            max(y for _, y in points) - min(y for _, y in points),
        )
        for points in signal_paste
    ]
    ground_paste_radii = [
        math.hypot(x - hole_at[0], y - hole_at[1])
        for points in ground_paste for x, y in points
    ]
    minimum_paste_distance = min(
        polygon_distance_to_point(points, hole_at) for points in paste_polygons
    )

    # There are Fab reference circles before this in some exports. Select the
    # unique F.Mask circle explicitly if the first circle was not it.
    mask_blocks = [block for block in child_blocks(footprint, "(fp_circle") if '(layer "F.Mask")' in block]
    if len(mask_blocks) != 1:
        raise ValueError(f"expected one MK1 F.Mask circle; found {len(mask_blocks)}")
    mask = mask_blocks[0]
    if f'(uuid "{MASK_APERTURE_UUID}")' not in mask:
        raise ValueError("MK1 acoustic mask-aperture UUID drift")
    mask_center = first_pair(r"\(center\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", mask, "mask center")
    mask_end = first_pair(r"\(end\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", mask, "mask radius")
    mask_stroke = first_number(r"\(stroke\s+\(width\s+([-+0-9.eE]+)\)", mask, "mask stroke")
    mask_radius = math.dist(mask_center, mask_end)
    mask_opening_diameter = 2.0 * (mask_radius + mask_stroke / 2.0)

    return {
        "footprint_uuid": MK1_FOOTPRINT_UUID,
        "position_mm": list(first_pair(r"\(at\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", footprint, "MK1 position")),
        "acoustic_hole": {
            "center_mm": list(hole_at),
            "drill_diameter_mm": drill,
            "npth": True,
        },
        "signal_pad_size_mm": signal_pads["1"]["size_mm"],
        "all_four_signal_pad_sizes_equal": len({tuple(pad["size_mm"]) for pad in signal_pads.values()}) == 1,
        "ground_ring": {
            "outer_diameter_mm": 2.0 * max(copper_radii),
            "inner_diameter_mm": 2.0 * min(copper_radii),
        },
        "paste": {
            "polygon_count": len(paste_polygons),
            "signal_polygon_count": len(signal_paste),
            "ground_ring_polygon_count": len(ground_paste),
            "signal_pad_size_mm": list(signal_paste_sizes[0]),
            "all_four_signal_pad_sizes_equal": len({
                tuple(round(value, 9) for value in size)
                for size in signal_paste_sizes
            }) == 1,
            "ground_ring_outer_diameter_mm": 2.0 * max(ground_paste_radii),
            "ground_ring_inner_diameter_mm": 2.0 * min(ground_paste_radii),
            "minimum_distance_from_hole_center_mm": minimum_paste_distance,
            "clearance_beyond_hole_edge_mm": minimum_paste_distance - drill / 2.0,
        },
        "mask": {
            "aperture_uuid": MASK_APERTURE_UUID,
            "opening_diameter_mm": mask_opening_diameter,
        },
    }


def historical_mask_finding(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    matches = []
    for violation in report.get("violations", []):
        uuids = {item.get("uuid") for item in violation.get("items", [])}
        if MASK_APERTURE_UUID in uuids and HISTORICAL_GND_TRACK_UUID in uuids:
            matches.append(violation)
    if len(matches) != 1:
        raise ValueError(f"expected one historical MK1 mask finding; found {len(matches)}")
    violation = matches[0]
    return {
        "report": str(path),
        "type": violation.get("type"),
        "severity": violation.get("severity"),
        "description": violation.get("description"),
        "mask_aperture_uuid": MASK_APERTURE_UUID,
        "gnd_track_uuid": HISTORICAL_GND_TRACK_UUID,
        "current_board_objects_survive": True,
    }


def close(actual: float, expected: float, tolerance: float = 0.002) -> bool:
    return abs(actual - expected) <= tolerance


def audit(
    board_path: Path = DEFAULT_BOARD,
    bom_path: Path = DEFAULT_BOM,
    drc_path: Path = DEFAULT_DRC,
) -> dict[str, object]:
    bom = parse_bom(bom_path)
    geometry = parse_geometry(board_path)
    finding = historical_mask_finding(drc_path)
    hole = float(geometry["acoustic_hole"]["drill_diameter_mm"])
    ring = geometry["ground_ring"]
    paste = geometry["paste"]
    source = T3902_SOURCE

    gates = {
        "bom_identity_exact": True,
        "pcb_hole_within_manufacturer_range": source["recommended_pcb_acoustic_hole_mm"]["min"] <= hole <= source["recommended_pcb_acoustic_hole_mm"]["max"],
        "pcb_hole_not_smaller_than_package_sound_port": hole >= source["package_sound_port_diameter_mm"],
        "all_signal_pad_sizes_match": geometry["all_four_signal_pad_sizes_equal"] and all(
            close(float(actual), float(expected))
            for actual, expected in zip(geometry["signal_pad_size_mm"], source["signal_pad_size_mm"])
        ),
        "ground_ring_matches_manufacturer_nominal": close(float(ring["outer_diameter_mm"]), source["ground_ring_outer_diameter_mm"]) and close(float(ring["inner_diameter_mm"]), source["ground_ring_inner_diameter_mm"]),
        "paste_stencil_matches_manufacturer_nominal": bool(paste["all_four_signal_pad_sizes_equal"]) and all(
            close(float(actual), float(expected))
            for actual, expected in zip(
                paste["signal_pad_size_mm"],
                source["suggested_paste_signal_pad_size_mm"],
            )
        ) and close(
            float(paste["ground_ring_outer_diameter_mm"]),
            source["suggested_ground_paste_outer_diameter_mm"],
        ) and close(
            float(paste["ground_ring_inner_diameter_mm"]),
            source["suggested_ground_paste_inner_diameter_mm"],
        ),
        "paste_geometry_clears_acoustic_bore": float(paste["clearance_beyond_hole_edge_mm"]) > 0.0,
        "clean_current_pcb_drc": False,
        "physical_port_unblocked_verified": False,
        "exact_image_controlled_acoustic_response_verified": False,
    }
    geometry_screen_passed = all(gates[key] for key in (
        "bom_identity_exact",
        "pcb_hole_within_manufacturer_range",
        "pcb_hole_not_smaller_than_package_sound_port",
        "all_signal_pad_sizes_match",
        "ground_ring_matches_manufacturer_nominal",
        "paste_stencil_matches_manufacturer_nominal",
        "paste_geometry_clears_acoustic_bore",
    ))
    return {
        "status": "PARTIAL_PHYSICAL_AND_EXACT_IMAGE_HIL_REQUIRED",
        "passed": False,
        "geometry_screen_passed": geometry_screen_passed,
        "source": source,
        "bom": bom,
        "board": str(board_path),
        "geometry": geometry,
        "historical_drc_finding": finding,
        "gates": gates,
        "interpretation": {
            "positive": "The exact embedded MK1 geometry follows the manufacturer nominal land pattern and its 0.50 mm acoustic bore is inside the recommended range.",
            "boundary": "The bore is exactly at the lower allowed limit, so fabrication tolerance, solder/residue, cover alignment, or debris can consume margin.",
            "not_proven": "Design geometry and digital PDM activity do not prove that the manufactured acoustic path is open or that the detector responds selectively.",
            "required_hil": [
                "Microscope or backlight inspection through the actual PCB port; record a photo and confirm no solder, flux, tape, coating, or debris blocks it.",
                "Frozen-image quiet baseline and controlled sweep/multitone/click stimulus with exact-ELF attempt/capture/failure/event/variance/floor counters.",
                "Repeat with flight cover geometry and with active solar harvesting after the final supercap is fitted.",
                "Obtain a clean current PCB DRC or disposition the surviving mask-aperture/GND-track finding with fabrication evidence.",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--drc", type=Path, default=DEFAULT_DRC)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.board, args.bom, args.drc)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
