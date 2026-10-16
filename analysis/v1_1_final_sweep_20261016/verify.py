#!/usr/bin/env python3
"""Verify both final packages and the saved JLC BOM capture using Python 3.

Paths resolve from this checkout, never the generator's historical absolute
paths. Only package-verification.json is written. No CAD or package is changed.
"""
import argparse
import ast
import collections
import copy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REVIEW = "analysis/v1_1_final_sweep_20261016"
DNP = "hardware/gerbers/v1.1-final-20261016"
UV = "hardware/gerbers/v1.1-final-uv-20261016"
OLD = "hardware/gerbers/v1.1-pilot-supplier-20261016"
PCB = "e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13"
SCH = "092ddb3451545cc6f7d7d64d8c02c933e89a40acb6897d865e3a8936d54e21fb"
BOM_FIELDS = ["Comment", "Designator", "Footprint", "LCSC Part #"]
CPL_FIELDS = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def stencil_functions(path):
    """Load only the existing pure read-only proof functions, without KiCad.

    test_stencil.py imports pcbnew/wx for separate fixture-generation tests.
    Its native S-expression and Gerber proof functions do not need either.
    Compiling this explicit function allowlist avoids importing or running its
    fixture-generation/main routines and keeps this verifier portable.
    """
    names = {"nodes", "prop", "scalar", "parse", "stable_object_order",
             "verify_native", "gerber_artwork", "verify_paste"}
    parsed = ast.parse(path.read_text(), filename=str(path))
    selected = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != names:
        raise ValueError("Missing required stencil proof function")
    namespace = {"re": re, "collections": collections, "copy": copy, "json": json}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def verify_package_evidence(root, package_relative, manifest, helper):
    """Rebase recorded source/export roots without following historic paths."""
    require = helper.require
    original_source = PurePosixPath(manifest["source"])
    require(original_source.is_absolute() and original_source.parts[-2:] == ("hardware", "pcb"),
            "Unrecognized original package source root")
    anchors = {original_source.parents[1]}
    evidence = manifest["evidence_files"]
    require(isinstance(evidence, dict) and bool(evidence), "Missing package provenance hashes")
    # The previous package exported from the canonical checkout while using a
    # worktree CAD source. Its own historical-PCB output fixes that export root
    # unambiguously; no basename search or historical filesystem access occurs.
    suffix = PurePosixPath(package_relative, "native", "historical-v1.kicad_pcb").parts
    recorded_outputs = [PurePosixPath(p) for p in evidence if PurePosixPath(p).parts[-len(suffix):] == suffix]
    require(len(recorded_outputs) == 1, "Missing/ambiguous package export-root evidence")
    anchors.add(PurePosixPath(*recorded_outputs[0].parts[:-len(suffix)]))
    rebased = {}
    for recorded, digest in evidence.items():
        original = PurePosixPath(recorded)
        require(original.is_absolute() and ".." not in original.parts, "Malformed recorded evidence path")
        candidates = set()
        for anchor in anchors:
            try:
                candidates.add(str(original.relative_to(anchor)))
            except ValueError:
                pass
        require(len(candidates) == 1, "Evidence cannot be rebased unambiguously: " + recorded)
        relative = candidates.pop()
        require(relative not in rebased, "Evidence paths alias after rebasing: " + relative)
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                "Malformed evidence SHA-256")
        path = helper.local_path(root, relative)
        require(path.is_file() and helper.sha(path) == digest, "Provenance hash mismatch: " + relative)
        rebased[relative] = digest
    return {"verified_count": len(rebased), "rebased_files": rebased,
            "recorded_roots_rebased": sorted(str(p) for p in anchors)}


def verify_review_manifest(root, helper):
    relative_manifest = REVIEW + "/manifest.json"
    path = root / relative_manifest
    if not path.exists():
        return {"present": False, "verified_file_count": 0}
    digest = helper.sha(path)
    manifest = helper.read_json(path)
    files = manifest.get("files")
    helper.require(isinstance(files, dict) and bool(files), "Missing final-sweep files hash map")
    helper.require(relative_manifest not in files and REVIEW + "/package-verification.json" not in files,
                   "Circular final-sweep manifest entry")
    for relative, expected in files.items():
        helper.require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
                       "Invalid final-sweep SHA-256: " + relative)
        target = helper.local_path(root, relative)
        helper.require(target.is_file() and helper.sha(target) == expected,
                       "Final-sweep evidence hash mismatch: " + relative)
    helper.require(helper.sha(path) == digest, "Final-sweep manifest changed during verification")
    return {"present": True, "path": relative_manifest, "sha256": digest, "verified_file_count": len(files)}


