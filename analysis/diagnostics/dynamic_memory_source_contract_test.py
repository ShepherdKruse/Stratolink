#!/usr/bin/env python3
"""Verify the current flight ELF's allocation contract during development.

The immutable candidate test remains hash-bound to the last frozen image until
the next candidate is cut. This companion regression keeps the underlying
source/disassembly/RAM model live while the worktree is intentionally newer.
"""

from pathlib import Path

from dynamic_memory_audit import audit


ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT / "firmware/.pio/build/stratolink/firmware.elf"
AUDIT_SOURCE = ROOT / "analysis/diagnostics/dynamic_memory_audit.py"


def main() -> None:
    assert "write_create_once(args.output" in AUDIT_SOURCE.read_text(
        encoding="utf-8"
    )
    assert ELF.is_file(), "current flight ELF is absent"
    result = audit(ROOT, ELF)
    assert result["schema"] == "stratolink.dynamic_memory_audit.v2"
    assert result["pass"] is True
    assert result["persistent_heap_payload_bytes"] == 1008
    assert result["radio_transient_peak_payload_bytes"] == 520
    assert result["modeled_peak_heap_bytes"] == 1592
    assert result["modeled_ram_after_peak_heap_before_stack_bytes"] == (
        result["uncommitted_ram_bytes"] - result["modeled_peak_heap_bytes"]
    )
    assert result["modeled_margin_ratio"] > 20
    assert result["checks"]["radio_allocation_staged_and_null_checked"] is True
    assert (
        "staged RadioLib allocation and emitted pre-constructor null branches"
        in result["scope"]["proves"]
    )
    assert "on-target stack high-water mark" in result["scope"]["does_not_prove"]
    print("PASS: current flight ELF dynamic-memory source contract")


if __name__ == "__main__":
    main()
