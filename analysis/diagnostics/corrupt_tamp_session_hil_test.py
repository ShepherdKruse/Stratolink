#!/usr/bin/env python3
"""Test the retained-session corruption gate without touching hardware."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from corrupt_tamp_session_hil import build_script
from evidence_provenance import record
from preserve_precursor import sha256
from verify_flight_candidate import (
    EXPECTED_BIN_SHA256,
    EXPECTED_ELF_SHA256,
)


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "corrupt_tamp_session_hil.py"


def file_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_state(
    root: Path,
    profile: str,
    created: datetime,
) -> tuple[Path, Path]:
    state = root / f"{profile}.json"
    state.write_text(
        json.dumps(
            {
                "manifest_elf_sha256": EXPECTED_ELF_SHA256,
                "profile_gate": {"profile": profile, "passed": True},
                "health": {"boot": {"count": 7}},
                "tamp": {
                    "boot": {"count": 7},
                    "session": {"dev_addr": "260CACD0"},
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = root / f"{profile}_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "created_utc": created.isoformat(),
                "passed": True,
                "decoded_redacted_state": file_record(state),
            }
        ),
        encoding="utf-8",
    )
    return state, manifest


def main() -> None:
    state_read = HERE / "generated/jlink_read_flight_state.jlink"
    controlled = build_script(state_read, 0x4000B10C, 0x260CACD1)
    lines = controlled.splitlines()
    writes = [line for line in lines if line.startswith(("w1 ", "w2 ", "w4 "))]
    assert writes == ["w4 0x4000B10C 0x260CACD1"]
    assert lines.count("r") == 1
    assert "sleep 10000" in lines
    assert all(
        line.startswith(("mem8 ", "mem16 ", "mem32 "))
        for line in lines[lines.index("h", 2) + 1:-2]
    )

    with tempfile.TemporaryDirectory(prefix="stratolink-tamp-corrupt-test-") as raw:
        root = Path(raw)
        source = root / "source"
        source.write_text("candidate\n", encoding="utf-8")
        hil_manifest = HERE / "generated/stratolink_flight_hil_manifest.json"
        candidate = root / "candidate.json"
        candidate.write_text(
            json.dumps(
                {
                    "passed": True,
                    "candidate": {
                        "elf_sha256": EXPECTED_ELF_SHA256,
                        "bin_sha256": EXPECTED_BIN_SHA256,
                    },
                    "provenance": {
                        "source": record(source),
                        "generated/stratolink_flight_hil_manifest.json": (
                            record(hil_manifest)
                        ),
                        "generated/jlink_read_flight_state.jlink": (
                            record(state_read)
                        ),
                    },
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
        joined = write_state(root, "joined-us", now)
        cold = write_state(root, "cold-fail-closed", now)
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
        output_dir = root / "evidence"
        command = [
            sys.executable,
            str(SCRIPT),
            "--label",
            "crc",
            "--before-state",
            str(joined[0]),
            "--before-manifest",
            str(joined[1]),
            "--output-dir",
            str(output_dir),
            "--candidate-verification",
            str(candidate),
            "--flash-manifest",
            str(flash),
            "--handoff-power",
            str(handoff),
            "--check-only",
        ]
        ready = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        report = json.loads(ready.stdout)
        assert report["ready"] is True
        assert report["mutation"] == {
            "address": "0x4000B10C",
            "bit": 0,
            "corrupted_devaddr": "260CACD1",
            "original_devaddr": "260CACD0",
            "word": 3,
        }

        wrong = command.copy()
        wrong[wrong.index("--before-state") + 1] = str(cold[0])
        wrong[wrong.index("--before-manifest") + 1] = str(cold[1])
        wrong_profile = subprocess.run(
            wrong,
            text=True,
            capture_output=True,
            check=False,
        )
        assert wrong_profile.returncode != 0
        assert "joined-us" in wrong_profile.stderr

        collision_path = (
            output_dir / "stratolink2_tamp_session_corruption_crc_20260725.json"
        )
        collision_path.parent.mkdir(parents=True)
        collision_path.write_text("occupied\n", encoding="utf-8")
        collision = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite TAMP-corruption evidence" in collision.stderr

        collision_path.unlink()
        stale_value = json.loads(joined[1].read_text(encoding="utf-8"))
        stale_value["created_utc"] = (now - timedelta(hours=1)).isoformat()
        joined[1].write_text(json.dumps(stale_value), encoding="utf-8")
        stale = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert stale.returncode != 0
        assert "stale or future-dated" in stale.stderr

    print("PASS: TAMP corruption is one-bit, exact-state, and fail-closed gated")


if __name__ == "__main__":
    main()
