#!/usr/bin/env python3
"""Synthetic HIL-action transition and evidence-integrity tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from evidence_provenance import verify_all as verify_provenance
from preserve_precursor import sha256
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "compare_hil_action_states.py"


def file_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def state(profile: str) -> dict:
    return {
        "manifest_elf_sha256": EXPECTED_ELF_SHA256,
        "profile_gate": {"profile": profile, "passed": True},
        "health": {
            "boot": {"count": 4},
            "session": {"region_id": 0},
            "region_lease": {"known": False, "age_seconds": 0},
        },
        "tamp": {
            "boot": {"count": 4},
            "region_lease": {"valid": False, "age_seconds": 0},
        },
    }


def write_capture(
    root: Path,
    name: str,
    value: dict,
    created: datetime,
) -> tuple[Path, Path]:
    decoded = root / f"{name}.json"
    decoded.write_text(json.dumps(value), encoding="utf-8")
    manifest = root / f"{name}_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "created_utc": created.isoformat(),
                "passed": True,
                "decoded_redacted_state": file_record(decoded),
            }
        ),
        encoding="utf-8",
    )
    return decoded, manifest


def write_action(
    root: Path,
    scenario: str,
    before: tuple[Path, Path],
    created: datetime,
) -> Path:
    gate = root / f"{scenario}_gate"
    gate.write_text("gate\n", encoding="utf-8")
    script = root / f"{scenario}.jlink"
    script.write_text("connect\nh\ng\nexit\n", encoding="utf-8")
    raw = root / f"{scenario}_raw"
    raw.write_text("Target halted\nTarget started\n", encoding="utf-8")
    action = root / f"{scenario}_manifest.json"
    action.write_text(
        json.dumps(
            {
                "created_utc": created.isoformat(),
                "action": scenario,
                "label": "test",
                "passed": True,
                "action_issued": True,
                "reset_issued": scenario == "clear-region-lease",
                "target": {
                    "jlink_serial": "802007563",
                    "ppk2_before": {"source_mv": 4660, "max_reconnects": 0},
                    "ppk2_after": {"source_mv": 4660, "max_reconnects": 0},
                },
                "candidate": {
                    "elf_sha256": EXPECTED_ELF_SHA256,
                    "bin_sha256": EXPECTED_BIN_SHA256,
                },
                "before_evidence": {
                    "state": file_record(before[0]),
                    "manifest": file_record(before[1]),
                },
                "gate_inputs": {"gate": file_record(gate)},
                "action_evidence": {
                    "script": file_record(script),
                    "raw": file_record(raw),
                },
            }
        ),
        encoding="utf-8",
    )
    return action


def invoke(
    scenario: str,
    before: tuple[Path, Path],
    action: Path,
    after: tuple[Path, Path],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before[0]),
            "--before-manifest",
            str(before[1]),
            "--action-manifest",
            str(action),
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-action-compare-test-") as raw:
        root = Path(raw)
        base = datetime.now(timezone.utc) - timedelta(minutes=3)
        cold_value = state("cold-fail-closed")
        cold = write_capture(root, "cold", cold_value, base)
        authorized_value = state("authorized-us")
        authorized_value["health"]["region_lease"] = {
            "known": True,
            "age_seconds": 2,
        }
        authorized_value["tamp"]["region_lease"] = {
            "valid": True,
            "age_seconds": 2,
        }
        authorized = write_capture(
            root,
            "authorized",
            authorized_value,
            base + timedelta(minutes=2),
        )
        authorize_action = write_action(
            root,
            "authorize-us",
            cold,
            base + timedelta(minutes=1),
        )
        authorize = invoke("authorize-us", cold, authorize_action, authorized)
        assert authorize.returncode == 0, authorize.stdout + authorize.stderr
        verify_provenance(json.loads(authorize.stdout)["provenance"])

        bad_authorized_value = deepcopy(authorized_value)
        bad_authorized_value["health"]["boot"]["count"] += 1
        bad_authorized = write_capture(
            root,
            "bad_authorized",
            bad_authorized_value,
            base + timedelta(minutes=2),
        )
        bad_authorize = invoke(
            "authorize-us",
            cold,
            authorize_action,
            bad_authorized,
        )
        assert bad_authorize.returncode != 0
        assert "unexpectedly reset" in bad_authorize.stdout

        joined_value = state("joined-us")
        joined_value["health"]["region_lease"]["known"] = True
        joined_value["tamp"]["region_lease"]["valid"] = True
        joined = write_capture(root, "joined", joined_value, base)
        cleanup_after_value = state("cold-fail-closed")
        cleanup_after_value["health"]["boot"]["count"] = 5
        cleanup_after_value["tamp"]["boot"]["count"] = 5
        cleanup_after = write_capture(
            root,
            "cleanup_after",
            cleanup_after_value,
            base + timedelta(minutes=2),
        )
        cleanup_action = write_action(
            root,
            "clear-region-lease",
            joined,
            base + timedelta(minutes=1),
        )
        cleanup = invoke(
            "clear-region-lease",
            joined,
            cleanup_action,
            cleanup_after,
        )
        assert cleanup.returncode == 0, cleanup.stdout + cleanup.stderr

        cleanup_raw = root / "clear-region-lease_raw"
        cleanup_raw.write_text("mutated\n", encoding="utf-8")
        mutation = invoke(
            "clear-region-lease",
            joined,
            cleanup_action,
            cleanup_after,
        )
        assert mutation.returncode != 0
        assert "no longer matches its manifest" in mutation.stderr

    print("PASS: authorize/cleanup actions are bracketed and machine-proven")


if __name__ == "__main__":
    main()
