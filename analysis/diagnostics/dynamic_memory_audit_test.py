#!/usr/bin/env python3
"""Regression test for the exact-flight dynamic-memory audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "analysis/diagnostics/dynamic_memory_audit.py"
ELF = ROOT / "firmware/.pio/build/stratolink/firmware.elf"
V15_ELF_SHA256 = "8fa10da859b2c542d244cb2f62bebcf388730cbeea9eb4746a94c2d50e3d91f8"


def main() -> int:
    assert ELF.is_file(), "flight ELF is absent"
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == V15_ELF_SHA256, "flight ELF is not frozen candidate v15"
    completed = subprocess.run(
        [str(ROOT / "analysis/.venv/bin/python"), str(SCRIPT), "--repo", str(ROOT), "--elf", str(ELF)],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)
    assert result["pass"] is True
    assert result["uncommitted_ram_bytes"] == 58792
    assert result["persistent_heap_payload_bytes"] == 1008
    assert result["radio_transient_peak_payload_bytes"] == 520
    assert result["modeled_peak_heap_bytes"] == 1592
    assert result["modeled_ram_after_peak_heap_before_stack_bytes"] == 57200
    assert result["modeled_margin_ratio"] > 36
    assert "on-target stack high-water mark" in result["scope"]["does_not_prove"]
    print("PASS: frozen candidate-v15 dynamic-memory budget is source- and ELF-bound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
