#!/usr/bin/env python3
"""Verify the current supplier evidence from any checkout using Python 3.

manifest.json must contain nonempty ``sources`` and ``evidence`` objects. Each
maps repository-relative POSIX paths to lowercase SHA-256 strings. Other fields
are descriptive metadata. All paths resolve below --repo; historical absolute
source/evidence paths embedded in the generated package are never followed.

Default invocation:
    python3 analysis/v1_1_supplier_review_20261016/verify.py
"""
import argparse
import collections
import copy
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REVIEW = "analysis/v1_1_supplier_review_20261016"
PACKAGE = "hardware/gerbers/v1.1-pilot-supplier-20261016"
PREVIOUS = "hardware/gerbers/v1.1-pilot"
PCB_SHA256 = "25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f"
SCH_SHA256 = "c772c2a0edff4d6f7616afb0988fc95c2cbb8c2d3572c1429fc0f3718f69e921"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=no_duplicate_keys)


def local_path(root, relative):
    require(isinstance(relative, str) and bool(relative), "Empty or non-string path")
    pure = PurePosixPath(relative)
    require(not pure.is_absolute() and ".." not in pure.parts and "\\" not in relative,
            "Expected repository-relative POSIX path: " + relative)
    path = (root / relative).resolve()
    require(root == path or root in path.parents, "Path escapes repository: " + relative)
    return path


def csv_rows(path, expected_fields):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == expected_fields, "Unexpected CSV columns: " + str(path))
        records = list(reader)
    result = {}
    for row in records:
        ref = row["Designator"]
        require(re.fullmatch(r"[A-Z]+[1-9][0-9]*", ref) is not None, "Invalid reference: " + ref)
        require(ref not in result, "Duplicate CSV reference: " + ref)
        require(None not in row and all(value is not None for value in row.values()), "Malformed CSV row: " + ref)
        result[ref] = row
    return result


def verify_cpl(before, after):
    require(set(before) == set(after) and len(after) == 57, "CPL population must remain 57 references")
    require(before["U8"]["Rotation"] == "180.000000", "Unexpected original U8 rotation")
    expected = copy.deepcopy(before)
    expected["U8"]["Rotation"] = "90.000000"
    require(after == expected, "CPL differs beyond the U8 180 to 90 degree correction")


def verify_selected_rows(captured, bom, cpl):
    require(isinstance(captured, list) and len(captured) == 57, "Supplier capture must contain exactly 57 rows")
    selected = {}
    for row in captured:
        require(isinstance(row, dict) and row.get("checked") is True, "Every supplier row must be selected")
        cells = row.get("cells")
        require(isinstance(cells, list) and len(cells) in (6, 10) and all(isinstance(s, str) for s in cells),
                "Unexpected captured supplier table shape")
        # Captured JLC BOM table has separate Top Designator and Bottom
        # Designator columns. Merged procurement cells produce 6-cell rows.
        require(bool(cells[0].strip()) != bool(cells[1].strip()), "Expected exactly one populated side column")
        side = "top" if cells[0].strip() else "bottom"
        ref = (cells[0] or cells[1]).strip()
        require(ref not in selected, "Duplicate supplier reference: " + ref)
        require(ref in bom and ref in cpl, "Unexpected supplier reference: " + ref)
        chosen = [line.strip() for line in cells[4].splitlines() if line.strip()]
        require(len(chosen) >= 2 and re.fullmatch(r"C[0-9]+", chosen[1]) is not None,
                "Missing selected supplier identity for " + ref)
        expected = bom[ref]
        require(cells[2].strip() == chosen[0] == expected["Comment"], "Requested or selected MPN mismatch: " + ref)
        require(chosen[1] == expected["LCSC Part #"], "Selected LCSC part mismatch: " + ref)
        require(cells[3].strip() == expected["Footprint"], "Supplier footprint mismatch: " + ref)
        require(side == cpl[ref]["Layer"], "Supplier side mismatch: " + ref)
        selected[ref] = {"mpn": chosen[0], "lcsc": chosen[1], "side": side}
    require(set(selected) == set(bom) == set(cpl), "Supplier/BOM/CPL reference sets differ")
    sides = dict(collections.Counter(row["side"] for row in selected.values()))
    require(sides == {"top": 41, "bottom": 16}, "Unexpected supplier side totals")
    return selected, sides


