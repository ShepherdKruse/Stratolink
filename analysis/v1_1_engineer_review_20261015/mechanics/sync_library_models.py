"""Preserve the reroute's embedded AE2/L2 model attachments in local libraries.

This changes library model metadata only. Run compare_model_transforms.py with
KiCad Python afterward. The board, pads, copper, paste and mask are untouched.
"""
from pathlib import Path
import argparse
import hashlib
import json


def sync(project):
    project = Path(project).resolve()
    pcb = project / "stratolink.kicad_pcb"
    original_pcb = pcb.read_bytes()
    rows = []
    for name in ("Stratolink_GNSS_Wire_PTH_D1p0", "INDC1608X90N"):
        path = project / "lib" / (name + ".kicad_mod")
        old = path.read_text()
        if name.startswith("Stratolink_GNSS"):
            before, after = "(xyz 0 -0.2 0.25)", "(xyz 0 -0.2 0.15)"
            assert old.count('(model "${KIPRJMOD}/lib/Stratolink_Wire_48mm_D0p321_Nominal.step"') == 1
            assert old.count(before) + old.count(after) == 1
            new = old.replace(before, after)
            reason = "Retain the incoming AE2 model's 0.15 mm Z offset."
        else:
            attachment = '\n  (model "${KIPRJMOD}/lib/MLZ1608N100LT000.STEP"\n    (offset (xyz 0 0 0))\n    (scale (xyz 1 1 1))\n    (rotate (xyz -90 0 0))\n  )\n'
            if "(model " in old:
                assert old.count(attachment) == 1
                new = old
            else:
                end = old.rfind(")")
                assert end >= 0 and not old[end + 1:].strip()
                new = old[:end] + attachment + old[end:]
            reason = "Retain the incoming L2 inductor model and its -90 degree X rotation."
        path.write_text(new)
        rows.append({"file": str(path.relative_to(project)), "before_sha256": hashlib.sha256(old.encode()).hexdigest(), "after_sha256": hashlib.sha256(new.encode()).hexdigest(), "changed": new != old, "reason": reason})
    assert pcb.read_bytes() == original_pcb
    return {"pcb_sha256_unchanged": hashlib.sha256(original_pcb).hexdigest(), "library_model_only_changes": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    result = sync(args.project)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
