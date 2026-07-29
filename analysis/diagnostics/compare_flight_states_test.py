#!/usr/bin/env python3
"""Synthetic reset-transition tests for flight-state comparison."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from compare_flight_states import load_capture
from evidence_provenance import verify_all as verify_provenance
from preserve_precursor import sha256
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "compare_flight_states.py"


def file_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def state() -> dict:
    session = {
        "joined": True,
        "region": "US915",
        "next_fcnt_up": 10,
        "next_fcnt_down": 3,
    }
    return {
        "manifest_elf_sha256": EXPECTED_ELF_SHA256,
        "profile_gate": {"profile": "joined-us", "passed": True},
        "health": {
            "boot": {"count": 4},
            "session": deepcopy(session),
            "region_lease": {"known": True, "age_seconds": 100},
            "command": {
                "rx_count": 1,
                "command_count": 1,
                "last_fport": 10,
                "last_sequence": 42,
                "sequence_persist_failures": 0,
                "ack_valid": True,
                "ack_sequence": 42,
                "relay_enabled": True,
            },
            "downlink": {
                "frame_count": 1,
                "irq_count": 1,
                "last_window": 1,
                "last_reject": 0,
            },
            "b2b_queues": {"origin_id_ready": True},
        },
        "tamp": {
            "boot": {"valid": True, "count": 4},
            "session": {
                "valid": True,
                "region": "US915",
                "dev_addr": "26000001",
                "network_key_present": True,
                "application_key_present": True,
                "next_fcnt_up": 10,
                "next_fcnt_down": 3,
            },
            "region_lease": {"valid": True, "age_seconds": 100},
            "b2b_origin_id": {"valid": True, "next_id": 7},
            "command_sequence": {
                "valid": True,
                "last_applied": 42,
                "relay_enabled": True,
            },
        },
    }


def write_capture(
    root: Path,
    name: str,
    value: dict,
    created_utc: datetime,
) -> tuple[Path, Path]:
    decoded = root / f"{name}.json"
    decoded.write_text(json.dumps(value), encoding="utf-8")
    manifest = root / f"{name}_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "created_utc": created_utc.isoformat(),
                "passed": True,
                "decoded_redacted_state": {
                    "path": str(decoded),
                    "bytes": decoded.stat().st_size,
                    "sha256": sha256(decoded),
                },
            }
        ),
        encoding="utf-8",
    )
    return decoded, manifest


def write_reset(
    root: Path,
    created_utc: datetime,
) -> Path:
    gate = root / "reset_gate.json"
    gate.write_text("gate\n", encoding="utf-8")
    script = root / "reset.jlink"
    script.write_text("connect\nr\ng\nexit\n", encoding="utf-8")
    raw = root / "reset_raw.txt"
    raw.write_text("Resetting target\nTarget started\n", encoding="utf-8")
    reset = root / "reset_manifest.json"
    reset.write_text(
        json.dumps(
            {
                "created_utc": created_utc.isoformat(),
                "label": "test",
                "passed": True,
                "reset_issued": True,
                "target": {
                    "jlink_serial": "802007563",
                    "ppk2_before": {"source_mv": 4660, "max_reconnects": 0},
                    "ppk2_after": {"source_mv": 4660, "max_reconnects": 0},
                },
                "candidate": {
                    "elf_sha256": EXPECTED_ELF_SHA256,
                    "bin_sha256": EXPECTED_BIN_SHA256,
                },
                "gate_inputs": {"candidate": file_record(gate)},
                "reset_evidence": {
                    "script": file_record(script),
                    "raw": file_record(raw),
                },
            }
        ),
        encoding="utf-8",
    )
    return reset


def invoke(
    before: tuple[Path, Path],
    reset: Path,
    after: tuple[Path, Path],
    scenario: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before[0]),
            "--before-manifest",
            str(before[1]),
            "--reset-manifest",
            str(reset),
            "--after",
            str(after[0]),
            "--after-manifest",
            str(after[1]),
            "--scenario",
            scenario,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def reset_after(before: dict, fcnt_up_advance: int) -> dict:
    after = deepcopy(before)
    after["health"]["boot"]["count"] += 1
    after["tamp"]["boot"]["count"] += 1
    after["health"]["session"]["next_fcnt_up"] += fcnt_up_advance
    after["tamp"]["session"]["next_fcnt_up"] += fcnt_up_advance
    after["health"]["command"]["rx_count"] = 0
    after["health"]["command"]["command_count"] = 0
    after["health"]["downlink"]["frame_count"] = 0
    return after


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-state-compare-test-") as raw:
        root = Path(raw)
        base = datetime.now(timezone.utc) - timedelta(minutes=5)
        before_value = state()
        before = write_capture(root, "before", before_value, base)
        reset = write_reset(root, base + timedelta(minutes=1))

        cold_value = deepcopy(before_value)
        cold_value["profile_gate"]["profile"] = "cold-fail-closed"
        cold = write_capture(root, "cold", cold_value, base)
        assert (
            load_capture(
                cold[0],
                cold[1],
                expected_profile="cold-fail-closed",
            )
            == cold_value
        )
        try:
            load_capture(cold[0], cold[1])
        except SystemExit as error:
            assert "joined-us" in str(error)
        else:
            raise AssertionError("joined-US loader accepted cold-fail-closed evidence")

        session_after = write_capture(
            root,
            "session_after",
            reset_after(before_value, 1),
            base + timedelta(minutes=2),
        )
        session = invoke(before, reset, session_after, "session-reset")
        assert session.returncode == 0, session.stdout + session.stderr
        verify_provenance(json.loads(session.stdout)["provenance"])

        replay_value = reset_after(before_value, 0)
        replay = write_capture(
            root,
            "replay",
            replay_value,
            base + timedelta(minutes=2),
        )
        replay_result = invoke(before, reset, replay, "session-reset")
        assert replay_result.returncode != 0
        assert "FCntUp did not advance" in replay_result.stdout

        downlink_after = write_capture(
            root,
            "downlink_after",
            reset_after(before_value, 0),
            base + timedelta(minutes=2),
        )
        downlink = invoke(before, reset, downlink_after, "downlink-reset")
        assert downlink.returncode == 0, downlink.stdout + downlink.stderr

        lost_sequence_value = reset_after(before_value, 0)
        lost_sequence_value["tamp"]["command_sequence"]["last_applied"] = 43
        lost_sequence = write_capture(
            root,
            "lost_sequence",
            lost_sequence_value,
            base + timedelta(minutes=2),
        )
        lost_sequence_result = invoke(
            before,
            reset,
            lost_sequence,
            "downlink-reset",
        )
        assert lost_sequence_result.returncode != 0
        assert "retained command state changed" in lost_sequence_result.stdout

        lost_relay_value = reset_after(before_value, 0)
        lost_relay_value["tamp"]["command_sequence"]["relay_enabled"] = False
        lost_relay = write_capture(
            root,
            "lost_relay",
            lost_relay_value,
            base + timedelta(minutes=2),
        )
        lost_relay_result = invoke(before, reset, lost_relay, "downlink-reset")
        assert lost_relay_result.returncode != 0
        assert "retained command state changed" in lost_relay_result.stdout

        b2b_after = write_capture(
            root,
            "b2b_after",
            reset_after(before_value, 0),
            base + timedelta(minutes=2),
        )
        b2b = invoke(before, reset, b2b_after, "b2b-reset")
        assert b2b.returncode == 0, b2b.stdout + b2b.stderr

        session_after[0].write_text("mutated\n", encoding="utf-8")
        mutation = invoke(before, reset, session_after, "session-reset")
        assert mutation.returncode != 0
        assert "no longer matches its manifest" in mutation.stderr

        session_after = write_capture(
            root,
            "session_after_replacement",
            reset_after(before_value, 1),
            base + timedelta(minutes=2),
        )
        reset_raw = root / "reset_raw.txt"
        reset_raw.write_text("mutated\n", encoding="utf-8")
        reset_mutation = invoke(before, reset, session_after, "session-reset")
        assert reset_mutation.returncode != 0
        assert "no longer matches its manifest" in reset_mutation.stderr

    print("PASS: session/downlink/B2B reset transitions and evidence integrity")


if __name__ == "__main__":
    main()
