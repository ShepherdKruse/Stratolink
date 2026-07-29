#!/usr/bin/env python3
"""Pin the stated relationship between stale KiCad DRC and current geometry."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PCB = ROOT / "hardware/pcb/stratolink.kicad_pcb"
REPORT = ROOT / "hardware/pcb/drc-final.json"
AUDIT = HERE / "STRATOLINK2_HARDWARE_RULE_AUDIT_20260725.md"


def all_items_survive(violation: dict, board_text: str) -> bool:
    items = violation.get("items", [])
    return bool(items) and all(
        isinstance(item.get("uuid"), str) and item["uuid"] in board_text
        for item in items
    )


def main() -> None:
    board_text = PCB.read_text(encoding="utf-8")
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["kicad_version"] == "8.0.3"
    violations = report["violations"]
    assert len(violations) == 84
    errors = [row for row in violations if row.get("severity") == "error"]
    assert len(errors) == 17

    surviving = [row for row in errors if all_items_survive(row, board_text)]
    counts = Counter(row["type"] for row in surviving)
    assert counts == {
        "solder_mask_bridge": 9,
        "starved_thermal": 6,
        "courtyards_overlap": 1,
    }
    assert len(surviving) == 16

    missing_error_refs = [row for row in errors if row not in surviving]
    assert [row["type"] for row in missing_error_refs] == ["items_not_allowed"]
    assert not all_items_survive(report["unconnected_items"][0], board_text)

    audit = AUDIT.read_text(encoding="utf-8")
    for phrase in (
        "16 of those 17 error findings",
        "nine mask-aperture findings",
        "six one-spoke",
        "D1/AE1 courtyard overlap",
    ):
        assert phrase in audit

    print(
        "PASS: stale KiCad-8 findings are accurately scoped against current "
        "PCB UUIDs (16/17 error objects survive)"
    )


if __name__ == "__main__":
    main()
