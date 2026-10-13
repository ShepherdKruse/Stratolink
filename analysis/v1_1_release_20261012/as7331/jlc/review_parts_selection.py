#!/usr/bin/env python3
"""Audit the saved JLC accessibility snapshot without browser interaction."""
from pathlib import Path
import csv
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / "hardware/gerbers/v1.1-pilot"


def csv_by_ref(path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {row["Designator"]: row for row in rows}
    assert len(result) == len(rows), f"Duplicate CSV reference: {path}"
    return result


def main():
    snapshot = HERE / "matched-parts-selection.txt"
    text = snapshot.read_text()
    row_matches = list(re.finditer(r"^        - row (.+):$", text, re.M))
    parsed = {}
    header_rows = 0
    for index, match in enumerate(row_matches):
        block = text[match.end():row_matches[index + 1].start()
                     if index + 1 < len(row_matches) else len(text)]
        cells = []
        for cell in re.finditer(r"^          - cell(.*)$", block, re.M):
            label = cell.group(1).strip().removesuffix(":")
            cells.append(json.loads(label) if label.startswith('"') else label)
        if not cells:
            assert "columnheader" in block, "Unexpected non-data row"
            header_rows += 1
            continue
        assert len(cells) >= 5
        top, bottom, comment, footprint, detail = cells[:5]
        assert bool(top) != bool(bottom), "Ambiguous placement side"
        ref = top or bottom
        assert re.fullmatch(r"[A-Z]+\d+", ref), ref
        assert ref not in parsed, f"Duplicate UI row: {ref}"
        checkbox_lines = re.findall(r"^\s*- checkbox(.*)$", block, re.M)
        assert checkbox_lines == [" [checked]"], (ref, checkbox_lines)
        mpn, lcsc, _ = detail.split(maxsplit=2)
        assert re.fullmatch(r"C\d+", lcsc), (ref, detail)
        parsed[ref] = dict(ref=ref, selected=True, uploaded_comment=comment,
                           uploaded_footprint=footprint, matched_mpn=mpn,
                           matched_lcsc=lcsc, side="top" if top else "bottom")

    bom = csv_by_ref(PACKAGE / "BOM-stratolink.csv")
    cpl = csv_by_ref(PACKAGE / "CPL-stratolink.csv")
    profile = json.loads((PACKAGE / "population-profile.json").read_text())
    audit = json.loads((PACKAGE / "assembly-audit.json").read_text())
    assert header_rows == 2
    assert len(parsed) == len(bom) == len(cpl) == 57
    assert set(parsed) == set(bom) == set(cpl) == set(audit["assembly"])
    for ref, row in parsed.items():
        expected = bom[ref]
        assert row["uploaded_comment"] == expected["Comment"], ref
        assert row["uploaded_footprint"] == expected["Footprint"], ref
        assert row["matched_mpn"] == expected["Comment"], ref
        assert row["matched_lcsc"] == expected["LCSC Part #"], ref
        assert row["side"] == cpl[ref]["Layer"], ref
        design = audit["design_assembly"][ref]
        assert row["matched_mpn"] == design["mpn"], ref
        assert row["matched_lcsc"] == design["lcsc"], ref
        assert row["uploaded_footprint"] == design["footprint"], ref
    assert len(audit["design_assembly"]) == 58
    assert set(audit["design_assembly"]) - set(parsed) == {"U6"}
    assert set(profile["omit"]) == {"U6"}
    assert all(ref in parsed for ref in ("C14", "C23", "R27"))
    assert parsed["C14"]["matched_lcsc"] == parsed["C23"]["matched_lcsc"] == "C1525"
    assert parsed["R27"]["matched_lcsc"] == "C4313228"
    sources = [snapshot, PACKAGE / "BOM-stratolink.csv", PACKAGE / "CPL-stratolink.csv",
               PACKAGE / "population-profile.json", PACKAGE / "assembly-audit.json",
               Path(__file__).resolve()]
    report = dict(
        status="PASS", reviewed_date="2026-10-13", selected_rows=len(parsed),
        design_assembly_rows=58, unselected_design_assembly=["U6"],
        exact_bom_reference_set=True, all_mpn_lcsc_and_footprint_matches=True,
        cpl_reference_set_and_sides_match=True,
        support_circuit_selected={ref: parsed[ref] for ref in ("C14", "C23", "R27")},
        rows=[parsed[ref] for ref in sorted(parsed)], discrepancies=[],
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sources},
        limitations=[
            "This verifies the saved matched-parts snapshot, not subsequent live browser state.",
            "The BOM page exposes placement side but not rotation or coordinates; those need the component-placement view and package verification.",
            "Part quantities shown by JLC include supplier purchasing overhead; 57 refers to populated designator rows, not purchased units.",
            "U6 is the sole omission from the 58-part design assembly set; manual/non-assembly items remain governed by the separate assembly exclusions."
        ])
    (HERE / "parts-selection-review.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = """# JLC matched-parts selection review

**PASS — 2026-10-13.** The saved `matched-parts-selection.txt` contains exactly 57 unique part rows, all checked. Each row's matched manufacturer part number and LCSC number equals the pilot BOM; uploaded comments and footprints also match. The reference set and top/bottom columns equal the CPL.

- C14 and C23: CL05B104KO5NNNC / C1525, selected.
- R27: MCU0805MD3304BP500 / C4313228, selected.
- U6 is the sole omitted part from the 58-part design assembly set, matching the explicit pilot population profile.
- No discrepancies found.

`parts-selection-review.json` contains every row and source hashes. Reproduce with `python3 review_parts_selection.py`. This audit uses only the saved snapshot and local package; it does not inspect subsequent browser changes or verify coordinates/rotation, which are absent from the BOM page.
"""
    (HERE / "parts-selection-review.md").write_text(summary)
    print("PASS: 57/57 rows selected, exact MPN/LCSC/footprint/side matches; U6 only omitted.")


if __name__ == "__main__":
    main()
