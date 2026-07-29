#!/usr/bin/env python3
"""Adversarial precondition tests for exact-candidate reset evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from evidence_provenance import record
from preserve_precursor import sha256
from verify_flight_candidate import (
    EXPECTED_BIN_SHA256,
    EXPECTED_ELF_SHA256,
)


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "reset_flight_candidate.py"


def file_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-reset-test-") as raw:
        root = Path(raw)
        source = root / "source"
        source.write_text("candidate\n", encoding="utf-8")
        candidate = root / "candidate.json"
        candidate.write_text(
            json.dumps(
                {
                    "passed": True,
                    "candidate": {
                        "elf_sha256": EXPECTED_ELF_SHA256,
                        "bin_sha256": EXPECTED_BIN_SHA256,
                    },
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        flash_raw = root / "flash_raw.txt"
        flash_raw.write_text("verified\n", encoding="utf-8")
        flash = root / "flash.json"
        flash.write_text(
            json.dumps(
                {
                    "reserved_devnonce_pages_preserved": True,
                    "candidate": {
                        "elf_sha256": EXPECTED_ELF_SHA256,
                        "bin_sha256": EXPECTED_BIN_SHA256,
                    },
                    "target": {"jlink_serial": "802007563"},
                    "flash_evidence": {"raw": file_record(flash_raw)},
                }
            ),
            encoding="utf-8",
        )
        now = datetime.now(timezone.utc)
        handoff = root / "handoff.jsonl"
        handoff.write_text(
            json.dumps(
                {
                    "utc": (now - timedelta(seconds=30)).isoformat(),
                    "event": "ppk2_power_on",
                    "source_mv": 4660,
                    "reconnects": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "utc": now.isoformat(),
                    "event": "ppk2_power_heartbeat",
                    "source_mv": 4660,
                    "reconnects": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_jlink = fake_bin / "JLinkExe"
        fake_jlink.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' 'Connecting to J-Link via USB...O.K.' "
            "'Resetting target' 'Target halted' 'Target started'\n",
            encoding="utf-8",
        )
        fake_jlink.chmod(0o755)
        output_dir = root / "evidence"
        command = [
            sys.executable,
            str(SCRIPT),
            "--label",
            "session",
            "--output-dir",
            str(output_dir),
            "--candidate-verification",
            str(candidate),
            "--flash-manifest",
            str(flash),
            "--handoff-power",
            str(handoff),
        ]
        environment = dict(os.environ)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

        ready = subprocess.run(
            command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert '"ready": true' in ready.stdout

        wrong_probe = subprocess.run(
            command + ["--check-only", "--jlink-serial", "1"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert wrong_probe.returncode != 0
        assert "unrecognized J-Link" in wrong_probe.stderr

        flash_raw.write_text("mutated\n", encoding="utf-8")
        mutated = subprocess.run(
            command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert mutated.returncode != 0
        assert "no longer matches its manifest" in mutated.stderr
        flash_raw.write_text("verified\n", encoding="utf-8")

        reset = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert reset.returncode == 0, reset.stdout + reset.stderr
        manifest_path = (
            output_dir
            / "stratolink2_flight_reset_session_20260725_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["passed"] is True
        assert manifest["reset_issued"] is True
        assert manifest["target"]["ppk2_before"]["source_mv"] == 4660
        assert manifest["target"]["ppk2_after"]["max_reconnects"] == 0
        assert manifest["candidate"]["bin_sha256"] == EXPECTED_BIN_SHA256
        for evidence in (
            *manifest["gate_inputs"].values(),
            *manifest["reset_evidence"].values(),
        ):
            path = Path(evidence["path"])
            assert path.stat().st_size == evidence["bytes"]
            assert sha256(path) == evidence["sha256"]

        collision = subprocess.run(
            command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite reset evidence" in collision.stderr

    print("PASS: reset is exact-candidate, power-gated, and create-once")


if __name__ == "__main__":
    main()
