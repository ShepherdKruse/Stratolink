#!/usr/bin/env python3
"""Capture one create-once, byte-exact STM32 DevNonce journal image."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from decode_devnonce_journal import JOURNAL_BYTES, atomic_json, decode
from flash_flight_candidate import load_handoff, require_gate, verify_file_record
from preserve_precursor import (
    atomic_manifest,
    commit_partial_create_once,
    run_jlink,
    sha256,
    write_exclusive,
)
from verify_flight_candidate import EXPECTED_BIN_SHA256


HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
JLINK_SERIAL = "802007563"
LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def paths(label: str, output_dir: Path = LOGS) -> dict[str, Path]:
    stem = output_dir / f"stratolink2_devnonce_{label}_20260725"
    return {
        "script": stem.with_name(stem.name + "_read.jlink"),
        "raw": stem.with_name(stem.name + "_raw.txt"),
        "journal": stem.with_suffix(".bin"),
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
        raise SystemExit(
            "refusing to overwrite DevNonce evidence: " + ", ".join(collisions)
        )


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
    parser.add_argument("--max-heartbeat-age-seconds", type=float, default=60)
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

    ppk2 = load_handoff(args.handoff_power, args.max_heartbeat_age_seconds)
    artifacts = paths(args.label, args.output_dir.resolve())
    require_create_once(artifacts)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
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
    journal_partial = artifacts["journal"].with_suffix(
        artifacts["journal"].suffix + ".partial"
    )
    script = "\n".join(
        [
            "connect",
            "h",
            f"savebin {journal_partial} 0x0803F000 0x00001000",
            "g",
            "exit",
            "",
        ]
    )
    write_exclusive(artifacts["script"], script)
    run_jlink(executable, JLINK_SERIAL, artifacts["script"], artifacts["raw"])
    if (
        not journal_partial.is_file()
        or journal_partial.stat().st_size != JOURNAL_BYTES
    ):
        raise SystemExit("DevNonce journal read is missing or wrong-sized")
    commit_partial_create_once(
        journal_partial,
        artifacts["journal"],
        "DevNonce journal evidence",
    )

    decoded = decode(artifacts["journal"])
    decoded["passed"] = (
        decoded["invalid_record_count"] == 0
        and decoded["monotonic_unique_sequence"]
    )
    atomic_json(artifacts["decoded"], decoded)
    post_ppk2 = load_handoff(args.handoff_power, args.max_heartbeat_age_seconds)
    evidence = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "passed": decoded["passed"],
        "target": {
            "device": "STM32WLE5CC",
            "jlink_serial": JLINK_SERIAL,
        },
        "ppk2_before": ppk2,
        "ppk2_after": post_ppk2,
        "candidate_verification_sha256": sha256(args.candidate_verification),
        "flash_manifest_sha256": sha256(args.flash_manifest),
        "artifacts": {
            name: {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in artifacts.items()
            if name != "manifest"
        },
        "journal": {
            "valid_record_count": decoded["valid_record_count"],
            "invalid_record_count": decoded["invalid_record_count"],
            "highest_nonce": decoded["highest_nonce"],
            "next_nonce": decoded["next_nonce"],
            "exhausted": decoded["exhausted"],
        },
    }
    atomic_manifest(artifacts["manifest"], evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not decoded["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
