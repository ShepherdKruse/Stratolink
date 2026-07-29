#!/usr/bin/env python3
"""Apply one allow-listed, create-once mutation to the exact flight image."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from compare_flight_states import load_capture, parse_created_utc
from flash_flight_candidate import load_handoff, require_gate, verify_file_record
from preserve_precursor import (
    atomic_manifest,
    file_record,
    run_jlink,
    sha256,
    write_exclusive,
)
from reset_flight_candidate import load_flash_manifest
from verify_flight_candidate import (
    EXPECTED_BIN_SHA256,
    EXPECTED_ELF_SHA256,
)


HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
JLINK_SERIAL = "802007563"
LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
ACTIONS = {
    "authorize-us": {
        "script": "jlink_bench_authorize_us.jlink",
        "before_profile": "cold-fail-closed",
        "reset_issued": False,
        "description": (
            "set only exact-candidate RAM region age=0, region-known=1, and "
            "trusted-provenance=1 "
            "after a proved US915 fail-closed state"
        ),
    },
    "clear-region-lease": {
        "script": "jlink_bench_clear_region_lease.jlink",
        "before_profile": "joined-us",
        "reset_issued": True,
        "description": (
            "invalidate only the retained region-lease magic, reset, and run"
        ),
    },
}


def require_safe_authorize_script(path: Path) -> None:
    """Reject the pre-fix sequence that wrote BSS at Reset_Handler."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if (
        lines[:5] != ["connect", "h", "g", "sleep 5000", "h"]
        or lines[-5:] != ["g", "sleep 75000", "h", "g", "exit"]
        or sum(line.startswith("w4 ") for line in lines) != 1
        or sum(line.startswith("w1 ") for line in lines) != 2
    ):
        raise SystemExit(
            "authorize-us script lacks initialized-BSS startup recovery or "
            "the full-cycle persistence interval"
        )


def paths(action: str, label: str, output_dir: Path = LOGS) -> dict[str, Path]:
    action_stem = action.replace("-", "_")
    stem = output_dir / f"stratolink2_flight_action_{action_stem}_{label}_20260725"
    return {
        "script": stem.with_name(stem.name + ".jlink"),
        "raw": stem.with_name(stem.name + "_raw.txt"),
        "manifest": stem.with_name(stem.name + "_manifest.json"),
    }


def require_create_once(artifacts: dict[str, Path]) -> None:
    collisions = [
        str(path)
        for path in artifacts.values()
        if path.exists() or path.with_suffix(path.suffix + ".partial").exists()
    ]
    if collisions:
        raise SystemExit(
            "refusing to overwrite HIL action evidence: " + ", ".join(collisions)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=tuple(ACTIONS), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--before-state", type=Path, required=True)
    parser.add_argument("--before-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=LOGS)
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
    parser.add_argument("--jlink-serial", default=JLINK_SERIAL)
    parser.add_argument("--max-heartbeat-age-seconds", type=float, default=60)
    parser.add_argument("--max-state-age-seconds", type=float, default=300)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if not LABEL.fullmatch(args.label):
        parser.error("--label must be 1-40 lowercase letters/digits/_/-")
    if args.jlink_serial != JLINK_SERIAL:
        raise SystemExit("refusing an unrecognized J-Link serial")
    if not 1 <= args.max_state_age_seconds <= 1800:
        parser.error("--max-state-age-seconds must be between 1 and 1800")

    specification = ACTIONS[args.action]
    candidate = require_gate(args.candidate_verification, ("passed",))
    if (
        candidate.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or candidate.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit("candidate report does not identify the frozen release")
    load_flash_manifest(args.flash_manifest)

    generated_script = HERE / "generated" / str(specification["script"])
    if args.action == "authorize-us":
        require_safe_authorize_script(generated_script)
    provenance_key = f"generated/{specification['script']}"
    script_record = candidate.get("provenance", {}).get(provenance_key)
    if not isinstance(script_record, dict):
        raise SystemExit("candidate report does not bind the requested HIL script")
    recorded_script = verify_file_record(script_record)
    if recorded_script.resolve() != generated_script.resolve():
        raise SystemExit("candidate report binds an unexpected HIL script path")

    load_capture(
        args.before_state,
        args.before_manifest,
        expected_profile=str(specification["before_profile"]),
    )
    before_manifest = json.loads(args.before_manifest.read_text(encoding="utf-8"))
    before_created = parse_created_utc(
        before_manifest.get("created_utc"),
        args.before_manifest,
    )
    state_age = (datetime.now(timezone.utc) - before_created).total_seconds()
    if not 0 <= state_age <= args.max_state_age_seconds:
        raise SystemExit(
            f"before-state capture is stale or future-dated ({state_age:.3f}s)"
        )

    ppk2_before = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )
    artifacts = paths(args.action, args.label, args.output_dir.resolve())
    require_create_once(artifacts)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "action": args.action,
                    "label": args.label,
                    "before_profile": specification["before_profile"],
                    "ppk2": ppk2_before,
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
    write_exclusive(
        artifacts["script"],
        generated_script.read_text(encoding="utf-8"),
    )
    if sha256(artifacts["script"]) != sha256(generated_script):
        raise SystemExit("copied HIL action script differs from frozen source")
    run_jlink(
        executable,
        args.jlink_serial,
        artifacts["script"],
        artifacts["raw"],
    )
    connected_under_reset = (
        "Can not attach to CPU. Trying connect under reset."
        in artifacts["raw"].read_text(encoding="utf-8", errors="replace")
    )
    ppk2_after = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "action": args.action,
        "label": args.label,
        "passed": True,
        "action_issued": True,
        "reset_issued": specification["reset_issued"],
        "scope": specification["description"],
        "required_after_evidence": (
            "capture a new atomic flight state immediately and prove the "
            "documented transition; this manifest proves the issued action, "
            "not its firmware-visible effect"
        ),
        "target": {
            "device": "STM32WLE5CC",
            "interface": "SWD",
            "speed_khz": 4000,
            "jlink_serial": args.jlink_serial,
            "transport": {
                "connected_under_reset": connected_under_reset,
                "initialized_bss_recovery_ms": (
                    5000 if args.action == "authorize-us" else 0
                ),
                "post_action_persistence_ms": (
                    75000 if args.action == "authorize-us" else 0
                ),
            },
            "ppk2_before": ppk2_before,
            "ppk2_after": ppk2_after,
        },
        "candidate": {
            "elf_sha256": EXPECTED_ELF_SHA256,
            "bin_sha256": EXPECTED_BIN_SHA256,
        },
        "before_evidence": {
            "state": file_record(args.before_state),
            "manifest": file_record(args.before_manifest),
            "profile": specification["before_profile"],
            "age_seconds_at_action": round(state_age, 3),
        },
        "gate_inputs": {
            "candidate_verification": file_record(args.candidate_verification),
            "flash_manifest": file_record(args.flash_manifest),
            "generated_script": file_record(generated_script),
        },
        "action_evidence": {
            "script": file_record(artifacts["script"]),
            "raw": file_record(artifacts["raw"]),
        },
    }
    atomic_manifest(artifacts["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
