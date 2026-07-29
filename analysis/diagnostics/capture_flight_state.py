#!/usr/bin/env python3
"""Capture and decode one create-once atomic flight RAM+TAMP snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from decode_flight_state import (
    atomic_json,
    decode_health,
    decode_tamp,
    parse_memory,
    profile_gate,
)
from flash_flight_candidate import load_handoff, require_gate, verify_file_record
from preserve_precursor import atomic_manifest, run_jlink, sha256
from verify_flight_candidate import EXPECTED_BIN_SHA256


HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
JLINK_SERIAL = "802007563"
LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
CONNECT_UNDER_RESET_MARKER = "can not attach to cpu. trying connect under reset."


def classify_transport(transcript: str, wake_after_stop: bool) -> dict:
    """Classify whether the memory snapshot was taken from a running image.

    J-Link cannot non-invasively attach to this STM32WLE5 while it is in
    STOP1. Commander then falls back to connect-under-reset and halts at the
    reset vector, before RTCAPB is enabled. RAM and RTC/TAMP reads from that
    state are not an atomic snapshot of the running firmware and must never be
    decoded as cold or corrupt application state.
    """
    lowered = transcript.lower()
    connected_under_reset = CONNECT_UNDER_RESET_MARKER in lowered
    failures: list[str] = []
    if connected_under_reset and not wake_after_stop:
        failures.append(
            "J-Link connected under reset from STOP1; RAM/TAMP snapshot is invalid"
        )
    if wake_after_stop:
        if "sleep(5000)" not in lowered or transcript.count("J-Link>h") < 2:
            failures.append(
                "guarded STOP1 wake did not run for 5000 ms and re-halt"
            )
    return {
        "connected_under_reset": connected_under_reset,
        "wake_after_stop": wake_after_stop,
        "target_reset_by_attach": connected_under_reset,
        "passed": not failures,
        "failures": failures,
    }


def paths(label: str, output_dir: Path = LOGS) -> dict[str, Path]:
    stem = output_dir / f"stratolink2_flight_state_{label}_20260728"
    return {
        "raw": stem.with_name(stem.name + "_raw.txt"),
        "decoded": stem.with_suffix(".json"),
        "manifest": stem.with_name(stem.name + "_manifest.json"),
    }


def require_create_once(artifacts: dict[str, Path]) -> None:
    collisions = [
        str(path)
        for path in artifacts.values()
        if path.exists() or path.with_suffix(path.suffix + ".partial").exists()
    ]
    if collisions:
        raise SystemExit("refusing to overwrite state evidence: " + ", ".join(collisions))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", type=Path, default=LOGS)
    parser.add_argument(
        "--profile",
        choices=(
            "inspect",
            "cold-fail-closed",
            "session-corrupt",
            "authorized-us",
            "joined-us",
        ),
        required=True,
    )
    parser.add_argument(
        "--candidate-verification",
        type=Path,
        default=LOGS / "stratolink2_flight_candidate_verification_20260728_v15.json",
    )
    parser.add_argument(
        "--flash-manifest",
        type=Path,
        default=LOGS / "stratolink2_flight_flash_20260728_v15_manifest.json",
    )
    parser.add_argument(
        "--handoff-power",
        type=Path,
        default=LOGS / "stratolink2_bench_hold_20260728.jsonl",
    )
    parser.add_argument("--max-heartbeat-age-seconds", type=float, default=60)
    parser.add_argument(
        "--wake-after-stop",
        action="store_true",
        help=(
            "use the exact generated run-5000ms/re-halt script; this permits "
            "Commander connect-under-reset and records that reset explicitly"
        ),
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not LABEL.fullmatch(args.label):
        parser.error("--label must be 1-40 lowercase letters/digits/_/-")

    candidate = require_gate(args.candidate_verification, ("passed",))
    if candidate.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256:
        raise SystemExit("candidate report does not identify the frozen BIN")
    flash = json.loads(args.flash_manifest.read_text(encoding="utf-8"))
    if (
        flash.get("reserved_devnonce_pages_preserved") is not True
        or flash.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
        or flash.get("target", {}).get("jlink_serial") != JLINK_SERIAL
    ):
        raise SystemExit("passing exact-candidate flash manifest is absent")
    flash_evidence = flash.get("flash_evidence")
    if not isinstance(flash_evidence, dict) or not flash_evidence:
        raise SystemExit("flash evidence records are missing")
    for value in flash_evidence.values():
        if not isinstance(value, dict):
            raise SystemExit("flash evidence record is malformed")
        verify_file_record(value)
    state_script = HERE / "generated" / (
        "jlink_wake_read_flight_state.jlink"
        if args.wake_after_stop else "jlink_read_flight_state.jlink"
    )
    manifest_path = HERE / "generated/stratolink_flight_hil_manifest.json"
    for path in (state_script, manifest_path):
        provenance_key = f"generated/{path.name}"
        record = candidate.get("provenance", {}).get(provenance_key)
        if not isinstance(record, dict):
            raise SystemExit(
                f"candidate report does not bind {provenance_key}"
            )
        recorded_path = verify_file_record(record)
        if recorded_path.resolve() != path.resolve():
            raise SystemExit(
                f"candidate report binds an unexpected {provenance_key} path"
            )
    ppk2 = load_handoff(args.handoff_power, args.max_heartbeat_age_seconds)
    artifacts = paths(args.label, args.output_dir.resolve())
    require_create_once(artifacts)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "profile": args.profile,
                    "ppk2": ppk2,
                    "artifacts": {
                        name: str(path) for name, path in artifacts.items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    executable = shutil.which("JLinkExe")
    if executable is None:
        raise SystemExit("JLinkExe not found")
    transcript = run_jlink(
        executable,
        JLINK_SERIAL,
        state_script,
        artifacts["raw"],
    )
    transport = classify_transport(transcript, args.wake_after_stop)
    hil_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if transport["passed"]:
        memory = parse_memory(artifacts["raw"])
        health = decode_health(hil_manifest, memory)
        tamp = decode_tamp(hil_manifest, memory)
        gate = profile_gate(args.profile, health, tamp)
        if not tamp["boot"]["valid"]:
            gate["failures"].append(
                "running-image capture has no valid retained boot record"
            )
            gate["passed"] = False
    else:
        health = None
        tamp = None
        gate = {
            "profile": args.profile,
            "passed": False,
            "failures": list(transport["failures"]),
        }
    decoded = {
        "scope": (
            "single-halt RAM+TAMP snapshot; retained session keys are redacted "
            "from this decoded artifact"
        ),
        "manifest_elf_sha256": hil_manifest["elf_sha256"],
        "transport": transport,
        "health": health,
        "tamp": tamp,
        "profile_gate": gate,
    }
    atomic_json(artifacts["decoded"], decoded)
    post_ppk2 = load_handoff(args.handoff_power, args.max_heartbeat_age_seconds)
    evidence = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "profile": args.profile,
        "passed": gate["passed"],
        "transport": transport,
        "ppk2_before": ppk2,
        "ppk2_after": post_ppk2,
        "candidate_verification_sha256": sha256(args.candidate_verification),
        "flash_manifest_sha256": sha256(args.flash_manifest),
        "hil_manifest_sha256": sha256(manifest_path),
        "raw_private_state": {
            "path": str(artifacts["raw"]),
            "bytes": artifacts["raw"].stat().st_size,
            "sha256": sha256(artifacts["raw"]),
            "note": "contains retained session keys; do not publish",
        },
        "decoded_redacted_state": {
            "path": str(artifacts["decoded"]),
            "bytes": artifacts["decoded"].stat().st_size,
            "sha256": sha256(artifacts["decoded"]),
        },
        "failures": gate["failures"],
    }
    atomic_manifest(artifacts["manifest"], evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not gate["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