def verify(root, manifest_path):
    root = root.resolve()
    manifest = read_json(manifest_path)
    require(isinstance(manifest, dict), "Supplier manifest must be an object")
    declared = {}
    category_counts = {}
    for category in ("sources", "evidence"):
        files = manifest.get(category)
        require(isinstance(files, dict) and bool(files), "Missing nonempty " + category + " hash map")
        category_counts[category] = len(files)
        for relative, digest in files.items():
            require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                    "Invalid SHA-256 for " + relative)
            require(relative not in declared, "Path occurs in both hash maps: " + relative)
            path = local_path(root, relative)
            require(path.is_file() and sha(path) == digest, "Missing file or SHA-256 mismatch: " + relative)
            declared[relative] = digest
    required = {
        "hardware/pcb/stratolink.kicad_pcb", "hardware/pcb/stratolink.kicad_sch",
        PREVIOUS + "/BOM-stratolink.csv", PREVIOUS + "/CPL-stratolink.csv",
        PACKAGE + "/BOM-stratolink.csv", PACKAGE + "/CPL-stratolink.csv",
        PACKAGE + "/manifest.json", PACKAGE + "/assembly-audit.json",
        PACKAGE + "/native/positions.csv", REVIEW + "/bom-final.json",
        REVIEW + "/u8-corrected-close.png", REVIEW + "/verify.py",
    }
    require(required <= set(declared), "Manifest omits required proof inputs: " + ", ".join(sorted(required - set(declared))))
    require(declared["hardware/pcb/stratolink.kicad_pcb"] == PCB_SHA256, "Wrong reviewed PCB revision")
    require(declared["hardware/pcb/stratolink.kicad_sch"] == SCH_SHA256, "Wrong reviewed schematic revision")
    package, previous = root / PACKAGE, root / PREVIOUS
    generated = read_json(package / "manifest.json")
    require(generated["source_files"]["stratolink.kicad_pcb"] == PCB_SHA256, "Package PCB identity mismatch")
    require(generated["source_files"]["stratolink.kicad_sch"] == SCH_SHA256, "Package schematic identity mismatch")
    require(generated["finish"] == "green-mask-no-silk", "Unexpected fabrication finish")
    for relative, digest in generated["output_files"].items():
        path = local_path(package.resolve(), relative)
        require(path.is_file() and sha(path) == digest, "Package output hash mismatch: " + relative)
    actual_outputs = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file() and p != package / "manifest.json"}
    require(actual_outputs == set(generated["output_files"]), "Unmanifested or missing package output")
    bom_fields = ["Comment", "Designator", "Footprint", "LCSC Part #"]
    cpl_fields = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]
    bom = csv_rows(package / "BOM-stratolink.csv", bom_fields)
    cpl = csv_rows(package / "CPL-stratolink.csv", cpl_fields)
    old_cpl = csv_rows(previous / "CPL-stratolink.csv", cpl_fields)
    require((package / "BOM-stratolink.csv").read_bytes() == (previous / "BOM-stratolink.csv").read_bytes(),
            "Supplier correction changed BOM")
    verify_cpl(old_cpl, cpl)
    require(len(bom) == len(cpl) == 57 and set(bom) == set(cpl) and "U6" not in bom, "Unexpected pilot population")
    selected, sides = verify_selected_rows(read_json(root / REVIEW / "bom-final.json"), bom, cpl)
    audit = read_json(package / "assembly-audit.json")
    assembly = audit["assembly"]
    require(set(assembly) == set(bom), "Assembly audit population mismatch")
    require(set(audit["population_profile"]["omit"]) == {"U6"}, "Unexpected DNP population")
    require(generated["assembly_count"] == 57 and generated["design_assembly_count"] == 58, "Unexpected package counts")
    with (package / "native/positions.csv").open(newline="") as stream:
        native = {row["Ref"]: row for row in csv.DictReader(stream)}
    for ref, row in assembly.items():
        require(bom[ref] == {"Comment": row["mpn"], "Designator": ref, "Footprint": row["footprint"],
                             "LCSC Part #": row["lcsc"]}, "BOM differs from assembly audit: " + ref)
        require(cpl[ref] == {"Designator": ref, "Mid X": f"{row['center_mm'][0]:.6f}",
                             "Mid Y": f"{-row['center_mm'][1]:.6f}", "Layer": row["side"],
                             "Rotation": f"{row['rotation_deg']:.6f}"}, "CPL differs from assembly audit: " + ref)
        require(ref in native and native[ref]["Side"] == row["side"], "Native placement side mismatch: " + ref)
    return {
        "passed": True, "manifest_sha256": sha(manifest_path), "verified_hashes": category_counts,
        "pcb_sha256": PCB_SHA256, "schematic_sha256": SCH_SHA256,
        "package_manifest_sha256": sha(package / "manifest.json"),
        "package_output_hashes_verified": len(generated["output_files"]),
        "selected_assembly_references": len(selected), "selected_sides": sides,
        "selected_MPN_LCSC_footprint_reference_side_matches": True,
        "bom_byte_identical_to_previous": True, "only_CPL_change": "U8: 180 to 90 degrees",
        "other_CPL_rows_unchanged": 56, "omitted_reference": "U6",
        "absolute_source_paths_followed": False,
        "limit": "Verifies recorded hashes and supplier table identities. U8 visual orientation remains supported by the separately recorded preview image; this script does not infer pin orientation from pixels or certify factory CAM.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.repo, args.manifest), indent=2))


if __name__ == "__main__":
    main()
