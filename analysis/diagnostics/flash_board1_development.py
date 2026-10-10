#!/usr/bin/env python3
"""Guard and record one StratoLink-1 development-image flash.

This wrapper intentionally has no StratoLink-2 soak, candidate-version, PPK2,
or backend gates.  Its authority is narrow: program one caller-supplied BIN at
0x08000000 after binding its SHA-256 and a complete 256 KiB pre-flash baseline.
The opaque final 4 KiB flash page is verified against that baseline before the
programming command and captured plus verified again before reset/run.  The
default preserves it byte-for-byte.  An explicit initialization option instead
archives those legacy bytes, performs one exact bounded no-reset erase of that
page, and proves the resulting page is all 0xFF before reset/run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TARGET_DEVICE = "STM32WLE5CC"
FLASH_ADDRESS = 0x08000000
FLASH_BYTES = 256 * 1024
RESERVED_ADDRESS = 0x0803F000
RESERVED_OFFSET = RESERVED_ADDRESS - FLASH_ADDRESS
RESERVED_BYTES = 4096
RESERVED_END_ADDRESS = RESERVED_ADDRESS + RESERVED_BYTES - 1
SERIAL = re.compile(r"^[0-9]{1,20}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
BENIGN_CONNECT_PREAMBLE = (
    "j-link connection not established yet but required for command."
)

FAILURE_MARKERS = (
    "cannot connect",
    "could not connect",
    "failed to connect",
    "connection not established",
    "verification failed",
    "verify failed",
    "failed to verify",
    "programming failed",
    "error while programming",
    "cannot open file",
    "could not open file",
    "failed to open file",
    "failed to save",
    "could not save",
    "script file read error",
    "unknown command",
)
FORBIDDEN_MUTATION_MARKERS = (
    "mass erase",
    "mass-erase",
    "full chip erase",
    "chip erase",
    "erase chip",
    "erasing chip",
    "entire chip erase",
    "erase all flash",
    "erasing all flash",
    "unlock device",
    "unlocking device",
    "device will be unlocked",
    "unsecure device",
    "unsecuring device",
    "device will be unsecured",
    "device has been unlocked",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, private: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if private:
        value["private"] = True
    return value


def bound_file_record(
    path: Path,
    value: bytes,
    *,
    private: bool = False,
) -> dict[str, object]:
    record: dict[str, object] = {
        "path": str(path.resolve()),
        "bytes": len(value),
        "sha256": sha256_bytes(value),
    }
    if private:
        record["private"] = True
    return record


def write_bytes_exclusive(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def write_exclusive(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def commit_partial_create_once(partial: Path, path: Path, noun: str) -> None:
    try:
        os.link(partial, path)
    except FileExistsError as error:
        raise SystemExit(f"refusing to overwrite {noun}: {path}") from error
    partial.unlink()


def atomic_manifest(path: Path, value: dict[str, object]) -> None:
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


def artifact_paths(prefix: Path) -> dict[str, Path]:
    return {
        "candidate": prefix.with_name(prefix.name + "_program.bin"),
        "reserved_before": prefix.with_name(
            prefix.name + "_reserved_0803f000_before.bin"
        ),
        "reserved_after": prefix.with_name(
            prefix.name + "_reserved_0803f000_after.bin"
        ),
        "reserved_erased": prefix.with_name(
            prefix.name + "_reserved_0803f000_expected_erased.bin"
        ),
        "script": prefix.with_name(prefix.name + "_flash.jlink"),
        "raw": prefix.with_name(prefix.name + "_flash_raw.txt"),
        "manifest": prefix.with_name(prefix.name + "_manifest.json"),
    }


def require_create_once(paths: dict[str, Path]) -> None:
    collisions: list[str] = []
    for path in paths.values():
        for candidate in (path, path.with_suffix(path.suffix + ".partial")):
            if candidate.exists():
                collisions.append(str(candidate))
    if collisions:
        raise SystemExit(
            "refusing to overwrite Board1 development-flash evidence: "
            + ", ".join(collisions)
        )


def validate_inputs(
    binary_path: Path,
    expected_sha256: str,
    baseline_path: Path,
) -> tuple[bytes, bytes, str]:
    if not SHA256.fullmatch(expected_sha256):
        raise SystemExit("--expected-bin-sha256 must be exactly 64 hex characters")
    normalized_sha256 = expected_sha256.lower()
    if not binary_path.is_file():
        raise SystemExit(f"BIN is missing: {binary_path}")
    binary = binary_path.read_bytes()
    if not binary:
        raise SystemExit("BIN is empty")
    if len(binary) > RESERVED_OFFSET:
        raise SystemExit(
            "BIN overlaps the opaque reserved page at 0x0803F000; refusing flash"
        )
    actual_sha256 = sha256_bytes(binary)
    if actual_sha256 != normalized_sha256:
        raise SystemExit(
            "BIN SHA-256 mismatch: "
            f"expected {normalized_sha256}, observed {actual_sha256}"
        )
    if not baseline_path.is_file():
        raise SystemExit(f"256 KiB baseline flash is missing: {baseline_path}")
    baseline = baseline_path.read_bytes()
    if len(baseline) != FLASH_BYTES:
        raise SystemExit(
            f"baseline flash has {len(baseline)} bytes, expected {FLASH_BYTES}"
        )
    return binary, baseline, normalized_sha256


def jlink_path(path: Path) -> str:
    value = str(path.resolve())
    if any(character in value for character in ('"', "\r", "\n")):
        raise SystemExit(f"J-Link path contains an unsupported character: {value!r}")
    return f'"{value}"'


def build_flash_script(
    paths: dict[str, Path],
    *,
    initialize_reserved_erased: bool = False,
) -> str:
    reserved_after_partial = paths["reserved_after"].with_suffix(
        paths["reserved_after"].suffix + ".partial"
    )
    expected_reserved_path = (
        paths["reserved_erased"]
        if initialize_reserved_erased
        else paths["reserved_before"]
    )
    commands = [
        "connect",
        "h",
        f"verifybin {jlink_path(paths['reserved_before'])} 0x{RESERVED_ADDRESS:08X}",
        f"loadfile {jlink_path(paths['candidate'])} 0x{FLASH_ADDRESS:08X} noreset",
        f"verifybin {jlink_path(paths['candidate'])} 0x{FLASH_ADDRESS:08X}",
    ]
    if initialize_reserved_erased:
        commands.extend(
            [
                f"erase 0x{RESERVED_ADDRESS:08X} "
                f"0x{RESERVED_END_ADDRESS:08X} noreset",
                f"verifybin {jlink_path(paths['reserved_erased'])} "
                f"0x{RESERVED_ADDRESS:08X}",
            ]
        )
    commands.extend(
        [
            f"savebin {jlink_path(reserved_after_partial)} "
            f"0x{RESERVED_ADDRESS:08X} 0x{RESERVED_BYTES:08X}",
            f"verifybin {jlink_path(expected_reserved_path)} "
            f"0x{RESERVED_ADDRESS:08X}",
            "r",
            "g",
            "exit",
            "",
        ]
    )
    return "\n".join(commands)


def classify_transcript(
    transcript: str,
    returncode: int,
    *,
    initialize_reserved_erased: bool = False,
    expected_serial: str | None = None,
) -> dict[str, object]:
    lowered = transcript.lower()
    marker_text = lowered
    benign_connect_preamble_seen = BENIGN_CONNECT_PREAMBLE in marker_text
    if (
        benign_connect_preamble_seen
        and "cortex-m4 identified." in marker_text
        and "script processing completed." in marker_text
    ):
        marker_text = marker_text.replace(BENIGN_CONNECT_PREAMBLE, "")
    failure_markers = [
        marker for marker in FAILURE_MARKERS if marker in marker_text
    ]
    forbidden_markers = [
        marker for marker in FORBIDDEN_MUTATION_MARKERS if marker in lowered
    ]
    implicit_reset = "performing implicit reset" in lowered
    load_commands = re.findall(r"(?im)^\s*j-link>\s*loadfile\b.*$", transcript)
    verify_commands = re.findall(r"(?im)^\s*j-link>\s*verifybin\b.*$", transcript)
    erase_commands = re.findall(r"(?im)^\s*j-link>\s*erase\b.*$", transcript)
    unlock_commands = re.findall(
        r"(?im)^\s*j-link>\s*(?:unlock|unsecure)\b.*$", transcript
    )
    if unlock_commands:
        forbidden_markers.append("explicit unlock/unsecure command")
    verification_successes = lowered.count("verify successful")
    reset_seen = bool(re.search(r"(?im)^\s*j-link>\s*r\s*$", transcript))
    run_seen = bool(re.search(r"(?im)^\s*j-link>\s*g\s*$", transcript))
    required_failures: list[str] = []
    if "cortex-m4 identified." not in lowered:
        required_failures.append("Cortex-M4 identification missing")
    expected_device_marker = f'device "{TARGET_DEVICE.lower()}" selected.'
    selected_device_seen = expected_device_marker in lowered
    if not selected_device_seen:
        required_failures.append(f"{TARGET_DEVICE} selection missing")
    serial_seen = (
        expected_serial is None
        or re.search(
            rf"(?im)^\s*s/n:\s*{re.escape(expected_serial)}\s*$",
            transcript,
        )
        is not None
    )
    if not serial_seen:
        required_failures.append("requested J-Link serial was not observed")
    if "script processing completed." not in lowered:
        required_failures.append("script completion missing")
    if len(load_commands) != 1:
        required_failures.append("expected exactly one loadfile command")
    elif "0x08000000" not in load_commands[0].lower() or "noreset" not in load_commands[0].lower():
        required_failures.append("loadfile was not the bounded noreset BIN program")
    expected_verify_count = 4 if initialize_reserved_erased else 3
    if (
        len(verify_commands) != expected_verify_count
        or verification_successes < expected_verify_count
    ):
        required_failures.append(
            f"{expected_verify_count} explicit verifybin successes were not observed"
        )
    flash_verify_count = sum(
        "0x08000000" in command.lower() for command in verify_commands
    )
    reserved_verify_count = sum(
        "0x0803f000" in command.lower() for command in verify_commands
    )
    if flash_verify_count != 1 or reserved_verify_count != expected_verify_count - 1:
        required_failures.append("verifybin commands did not cover the exact flash scopes")
    expected_erase = (
        f"j-link>erase 0x{RESERVED_ADDRESS:08x} "
        f"0x{RESERVED_END_ADDRESS:08x} noreset"
    )
    normalized_erases = [
        re.sub(r"\s+", " ", command.strip().lower())
        for command in erase_commands
    ]
    if initialize_reserved_erased:
        if normalized_erases != [expected_erase]:
            required_failures.append(
                "exactly one bounded noreset erase of 0x0803F000-0x0803FFFF "
                "was not observed"
            )
    elif erase_commands:
        forbidden_markers.append("explicit erase command")
    if not reset_seen or not run_seen:
        required_failures.append("explicit reset/run was not observed")
    if implicit_reset:
        required_failures.append("loadfile performed an implicit reset")
    passed = (
        returncode == 0
        and not failure_markers
        and not forbidden_markers
        and not required_failures
    )
    return {
        "returncode": returncode,
        "benign_commander_connect_preamble_seen": benign_connect_preamble_seen,
        "failure_markers": sorted(set(failure_markers)),
        "forbidden_mutation_markers": sorted(set(forbidden_markers)),
        "loadfile_command_count": len(load_commands),
        "verifybin_command_count": len(verify_commands),
        "verify_success_count": verification_successes,
        "erase_command_count": len(erase_commands),
        "bounded_reserved_erase_seen": normalized_erases == [expected_erase],
        "reserved_initialization_requested": initialize_reserved_erased,
        "selected_device_seen": selected_device_seen,
        "requested_serial_seen": serial_seen,
        "explicit_reset_seen": reset_seen,
        "run_seen": run_seen,
        "implicit_reset_seen": implicit_reset,
        "required_failures": required_failures,
        "passed": passed,
    }


def run_jlink(
    executable: str,
    serial: str,
    speed_khz: int,
    script: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            executable,
            "-device",
            TARGET_DEVICE,
            "-if",
            "SWD",
            "-speed",
            str(speed_khz),
            "-SelectEmuBySN",
            serial,
            "-NoGui",
            "1",
            "-ExitOnError",
            "1",
            "-CommanderScript",
            str(script),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def record_post_access(
    path: Path,
    expected_sha256: str,
    noun: str,
    failures: list[str],
) -> dict[str, object] | None:
    try:
        record = file_record(path, private=True)
    except OSError as error:
        failures.append(f"{noun} cannot be re-read after target access: {error}")
        return None
    if record["sha256"] != expected_sha256:
        failures.append(f"{noun} changed during target access")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--bin", dest="binary", type=Path, required=True)
    parser.add_argument("--expected-bin-sha256", required=True)
    parser.add_argument("--baseline-flash", type=Path, required=True)
    parser.add_argument("--jlink-serial", required=True)
    parser.add_argument("--speed-khz", type=int, default=4000)
    parser.add_argument(
        "--initialize-reserved-erased",
        action="store_true",
        help=(
            "explicitly preserve the legacy reserved-page bytes as evidence, then "
            "erase only 0x0803F000-0x0803FFFF and verify all 0xFF before reset/run"
        ),
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if not SERIAL.fullmatch(args.jlink_serial):
        raise SystemExit("--jlink-serial must be the exact numeric probe serial")
    if not 1 <= args.speed_khz <= 4000:
        parser.error("--speed-khz must be between 1 and 4000")

    binary_path = args.binary.resolve()
    baseline_path = args.baseline_flash.resolve()
    binary, baseline, expected_sha256 = validate_inputs(
        binary_path,
        args.expected_bin_sha256,
        baseline_path,
    )
    binary_input_record = bound_file_record(binary_path, binary, private=True)
    baseline_input_record = bound_file_record(
        baseline_path,
        baseline,
        private=True,
    )
    reserved_before = baseline[RESERVED_OFFSET : RESERVED_OFFSET + RESERVED_BYTES]
    if len(reserved_before) != RESERVED_BYTES:
        raise SystemExit("baseline does not contain the complete opaque reserved page")
    expected_reserved_after = (
        b"\xFF" * RESERVED_BYTES
        if args.initialize_reserved_erased
        else reserved_before
    )
    reserved_action = (
        "initialize_erased"
        if args.initialize_reserved_erased
        else "preserve_byte_for_byte"
    )

    paths = artifact_paths(args.prefix.resolve())
    require_create_once(paths)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "candidate": {
                        "path": str(binary_path),
                        "bytes": len(binary),
                        "sha256": expected_sha256,
                        "program_address": f"0x{FLASH_ADDRESS:08X}",
                        "program_end_exclusive": f"0x{FLASH_ADDRESS + len(binary):08X}",
                    },
                    "baseline": {
                        **baseline_input_record,
                        "reserved_sha256": sha256_bytes(reserved_before),
                        "reserved_non_ff_bytes": sum(
                            value != 0xFF for value in reserved_before
                        ),
                    },
                    "reserved_page_action": reserved_action,
                    "expected_reserved_after_sha256": sha256_bytes(
                        expected_reserved_after
                    ),
                    "target": {
                        "device": TARGET_DEVICE,
                        "jlink_serial": args.jlink_serial,
                        "speed_khz": args.speed_khz,
                    },
                    "artifacts": {name: str(path) for name, path in paths.items()},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    paths["candidate"].parent.mkdir(parents=True, exist_ok=True)
    write_bytes_exclusive(paths["candidate"], binary)
    write_bytes_exclusive(paths["reserved_before"], reserved_before)
    if args.initialize_reserved_erased:
        write_bytes_exclusive(paths["reserved_erased"], expected_reserved_after)
    write_exclusive(
        paths["script"],
        build_flash_script(
            paths,
            initialize_reserved_erased=args.initialize_reserved_erased,
        ),
    )

    executable = shutil.which("JLinkExe")
    if executable is None:
        raise SystemExit("JLinkExe not found; frozen inputs remain create-once")

    result = run_jlink(
        executable,
        args.jlink_serial,
        args.speed_khz,
        paths["script"],
    )
    write_exclusive(paths["raw"], result.stdout)
    transport = classify_transcript(
        result.stdout,
        result.returncode,
        initialize_reserved_erased=args.initialize_reserved_erased,
        expected_serial=args.jlink_serial,
    )

    failures: list[str] = []
    if not transport["passed"]:
        failures.append("J-Link transcript did not prove the bounded flash sequence")

    reserved_partial = paths["reserved_after"].with_suffix(
        paths["reserved_after"].suffix + ".partial"
    )
    reserved_after_record: dict[str, object] | None = None
    reserved_matches_expected = False
    reserved_identical_to_before = False
    if reserved_partial.is_file() and reserved_partial.stat().st_size == RESERVED_BYTES:
        commit_partial_create_once(
            reserved_partial,
            paths["reserved_after"],
            "Board1 post-flash reserved-page evidence",
        )
        reserved_after_record = file_record(paths["reserved_after"], private=True)
        reserved_after_bytes = paths["reserved_after"].read_bytes()
        reserved_identical_to_before = reserved_after_bytes == reserved_before
        reserved_matches_expected = reserved_after_bytes == expected_reserved_after
        if not reserved_matches_expected:
            failures.append(
                "opaque reserved page does not match the requested post-flash state"
            )
    else:
        failures.append("post-flash reserved-page capture is missing or wrong-sized")

    frozen_candidate_record = record_post_access(
        paths["candidate"],
        expected_sha256,
        "frozen candidate copy",
        failures,
    )
    binary_post_access_record = record_post_access(
        binary_path,
        expected_sha256,
        "input BIN",
        failures,
    )
    baseline_post_access_record = record_post_access(
        baseline_path,
        str(baseline_input_record["sha256"]),
        "baseline flash",
        failures,
    )

    passed = transport["passed"] and reserved_matches_expected and not failures
    manifest = {
        "schema": "stratolink.board1_development_flash.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "payload": "stratolink-1",
        "passed": passed,
        "scope": (
            "user-authorized development flash of one exact BIN; optional exact "
            "reserved-page initialization only; no mass-erase, unlock, option-byte "
            "write, or StratoLink-2 launch gate"
        ),
        "target": {
            "device": TARGET_DEVICE,
            "interface": "SWD",
            "speed_khz": args.speed_khz,
            "jlink_serial": args.jlink_serial,
        },
        "candidate": {
            "source": binary_input_record,
            "source_post_access": binary_post_access_record,
            "frozen_program_copy": frozen_candidate_record,
            "required_sha256": expected_sha256,
            "program_address": f"0x{FLASH_ADDRESS:08X}",
            "program_end_exclusive": f"0x{FLASH_ADDRESS + len(binary):08X}",
        },
        "baseline_flash": {
            **baseline_input_record,
            "post_access": baseline_post_access_record,
        },
        "reserved_page": {
            "address": f"0x{RESERVED_ADDRESS:08X}",
            "bytes": RESERVED_BYTES,
            "opaque": True,
            "action": reserved_action,
            "before": file_record(paths["reserved_before"], private=True),
            "after": reserved_after_record,
            "before_non_ff_bytes": sum(value != 0xFF for value in reserved_before),
            "before_preserved_as_evidence": True,
            "expected_after_sha256": sha256_bytes(expected_reserved_after),
            "expected_erased_artifact": (
                file_record(paths["reserved_erased"], private=True)
                if args.initialize_reserved_erased
                else None
            ),
            "byte_identical": reserved_identical_to_before,
            "matches_requested_post_flash_state": reserved_matches_expected,
        },
        "programming": {
            "program_only_bin": True,
            "explicit_verifybin": True,
            "explicit_reset_run": True,
            "bounded_reserved_initialization": args.initialize_reserved_erased,
            "transcript": transport,
        },
        "artifacts": {
            "commander_script": file_record(paths["script"]),
            "raw_transcript": file_record(paths["raw"], private=True),
        },
        "failures": failures,
    }
    atomic_manifest(paths["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
