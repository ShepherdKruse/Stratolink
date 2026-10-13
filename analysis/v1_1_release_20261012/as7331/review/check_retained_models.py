#!/usr/bin/env python3
"""Compare retained component body/model/custom-pad primitives to the frozen Git baseline.

Use KiCad Python because the existing S-expression parser imports pcbnew. This
reads the baseline from Git rather than the canonical path, which can be promoted.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASELINE_REVISION = "60c805e"
BASELINE_SHA256 = "8e2f83797dd68195aa71b73fc252fe57e53ccd3683ef5f74739dc4d25d6ce8d5"
sys.path.insert(0, str(ROOT / "analysis/v1_1_solar_attachments_20261012/review"))
import check_solar_attachments as sx


def body_graphics(footprint):
    kinds = {"fp_line", "fp_rect", "fp_arc", "fp_circle", "fp_poly"}
    return [node for node in footprint if isinstance(node, list)
            and node[0] in kinds and sx.field(node, "layer") in {"F.Fab", "B.Fab"}]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()
    baseline = subprocess.check_output(
        ["git", "show", f"{BASELINE_REVISION}:hardware/pcb/stratolink.kicad_pcb"], cwd=ROOT)
    assert hashlib.sha256(baseline).hexdigest() == BASELINE_SHA256
    candidate_path = args.candidate / "stratolink.kicad_pcb"
    candidate = candidate_path.read_bytes()
    old, new = [{sx.prop(f, "Reference"): f for f in sx.nodes(sx.parse(data.decode()), "footprint")}
                for data in (baseline, candidate)]
    checked = dict(models=0, body_graphics=0, custom_pad_primitives=0)
    differences = []
    refs = sorted(set(old) - {"U6"})
    for ref in refs:
        a, b = old[ref], new[ref]
        if sx.nodes(a, "model") != sx.nodes(b, "model"):
            differences.append([ref, "model"])
        checked["models"] += len(sx.nodes(a, "model"))
        if sorted(map(str, body_graphics(a))) != sorted(map(str, body_graphics(b))):
            differences.append([ref, "body_graphics"])
        checked["body_graphics"] += len(body_graphics(a))
        pa, pb = [{sx.field(p, "uuid"): sx.nodes(p, "primitives") for p in sx.nodes(f, "pad")}
                  for f in (a, b)]
        if pa != pb:
            differences.append([ref, "custom_pad_primitives"])
        checked["custom_pad_primitives"] += sum(bool(p) for p in pa.values())
    result = dict(
        status="PASS" if not differences else "FAIL",
        baseline_git_revision=BASELINE_REVISION,
        baseline_source_sha256=BASELINE_SHA256,
        candidate=str(candidate_path),
        candidate_source_sha256=hashlib.sha256(candidate).hexdigest(),
        retained_component_count=len(refs), checked=checked, differences=differences)
    (HERE / "retained-model-body-primitives.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    assert not differences, differences


if __name__ == "__main__":
    main()
