#!/usr/bin/env python3
"""Corrupt one retained-session data bit and prove fail-closed restore."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from compare_flight_states import load_capture, parse_created_utc
from decode_flight_state import (
    atomic_json,
    decode_health,
    decode_tamp,
    parse_memory,
    profile_gate,
)
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
SESSION_DEVADDR_WORD = 3
SETTLE_MS = 10000


def paths(label: str, output_dir: Path = LOGS) -> dict[str, Path]:
    stem = output_dir / f"stratolink2_tamp_session_corruption_{label}_20260725"
    return {
        "script": stem.with_name(stem.name + ".jlink"),
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
        raise SystemExit(
            "refusing to overwrite TAMP-corruption evidence: "
            + ", ".join(collisions)
        )


def build_script(
    state_read_script: Path,
    devaddr_address: int,
    corrupted_devaddr: int,
) -> str:
    lines = [
        line.strip()
        for line in state_read_script.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if lines[:2] != ["connect", "h"] or lines[-2:] != ["g", "exit"]:
        raise SystemExit("frozen state-read script has an unexpected envelope")
    reads = lines[2:-2]
    if not reads or any(
        not command.startswith(("mem8 ", "mem16 ", "mem32 "))
        for command in reads
    ):
        raise SystemExit("frozen state-read script contains a non-read command")
    if devaddr_address % 4 or not 0 <= corrupted_devaddr <= 0xFFFFFFFF:
        raise SystemExit("invalid controlled TAMP corruption")
    commands = [
        "connect",
        "h",
        f"w4 0x{devaddr_address:08X} 0x{corrupted_devaddr:08X}",
        "r",
        "g",
        f"sleep {SETTLE_MS}",
        "h",
        *reads,
        "g",
        "exit",
        "",
    ]
    return "\n".join(commands)


def main() -> None:
    parser = argparse.ArgumentParser()
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

    candidate = require_gate(args.candidate_verification, ("passed",))
    if (
        candidate.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or candidate.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit("candidate report does not identify the frozen release")
    load_flash_manifest(args.flash_manifest)

    manifest_path = HERE / "generated/stratolink_flight_hil_manifest.json"
    state_read_script = HERE / "generated/jlink_read_flight_state.jlink"
    for key, expected_path in (
        ("generated/stratolink_flight_hil_manifest.json", manifest_path),
        ("generated/jlink_read_flight_state.jlink", state_read_script),
    ):
        record = candidate.get("provenance", {}).get(key)
        if not isinstance(record, dict):
            raise SystemExit(f"candidate report does not bind {key}")
        if verify_file_record(record).resolve() != expected_path.resolve():
            raise SystemExit(f"candidate report binds an unexpected {key}")

    before = load_capture(
        args.before_state,
        args.before_manifest,
        expected_profile="joined-us",
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

    original_devaddr = int(before["tamp"]["session"]["dev_addr"], 16)
    corrupted_devaddr = original_devaddr ^ 1
    hil_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    devaddr_address = (
        int(hil_manifest["tamp_bkp0_address"]) + 4 * SESSION_DEVADDR_WORD
    )
    generated_script = build_script(
        state_read_script,
        devaddr_address,
        corrupted_devaddr,
    )
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
                    "mutation": {
                        "address": f"0x{devaddr_address:08X}",
                        "word": SESSION_DEVADDR_WORD,
                        "bit": 0,
                        "original_devaddr": f"{original_devaddr:08X}",
                        "corrupted_devaddr": f"{corrupted_devaddr:08X}",
                    },
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
    write_exclusive(artifacts["script"], generated_script)
    run_jlink(
        executable,
        args.jlink_serial,
        artifacts["script"],
        artifacts["raw"],
    )
    memory = parse_memory(artifacts["raw"])
    health = decode_health(hil_manifest, memory)
    tamp = decode_tamp(hil_manifest, memory)
    gate = profile_gate("session-corrupt", health, tamp)
    failures = list(gate["failures"])
    if tamp["session"]["dev_addr"] != f"{corrupted_devaddr:08X}":
        failures.append("observed retained DevAddr is not the one-bit mutation")
    if health["boot"]["count"] != before["health"]["boot"]["count"] + 1:
        failures.append("RAM boot count did not advance exactly once")
    if tamp["boot"]["count"] != before["tamp"]["boot"]["count"] + 1:
        failures.append("retained boot count did not advance exactly once")
    final_gate = {
        "profile": "session-corrupt",
        "passed": not failures,
        "failures": failures,
    }
    decoded = {
        "scope": (
            "one-bit retained DevAddr corruption, one controlled reset, and "
            "single-halt RAM+TAMP rejection snapshot; session keys redacted"
        ),
        "manifest_elf_sha256": hil_manifest["elf_sha256"],
        "mutation": {
            "address": f"0x{devaddr_address:08X}",
            "word": SESSION_DEVADDR_WORD,
            "bit": 0,
            "original_devaddr": f"{original_devaddr:08X}",
            "corrupted_devaddr": f"{corrupted_devaddr:08X}",
        },
        "health": health,
        "tamp": tamp,
        "profile_gate": final_gate,
    }
    atomic_json(artifacts["decoded"], decoded)
    ppk2_after = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "label": args.label,
        "passed": final_gate["passed"],
        "mutation_issued": True,
        "reset_issued": True,
        "target": {
            "device": "STM32WLE5CC",
            "jlink_serial": args.jlink_serial,
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
            "profile": "joined-us",
            "age_seconds_at_mutation": round(state_age, 3),
        },
        "gate_inputs": {
            "candidate_verification": file_record(args.candidate_verification),
            "flash_manifest": file_record(args.flash_manifest),
            "hil_manifest": file_record(manifest_path),
            "state_read_script": file_record(state_read_script),
        },
        "mutation": decoded["mutation"],
        "mutation_evidence": {
            "script": file_record(artifacts["script"]),
            "raw_private_state": {
                **file_record(artifacts["raw"]),
                "note": "contains retained session keys; do not publish",
            },
            "decoded_redacted_state": file_record(artifacts["decoded"]),
        },
        "failures": failures,
    }
    atomic_manifest(artifacts["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if not final_gate["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
