#!/usr/bin/env python3
"""Gate and byte-verify the one-shot flash of the frozen flight candidate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from evidence_provenance import verify_all as verify_provenance
from preserve_precursor import (
    EXPECTED_FLASH_BYTES,
    atomic_manifest,
    commit_partial_create_once,
    EXPECTED_OPTR_BYTES,
    EXPECTED_PRE_RETRY_FLASH_SHA256,
    EXPECTED_RAM_BYTES,
    FLASH_OPTR_IWDG_STOP,
    load_json,
    require_engineering_acceptance,
    run_jlink,
    sha256,
    write_exclusive,
)
from verify_flight_candidate import (
    EXPECTED_BIN_SHA256,
    EXPECTED_ELF_SHA256,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOGS = HERE / "logs"
DEFAULT_PREFIX = LOGS / "stratolink2_flight_flash_20260725"
EXPECTED_JLINK_SERIAL = "802007563"
RESERVED_OFFSET = 0x3F000
RESERVED_BYTES = 0x1000
SUPERSEDED_V10_BUILD_RECORDS = {
    str((ROOT / "firmware/.pio/build/stratolink/firmware.elf").resolve()): {
        "bytes": 239736,
        "sha256": "32d98b6416f74315cb14455f0fb71c1e795bf6699be531d2b8749177e82d8439",
    },
    str((ROOT / "firmware/.pio/build/stratolink/firmware.bin").resolve()): {
        "bytes": 132820,
        "sha256": "92876b738d48b437b1238061ab1a8c3e66f12ac595c406905447208c1d1fdf2d",
    },
}


def verify_file_record(value: dict) -> Path:
    try:
        path = Path(value["path"])
        expected_bytes = value["bytes"]
        expected_hash = value["sha256"]
    except (KeyError, TypeError) as error:
        raise SystemExit(f"invalid precursor artifact record: {value!r}") from error
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes < 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or not path.is_file()
    ):
        raise SystemExit(f"invalid precursor artifact record: {value!r}")
    if path.stat().st_size != expected_bytes or sha256(path) != expected_hash:
        raise SystemExit(f"precursor artifact no longer matches its manifest: {path}")
    return path


def require_gate(path: Path, pass_key: tuple[str, ...]) -> dict:
    value = load_json(path)
    cursor: object = value
    for key in pass_key:
        cursor = cursor.get(key) if isinstance(cursor, dict) else None
    if cursor is not True:
        raise SystemExit(f"required passing gate is absent: {path}")
    try:
        verify_provenance(value.get("provenance"))
    except ValueError as error:
        raise SystemExit(f"gate provenance failed for {path}: {error}") from error
    return value


def require_precursor_manifest(path: Path, jlink_serial: str) -> tuple[dict, dict[str, Path]]:
    """Revalidate every immutable preservation claim before flashing."""
    precursor = load_json(path)
    if precursor.get("target", {}).get("jlink_serial") != jlink_serial:
        raise SystemExit("precursor manifest used a different J-Link")
    if precursor.get("flash_unchanged_during_soak") is not True:
        raise SystemExit("precursor manifest does not prove unchanged soak flash")

    records = precursor.get("precursor")
    if not isinstance(records, dict):
        raise SystemExit("precursor artifact manifest is missing")
    required = {"flash", "ram", "flash_optr"}
    if not required.issubset(records):
        raise SystemExit("precursor flash/RAM/option-byte dumps are missing")
    paths = {
        name: verify_file_record(value)
        for name, value in records.items()
        if isinstance(value, dict)
    }
    if not required.issubset(paths):
        raise SystemExit("precursor flash/RAM/option-byte dumps are invalid")
    if paths["flash"].stat().st_size != EXPECTED_FLASH_BYTES:
        raise SystemExit("precursor flash dump has the wrong byte length")
    if paths["ram"].stat().st_size != EXPECTED_RAM_BYTES:
        raise SystemExit("precursor RAM dump has the wrong byte length")
    if paths["flash_optr"].stat().st_size != EXPECTED_OPTR_BYTES:
        raise SystemExit("precursor option-byte dump has the wrong byte length")

    pre_retry = precursor.get("pre_retry_flash")
    if not isinstance(pre_retry, dict):
        raise SystemExit("precursor manifest lacks the pre-retry flash baseline")
    pre_retry_path = verify_file_record(pre_retry)
    if (
        pre_retry_path.stat().st_size != EXPECTED_FLASH_BYTES
        or pre_retry.get("sha256") != EXPECTED_PRE_RETRY_FLASH_SHA256
        or sha256(paths["flash"]) != EXPECTED_PRE_RETRY_FLASH_SHA256
    ):
        raise SystemExit("precursor manifest does not bind the fixed unchanged baseline")

    option_claim = precursor.get("flash_option_register")
    option_value = int.from_bytes(paths["flash_optr"].read_bytes(), "little")
    if (
        not isinstance(option_claim, dict)
        or option_claim.get("iwdg_runs_in_stop") is not True
        or option_claim.get("sha256") != sha256(paths["flash_optr"])
        or (option_value & FLASH_OPTR_IWDG_STOP) == 0
    ):
        raise SystemExit("precursor option-byte watchdog premise is unproven")

    evidence_inputs = precursor.get("evidence_inputs")
    if not isinstance(evidence_inputs, dict):
        raise SystemExit("precursor evidence provenance is missing")
    immutable_inputs = dict(evidence_inputs)
    for build_path, expected in SUPERSEDED_V10_BUILD_RECORDS.items():
        record = immutable_inputs.pop(build_path, None)
        if (
            not isinstance(record, dict)
            or record.get("path") != build_path
            or record.get("bytes") != expected["bytes"]
            or record.get("sha256") != expected["sha256"]
            or record.get("append_allowed") is not False
        ):
            raise SystemExit(
                "precursor manifest does not exactly bind the superseded v10 "
                f"build record: {build_path}"
            )
    try:
        # The preserved precursor was captured while v10 occupied PlatformIO's
        # mutable build directory. Those two historical records cannot still
        # match after the independently verified v15 build replaces that
        # directory. Validate their exact frozen v10 metadata above, every
        # other preservation input here, and the live v15 bytes through the
        # separate candidate-verification gate in main().
        verify_provenance(immutable_inputs)
    except ValueError as error:
        raise SystemExit(
            f"precursor evidence provenance failed: {error}"
        ) from error
    return precursor, paths


def load_handoff(path: Path, max_age_seconds: float) -> dict:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assertions = [
        row for row in rows
        if row.get("event") in ("ppk2_power_on", "ppk2_power_heartbeat")
    ]
    heartbeats = [
        row for row in assertions if row.get("event") == "ppk2_power_heartbeat"
    ]
    if (
        len([row for row in assertions if row.get("event") == "ppk2_power_on"]) != 1
        or not heartbeats
        or {int(row.get("source_mv", 0)) for row in assertions} != {4660}
        or max(int(row.get("reconnects", 0)) for row in assertions) != 0
    ):
        raise SystemExit("standby PPK2 supervisor is not continuously healthy")
    last = datetime.fromisoformat(heartbeats[-1]["utc"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - last).total_seconds()
    if not 0 <= age <= max_age_seconds:
        raise SystemExit(
            f"standby PPK2 heartbeat is stale or future-dated ({age:.3f}s)"
        )
    return {
        "path": str(path.resolve()),
        "last_heartbeat_utc": heartbeats[-1]["utc"],
        "heartbeat_age_seconds": round(age, 3),
        "source_mv": 4660,
        "max_reconnects": 0,
    }


def require_devnonce_baseline(
    manifest_path: Path,
    journal_path: Path,
    candidate_verification: Path,
    jlink_serial: str,
) -> tuple[dict, bytes]:
    """Accept only a passing exact-candidate journal as a post-HIL baseline."""
    manifest = load_json(manifest_path)
    summary = manifest.get("journal", {})
    record = manifest.get("artifacts", {}).get("journal")
    if (
        manifest.get("passed") is not True
        or manifest.get("target", {}).get("jlink_serial") != jlink_serial
        or manifest.get("candidate_verification_sha256")
        != sha256(candidate_verification)
        or summary.get("invalid_record_count") != 0
        or summary.get("exhausted") is not False
        or not isinstance(summary.get("valid_record_count"), int)
        or summary.get("valid_record_count", 0) < 1
        or not isinstance(record, dict)
    ):
        raise SystemExit("post-HIL DevNonce baseline manifest is not passing")
    recorded_path = verify_file_record(record)
    if recorded_path.resolve() != journal_path.resolve():
        raise SystemExit("DevNonce manifest identifies an unexpected journal")
    if journal_path.stat().st_size != RESERVED_BYTES:
        raise SystemExit("DevNonce baseline has the wrong byte length")
    return manifest, journal_path.read_bytes()


def paths(prefix: Path) -> dict[str, Path]:
    return {
        "flash_raw": prefix.with_name(prefix.name + "_raw.txt"),
        "reserved_script": prefix.with_name(prefix.name + "_reserved_read.jlink"),
        "reserved_raw": prefix.with_name(prefix.name + "_reserved_read_raw.txt"),
        "reserved_after": prefix.with_name(prefix.name + "_reserved_after.bin"),
        "manifest": prefix.with_name(prefix.name + "_manifest.json"),
    }


def require_create_once(artifacts: dict[str, Path]) -> None:
    collisions = [
        str(path)
        for path in artifacts.values()
        if path.exists() or path.with_suffix(path.suffix + ".partial").exists()
    ]
    if collisions:
        raise SystemExit("refusing to overwrite flash evidence: " + ", ".join(collisions))


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
        "--precursor-manifest",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--handoff-power",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--devnonce-baseline",
        type=Path,
        help="passing 4096-byte post-HIL DevNonce journal baseline",
    )
    parser.add_argument(
        "--devnonce-manifest",
        type=Path,
        help="capture manifest binding --devnonce-baseline to this candidate",
    )
    parser.add_argument("--jlink-serial", default=EXPECTED_JLINK_SERIAL)
    parser.add_argument("--max-heartbeat-age-seconds", type=float, default=60)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if args.jlink_serial != EXPECTED_JLINK_SERIAL:
        raise SystemExit("refusing an unrecognized J-Link serial")
    summary = load_json(args.summary)
    sensor = load_json(args.sensor_model)
    standard_gates_pass = (
        summary.get("final_gate", {}).get("passed") is True
        and sensor.get("passed") is True
    )
    acceptance = None
    if standard_gates_pass:
        require_gate(args.summary, ("final_gate", "passed"))
        require_gate(args.sensor_model, ("passed",))
    else:
        acceptance = require_engineering_acceptance(args.engineering_acceptance)
    candidate = require_gate(args.candidate_verification, ("passed",))
    if (
        candidate.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or candidate.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit("candidate report does not name the frozen release hashes")

    precursor, precursor_paths = require_precursor_manifest(
        args.precursor_manifest,
        args.jlink_serial,
    )
    if (args.devnonce_baseline is None) != (args.devnonce_manifest is None):
        raise SystemExit(
            "supply both --devnonce-baseline and --devnonce-manifest"
        )
    devnonce_manifest = None
    if args.devnonce_baseline is not None and args.devnonce_manifest is not None:
        devnonce_manifest, expected_reserved = require_devnonce_baseline(
            args.devnonce_manifest,
            args.devnonce_baseline,
            args.candidate_verification,
            args.jlink_serial,
        )
        reserved_baseline_source = "passing_post_hil_devnonce_capture"
    else:
        precursor_flash = precursor_paths["flash"].read_bytes()
        expected_reserved = precursor_flash[
            RESERVED_OFFSET:RESERVED_OFFSET + RESERVED_BYTES
        ]
        reserved_baseline_source = "preserved_precursor_flash"

    handoff = load_handoff(args.handoff_power, args.max_heartbeat_age_seconds)
    artifacts = paths(args.prefix.resolve())
    require_create_once(artifacts)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "candidate_bin_sha256": EXPECTED_BIN_SHA256,
                    "precursor_flash_sha256": sha256(precursor_paths["flash"]),
                    "reserved_baseline_sha256": sha256(
                        args.devnonce_baseline
                        if args.devnonce_baseline is not None
                        else precursor_paths["flash"]
                    ),
                    "reserved_baseline_source": reserved_baseline_source,
                    "ppk2": handoff,
                    "artifacts": {
                        key: str(path) for key, path in artifacts.items()
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
    flash_script = HERE / "generated/jlink_flash_flight.jlink"
    run_jlink(
        executable,
        args.jlink_serial,
        flash_script,
        artifacts["flash_raw"],
    )

    reserved_partial = artifacts["reserved_after"].with_suffix(
        artifacts["reserved_after"].suffix + ".partial"
    )
    reserved_script = "\n".join(
        [
            "connect",
            "h",
            f"savebin {reserved_partial} 0x0803F000 0x00001000",
            "g",
            "exit",
            "",
        ]
    )
    write_exclusive(artifacts["reserved_script"], reserved_script)
    run_jlink(
        executable,
        args.jlink_serial,
        artifacts["reserved_script"],
        artifacts["reserved_raw"],
    )
    if not reserved_partial.is_file() or reserved_partial.stat().st_size != RESERVED_BYTES:
        raise SystemExit("post-flash reserved-page read is missing or wrong-sized")
    observed_reserved = reserved_partial.read_bytes()
    if observed_reserved != expected_reserved:
        raise SystemExit(
            "flight image was flashed, but the reserved DevNonce pages changed; "
            "do not proceed to launch"
        )
    commit_partial_create_once(
        reserved_partial,
        artifacts["reserved_after"],
        "post-flash reserved-page evidence",
    )

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "target": {
            "device": "STM32WLE5CC",
            "jlink_serial": args.jlink_serial,
            "ppk2": load_handoff(
                args.handoff_power,
                args.max_heartbeat_age_seconds,
            ),
        },
        "candidate": candidate["candidate"],
        "precursor_manifest": {
            "path": str(args.precursor_manifest.resolve()),
            "sha256": sha256(args.precursor_manifest),
        },
        "reserved_baseline": {
            "source": reserved_baseline_source,
            "journal": (
                {
                    "path": str(args.devnonce_baseline.resolve()),
                    "bytes": args.devnonce_baseline.stat().st_size,
                    "sha256": sha256(args.devnonce_baseline),
                }
                if args.devnonce_baseline is not None
                else None
            ),
            "manifest": (
                {
                    "path": str(args.devnonce_manifest.resolve()),
                    "bytes": args.devnonce_manifest.stat().st_size,
                    "sha256": sha256(args.devnonce_manifest),
                }
                if devnonce_manifest is not None and args.devnonce_manifest is not None
                else None
            ),
        },
        "gate_artifacts": {
            "summary_sha256": sha256(args.summary),
            "sensor_model_sha256": sha256(args.sensor_model),
            "candidate_verification_sha256": sha256(
                args.candidate_verification
            ),
            "engineering_acceptance_sha256": (
                sha256(args.engineering_acceptance)
                if acceptance is not None and args.engineering_acceptance is not None
                else None
            ),
        },
        "flash_evidence": {
            name: {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in artifacts.items()
            if name != "manifest"
        },
        "reserved_devnonce_pages_preserved": True,
    }
    atomic_manifest(artifacts["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
