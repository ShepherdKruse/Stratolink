#!/usr/bin/env python3
"""Test that allow-listed HIL mutations are exact, gated, and create-once."""

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
SCRIPT = HERE / "apply_flight_hil_action.py"


def file_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_state(root: Path, profile: str, now: datetime) -> tuple[Path, Path]:
    state = root / f"{profile}.json"
    state.write_text(
        json.dumps(
            {
                "manifest_elf_sha256": EXPECTED_ELF_SHA256,
                "profile_gate": {"profile": profile, "passed": True},
            }
        ),
        encoding="utf-8",
    )
    manifest = root / f"{profile}_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "created_utc": now.isoformat(),
                "passed": True,
                "decoded_redacted_state": file_record(state),
            }
        ),
        encoding="utf-8",
    )
    return state, manifest


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-hil-action-test-") as raw:
        root = Path(raw)
        generated = root / "jlink_bench_authorize_us.jlink"
        generated.write_text(
            "connect\nh\ng\nsleep 5000\nh\n"
            "w4 0x20001358 0\nw1 0x2000135C 1\nw1 0x20001360 1\n"
            "g\nsleep 75000\nh\ng\nexit\n",
            encoding="utf-8",
        )
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
                    "provenance": {
                        "source": record(source),
                        "generated/jlink_bench_authorize_us.jlink": (
                            file_record(generated)
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
        cold = write_state(root, "cold-fail-closed", now)
        joined = write_state(root, "joined-us", now)
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
            "#!/bin/sh\nprintf '%s\\n' 'Connected' 'Target halted' 'Target started'\n",
            encoding="utf-8",
        )
        fake_jlink.chmod(0o755)
        output_dir = root / "evidence"
        command = [
            sys.executable,
            str(SCRIPT),
            "--action",
            "authorize-us",
            "--label",
            "bench",
            "--before-state",
            str(cold[0]),
            "--before-manifest",
            str(cold[1]),
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

        # Point the tool's required frozen generated-script path at the fixture
        # by replacing only the candidate record path after copying the fixture
        # into a synthetic diagnostics/generated tree is impossible here.
        real_generated = HERE / "generated/jlink_bench_authorize_us.jlink"
        candidate_value = json.loads(candidate.read_text(encoding="utf-8"))
        candidate_value["provenance"][
            "generated/jlink_bench_authorize_us.jlink"
        ] = record(real_generated)
        candidate.write_text(json.dumps(candidate_value), encoding="utf-8")

        ready = subprocess.run(
            command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert '"ready": true' in ready.stdout

        wrong_profile_command = command.copy()
        before_index = wrong_profile_command.index("--before-state")
        wrong_profile_command[before_index + 1] = str(joined[0])
        manifest_index = wrong_profile_command.index("--before-manifest")
        wrong_profile_command[manifest_index + 1] = str(joined[1])
        wrong_profile = subprocess.run(
            wrong_profile_command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert wrong_profile.returncode != 0
        assert "cold-fail-closed" in wrong_profile.stderr

        action = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert action.returncode == 0, action.stdout + action.stderr
        manifest_path = (
            output_dir
            / "stratolink2_flight_action_authorize_us_bench_20260725_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["passed"] is True
        assert manifest["action"] == "authorize-us"
        assert manifest["reset_issued"] is False
        assert manifest["target"]["transport"] == {
            "connected_under_reset": False,
            "initialized_bss_recovery_ms": 5000,
            "post_action_persistence_ms": 75000,
        }
        assert (
            manifest["action_evidence"]["script"]["sha256"]
            == manifest["gate_inputs"]["generated_script"]["sha256"]
        )

        collision = subprocess.run(
            command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite HIL action evidence" in collision.stderr

        real_script_record = candidate_value["provenance"][
            "generated/jlink_bench_authorize_us.jlink"
        ]
        real_script_record["sha256"] = "0" * 64
        candidate.write_text(json.dumps(candidate_value), encoding="utf-8")
        mutated_command = command.copy()
        mutated_command[mutated_command.index("--label") + 1] = "mutation"
        mutation = subprocess.run(
            mutated_command + ["--check-only"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        assert mutation.returncode != 0
        assert "provenance" in mutation.stderr or "manifest" in mutation.stderr

    print("PASS: allow-listed HIL action is exact, state-gated, and create-once")


if __name__ == "__main__":
    main()
