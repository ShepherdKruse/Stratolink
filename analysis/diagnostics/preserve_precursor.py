#!/usr/bin/env python3
"""Preserve the one-shot precursor MCU state without overwrite risk.

This tool is intentionally gated by the completed soak and sensor-model JSON.
It selects the known J-Link EDU Mini, halts only after those non-invasive gates
pass, saves full flash/RAM/TAMP plus precursor health reads, resumes the MCU,
and writes a hash manifest. Every artifact is create-once.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from evidence_provenance import (
    record as provenance_record,
    verify_all as verify_provenance,
)
from verify_flight_candidate import (
    EXPECTED_BIN_SHA256,
    EXPECTED_ELF_SHA256,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_LOGS = HERE / "logs"
DEFAULT_PREFIX = DEFAULT_LOGS / "stratolink2_precursor_20260725"
DEFAULT_PRE_RETRY_FLASH = (
    ROOT
    / "firmware/.pio/precursor_evidence/"
    "stratolink2_pre_retry_flash_20260724.bin"
)
EXPECTED_PRE_RETRY_FLASH_SHA256 = (
    "fd6ed6053206ddfe63ab40c7333752b383ad5f71caa07af3c334e5da4d5891f9"
)
EXPECTED_FLASH_BYTES = 256 * 1024
EXPECTED_RAM_BYTES = 64 * 1024
EXPECTED_OPTR_BYTES = 4
FLASH_OPTR_ADDRESS = 0x58004020
FLASH_OPTR_IWDG_STOP = 1 << 17
EXPECTED_JLINK_SERIAL = "802007563"
FAILURE_MARKERS = (
    "cannot connect",
    "could not connect",
    "failed to connect",
    "connection not established",
    "script file read error",
    "unknown command",
    "verification failed",
    "verify failed",
    "failed to verify",
    "could not verify",
    "programming failed",
    "error while programming",
    "cannot open file",
    "could not open file",
    "failed to open file",
    "failed to save",
    "could not save",
)
BENIGN_CONNECT_PREAMBLE = (
    "j-link connection not established yet but required for command."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"required gate artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def validate_pre_retry_flash(path: Path, expected_sha256: str) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"refusing target access: pre-retry flash is missing: {path}"
        )
    if path.stat().st_size != EXPECTED_FLASH_BYTES:
        raise SystemExit(
            "refusing target access: pre-retry flash has wrong byte length"
        )
    actual = sha256(path)
    if actual != expected_sha256:
        raise SystemExit(
            "refusing target access: pre-retry flash SHA-256 changed"
        )
    return file_record(path)


def require_flash_unchanged(pre_retry: dict, post_soak_path: Path) -> None:
    if sha256(post_soak_path) != pre_retry.get("sha256"):
        raise SystemExit(
            "pre-retry/post-soak flash mismatch: preserve the create-once artifacts, "
            "do not reset or flash the target"
        )


def validate_option_register(path: Path) -> dict[str, object]:
    """Bind the hardware watchdog-in-STOP premise used by the flight image."""
    if not path.is_file() or path.stat().st_size != EXPECTED_OPTR_BYTES:
        raise SystemExit("FLASH OPTR capture is missing or wrong-sized")
    value = int.from_bytes(path.read_bytes(), byteorder="little")
    if (value & FLASH_OPTR_IWDG_STOP) == 0:
        raise SystemExit(
            "FLASH OPTR IWDG_STOP is clear: the watchdog freezes in STOP1; "
            "do not flash or claim RTC-hang recovery"
        )
    return {
        **file_record(path),
        "address": f"0x{FLASH_OPTR_ADDRESS:08X}",
        "value": f"0x{value:08X}",
        "iwdg_runs_in_stop": True,
    }


def require_completed_gates(
    summary_path: Path,
    sensor_path: Path,
    candidate_path: Path,
    engineering_acceptance_path: Path | None = None,
) -> None:
    summary = load_json(summary_path)
    sensor = load_json(sensor_path)
    candidate = load_json(candidate_path)
    standard_gates_pass = (
        summary.get("final_gate", {}).get("passed") is True
        and sensor.get("passed") is True
    )
    if not standard_gates_pass:
        require_engineering_acceptance(engineering_acceptance_path)
    if candidate.get("passed") is not True:
        raise SystemExit("refusing target access: flight-candidate gate is not passing")
    if (
        candidate.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or candidate.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit(
            "refusing target access: candidate report does not name frozen hashes"
        )
    try:
        verify_provenance(summary.get("provenance"))
        verify_provenance(sensor.get("provenance"))
        verify_provenance(candidate.get("provenance"))
    except ValueError as error:
        raise SystemExit(
            f"refusing target access: gate input provenance failed: {error}"
        ) from error


def require_engineering_acceptance(path: Path | None) -> dict:
    """Validate a separate, explicit human acceptance without rewriting failures."""
    if path is None or not path.is_file():
        raise SystemExit(
            "refusing target access: soak/sensor gates failed and no engineering "
            "acceptance was supplied"
        )
    value = load_json(path)
    if (
        value.get("schema") != "stratolink.engineering_acceptance.v1"
        or value.get("accepted") is not True
        or value.get("decision", {}).get("source") != "user"
        or value.get("decision", {}).get("scope")
        != "retry3_v15_hil"
        or value.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or value.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit("refusing target access: engineering acceptance is invalid")
    deviations = value.get("accepted_deviations")
    if not isinstance(deviations, list) or {
        item.get("id") for item in deviations if isinstance(item, dict)
    } != {"retry3_vstor_4558mv", "retry3_standby_host_permission"}:
        raise SystemExit(
            "refusing target access: engineering acceptance does not name both "
            "retry-3 deviations"
        )
    try:
        verify_provenance(value.get("provenance"))
    except ValueError as error:
        raise SystemExit(
            f"refusing target access: engineering acceptance provenance failed: {error}"
        ) from error
    return value


def load_handoff(path: Path, max_age_seconds: float) -> dict:
    if not path.is_file():
        raise SystemExit("refusing target access: standby PPK2 log is missing")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assertions = [
        row
        for row in rows
        if row.get("event") in ("ppk2_power_on", "ppk2_power_heartbeat")
    ]
    power_on = [row for row in assertions if row.get("event") == "ppk2_power_on"]
    heartbeats = [
        row for row in assertions if row.get("event") == "ppk2_power_heartbeat"
    ]
    times = [
        datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))
        for row in assertions
    ]
    if (
        len(power_on) != 1
        or not heartbeats
        or {int(row.get("source_mv", 0)) for row in assertions} != {4660}
        or max(int(row.get("reconnects", 0)) for row in assertions) != 0
        or not all(later > earlier for earlier, later in zip(times, times[1:]))
    ):
        raise SystemExit(
            "refusing target access: standby PPK2 is not continuously healthy"
        )
    last = datetime.fromisoformat(
        heartbeats[-1]["utc"].replace("Z", "+00:00")
    )
    age = (datetime.now(timezone.utc) - last).total_seconds()
    if not 0 <= age <= max_age_seconds:
        raise SystemExit(
            "refusing target access: standby PPK2 heartbeat is stale or "
            f"future-dated ({age:.3f}s)"
        )
    return {
        "path": str(path.resolve()),
        "last_heartbeat_utc": heartbeats[-1]["utc"],
        "heartbeat_age_seconds": round(age, 3),
        "source_mv": 4660,
        "max_reconnects": 0,
    }


def artifact_paths(prefix: Path) -> dict[str, Path]:
    return {
        "flash": prefix.with_name(prefix.name + "_flash.bin"),
        "ram": prefix.with_name(prefix.name + "_ram.bin"),
        "flash_optr": prefix.with_name(prefix.name + "_flash_optr.bin"),
        "preserve_script": prefix.with_name(prefix.name + "_preserve.jlink"),
        "preserve_raw": prefix.with_name(prefix.name + "_preserve_raw.txt"),
        "health_raw": prefix.with_name(prefix.name + "_health_raw.txt"),
        "manifest": prefix.with_name(prefix.name + "_manifest.json"),
    }


def require_create_once(paths: dict[str, Path]) -> None:
    collisions: list[str] = []
    for path in paths.values():
        if path.exists() or path.with_suffix(path.suffix + ".partial").exists():
            collisions.append(str(path))
    if collisions:
        raise SystemExit(
            "refusing to overwrite precursor evidence: " + ", ".join(collisions)
        )


def write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def commit_partial_create_once(partial: Path, path: Path, noun: str) -> None:
    """Publish a validated partial without ever replacing existing evidence."""
    try:
        os.link(partial, path)
    except FileExistsError as error:
        raise SystemExit(f"refusing to overwrite {noun}: {path}") from error
    partial.unlink()


def run_jlink(
    executable: str,
    serial: str,
    script: Path,
    raw_output: Path,
) -> str:
    result = subprocess.run(
        [
            executable,
            "-device",
            "STM32WLE5CC",
            "-if",
            "SWD",
            "-speed",
            "4000",
            "-SelectEmuBySN",
            serial,
            "-CommanderScript",
            str(script),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    write_exclusive(raw_output, result.stdout)
    lowered = result.stdout.lower()
    # Commander prints this sentence before its first explicit `connect`, even
    # when the following USB/SWD connection and the complete command script
    # succeed.  Ignore only that exact preamble and only when the transcript
    # also proves a connected Cortex-M4 and completed script.  Other
    # "connection not established" text remains fatal.
    marker_text = lowered
    if (
        BENIGN_CONNECT_PREAMBLE in marker_text
        and "cortex-m4 identified." in marker_text
        and "script processing completed." in marker_text
    ):
        marker_text = marker_text.replace(BENIGN_CONNECT_PREAMBLE, "")
    failures = [
        marker for marker in FAILURE_MARKERS if marker in marker_text
    ]
    if result.returncode != 0 or failures:
        raise SystemExit(
            f"J-Link command failed (exit={result.returncode}, markers={failures}); "
            f"raw output preserved at {raw_output}"
        )
    return result.stdout


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def atomic_manifest(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".partial",
        delete=False,
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise SystemExit(f"refusing to overwrite manifest: {path}") from error
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--sensor-model",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-verification",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--engineering-acceptance",
        type=Path,
        help=(
            "explicit user acceptance used only when the original soak or sensor "
            "gate remains non-passing"
        ),
    )
    parser.add_argument(
        "--handoff-power",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--primary-power",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--ttn",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--supabase",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--soak-plot",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--readiness-plot",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-elf",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-bin",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--pre-retry-flash",
        type=Path,
        default=DEFAULT_PRE_RETRY_FLASH,
        help="complete target flash captured before the clean retry",
    )
    parser.add_argument(
        "--expected-pre-retry-flash-sha256",
        default=EXPECTED_PRE_RETRY_FLASH_SHA256,
    )
    parser.add_argument("--jlink-serial", default=EXPECTED_JLINK_SERIAL)
    parser.add_argument("--max-heartbeat-age-seconds", type=float, default=60)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="verify gates and collision-free paths without touching the target",
    )
    args = parser.parse_args()

    if args.jlink_serial != EXPECTED_JLINK_SERIAL:
        raise SystemExit("refusing target access: unrecognized J-Link serial")
    pre_retry_flash = validate_pre_retry_flash(
        args.pre_retry_flash,
        args.expected_pre_retry_flash_sha256,
    )
    require_completed_gates(
        args.summary,
        args.sensor_model,
        args.candidate_verification,
        args.engineering_acceptance,
    )
    pre_handoff = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )
    evidence_inputs = [
        args.summary,
        args.sensor_model,
        args.candidate_verification,
        args.pre_retry_flash,
        args.primary_power,
        args.handoff_power,
        args.ttn,
        args.supabase,
        args.soak_plot,
        args.readiness_plot,
        args.candidate_elf,
        args.candidate_bin,
    ]
    if args.engineering_acceptance is not None:
        evidence_inputs.append(args.engineering_acceptance)
    missing = [str(path) for path in evidence_inputs if not path.is_file()]
    if missing:
        raise SystemExit(
            "refusing target access: evidence bundle inputs are missing: "
            + ", ".join(missing)
        )
    paths = artifact_paths(args.prefix.resolve())
    require_create_once(paths)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "jlink_serial": args.jlink_serial,
                    "ppk2": pre_handoff,
                    "pre_retry_flash": pre_retry_flash,
                    "evidence_input_count": len(evidence_inputs),
                    "artifacts": {
                        key: str(path) for key, path in paths.items()
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

    flash_partial = paths["flash"].with_suffix(paths["flash"].suffix + ".partial")
    ram_partial = paths["ram"].with_suffix(paths["ram"].suffix + ".partial")
    optr_partial = paths["flash_optr"].with_suffix(
        paths["flash_optr"].suffix + ".partial"
    )
    preserve_script = "\n".join(
        [
            "connect",
            "h",
            f"savebin {flash_partial} 0x08000000 0x00040000",
            f"savebin {ram_partial} 0x20000000 0x00010000",
            f"savebin {optr_partial} 0x{FLASH_OPTR_ADDRESS:08X} 0x00000004",
            "mem32 0x4000B100 32",
            "g",
            "exit",
            "",
        ]
    )
    write_exclusive(paths["preserve_script"], preserve_script)
    run_jlink(
        executable,
        args.jlink_serial,
        paths["preserve_script"],
        paths["preserve_raw"],
    )
    if flash_partial.stat().st_size != EXPECTED_FLASH_BYTES:
        raise SystemExit(
            f"flash dump has {flash_partial.stat().st_size} bytes, "
            f"expected {EXPECTED_FLASH_BYTES}"
        )
    if ram_partial.stat().st_size != EXPECTED_RAM_BYTES:
        raise SystemExit(
            f"RAM dump has {ram_partial.stat().st_size} bytes, "
            f"expected {EXPECTED_RAM_BYTES}"
        )
    optr_record = validate_option_register(optr_partial)
    commit_partial_create_once(
        flash_partial, paths["flash"], "precursor flash evidence"
    )
    commit_partial_create_once(
        ram_partial, paths["ram"], "precursor RAM evidence"
    )
    commit_partial_create_once(
        optr_partial, paths["flash_optr"], "precursor option-byte evidence"
    )
    optr_record = validate_option_register(paths["flash_optr"])

    health_script = HERE / "jlink_read_soak_health.jlink"
    run_jlink(
        executable,
        args.jlink_serial,
        health_script,
        paths["health_raw"],
    )
    post_handoff = load_handoff(
        args.handoff_power,
        args.max_heartbeat_age_seconds,
    )

    require_flash_unchanged(pre_retry_flash, paths["flash"])

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "target": {
            "device": "STM32WLE5CC",
            "interface": "SWD",
            "speed_khz": 4000,
            "jlink_serial": args.jlink_serial,
            "ppk2_before": pre_handoff,
            "ppk2_after": post_handoff,
        },
        "precursor": {
            key: file_record(paths[key])
            for key in (
                "flash",
                "ram",
                "flash_optr",
                "preserve_script",
                "preserve_raw",
                "health_raw",
            )
        },
        "pre_retry_flash": pre_retry_flash,
        "flash_unchanged_during_soak": True,
        "flash_option_register": optr_record,
        "evidence_inputs": {
            str(path.resolve()): provenance_record(
                path,
                append_allowed=(path.resolve() == args.handoff_power.resolve()),
            )
            for path in evidence_inputs
        },
    }
    atomic_manifest(paths["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
