#!/usr/bin/env python3
"""Promote the frozen five-file sourcing ECO and regenerate a matching pilot export.

Run only after the parent has checked the open KiCad project for unsaved edits.
Requires the independent replacement-U2 orientation PASS and its exact probe CPL.
Preserves the previous complete package and five original CAD files in scratch.
No git staging, commit, supplier upload, checkout, or UV modification is performed.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PYTHON = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def verify(root, hashes):
    for name, digest in hashes.items():
        path = root / name
        assert (sha(path) if path.exists() else None) == digest, name


def rows(path, key):
    with path.open(newline="") as stream:
        values = list(csv.DictReader(stream))
    result = {row[key]: row for row in values}
    assert len(result) == len(values)
    return result


def nets(path):
    return {net.get("name"): sorted(tuple(sorted(node.attrib.items())) for node in net.findall("node"))
            for net in ET.parse(path).findall("./nets/net")}


def main():
    source = ROOT / "hardware/pcb"
    package = ROOT / "hardware/gerbers/v1.1-pilot"
    profile_path = HERE.parent / "jlc/supplier-rotation-profile.json"
    review_path = HERE.parent / "radio_sourcing/u2-supplier-orientation-review.md"
    probe = HERE / "CPL-U2-90-probe.csv"
    build = load(HERE / "r4-u2-metadata-build.json")
    validation = load(HERE / "r4-u2-verification.json")
    assert validation["status"] == "PASS"
    candidate = Path(build["candidate"])
    archive = candidate.parent / "r4-u2-promotion-before"
    assert not archive.exists()
    review = review_path.read_text()
    assert "PASS" in review and "90" in review and "C5452091" in review
    assert probe.is_file()
    before = load(package / "manifest.json")
    assert before["source_files"] == build["protected_source_inputs"]
    verify(source, before["source_files"])
    verify(package, before["output_files"])
    assert len(before["source_files"]) == 160
    assert len(build["changed_files"]) == 5
    for name, change in build["changed_files"].items():
        assert sha(source / name) == change["before"]
        assert sha(candidate / name) == change["after"]
    unrelated = load(HERE.parent / "baseline.json")["unrelated_tracked"]
    assert len(unrelated) == 100
    verify(ROOT, unrelated)
    old_profile = load(profile_path)
    assert set(old_profile) == {"U1", "U4", "U7", "U8"}
    assert sha(profile_path) == "a8976ab0107919d4fd0d1aa63c263f70097ec8371fc1d183be1b6573d1912518"
    old_cpl, probe_cpl = rows(package / "CPL-stratolink.csv", "Designator"), rows(probe, "Designator")
    assert set(old_cpl) == set(probe_cpl) and len(old_cpl) == 56
    assert [ref for ref in old_cpl if old_cpl[ref] != probe_cpl[ref]] == ["U2"]
    desired = dict(old_cpl["U2"])
    desired["Rotation"] = "90.000000"
    assert desired == probe_cpl["U2"]

    archive.mkdir(parents=True)
    for name in build["changed_files"]:
        dest = archive / "cad" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, dest)
    shutil.copyfile(profile_path, archive / "supplier-rotation-profile.json")
    package.rename(archive / "pilot-package")
    verify(archive / "pilot-package", before["output_files"])
    profile = dict(old_profile)
    profile["U2"] = {
        "rotation_deg": 90,
        "evidence": "analysis/v1_1_release_20261012/radio_sourcing/u2-supplier-orientation-review.md; analysis/v1_1_release_20261012/sourcing_followup/u2-placement-cpl90-full.png; analysis/v1_1_release_20261012/sourcing_followup/CPL-U2-90-probe.csv",
        "reason": "Actual C5452091 RAK3172-8-SM-NI model after CPL90 reimport has pin 1 lower-left and its 12-pad edge at the bottom in the top view, matching native numbered lands and the manufacturer pinout.",
    }
    write(profile_path, profile)
    for name in build["changed_files"]:
        shutil.copyfile(candidate / name, source / name)
    expected_source = dict(before["source_files"])
    expected_source.update({name: value["after"] for name, value in build["changed_files"].items()})
    verify(source, expected_source)
    commands = []
    def run(name, command):
        commands.append(command)
        result = subprocess.run(command, text=True, capture_output=True)
        (archive / (name + ".log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, (name, result.returncode)
    run("export", [PYTHON, str(HERE.parent / "manufacturing/generate.py"),
                   "--candidate", str(source), "--output", str(package),
                   "--allow-part-change", "R1", "--allow-part-change", "R4",
                   "--allow-part-change", "U2", "--supplier-rotation-profile", str(profile_path)])
    run("drc", [CLI, "pcb", "drc", "--schematic-parity", "--refill-zones", "--format", "json",
                "--output", str(HERE / "promoted-drc.json"), str(source / "stratolink.kicad_pcb")])
    run("erc", [CLI, "sch", "erc", "--format", "json", "--output", str(HERE / "promoted-erc.json"),
                str(source / "stratolink.kicad_sch")])
    after = load(package / "manifest.json")
    assert after["source_files"] == expected_source
    verify(source, expected_source)
    verify(package, after["output_files"])
    verify(ROOT, unrelated)
    assert len(after["output_files"]) == 28
    assert set(p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()) == set(after["output_files"]) | {"manifest.json"}
    assert (package / "CPL-stratolink.csv").read_bytes() == probe.read_bytes()
    assert (package / "supplier-rotation-profile.json").read_bytes() == profile_path.read_bytes()
    assert after["assembly_count"] == 56 and after["exclusion_count"] == 10
    previous = archive / "pilot-package"
    a, b = rows(previous / "BOM-stratolink.csv", "Designator"), rows(package / "BOM-stratolink.csv", "Designator")
    assert set(a) == set(b) and {ref for ref in a if a[ref] != b[ref]} == {"R4", "U2"}
    assert nets(previous / "native/netlist.xml") == nets(package / "native/netlist.xml")
    old_drc, new_drc = load(HERE / "r4-u2-drc.json"), load(HERE / "promoted-drc.json")
    for key in ("violations", "unconnected_items", "schematic_parity"):
        assert old_drc[key] == new_drc[key], key
    erc = load(HERE / "promoted-erc.json")
    assert not [v for sheet in erc["sheets"] for v in sheet["violations"]]
    # Fresh native artwork may change creation timestamps only.
    prefixes = ("%TF.CreationDate,", "G04 Created by KiCad (PCBNEW 10.0.0) date ",
                "; DRILL file KiCad 10.0.0 date ", "; #@! TF.CreationDate,")
    artwork = []
    for path in sorted((previous / "gerbers").iterdir()):
        other = package / "gerbers" / path.name
        if path.suffix == ".gbrjob":
            first, second = load(path), load(other)
            del first["Header"]["CreationDate"]
            del second["Header"]["CreationDate"]
            assert first == second
        else:
            normalize = lambda file: [line for line in file.read_text().splitlines() if not line.startswith(prefixes)]
            assert normalize(path) == normalize(other), path.name
        artwork.append(path.name)
    report = dict(status="PASS: five metadata files promoted and fresh matching export verified",
                  source=str(source), package=str(package), archived_originals=str(archive),
                  candidate=str(candidate), baseline_commit=build["baseline_commit"],
                  changed_cad_files=build["changed_files"], script_sha256=sha(Path(__file__)),
                  old_package_manifest_sha256=sha(previous / "manifest.json"),
                  new_package_manifest_sha256=sha(package / "manifest.json"),
                  old_profile_sha256=sha(archive / "supplier-rotation-profile.json"),
                  new_profile_sha256=sha(profile_path),
                  independent_u2_review=dict(path=str(review_path), sha256=sha(review_path)),
                  exact_ui_probe=dict(path=str(probe), sha256=sha(probe)),
                  native_commands=commands, native_drc=dict(silk_warnings=4, opens=0, parity=0, library_mismatches=0),
                  filtered_erc=0, native_netlist_names_pin_membership_types_unchanged=True,
                  source_inputs_verified=160, output_files_verified=28, unrelated_tracked_preserved=100,
                  assembly_refs=56, exclusions=10, bom_changed_refs=["R4", "U2"],
                  cpl_changed_refs=["U2"], cpl_byte_identical_to_reviewed_probe=True,
                  physical_artwork_identical_except_creation_timestamps=artwork,
                  output_files=after["output_files"], uv_unchanged=True,
                  no_staging_commit_upload_or_order=True)
    write(HERE / "promotion.json", report)
    print(json.dumps({key: report[key] for key in ("status", "source", "package", "archived_originals",
          "new_package_manifest_sha256", "new_profile_sha256", "source_inputs_verified", "output_files_verified",
          "unrelated_tracked_preserved", "native_drc", "filtered_erc")}, indent=2))


if __name__ == "__main__":
    main()
