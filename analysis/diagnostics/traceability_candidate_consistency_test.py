#!/usr/bin/env python3
"""Keep the post-flight ledger bound to superseded candidate-v9 evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TRACEABILITY = HERE / "STRATOLINK2_POSTFLIGHT_CHANGE_TRACEABILITY.md"
VERIFICATION = (
    HERE / "logs/stratolink2_flight_candidate_verification_20260726_v9.json"
)
EXPECTED_REPORT_SHA256 = (
    "23cdf81b927b064456d306e93a7e54b38d7cd05cac948babc18d4810ed5d6d1b"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    report = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    ledger = TRACEABILITY.read_text(encoding="utf-8")

    assert sha256(VERIFICATION) == EXPECTED_REPORT_SHA256
    assert report["passed"] is True
    assert report["failures"] == []
    assert report["source_freshness"]["inputs_checked"] == 88
    assert report["source_freshness"]["newer_than_elf"] == []
    assert report["hil"]["required_symbols"] == 47
    assert report["hil"]["mismatches"] == []

    candidate = report["candidate"]
    memory = report["memory"]
    for exact in (
        "## Superseded candidate v9 identity — historical evidence only",
        candidate["elf_sha256"],
        candidate["bin_sha256"],
        f'{candidate["elf_bytes"]:,}',
        f'{candidate["bin_bytes"]:,}',
        f'{memory["loadable_flash_bytes"]:,}',
        f'{memory["initialized_static_ram_bytes"]:,}',
        f'{memory["reserved_heap_stack_bytes"]:,}',
        EXPECTED_REPORT_SHA256,
        "Candidate v9 is **superseded and must not be flashed**",
        "post-v9 source repairs require a newly numbered",
    ):
        assert exact in ledger, f"candidate ledger missing {exact!r}"

    assert "The current transitional build is byte-reproducible" not in ledger
    assert "zero failures" in ledger
    print("PASS: post-flight traceability preserves and supersedes candidate v9")


if __name__ == "__main__":
    main()
