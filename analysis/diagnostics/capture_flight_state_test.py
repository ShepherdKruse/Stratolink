#!/usr/bin/env python3
"""Test atomic state-capture preconditions without target access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from evidence_provenance import record
from preserve_precursor import sha256
from verify_flight_candidate import EXPECTED_BIN_SHA256
from capture_flight_state import classify_transport


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "capture_flight_state.py"


def file_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> None:
    stopped = classify_transport(
        "Can not attach to CPU. Trying connect under reset.", False
    )
    assert stopped["passed"] is False
    assert stopped["target_reset_by_attach"] is True
    recovered = classify_transport(
        "Can not attach to CPU. Trying connect under reset.\n"
        "J-Link>h\nJ-Link>go\nJ-Link>sleep 5000\nSleep(5000)\nJ-Link>h\n",
        True,
    )
    assert recovered["passed"] is True
    assert recovered["target_reset_by_attach"] is True
    incomplete = classify_transport("J-Link>h\n", True)
    assert incomplete["passed"] is False

    with tempfile.TemporaryDirectory(prefix="stratolink-state-capture-test-") as raw:
        root = Path(raw)
        source = root / "source"
        source.write_text("candidate\n", encoding="utf-8")
        candidate = root / "candidate.json"
        candidate.write_text(
            json.dumps(
                {
                    "passed": True,
                    "candidate": {"bin_sha256": EXPECTED_BIN_SHA256},
                    "provenance": {
                        "source": record(source),
                        "generated/jlink_read_flight_state.jlink": record(
                            HERE / "generated/jlink_read_flight_state.jlink"
                        ),
                        "generated/stratolink_flight_hil_manifest.json": record(
                            HERE / "generated/stratolink_flight_hil_manifest.json"
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )
        flash_raw = root / "flash.txt"
        flash_raw.write_text("verified\n", encoding="utf-8")
        flash = root / "flash.json"
        flash.write_text(
            json.dumps(
                {
                    "reserved_devnonce_pages_preserved": True,
                    "candidate": {"bin_sha256": EXPECTED_BIN_SHA256},
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
        command = [
            sys.executable,
            str(SCRIPT),
            "--check-only",
            "--label",
            "test",
            "--output-dir",
            str(root),
            "--profile",
            "joined-us",
            "--candidate-verification",
            str(candidate),
            "--flash-manifest",
            str(flash),
            "--handoff-power",
            str(handoff),
        ]
        ready = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert '"ready": true' in ready.stdout

        flash_raw.write_text("mutated\n", encoding="utf-8")
        refused = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert refused.returncode != 0
        assert "no longer matches its manifest" in refused.stderr

    print("PASS: atomic state-capture gate and flash-evidence rejection")


if __name__ == "__main__":
    main()
