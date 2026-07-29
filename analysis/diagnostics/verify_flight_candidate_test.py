#!/usr/bin/env python3
"""Regression-test frozen-candidate acceptance and corruption rejection."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile

import verify_flight_candidate as verifier


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VERIFIER = HERE / "verify_flight_candidate.py"
ELF = ROOT / "firmware/.pio/build/stratolink/firmware.elf"
BIN = ROOT / "firmware/.pio/build/stratolink/firmware.bin"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-candidate-output-") as raw:
        output = Path(raw) / "verification.json"
        output.write_text("preserved\n", encoding="utf-8")
        collision = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--elf",
                str(Path(raw) / "missing.elf"),
                "--bin",
                str(Path(raw) / "missing.bin"),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite candidate evidence" in collision.stderr
        assert output.read_text(encoding="utf-8") == "preserved\n"

    current = subprocess.run(
        [sys.executable, str(VERIFIER)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    frozen_now = (
        ELF.is_file()
        and BIN.is_file()
        and verifier.sha256(ELF) == verifier.EXPECTED_ELF_SHA256
        and verifier.sha256(BIN) == verifier.EXPECTED_BIN_SHA256
    )
    if frozen_now:
        assert current.returncode == 0, current.stdout + current.stderr
        assert '"passed": true' in current.stdout
    else:
        # During development the checked-in verifier must deliberately reject
        # the transitional build.  Once the post-soak freeze updates the bound
        # hashes this branch stops applying and the positive path above is
        # exercised automatically.
        assert current.returncode != 0
        assert '"passed": false' in current.stdout
        assert "SHA-256 differs from the frozen candidate" in current.stdout

    with tempfile.TemporaryDirectory(prefix="stratolink-memory-gate-test-") as raw:
        invalid_dynamic = Path(raw) / "dynamic.json"
        invalid_static = Path(raw) / "static.json"
        invalid_dynamic.write_text("[]\n", encoding="utf-8")
        invalid_static.write_text("not-json\n", encoding="utf-8")
        invalid_audits = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--dynamic-memory-audit",
                str(invalid_dynamic),
                "--static-stack-audit",
                str(invalid_static),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert invalid_audits.returncode != 0
        assert "dynamic-memory audit is invalid" in invalid_audits.stdout
        assert "static-stack audit is invalid" in invalid_audits.stdout
        assert "Traceback" not in invalid_audits.stderr

    with tempfile.TemporaryDirectory(prefix="stratolink-candidate-test-") as raw:
        corrupted = Path(raw) / "firmware.bin"
        data = bytearray(BIN.read_bytes())
        data[len(data) // 2] ^= 0x01
        corrupted.write_bytes(data)
        rejected = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--elf",
                str(ELF),
                "--bin",
                str(corrupted),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected.returncode != 0
        assert "BIN SHA-256 differs" in rejected.stdout

    state = "frozen candidate accepted" if frozen_now else "transitional build rejected"
    print(
        f"PASS: {state}, overwrite refused, and one-bit corruption rejected"
    )


if __name__ == "__main__":
    main()