def verify(root):
    root = root.resolve()
    supplier_path = root / "analysis/v1_1_supplier_review_20261016/verify.py"
    compare_path = root / "analysis/v1_1_supplier_review_20261016/compare_package.py"
    stencil_path = root / "analysis/v1_1_release_20261012/as7331/manufacturing/test_stencil.py"
    supplier = module(supplier_path, "supplier_identity_helpers")
    comparison = module(compare_path, "supplier_artwork_helpers")
    stencil = stencil_functions(stencil_path)
    require, sha, read_json = supplier.require, supplier.sha, supplier.read_json
    require(__debug__, "Do not run with Python -O: imported proof functions use assertions")
    package_paths = {"DNP": root / DNP, "UV": root / UV, "previous_DNP": root / OLD}
    manifests = {name: read_json(path / "manifest.json") for name, path in package_paths.items()}
    source = root / "hardware/pcb"
    explicit = [source / ("stratolink" + suffix) for suffix in (".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_dru")]
    explicit += [source / "fp-lib-table", source / "sym-lib-table"]
    source_files = sorted({p for p in explicit if p.is_file()} | {
        p for folder in (source / "lib", source / "3d") for p in folder.rglob("*")
        if p.is_file() and p.suffix not in {".log", ".lck", ".pyc", ".pyo"}
        and "__pycache__" not in p.relative_to(source).parts
        and p.name != ".DS_Store" and not p.name.startswith("~")
    })
    live_hashes = {str(p.relative_to(source)): sha(p) for p in source_files}
    require(len(live_hashes) == 166, "Unexpected live manufacturing input inventory")
    require(live_hashes["stratolink.kicad_pcb"] == PCB, "Wrong repaired PCB")
    require(live_hashes["stratolink.kicad_sch"] == SCH, "Wrong preserved schematic")
    packages = {}
    for name, path in package_paths.items():
        manifest = manifests[name]
        provenance = verify_package_evidence(root, str(path.relative_to(root)), manifest, supplier)
        if name != "previous_DNP":
            require(manifest["source_files"] == live_hashes, "Incomplete or stale source hashes: " + name)
        require(manifest["finish"] == "green-mask-no-silk", "Unexpected finish: " + name)
        actual = {str(p.relative_to(path)) for p in path.rglob("*") if p.is_file() and p != path / "manifest.json"}
        require(actual == set(manifest["output_files"]), "Incomplete output inventory: " + name)
        for relative, digest in manifest["output_files"].items():
            require(sha(supplier.local_path(path.resolve(), relative)) == digest, "Output hash mismatch: " + name + "/" + relative)
        with zipfile.ZipFile(path / "fabrication-review.zip") as archive:
            names = [p.name for p in (path / "gerbers").iterdir() if p.is_file()]
            require(len(archive.namelist()) == len(set(archive.namelist())), "Duplicate ZIP member: " + name)
            require(set(archive.namelist()) == set(names), "ZIP/export membership mismatch: " + name)
            require(all(archive.read(member) == (path / "gerbers" / member).read_bytes() for member in names), "ZIP/export bytes differ: " + name)
        bom = supplier.csv_rows(path / "BOM-stratolink.csv", BOM_FIELDS)
        cpl = supplier.csv_rows(path / "CPL-stratolink.csv", CPL_FIELDS)
        audit = read_json(path / "assembly-audit.json")
        require(set(bom) == set(cpl) == set(audit["assembly"]), "BOM/CPL/audit population mismatch: " + name)
        for ref, row in audit["assembly"].items():
            require(bom[ref] == {"Comment": row["mpn"], "Designator": ref, "Footprint": row["footprint"], "LCSC Part #": row["lcsc"]}, "BOM/audit mismatch: " + ref)
            require(cpl[ref] == {"Designator": ref, "Mid X": f"{row['center_mm'][0]:.6f}", "Mid Y": f"{-row['center_mm'][1]:.6f}", "Layer": row["side"], "Rotation": f"{row['rotation_deg']:.6f}"}, "CPL/audit mismatch: " + ref)
        packages[name] = {"path": str(path.relative_to(root)), "manifest_sha256": sha(path / "manifest.json"),
                          "fabrication_zip_sha256": sha(path / "fabrication-review.zip"),
                          "bom_sha256": sha(path / "BOM-stratolink.csv"), "cpl_sha256": sha(path / "CPL-stratolink.csv"),
                          "source_hash_count": len(manifest["source_files"]), "output_hash_count": len(actual),
                          "assembly_count": len(bom), "complete_output_inventory_and_all_hashes_valid": True,
                          "zip_members_match_exports": True, "package_evidence": provenance}
    dnp, uv, old = (package_paths[k] for k in ("DNP", "UV", "previous_DNP"))
    for name in ("BOM-stratolink.csv", "CPL-stratolink.csv", "native/positions.csv"):
        require((dnp / name).read_bytes() == (old / name).read_bytes(), "Final DNP changed " + name)
    unchanged_artwork = []
    for folder in ("gerbers", "native/full-design-paste", "native/stencil/gerbers"):
        before, after = old / folder, dnp / folder
        require({p.name for p in before.iterdir()} == {p.name for p in after.iterdir()}, "Artwork inventory changed: " + folder)
        for path in sorted(before.iterdir()):
            other = after / path.name
            require(comparison.artwork(path) == comparison.artwork(other), "Artwork changed: " + str(path.relative_to(old)))
            unchanged_artwork.append({"file": str(path.relative_to(old)), "before_sha256": sha(path), "after_sha256": sha(other)})
    bom_dnp, bom_uv = [supplier.csv_rows(path / "BOM-stratolink.csv", BOM_FIELDS) for path in (dnp, uv)]
    cpl_dnp, cpl_uv = [supplier.csv_rows(path / "CPL-stratolink.csv", CPL_FIELDS) for path in (dnp, uv)]
    require(set(bom_uv) - set(bom_dnp) == {"U6"} and len(bom_dnp) == 57 and len(bom_uv) == 58, "Unexpected UV population difference")
    require({k: v for k, v in bom_uv.items() if k != "U6"} == bom_dnp, "UV variant changed retained BOM rows")
    require({k: v for k, v in cpl_uv.items() if k != "U6"} == cpl_dnp, "UV variant changed retained CPL rows")
    require(bom_uv["U6"]["Comment"] == "AS7331-AQFM" and bom_uv["U6"]["LCSC Part #"] == "C20482877", "Wrong U6 identity")
    require(cpl_dnp["U8"]["Rotation"] == cpl_uv["U8"]["Rotation"] == "90.000000", "Lost U8 supplier correction")
    audits = {name: read_json(path / "assembly-audit.json") for name, path in (("DNP", dnp), ("UV", uv))}
    require(audits["DNP"]["design_assembly"] == audits["UV"]["design_assembly"] == audits["UV"]["assembly"], "Complete-design assembly differs between variants")
    require(audits["DNP"]["assembly"] == {k: v for k, v in audits["UV"]["assembly"].items() if k != "U6"}, "Pilot omission changed other assembly data")
    require(set(audits["DNP"]["population_profile"]["omit"]) == {"U6"} and audits["UV"]["population_profile"] is None, "Unexpected variant profile")
    require({"R27", "C14", "C23"} <= set(bom_dnp), "U6 support components are missing")
    require((dnp / "native/positions.csv").read_bytes() == (uv / "native/positions.csv").read_bytes(), "Native position export differs between variants")
    identical_variant_files = []
    for path in sorted((dnp / "gerbers").iterdir()):
        if path.name == "stratolink-F_Paste.gtp":
            continue
        require(comparison.artwork(path) == comparison.artwork(uv / "gerbers" / path.name), "UV variant changed fabrication: " + path.name)
        identical_variant_files.append(path.name)
    require({p.name for p in (dnp / "gerbers").iterdir()} == {p.name for p in (uv / "gerbers").iterdir()}, "Variant Gerber inventories differ")
    stencil_changes = stencil["verify_native"](source / "stratolink.kicad_pcb", dnp / "native/stencil/stratolink.kicad_pcb")
    require(len(stencil_changes) == 16, "Pilot stencil must omit exactly 16 U6 paste flags")
    paste = {}
    for name in ("stratolink-F_Paste.gtp", "stratolink-B_Paste.gbp"):
        full, pilot = uv / "gerbers" / name, dnp / "gerbers" / name
        require(comparison.artwork(full) == comparison.artwork(dnp / "native/full-design-paste" / name), "UV paste differs from complete native design")
        require(pilot.read_bytes() == (dnp / "native/stencil/gerbers" / name).read_bytes(), "Pilot paste differs from stencil export")
        paste[name] = stencil["verify_paste"](full, pilot)
    stencil_proof = read_json(dnp / "stencil-population-proof.json")
    require(stencil_proof["source_pcb_sha256"] == PCB and stencil_proof["stencil_pcb_sha256"] == sha(dnp / "native/stencil/stratolink.kicad_pcb"), "Stencil proof identity mismatch")
    require(stencil_proof["omitted_refs"] == ["U6"], "Unexpected stencil omission")
    require({r["uuid"]: r for r in stencil_proof["pad_changes"]} == {r["uuid"]: r for r in stencil_changes}, "Stencil pad proof mismatch")
    ui_path = root / REVIEW / "jlc/bom-final.json"
    selected, sides = supplier.verify_selected_rows(read_json(ui_path), bom_dnp, cpl_dnp)
    require(live_hashes == {str(p.relative_to(source)): sha(p) for p in source_files}, "Live source changed during verification")
    review_manifest = verify_review_manifest(root, supplier)
    return {
        "status": "PASS", "verifier_sha256": sha(Path(__file__)),
        "helper_hashes": {str(p.relative_to(root)): sha(p) for p in (supplier_path, compare_path, stencil_path)},
        "source_files": live_hashes, "source_inventory_complete": True, "source_unchanged_during_verification": True,
        "packages": packages, "DNP_BOM_CPL_and_native_positions_byte_identical_to_previous": True,
        "DNP_artwork_identical_except_export_timestamps": unchanged_artwork,
        "UV_vs_DNP": {"only_added_reference": "U6", "U6_BOM": bom_uv["U6"], "U6_CPL": cpl_uv["U6"],
                      "all_retained_BOM_CPL_rows_identical": True, "all_other_fabrication_files_identical_except_timestamps": identical_variant_files,
                      "whole_stencil_PCB_exact_except_16_U6_paste_flags": True, "paste": paste},
        "JLC_final_capture": {"path": str(ui_path.relative_to(root)), "sha256": sha(ui_path), "selected_references": len(selected),
                              "selected_sides": sides, "all_selected_MPN_LCSC_footprint_reference_side_match": True},
        "historical_absolute_source_paths_followed": False,
        "final_sweep_evidence_manifest": review_manifest,
        "limits": ["Checks saved files and captured supplier selections, not the mutable live cart or final CAM.",
                   "The UV-populated package still needs U6 sourcing, supplier orientation review, firmware and optical qualification.",
                   "Timestamp normalization removes only known export date fields and comments, preserving every geometry command."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=HERE / "package-verification.json")
    args = parser.parse_args()
    report = verify(args.repo)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "live_source_files": len(report["source_files"]),
                      "packages": {k: {field: p[field] for field in ("assembly_count", "output_hash_count", "manifest_sha256")}
                                   for k, p in report["packages"].items()},
                      "DNP_timestamp_normalized_files": len(report["DNP_artwork_identical_except_export_timestamps"]),
                      "UV_added_reference": report["UV_vs_DNP"]["only_added_reference"],
                      "JLC_selected_references": report["JLC_final_capture"]["selected_references"],
                      "package_provenance_counts": {k: p["package_evidence"]["verified_count"] for k, p in report["packages"].items()},
                      "final_sweep_manifest_files": report["final_sweep_evidence_manifest"]["verified_file_count"]}, indent=2))


if __name__ == "__main__":
    main()
