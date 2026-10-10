#!/usr/bin/env python3
"""Create a one-shot baseline of StratoLink-1.

The target may be in STOP1. A failed attach is therefore an expected passive
result: J-Link reset retry inhibition is requested, the transcript is preserved, and a
later attempt waits for a normal firmware wake. Any connect-under-reset,
unlock, erase, or programming marker is fatal.

Successful debug attachment still perturbs timing and debug-control registers.
The manifest says so explicitly; this is a pre-flash firmware-forensics record,
not proof of uninterrupted application execution.

For the explicitly disposable development board, ``--development-reset-attach``
accepts J-Link's connect-under-reset fallback. The same bounded read-only
capture is performed and an explicit resume is attempted; erase, unlock, and
programming markers remain fatal. Commander completion is not proof that the
application resumed. Reset-inhibition settings are requests, not guarantees.
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
import signal
import subprocess
import time

from decode_flight_state import parse_memory, read_bytes
from evidence_provenance import (
    atomic_manifest,
    commit_partial_create_once,
    write_exclusive,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EXPECTED_JLINK_SERIAL = "802007563"
# Use the architecture-only target for this read-only forensic pass. SEGGER's
# STM32WLE5CC device InitTarget() performs its own connect-under-reset fallback
# before the Commander script can run; the generic core needs no flash loader
# to read memory and leaves reset policy under the explicit script setting.
FORENSIC_DEVICE = "Cortex-M4"
FLASH_ADDRESS = 0x08000000
FLASH_BYTES = 256 * 1024
RAM_ADDRESS = 0x20000000
RAM_BYTES = 64 * 1024
FLASH_OPTR_ADDRESS = 0x58004020
FLASH_OPTR_BYTES = 4
FLASH_OPTR_IWDG_STOP = 1 << 17
TAMP_ADDRESS = 0x4000B100
TAMP_WORDS = 20
TAMP_BYTES = TAMP_WORDS * 4
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_CLEANUP_TIMEOUT_SECONDS = 10.0
RESERVED_ADDRESS = 0x0803F000
RESERVED_BYTES = 4096
CONNECT_UNDER_RESET_MARKERS = (
    "can not attach to cpu. trying connect under reset.",
    "attach to cpu failed. executing connect under reset.",
    "connect failed. resetting via reset pin and trying again.",
)
RESET_MARKERS = CONNECT_UNDER_RESET_MARKERS + (
    "reset: halt core after reset",
    "reset: reset device",
)
BENIGN_CONNECT_PREAMBLE = (
    "j-link connection not established yet but required for command."
)
VTREF = re.compile(r"VTref=([0-9]+(?:\.[0-9]+)?)V")
CONNECT_FAILURE_MARKERS = (
    "could not connect to the target device",
    "cannot connect to the target device",
    "failed to initialize dap",
    "target connection not established",
    "connection not established",
)
MUTATION_MARKERS = (
    "mass erase",
    "mass-erase",
    "unlock device",
    "unsecure device",
    "unlocking device",
    "programming flash",
    "erasing flash",
    "erase done",
)
COMMAND_FAILURE_MARKERS = (
    "error:",
    "could not read",
    "cannot read",
    "failed to read",
    "error while reading",
    "cannot access memory",
    "could not start cpu",
    "cannot start cpu",
    "failed to start cpu",
    "could not halt",
    "cannot halt",
    "failed to halt",
    "cpu is not halted",
    "failed to save",
    "could not save",
    "cannot open file",
    "could not open file",
    "failed to open file",
    "script file read error",
    "unknown command",
    "syntax:",
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


def artifact_paths(prefix: Path) -> dict[str, Path]:
    return {
        "flash": prefix.with_name(prefix.name + "_flash.bin"),
        "ram": prefix.with_name(prefix.name + "_ram.bin"),
        "flash_optr": prefix.with_name(prefix.name + "_flash_optr.bin"),
        "tamp": prefix.with_name(prefix.name + "_tamp.bin"),
        "reserved": prefix.with_name(prefix.name + "_reserved_0803f000.bin"),
        "commander": prefix.with_name(prefix.name + "_capture.jlink"),
        "jlink_script": prefix.with_name(prefix.name + "_no_reset.JLinkScript"),
        "manifest": prefix.with_name(prefix.name + "_manifest.json"),
        "failure": prefix.with_name(prefix.name + "_failure.json"),
        "resume_commander": prefix.with_name(prefix.name + "_resume.jlink"),
    }


def attempt_path(prefix: Path, number: int) -> Path:
    return prefix.with_name(prefix.name + f"_attempt{number:04d}_raw.txt")


def require_create_once(prefix: Path, paths: dict[str, Path]) -> None:
    collisions: list[str] = []
    for path in paths.values():
        for candidate in (path, path.with_suffix(path.suffix + ".partial")):
            if candidate.exists():
                collisions.append(str(candidate))
    collisions.extend(
        str(path) for path in prefix.parent.glob(prefix.name + "_attempt*_raw.txt")
    )
    if collisions:
        raise SystemExit(
            "refusing to overwrite StratoLink-1 baseline evidence: "
            + ", ".join(collisions)
        )


def build_jlink_script() -> str:
    return "\n".join(
        [
            "int ConfigTargetSettings(void) {",
            '  JLINK_SYS_Report("-- forensic attach: inhibit reset retries --");',
            '  JLINK_ExecCommand("InhibitConnectRetries = 1");',
            '  JLINK_ExecCommand("SetRestartOnClose = 1");',
            "  return 0;",
            "}",
            "",
        ]
    )


def build_commander_script(paths: dict[str, Path]) -> str:
    ram_partial = paths["ram"].with_suffix(".bin.partial")
    optr_partial = paths["flash_optr"].with_suffix(".bin.partial")
    flash_partial = paths["flash"].with_suffix(".bin.partial")
    return "\n".join(
        [
            "connect",
            # Keep initial connect fail-fast; read/halt errors must still reach g.
            "ExitOnError 0",
            "h",
            f"savebin {ram_partial} 0x{RAM_ADDRESS:08X} 0x{RAM_BYTES:08X}",
            f"mem32 0x{TAMP_ADDRESS:08X} 0x{TAMP_WORDS:02X}",
            f"savebin {optr_partial} 0x{FLASH_OPTR_ADDRESS:08X} 0x{FLASH_OPTR_BYTES:08X}",
            f"savebin {flash_partial} 0x{FLASH_ADDRESS:08X} 0x{FLASH_BYTES:08X}",
            "g",
            "exit",
            "",
        ]
    )


def write_bytes_exclusive(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def transcript_metadata(
    transcript: str,
    returncode: int | None = 0,
    *,
    development_reset_attach: bool = False,
    require_capture: bool = True,
) -> dict[str, object]:
    lowered = transcript.lower()
    match = VTREF.search(transcript)
    mutation_markers = [marker for marker in MUTATION_MARKERS if marker in lowered]
    connect_reset_markers = [
        marker for marker in CONNECT_UNDER_RESET_MARKERS if marker in lowered
    ]
    reset_markers = [marker for marker in RESET_MARKERS if marker in lowered]
    reset_fallback = bool(reset_markers)
    connected = "cortex-m4 identified." in lowered
    completed = "script processing completed." in lowered
    commands = re.findall(r"^j-link>\s*(.*?)\s*$", lowered, re.MULTILINE)
    resume_seen = "g" in commands
    capture_seen = (
        "h" in commands
        and len([command for command in commands if command.startswith("savebin ")]) == 3
        and any(command.startswith("mem32 ") for command in commands)
        and resume_seen
        and commands.index("h") < commands.index("g")
        and all(index < commands.index("g") for index, command in enumerate(commands)
                if command.startswith(("savebin ", "mem32 ")))
    )
    failures = [marker for marker in COMMAND_FAILURE_MARKERS if marker in lowered]
    connection_text = lowered.replace(BENIGN_CONNECT_PREAMBLE, "")
    connection_failures = [
        marker for marker in CONNECT_FAILURE_MARKERS if marker in connection_text
    ]
    success = (
        returncode == 0
        and connected
        and completed
        and resume_seen
        and "exit" in commands
        and (capture_seen or not require_capture)
        and not connection_failures
        and not failures
        and (development_reset_attach or not reset_fallback)
        and not mutation_markers
    )
    return {
        "returncode": returncode,
        "vtref_v": float(match.group(1)) if match else None,
        "cortex_m4_identified": connected,
        "script_completed": completed,
        "halt_command_seen": "h" in commands,
        "capture_commands_seen": capture_seen,
        "resume_command_seen": resume_seen,
        "resume_verified": False,
        "connect_under_reset_marker": bool(connect_reset_markers),
        "connect_under_reset_markers": connect_reset_markers,
        "reset_markers": reset_markers,
        "development_reset_attach_authorized": development_reset_attach,
        "connection_failure_markers": connection_failures,
        "mutation_markers": mutation_markers,
        "command_failure_markers": failures,
        "passed": success,
    }


def identify_candidate_prefixes(
    flash_path: Path,
    candidates_root: Path,
) -> list[dict[str, object]]:
    flash = flash_path.read_bytes()
    matches: list[dict[str, object]] = []
    if not candidates_root.is_dir():
        return matches
    for candidate in sorted(candidates_root.glob("*/firmware.bin")):
        value = candidate.read_bytes()
        if value and len(value) <= len(flash) and flash[: len(value)] == value:
            matches.append(
                {
                    "candidate": candidate.parent.name,
                    "path": str(candidate.resolve()),
                    "bytes": len(value),
                    "sha256": sha256_bytes(value),
                }
            )
    return matches


def validate_partial(path: Path, expected_bytes: int, noun: str) -> None:
    if not path.is_file() or path.stat().st_size != expected_bytes:
        actual = path.stat().st_size if path.is_file() else None
        raise SystemExit(
            f"{noun} capture has {actual} bytes, expected {expected_bytes}"
        )


def run_commander(
    executable: str,
    serial: str,
    speed_khz: int,
    paths: dict[str, Path],
    commander: Path,
    raw: Path,
    timeout_seconds: float,
    *,
    development_reset_attach: bool = False,
    require_capture: bool = True,
) -> dict[str, object]:
    command = [
        executable,
        "-device",
        FORENSIC_DEVICE,
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
        "-JLinkScriptFile",
        str(paths["jlink_script"]),
        "-CommanderScript",
        str(commander),
    ]
    timed_out = False
    interrupted = False
    launch_error = None
    termination_error = None
    process = None
    returncode = None
    with raw.open("x", encoding="utf-8") as output:
        try:
            process = subprocess.Popen(
                command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
            )
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        except KeyboardInterrupt:
            interrupted = True
        except OSError as error:
            launch_error = str(error)
        finally:
            if process is not None and process.poll() is None:
                # A second Ctrl-C must not bypass reaping and overlap cleanup.
                previous_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    process.kill()
                    returncode = process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired) as error:
                    termination_error = str(error)
                finally:
                    signal.signal(signal.SIGINT, previous_sigint)
        output.flush()
        os.fsync(output.fileno())
    metadata = transcript_metadata(
        raw.read_text(encoding="utf-8", errors="replace"),
        returncode,
        development_reset_attach=development_reset_attach,
        require_capture=require_capture,
    )
    terminated = process is not None and process.poll() is not None
    metadata.update(
        timed_out=timed_out, interrupted=interrupted,
        timeout_seconds=timeout_seconds, launch_error=launch_error,
        process_terminated=terminated, termination_error=termination_error,
    )
    metadata["passed"] = bool(metadata["passed"] and terminated
                              and not timed_out and not interrupted)
    return metadata


def run_attempt(
    executable: str,
    serial: str,
    speed_khz: int,
    paths: dict[str, Path],
    prefix: Path,
    number: int,
    development_reset_attach: bool,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    cleanup_timeout_seconds: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS,
) -> tuple[Path, dict[str, object]]:
    raw = attempt_path(prefix, number)
    metadata = run_commander(
        executable, serial, speed_khz, paths, paths["commander"], raw,
        timeout_seconds, development_reset_attach=development_reset_attach,
    )
    cleanup_needed = metadata["timed_out"] or metadata["interrupted"] or (
        (metadata["cortex_m4_identified"] or metadata["halt_command_seen"])
        and not metadata["resume_command_seen"]
    )
    if cleanup_needed and metadata["process_terminated"]:
        cleanup_raw = raw.with_name(raw.stem + "_cleanup.txt")
        # Only the terminated session's cleanup may reconnect, once, to resume.
        write_exclusive(paths["resume_commander"], "connect\ng\nexit\n")
        cleanup = run_commander(
            executable, serial, speed_khz, paths, paths["resume_commander"],
            cleanup_raw, cleanup_timeout_seconds, require_capture=False,
        )
        metadata["cleanup"] = {"raw": file_record(cleanup_raw, private=True), **cleanup}
    return raw, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--jlink-serial", default=EXPECTED_JLINK_SERIAL)
    parser.add_argument("--speed-khz", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--retry-interval-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--cleanup-timeout-seconds", type=float,
                        default=DEFAULT_CLEANUP_TIMEOUT_SECONDS)
    parser.add_argument("--prior-attempt", type=Path, action="append", default=[])
    parser.add_argument(
        "--development-reset-attach",
        action="store_true",
        help=(
            "authorize connect-under-reset for the development board; the "
            "capture stays read-only and erase/program/unlock remains fatal"
        ),
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if args.jlink_serial != EXPECTED_JLINK_SERIAL:
        raise SystemExit("refusing target access: unrecognized J-Link serial")
    if not 1 <= args.speed_khz <= 4000:
        parser.error("--speed-khz must be between 1 and 4000")
    if not 1 <= args.max_attempts <= 1000:
        parser.error("--max-attempts must be between 1 and 1000")
    if not 0.1 <= args.retry_interval_seconds <= 60:
        parser.error("--retry-interval-seconds must be between 0.1 and 60")
    if not 0.1 <= args.timeout_seconds <= 300:
        parser.error("--timeout-seconds must be between 0.1 and 300")
    if not 0.1 <= args.cleanup_timeout_seconds <= 60:
        parser.error("--cleanup-timeout-seconds must be between 0.1 and 60")
    missing_prior = [str(path) for path in args.prior_attempt if not path.is_file()]
    if missing_prior:
        raise SystemExit("prior attempt transcript is missing: " + ", ".join(missing_prior))

    prefix = args.prefix.resolve()
    paths = artifact_paths(prefix)
    require_create_once(prefix, paths)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "jlink_serial": args.jlink_serial,
                    "speed_khz": args.speed_khz,
                    "max_attempts": args.max_attempts,
                    "timeout_seconds": args.timeout_seconds,
                    "cleanup_timeout_seconds": args.cleanup_timeout_seconds,
                    "reset_retries_inhibition_requested": True,
                    "development_reset_attach_authorized": (
                        args.development_reset_attach
                    ),
                    "artifacts": {key: str(value) for key, value in paths.items()},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    executable = shutil.which("JLinkExe")
    if executable is None:
        raise SystemExit("JLinkExe not found")

    paths["commander"].parent.mkdir(parents=True, exist_ok=True)
    write_exclusive(paths["jlink_script"], build_jlink_script())
    write_exclusive(paths["commander"], build_commander_script(paths))
    attempts: list[dict[str, object]] = []
    try:
        manifest = capture_baseline(args, executable, prefix, paths, attempts)
    except (SystemExit, OSError) as error:
        atomic_manifest(paths["failure"], {
            "schema": "stratolink.board1_baseline_failure.v1",
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "passed": False,
            "error": str(error),
            "attempts": attempts,
            "artifacts": {
                key: file_record(path, private=True)
                for key, path in paths.items()
                if key not in ("manifest", "failure") and path.is_file()
            },
            "partial_artifacts": {
                key: file_record(path.with_suffix(".bin.partial"), private=True)
                for key, path in paths.items()
                if key in ("ram", "flash_optr", "flash")
                and path.with_suffix(".bin.partial").is_file()
            },
        })
        raise SystemExit(f"{error}; failure evidence: {paths['failure']}") from error
    print(json.dumps(manifest, indent=2, sort_keys=True))


def capture_baseline(
    args: argparse.Namespace,
    executable: str,
    prefix: Path,
    paths: dict[str, Path],
    attempts: list[dict[str, object]],
) -> dict[str, object]:
    successful_raw: Path | None = None
    successful_transport: dict[str, object] | None = None
    for number in range(1, args.max_attempts + 1):
        raw, transport = run_attempt(
            executable,
            args.jlink_serial,
            args.speed_khz,
            paths,
            prefix,
            number,
            args.development_reset_attach,
            args.timeout_seconds,
            args.cleanup_timeout_seconds,
        )
        attempts.append({"raw": file_record(raw, private=True), **transport})
        if transport["passed"]:
            successful_raw = raw
            successful_transport = transport
            break
        # Retry only a failed initial attach, never an uncertain/partial capture.
        if (transport["timed_out"] or transport["interrupted"]
                or not transport["process_terminated"]
                or transport["cortex_m4_identified"]
                or transport["halt_command_seen"] or transport["mutation_markers"]
                or transport["reset_markers"]
                or transport["launch_error"]
                or any(paths[key].with_suffix(".bin.partial").exists()
                       for key in ("ram", "flash_optr", "flash"))):
            break
        if number < args.max_attempts:
            time.sleep(args.retry_interval_seconds)
    if successful_raw is None or successful_transport is None:
        raise SystemExit(
            "no authorized target attachment succeeded; failed transcripts "
            f"preserved under {prefix.parent}"
        )

    partials = {
        "ram": paths["ram"].with_suffix(".bin.partial"),
        "flash_optr": paths["flash_optr"].with_suffix(".bin.partial"),
        "flash": paths["flash"].with_suffix(".bin.partial"),
    }
    validate_partial(partials["ram"], RAM_BYTES, "RAM")
    validate_partial(partials["flash_optr"], FLASH_OPTR_BYTES, "FLASH OPTR")
    validate_partial(partials["flash"], FLASH_BYTES, "flash")

    memory = parse_memory(successful_raw)
    tamp = read_bytes(memory, TAMP_ADDRESS, TAMP_BYTES, "TAMP")
    flash = partials["flash"].read_bytes()
    reserved_offset = RESERVED_ADDRESS - FLASH_ADDRESS
    reserved = flash[reserved_offset : reserved_offset + RESERVED_BYTES]
    if len(reserved) != RESERVED_BYTES:
        raise SystemExit("full-flash capture does not contain the reserved page")

    for noun in ("ram", "flash_optr", "flash"):
        commit_partial_create_once(partials[noun], paths[noun], noun)
    write_bytes_exclusive(paths["tamp"], tamp)
    write_bytes_exclusive(paths["reserved"], reserved)

    optr = int.from_bytes(paths["flash_optr"].read_bytes(), byteorder="little")
    manifest = {
        "schema": "stratolink.board1_baseline.v2",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "payload": "stratolink-1",
        "scope": (
            "first successful target-access baseline after operator-applied bench "
            "power and earlier failed non-programming attach attempts"
        ),
        "target": {
            "device": FORENSIC_DEVICE,
            "silicon_target": "STM32WLE5CC",
            "interface": "SWD",
            "speed_khz": args.speed_khz,
            "jlink_serial": args.jlink_serial,
            "reset_retries_inhibition_requested": True,
            "development_reset_attach_authorized": args.development_reset_attach,
            "temporally_perturbed_by_debug_attach": True,
            **successful_transport,
        },
        "attempts": attempts,
        "prior_attempts": [file_record(path, private=True) for path in args.prior_attempt],
        "artifacts": {
            "flash": file_record(paths["flash"], private=True),
            "ram": file_record(paths["ram"], private=True),
            "tamp": file_record(paths["tamp"], private=True),
            "flash_optr": file_record(paths["flash_optr"]),
            "reserved_page": file_record(paths["reserved"], private=True),
            "commander_script": file_record(paths["commander"]),
            "jlink_script": file_record(paths["jlink_script"]),
            "successful_raw_transcript": file_record(successful_raw, private=True),
        },
        "flash_option_register": {
            "address": f"0x{FLASH_OPTR_ADDRESS:08X}",
            "value": f"0x{optr:08X}",
            "iwdg_runs_in_stop": bool(optr & FLASH_OPTR_IWDG_STOP),
        },
        "opaque_reserved_page": {
            "address": f"0x{RESERVED_ADDRESS:08X}",
            "bytes": RESERVED_BYTES,
            "sha256": sha256_bytes(reserved),
            "interpretation": "defer until captured firmware image is identified",
        },
        "known_candidate_prefix_matches": identify_candidate_prefixes(
            paths["flash"], ROOT / "firmware/.pio/flight_candidates"
        ),
        "notes": [
            (
                "Connect-under-reset was explicitly authorized for this development capture."
                if args.development_reset_attach
                else "No reset transcript marker was accepted."
            ),
            "No unlock, erase, or programming transcript marker was accepted.",
            "Reset-inhibition settings are requests, not guarantees against reset.",
            "An explicit g command completed without reported error; application resumption is not independently verified.",
            "RAM/TAMP are temporally perturbed by debugger attachment and are not uninterrupted-runtime evidence.",
            "Private artifacts can contain device/session material and remain in ignored local evidence.",
        ],
    }
    atomic_manifest(paths["manifest"], manifest)
    return manifest


if __name__ == "__main__":
    main()
