#!/usr/bin/env python3
"""Verify the current export without replacing historical AS7331 reports.

Run with KiCad Python after generating the package in this checkout. The older
native test functions resolve the export manifest's original source paths.
For a relocated checkout, use hardware/pcb/verify_review_package.py instead.
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "analysis/v1_1_release_20261012/as7331/manufacturing"))
from test_population import verify_package


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    package = ROOT / "hardware/gerbers/v1.1-pilot"
    report = verify_package(package, "AS7331-AQFM", "C20482877")
    report["pcb_sha256"] = sha(ROOT / "hardware/pcb/stratolink.kicad_pcb")
    report["package_manifest_sha256"] = sha(package / "manifest.json")
    report["checker_sha256"] = sha(Path(__file__))
    assert not list((package / "native/stencil").glob("*.kicad_prl"))
    assert not list((package / "native/stencil").glob("*.kicad_pro"))
    report["temporary_editor_companions_absent"] = True
    Path(__file__).with_name("package-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
