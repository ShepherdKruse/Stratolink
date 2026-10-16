#!/usr/bin/env python3
"""Verify the supplier-only U8 rotation export without changing either package.

Run with KiCad's Python from any working directory. Timestamp normalization is
limited to documented export metadata; drawing commands are compared exactly.
"""
from pathlib import Path
import copy
import csv
import hashlib
import json
import re
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis/v1_1_release_20261012/as7331/manufacturing"))
from test_population import verify_package


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def tree(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def artwork(path):
    if path.suffix == ".gbrjob":
        data = read_json(path)
        del data["Header"]["CreationDate"]
        return json.dumps(data, sort_keys=True)
    lines = path.read_text().splitlines()
    ignored = (
        r"%TF\.CreationDate,[^*]+\*%",
        r"G04 Created by KiCad \(PCBNEW 10\.0\.0\) date [^*]+\*",
        r"; DRILL file KiCad 10\.0\.0 date .+",
        r"; #@! TF\.CreationDate,.+",
    )
    return "\n".join(line for line in lines if not any(re.fullmatch(p, line) for p in ignored))


def rows(path):
    with path.open(newline="") as stream:
        values = list(csv.DictReader(stream))
    result = {row["Designator"]: row for row in values}
    assert len(values) == len(result)
    return result


def main():
    inputs = read_json(HERE / "package-inputs.json")
    old, new = Path(inputs["old_package"]), Path(inputs["new_package"])
    source = Path(inputs["source"])
    assert tree(old) == inputs["old_package_files"], "Frozen pilot package changed"
    assert tree(Path(inputs["frozen_manufacturing"])) == inputs["frozen_manufacturing_files"], "Frozen evidence changed"
    a, b = read_json(old / "manifest.json"), read_json(new / "manifest.json")
    assert a["source_files"] == b["source_files"] == inputs["source_files"]
    assert {name: sha(source / name) for name in b["source_files"]} == b["source_files"]
    assert b["source_files"]["stratolink.kicad_pcb"] == "25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f"
    package_proof = verify_package(new, "AS7331-AQFM", "C20482877")
    for rel, digest in a["output_files"].items():
        assert sha(old / rel) == digest
    assert a["finish"] == b["finish"] == "green-mask-no-silk"
    assert a["assembly_count"] == b["assembly_count"] == 57
    assert (old / "BOM-stratolink.csv").read_bytes() == (new / "BOM-stratolink.csv").read_bytes()
    before, after = rows(old / "CPL-stratolink.csv"), rows(new / "CPL-stratolink.csv")
    expected = copy.deepcopy(before)
    assert before["U8"]["Rotation"] == "180.000000"
    expected["U8"]["Rotation"] = "90.000000"
    assert after == expected, "Unexpected placement change"
    assert (old / "native/positions.csv").read_bytes() == (new / "native/positions.csv").read_bytes()
    strip_netlist_date = lambda p: re.sub(r"<date>[^<]*</date>", "<date>EXPORT_TIME</date>", p.read_text())
    assert strip_netlist_date(old / "native/netlist.xml") == strip_netlist_date(new / "native/netlist.xml")
    fabrication = []
    for folder in ("gerbers", "native/full-design-paste", "native/stencil/gerbers"):
        first, second = old / folder, new / folder
        assert {p.name for p in first.iterdir()} == {p.name for p in second.iterdir()}
        for path in sorted(first.iterdir()):
            other = second / path.name
            assert artwork(path) == artwork(other), "Fabrication geometry changed: " + str(path)
            fabrication.append({"file": str(path.relative_to(old)), "old_sha256": sha(path),
                                "new_sha256": sha(other), "equal_except_export_timestamps": True})
    for package in (old, new):
        with zipfile.ZipFile(package / "fabrication-review.zip") as archive:
            expected_members = {p.name for p in (package / "gerbers").iterdir()}
            assert set(archive.namelist()) == expected_members
            assert all(archive.read(name) == (package / "gerbers" / name).read_bytes() for name in expected_members)
    old_profile, new_profile = read_json(old / "supplier-rotation-profile.json"), read_json(new / "supplier-rotation-profile.json")
    assert {ref: row for ref, row in new_profile.items() if ref != "U8"} == old_profile
    assert new_profile["U8"]["rotation_deg"] == 90
    assert sha(new / "supplier-rotation-profile.json") == inputs["profile_sha256"] == sha(Path(inputs["profile_path"]))
    old_audit, new_audit = read_json(old / "assembly-audit.json"), read_json(new / "assembly-audit.json")
    expected_audit = copy.deepcopy(old_audit)
    for key in ("assembly", "design_assembly"):
        expected_audit[key]["U8"]["rotation_deg"] = 90.0
    expected_audit["supplier_rotation_profile"] = new_audit["supplier_rotation_profile"]
    assert expected_audit == new_audit
    assert old_audit["supplier_rotation_profile"]["overrides"] == new_audit["supplier_rotation_profile"]["overrides"][:-1]
    assert new_audit["supplier_rotation_profile"]["overrides"][-1]["ref"] == "U8"
    assert (old / "native/stencil/stratolink.kicad_pcb").read_bytes() == (new / "native/stencil/stratolink.kicad_pcb").read_bytes()
    assert not list((new / "native/stencil").glob("*.kicad_prl"))
    assert not list((new / "native/stencil").glob("*.kicad_pro"))
    report = {
        "pcb_sha256": b["source_files"]["stratolink.kicad_pcb"],
        "schematic_sha256": b["source_files"]["stratolink.kicad_sch"],
        "old_package": str(old), "new_package": str(new),
        "old_manifest_sha256": sha(old / "manifest.json"), "new_manifest_sha256": sha(new / "manifest.json"),
        "new_fabrication_zip_sha256": sha(new / "fabrication-review.zip"),
        "bom_sha256": sha(new / "BOM-stratolink.csv"),
        "old_cpl_sha256": sha(old / "CPL-stratolink.csv"), "new_cpl_sha256": sha(new / "CPL-stratolink.csv"),
        "profile_sha256": inputs["profile_sha256"], "checker_sha256": sha(Path(__file__)),
        "source_files_identical_and_unchanged": len(b["source_files"]),
        "frozen_pilot_and_engineer_manufacturing_evidence_unchanged": True,
        "bom_byte_identical": True, "native_positions_byte_identical": True,
        "netlist_identical_except_export_timestamp": True,
        "stencil_pcb_byte_identical": True, "all_zip_members_match_export_files": True,
        "only_placement_change": {"ref": "U8", "before": before["U8"], "after": after["U8"]},
        "other_placement_rows_unchanged": len(after) - 1,
        "fabrication_files": fabrication, "population_verification": package_proof,
        "supplier_reimport_status": "Pending fresh preview verification; this comparison does not certify supplier model orientation or factory CAM.",
    }
    (HERE / "package-comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"fabrication_files", "population_verification"}}, indent=2))


if __name__ == "__main__":
    main()
