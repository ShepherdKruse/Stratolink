#!/usr/bin/env python3
"""Issue one create-once, power-gated reset of the exact flight candidate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from flash_flight_candidate import (
    load_handoff,
    require_gate,
    verify_file_record,
)
from preserve_precursor import (
    atomic_manifest,
    file_record,
    run_jlink,
    write_exclusive,
)
from verify_flight_candidate import (
    EXPECTED_BIN_SHA256,
    EXPECTED_ELF_SHA256,
)


HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
JLINK_SERIAL = "802007563"
LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def paths(label: str, output_dir: Path = LOGS) -> dict[str, Path]:
    stem = output_dir / f"stratolink2_flight_reset_{label}_20260725"
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
            "refusing to overwrite reset evidence: " + ", ".join(collisions)
        )


def load_flash_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"passing exact-candidate flash manifest is absent: {path}") from error
    candidate = value.get("candidate", {})
    if (
        value.get("reserved_devnonce_pages_preserved") is not True
        or candidate.get("elf_sha256") != EXPECTED_ELF_SHA256
        or candidate.get("bin_sha256") != EXPECTED_BIN_SHA256
        or value.get("target", {}).get("jlink_serial") != JLINK_SERIAL
    ):
        raise SystemExit("passing exact-candidate flash manifest is absent")
    records = value.get("flash_evidence")
    if not isinstance(records, dict) or not records:
        raise SystemExit("flash evidence records are missing")
    for record in records.values():
        if not isinstance(record, dict):
            raise SystemExit("flash evidence record is malformed")
        verify_file_record(record)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
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
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if not LABEL.fullmatch(args.label):
        parser.error("--label must be 1-40 lowercase letters/digits/_/-")
    if args.jlink_serial != JLINK_SERIAL:
        raise SystemExit("refusing an unrecognized J-Link serial")

    candidate = require_gate(args.candidate_verification, ("passed",))
    if (
        candidate.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or candidate.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit("candidate report does not identify the frozen release")
    load_flash_manifest(args.flash_manifest)
    ppk2_before = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )
    artifacts = paths(args.label, args.output_dir.resolve())
    require_create_once(artifacts)

    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "label": args.label,
                    "jlink_serial": args.jlink_serial,
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
    script = "\n".join(("connect", "r", "g", "exit", ""))
    write_exclusive(artifacts["script"], script)
    run_jlink(
        executable,
        args.jlink_serial,
        artifacts["script"],
        artifacts["raw"],
    )
    ppk2_after = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "label": args.label,
        "passed": True,
        "reset_issued": True,
        "scope": (
            "one J-Link reset/run request; the immediately following atomic "
            "state capture must prove exactly one retained boot-count advance"
        ),
        "target": {
            "device": "STM32WLE5CC",
            "interface": "SWD",
            "speed_khz": 4000,
            "jlink_serial": args.jlink_serial,
            "ppk2_before": ppk2_before,
            "ppk2_after": ppk2_after,
        },
        "candidate": {
            "elf_sha256": EXPECTED_ELF_SHA256,
            "bin_sha256": EXPECTED_BIN_SHA256,
        },
        "gate_inputs": {
            "candidate_verification": file_record(args.candidate_verification),
            "flash_manifest": file_record(args.flash_manifest),
        },
        "reset_evidence": {
            "script": file_record(artifacts["script"]),
            "raw": file_record(artifacts["raw"]),
        },
    }
    atomic_manifest(artifacts["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
