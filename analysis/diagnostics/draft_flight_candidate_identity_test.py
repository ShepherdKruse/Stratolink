#!/usr/bin/env python3
"""The candidate identity draft must be reproducible and create-once."""

from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

from generate_flight_hil import SYMBOLS
from verify_flight_candidate import flight_source_inputs


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TOOL = HERE / "draft_flight_candidate_identity.py"
ELF = ROOT / "firmware/.pio/build/stratolink/firmware.elf"
BIN = ROOT / "firmware/.pio/build/stratolink/firmware.bin"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-identity-test-") as raw:
        directory = Path(raw)
        canonical_elf = directory / "canonical.elf"
        canonical_bin = directory / "canonical.bin"
        shutil.copyfile(ELF, canonical_elf)
        shutil.copyfile(BIN, canonical_bin)
        newest_source_ns = max(
            path.stat().st_mtime_ns for path in flight_source_inputs()
        )
        fresh_ns = newest_source_ns + 1_000_000_000
        os.utime(canonical_elf, ns=(fresh_ns, fresh_ns))
        os.utime(canonical_bin, ns=(fresh_ns, fresh_ns))

        output = directory / "identity.json"
        output.write_text("preserved\n", encoding="utf-8")
        collision = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--elf", str(canonical_elf),
                "--bin", str(canonical_bin),
                "--independent-elf", str(canonical_elf),
                "--independent-bin", str(canonical_bin),
                "--output", str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite" in collision.stderr
        assert output.read_text(encoding="utf-8") == "preserved\n"

        corrupted = directory / "corrupted.bin"
        data = bytearray(BIN.read_bytes())
        data[len(data) // 2] ^= 1
        corrupted.write_bytes(data)
        rejected = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--elf", str(canonical_elf),
                "--bin", str(canonical_bin),
                "--independent-elf", str(canonical_elf),
                "--independent-bin", str(corrupted),
                "--output", str(directory / "rejected.json"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected.returncode != 0
        assert "independent BIN is not byte-identical" in rejected.stderr
        assert not (directory / "rejected.json").exists()

        stale_elf = directory / "stale.elf"
        stale_bin = directory / "stale.bin"
        shutil.copyfile(canonical_elf, stale_elf)
        shutil.copyfile(canonical_bin, stale_bin)
        stale_ns = newest_source_ns - 1
        os.utime(stale_elf, ns=(stale_ns, stale_ns))
        os.utime(stale_bin, ns=(stale_ns, stale_ns))
        stale = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--elf", str(stale_elf),
                "--bin", str(stale_bin),
                "--independent-elf", str(stale_elf),
                "--independent-bin", str(stale_bin),
                "--output", str(directory / "stale.json"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert stale.returncode != 0
        assert "firmware inputs changed after a candidate build" in stale.stderr
        assert not (directory / "stale.json").exists()

        accepted_path = directory / "accepted.json"
        accepted = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--elf", str(canonical_elf),
                "--bin", str(canonical_bin),
                "--independent-elf", str(canonical_elf),
                "--independent-bin", str(canonical_bin),
                "--output", str(accepted_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr
        report = json.loads(accepted_path.read_text(encoding="utf-8"))
        assert report["passed"] is True
        assert report["byte_identical"] == {"elf": True, "bin": True}
        assert report["bindings"]["EXPECTED_HIL_SYMBOLS"] == len(SYMBOLS)
        assert "region_lease_trusted" in report["symbols"]
        assert len(report["provenance"]) >= 4

    print(
        "PASS: candidate identity draft accepts reproducible builds and rejects "
        "overwrite/mismatch/stale inputs"
    )


if __name__ == "__main__":
    main()
