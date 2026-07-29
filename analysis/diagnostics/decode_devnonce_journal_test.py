#!/usr/bin/env python3
"""Adversarial tests for DevNonce journal decoding and transition checks."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from evidence_provenance import verify_all as verify_provenance
from preserve_precursor import sha256
from decode_devnonce_journal import (
    JOURNAL_BYTES,
    PAGE_BYTES,
    RECORD_TAG,
    RECORDS_PER_PAGE,
)


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "decode_devnonce_journal.py"


def encoded(nonce: int) -> bytes:
    value = RECORD_TAG | nonce
    return struct.pack("<II", value, (~value) & 0xFFFFFFFF)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def manifest(path: Path, journal: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "passed": True,
                "target": {"jlink_serial": "802007563"},
                "candidate_verification_sha256": "0" * 64,
                "flash_manifest_sha256": "1" * 64,
                "artifacts": {
                    "journal": {
                        "path": str(journal),
                        "bytes": journal.stat().st_size,
                        "sha256": sha256(journal),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-devnonce-decode-test-") as raw:
        root = Path(raw)
        blank = b"\xff" * JOURNAL_BYTES
        before = root / "before.bin"
        after = root / "after.bin"
        write(before, blank)

        one = bytearray(blank)
        one[0:8] = encoded(0)
        write(after, one)
        before_manifest = manifest(root / "before_manifest.json", before)
        after_manifest = manifest(root / "after_manifest.json", after)
        advance = run(
            "--before",
            str(before),
            "--before-manifest",
            str(before_manifest),
            "--after",
            str(after),
            "--after-manifest",
            str(after_manifest),
            "--expect-advance",
            "1",
        )
        assert advance.returncode == 0, advance.stdout + advance.stderr
        advance_json = json.loads(advance.stdout)
        assert advance_json["passed"] is True
        verify_provenance(advance_json["provenance"])
        assert advance_json["after"]["highest_nonce"] == 0
        assert advance_json["changed_slots"] == [
            {
                "after_nonce": 0,
                "before_blank": True,
                "page": 0,
                "slot": 0,
            }
        ]

        comparison_output = root / "comparison.json"
        preserved = run(
            "--before",
            str(before),
            "--before-manifest",
            str(before_manifest),
            "--after",
            str(after),
            "--after-manifest",
            str(after_manifest),
            "--expect-advance",
            "1",
            "--output",
            str(comparison_output),
        )
        assert preserved.returncode == 0, preserved.stdout + preserved.stderr
        assert comparison_output.is_file()
        collision = run(
            "--before",
            str(before),
            "--before-manifest",
            str(before_manifest),
            "--after",
            str(after),
            "--after-manifest",
            str(after_manifest),
            "--expect-advance",
            "1",
            "--output",
            str(comparison_output),
        )
        assert collision.returncode != 0
        assert "refusing to overwrite" in collision.stderr

        unchanged = run(
            "--before",
            str(after),
            "--before-manifest",
            str(after_manifest),
            "--after",
            str(after),
            "--after-manifest",
            str(after_manifest),
            "--expect-advance",
            "0",
        )
        assert unchanged.returncode == 0, unchanged.stdout + unchanged.stderr
        assert json.loads(unchanged.stdout)["changed_slots"] == []

        corrupt = bytearray(one)
        corrupt[8:16] = b"\x00" * 8
        corrupt_path = root / "corrupt.bin"
        write(corrupt_path, corrupt)
        corrupt_result = run("--journal", str(corrupt_path))
        assert corrupt_result.returncode != 0
        corrupt_json = json.loads(corrupt_result.stdout)
        assert corrupt_json["invalid_record_count"] == 1
        assert corrupt_json["invalid_slots"] == [{"page": 0, "slot": 1}]

        unrelated = bytearray(one)
        unrelated[-1] = 0xFE
        unrelated_path = root / "unrelated.bin"
        write(unrelated_path, unrelated)
        unrelated_manifest = manifest(
            root / "unrelated_manifest.json",
            unrelated_path,
        )
        unrelated_result = run(
            "--before",
            str(after),
            "--before-manifest",
            str(after_manifest),
            "--after",
            str(unrelated_path),
            "--after-manifest",
            str(unrelated_manifest),
            "--expect-advance",
            "0",
        )
        assert unrelated_result.returncode != 0
        unrelated_json = json.loads(unrelated_result.stdout)
        assert unrelated_json["passed"] is False
        assert "after journal is corrupt" in unrelated_json["failures"]
        assert (
            "journal bytes do not match the exact firmware transition"
            in unrelated_json["failures"]
        )

        rollover_before = bytearray(blank)
        for slot in range(RECORDS_PER_PAGE):
            offset = slot * 8
            rollover_before[offset:offset + 8] = encoded(slot)
        rollover_before_path = root / "rollover-before.bin"
        write(rollover_before_path, rollover_before)
        rollover_after = bytearray(rollover_before)
        rollover_after[PAGE_BYTES:2 * PAGE_BYTES] = b"\xff" * PAGE_BYTES
        rollover_after[PAGE_BYTES:PAGE_BYTES + 8] = encoded(RECORDS_PER_PAGE)
        rollover_after_path = root / "rollover-after.bin"
        write(rollover_after_path, rollover_after)
        rollover_before_manifest = manifest(
            root / "rollover-before-manifest.json",
            rollover_before_path,
        )
        rollover_after_manifest = manifest(
            root / "rollover-after-manifest.json",
            rollover_after_path,
        )
        rollover = run(
            "--before",
            str(rollover_before_path),
            "--before-manifest",
            str(rollover_before_manifest),
            "--after",
            str(rollover_after_path),
            "--after-manifest",
            str(rollover_after_manifest),
            "--expect-advance",
            "1",
        )
        assert rollover.returncode == 0, rollover.stdout + rollover.stderr
        rollover_json = json.loads(rollover.stdout)
        assert rollover_json["exact_firmware_transition"] is True
        assert rollover_json["after"]["highest_nonce"] == RECORDS_PER_PAGE

        wrong_manifest = run(
            "--before",
            str(before),
            "--before-manifest",
            str(after_manifest),
            "--after",
            str(after),
            "--after-manifest",
            str(after_manifest),
            "--expect-advance",
            "1",
        )
        assert wrong_manifest.returncode != 0
        assert "does not bind" in wrong_manifest.stderr

        failing_manifest = root / "failing_manifest.json"
        failing_manifest.write_text(
            json.dumps(
                {
                    "passed": False,
                    "target": {"jlink_serial": "802007563"},
                    "candidate_verification_sha256": "0" * 64,
                    "flash_manifest_sha256": "1" * 64,
                    "artifacts": {
                        "journal": {
                            "path": str(before),
                            "bytes": before.stat().st_size,
                            "sha256": sha256(before),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        rejected_gate = run(
            "--before",
            str(before),
            "--before-manifest",
            str(failing_manifest),
            "--after",
            str(after),
            "--after-manifest",
            str(after_manifest),
            "--expect-advance",
            "1",
        )
        assert rejected_gate.returncode != 0
        assert "manifest is not passing" in rejected_gate.stderr

    print(
        "PASS: DevNonce decode, exact transition/rollover, corruption, "
        "and mutation gates"
    )


if __name__ == "__main__":
    main()
