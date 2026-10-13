#!/usr/bin/env python3
"""Apply the four UI-reviewed v1.1 CPL rotations without replacing fabrication.

Run against the original package and a fresh generate.py --supplier-rotation-profile
export. --evidence-dir must not exist. The four original mutable files are saved
there before any package write. To reproduce after correction, copy the package to
scratch, restore those four originals and remove supplier-rotation-profile.json;
then run this helper against that restored copy with a fresh evidence directory.
No CAD edits, native re-exports, upload, or order are performed by this helper.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def verify_files(root, hashes):
    for name, expected in hashes.items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts, name
        assert sha(root / name) == expected, name


def csv_rows(path):
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    refs = [row["Designator"] for row in rows]
    assert len(set(refs)) == len(refs) == 56
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "generated", "profile", "probe", "evidence-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    package, generated, profile, probe, evidence = (
        getattr(args, name).resolve()
        for name in ("package", "generated", "profile", "probe", "evidence_dir")
    )
    assert package != generated and not evidence.exists()
    assert package not in evidence.parents and generated not in evidence.parents
    before = read_json(package / "manifest.json")
    fresh = read_json(generated / "manifest.json")
    assert "post_export_corrections" not in before
    assert not (package / "supplier-rotation-profile.json").exists()
    assert len(before["source_files"]) == 160
    assert before["source_files"] == fresh["source_files"]
    assert before["source"] == fresh["source"]
    source = Path(before["source"])
    verify_files(source, before["source_files"])
    verify_files(package, before["output_files"])
    verify_files(generated, fresh["output_files"])
    assert len(before["output_files"]) == 27
    assert sha(package / "BOM-stratolink.csv") == sha(generated / "BOM-stratolink.csv")
    assert (generated / "CPL-stratolink.csv").read_bytes() == probe.read_bytes()
    assert (generated / "supplier-rotation-profile.json").read_bytes() == profile.read_bytes()

    expected = {"U1": (180.0, 90.0), "U4": (0.0, 270.0),
                "U7": (90.0, 0.0), "U8": (180.0, 90.0)}
    requested = read_json(profile)
    assert set(requested) == set(expected)
    for ref, (_, angle) in expected.items():
        assert requested[ref]["rotation_deg"] == angle
    old_rows = csv_rows(package / "CPL-stratolink.csv")
    new_rows = csv_rows(generated / "CPL-stratolink.csv")
    changes = []
    for old, new in zip(old_rows, new_rows):
        assert {k: v for k, v in old.items() if k != "Rotation"} == {
            k: v for k, v in new.items() if k != "Rotation"}
        ref = old["Designator"]
        if old != new:
            assert (float(old["Rotation"]), float(new["Rotation"])) == expected[ref]
            changes.append({"ref": ref, "before_deg": float(old["Rotation"]),
                            "after_deg": float(new["Rotation"])})
    assert {row["ref"] for row in changes} == set(expected)

    old_audit = read_json(package / "assembly-audit.json")
    new_audit = read_json(generated / "assembly-audit.json")
    profile_audit = new_audit["supplier_rotation_profile"]
    assert profile_audit == fresh["supplier_rotation_profile"]
    assert profile_audit["profile_sha256"] == sha(profile)
    assert {k: v for k, v in old_audit.items() if k != "assembly"} == {
        k: v for k, v in new_audit.items() if k not in ("assembly", "supplier_rotation_profile")}
    assert set(old_audit["assembly"]) == set(new_audit["assembly"])
    for ref, old in old_audit["assembly"].items():
        wanted = dict(old)
        if ref in expected:
            wanted["rotation_deg"] = expected[ref][1]
        assert wanted == new_audit["assembly"][ref], ref

    generator = Path(__file__).resolve().with_name("generate.py")
    assert fresh["evidence_files"][str(generator)] == sha(generator)
    original_manifest_hash = sha(package / "manifest.json")
    evidence.mkdir(parents=True)
    originals = ("manifest.json", "CPL-stratolink.csv", "assembly-audit.json", "README.md")
    for name in originals:
        shutil.copyfile(package / name, evidence / name)
    shutil.copyfile(generated / "manifest.json", evidence / "fresh-generation-manifest.json")

    changed_outputs = ("CPL-stratolink.csv", "assembly-audit.json", "README.md")
    for name in changed_outputs[:2]:
        shutil.copyfile(generated / name, package / name)
    shutil.copyfile(profile, package / "supplier-rotation-profile.json")
    readme = (generated / "README.md").read_text().replace(
        "This export applies 4 explicit supplier rotation overrides",
        "The post-export correction applies 4 explicit supplier rotation overrides")
    readme += (
        "\nPost-export correction: only U1 180→90°, U4 0→270°, U7 90→0°, and U8 180→90° "
        "were changed in the CPL after supplier preview. The corrected CPL exactly matches "
        "the reimported, pin-1-reviewed probe. All 56 centers, sides and reference designators "
        "are unchanged. The original Gerbers, drills, fabrication ZIP, BOM, native exports, "
        "logs and historical proof are retained byte-for-byte; they were not re-exported "
        "into this package. The original generator hash and native export commands remain "
        "in manifest.json. Its post_export_corrections entry separately records the current "
        "generator/profile/helper/report hashes and the archived original files. The retained "
        "historical-placement-proof.json establishes agreement with the repository v1 "
        "production INPUT CPL only; any legacy shipped wording there does not establish "
        "verified JLC post-CAM orientation.\n")
    (package / "README.md").write_text(readme)

    outputs = dict(before["output_files"])
    for name in (*changed_outputs, "supplier-rotation-profile.json"):
        outputs[name] = sha(package / name)
    unchanged = {name: digest for name, digest in before["output_files"].items()
                 if name not in changed_outputs}
    verify_files(package, unchanged)
    verify_files(source, before["source_files"])
    report = {
        "operation": "post-export supplier rotation correction; no fabrication re-export",
        "package": str(package), "original_manifest_sha256": original_manifest_hash,
        "original_files": {name: sha(evidence / name) for name in originals},
        "fresh_export_manifest_sha256": sha(evidence / "fresh-generation-manifest.json"),
        "current_generator_sha256": sha(generator), "helper_sha256": sha(Path(__file__)),
        "profile_sha256": sha(profile), "probe_sha256": sha(probe),
        "probe_path": str(probe), "cpl_byte_identical_to_ui_reviewed_probe": True,
        "rotation_changes": changes, "all_56_centers_sides_refs_unchanged": True,
        "source_files_verified_unchanged": len(before["source_files"]),
        "unchanged_original_outputs": unchanged, "corrected_output_files": outputs,
        "supplier_rotation_profile": profile_audit,
        "original_native_commands_and_generator_provenance_preserved": True,
    }
    report_path = evidence / "correction-report.json"
    write_json(report_path, report)
    after = dict(before)
    after["output_files"] = outputs
    after["post_export_corrections"] = [{
        "operation": report["operation"], "original_manifest_sha256": original_manifest_hash,
        "original_files_directory": str(evidence), "report_path": str(report_path),
        "report_sha256": sha(report_path), "helper_path": str(Path(__file__).resolve()),
        "helper_sha256": report["helper_sha256"], "current_generator_path": str(generator),
        "current_generator_sha256": sha(generator), "profile_sha256": sha(profile),
        "probe_sha256": sha(probe), "supplier_rotation_profile": profile_audit,
    }]
    write_json(package / "manifest.json", after)
    verify_files(package, after["output_files"])
    verify_files(source, after["source_files"])
    assert {k: v for k, v in after.items() if k not in ("output_files", "post_export_corrections")} == {
        k: v for k, v in before.items() if k != "output_files"}
    print(json.dumps({"manifest_sha256": sha(package / "manifest.json"),
                      "report_sha256": sha(report_path), "output_files": len(outputs),
                      "source_files": len(before["source_files"]),
                      "unchanged_original_outputs": len(unchanged), "rotations": changes}, indent=2))


if __name__ == "__main__":
    main()
