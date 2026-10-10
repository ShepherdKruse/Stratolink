#!/usr/bin/env python3
"""Provision one create-once retained launch authority on StratoLink-1.

This is a two-process operation. The first J-Link process is read-only: it
recovers safely if attachment occurred under reset, runs startup for five
seconds, and captures all 80 TAMP bytes. Python decodes BKP18 and refuses to
continue when it already contains any structurally valid legacy or v2
authority. A unique evidence prefix therefore cannot bypass device-level
create-once semantics.

Only after that gate passes is a second Commander script created and run. It
first verifies the complete pre-read TAMP image against the still-live target,
closing the gap between the two processes, and then issues exactly one w4 to
BKP18. The halted after-image and mem32 readback must match before reset/run.

The explicit --development-rearm-expired-us915 option permits manual bench
reauthorization only on probe 802007563: an existing v2 US915 LAUNCH record
must have age >= 1800 seconds. Fresh LAUNCH, GNSS, legacy, and other-region
authorities remain protected. This is not a launch safety bypass or automatic
firmware renewal; the operator must know this bench is physically in US915.
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
TAMP_ADDRESS = 0x4000B100
TAMP_BYTES = 80
BKP18_ADDRESS = 0x4000B148
BKP18_OFFSET = BKP18_ADDRESS - TAMP_ADDRESS
TAMP_LEASE_AGE_MASK = 0x7FF
TAMP_LEASE_MAGIC = 0x2D3
TAMP_REGION_LEASE_MAGIC = 0x16D
TAMP_REGION_LEASE_PAYLOAD_MASK = 0x3FFF
TAMP_REGION_AUTHORITY_GNSS = 0
TAMP_REGION_AUTHORITY_LAUNCH = 1
STARTUP_RECOVERY_MS = 5000
DEVELOPMENT_US915_SERIAL = "802007563"
DEVELOPMENT_AUTHORITY_EXPIRY_SEC = 1800
REGIONS = {
    "us915": 0,
    "eu868": 1,
    "as923": 2,
    "au915": 3,
}
REGION_NAMES = {value: key for key, value in REGIONS.items()}
SERIAL = re.compile(r"^[1-9][0-9]{5,19}$")
CONNECT_UNDER_RESET_MARKER = "can not attach to cpu. trying connect under reset."

FAILURE_MARKERS = (
    "cannot connect",
    "could not connect",
    "cannot halt",
    "could not halt",
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
    "erase all flash",
    "programming flash",
    "flash download",
    "downloading file",
    "unlock device",
    "unlocking device",
    "device will be unlocked",
    "unsecure device",
    "unsecuring device",
    "device will be unsecured",
)
FORBIDDEN_COMMANDS = (
    "erase",
    "loadfile",
    "loadbin",
    "program",
    "flash",
    "unlock",
    "unsecure",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, private: bool = False) -> dict[str, object]:
    record: dict[str, object] = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if private:
        record["private"] = True
    return record


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


def tamp_region_lease_crc8(payload: int) -> int:
    """Match tamp_region_lease_crc8() in firmware/include/tamp_record.h."""
    if not 0 <= payload <= TAMP_REGION_LEASE_PAYLOAD_MASK:
        raise ValueError("TAMP v2 payload is not 14 bits")
    crc = 0xA5
    for byte_index in range(2):
        crc ^= (payload >> (8 * byte_index)) & 0xFF
        for _ in range(8):
            crc = (
                ((crc << 1) ^ 0x07) & 0xFF
                if crc & 0x80
                else (crc << 1) & 0xFF
            )
    return crc


def encode_launch_authority(region_id: int) -> int:
    if region_id not in REGIONS.values():
        raise ValueError("region ID must be 0..3")
    payload = (region_id << 11) | (TAMP_REGION_AUTHORITY_LAUNCH << 13)
    return (
        (TAMP_REGION_LEASE_MAGIC << 22)
        | (tamp_region_lease_crc8(payload) << 14)
        | payload
    )


def decode_valid_authority(record: int) -> dict[str, object] | None:
    """Decode valid legacy/v2 records; return None for blank or corrupt data."""
    magic = record >> 22
    if magic == TAMP_REGION_LEASE_MAGIC:
        payload = record & TAMP_REGION_LEASE_PAYLOAD_MASK
        stored_crc = (record >> 14) & 0xFF
        if stored_crc != tamp_region_lease_crc8(payload):
            return None
        region_id = (payload >> 11) & 0x03
        source_id = (payload >> 13) & 0x01
        return {
            "format": "v2",
            "exact_region": True,
            "age_sec": payload & TAMP_LEASE_AGE_MASK,
            "region_id": region_id,
            "region": REGION_NAMES[region_id],
            "source_id": source_id,
            "source": "GNSS" if source_id == TAMP_REGION_AUTHORITY_GNSS else "LAUNCH",
        }
    if magic == TAMP_LEASE_MAGIC:
        age_sec = record & TAMP_LEASE_AGE_MASK
        check = (record >> 11) & TAMP_LEASE_AGE_MASK
        if check != ((~age_sec) & TAMP_LEASE_AGE_MASK):
            return None
        return {
            "format": "legacy",
            "exact_region": False,
            "age_sec": age_sec,
            "region_id": None,
            "region": None,
            "source_id": TAMP_REGION_AUTHORITY_GNSS,
            "source": "GNSS",
        }
    return None


def artifact_paths(prefix: Path) -> dict[str, Path]:
    return {
        "tamp_before": prefix.with_name(prefix.name + "_tamp_before.bin"),
        "tamp_after": prefix.with_name(prefix.name + "_tamp_after.bin"),
        "preflight_script": prefix.with_name(
            prefix.name + "_launch_authority_preflight.jlink"
        ),
        "preflight_raw": prefix.with_name(
            prefix.name + "_launch_authority_preflight_raw.txt"
        ),
        "write_script": prefix.with_name(
            prefix.name + "_launch_authority_write.jlink"
        ),
        "write_raw": prefix.with_name(
            prefix.name + "_launch_authority_write_raw.txt"
        ),
        "manifest": prefix.with_name(prefix.name + "_launch_authority_manifest.json"),
    }


def partial_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".partial")


def require_create_once(paths: dict[str, Path]) -> None:
    collisions: list[str] = []
    for path in paths.values():
        for candidate in (path, partial_path(path)):
            if candidate.exists():
                collisions.append(str(candidate))
    if collisions:
        raise SystemExit(
            "refusing to overwrite Board1 launch-authority evidence: "
            + ", ".join(collisions)
        )


def jlink_path(path: Path) -> str:
    value = str(path.resolve())
    if any(character in value for character in ('"', "\r", "\n")):
        raise SystemExit(f"J-Link path contains an unsupported character: {value!r}")
    return f'"{value}"'


def build_preflight_script(paths: dict[str, Path]) -> str:
    """Recover initialized state after a possible connect-under-reset attach."""
    commands = [
        "connect",
        "h",
        "g",
        f"sleep {STARTUP_RECOVERY_MS}",
        "h",
        (
            f"savebin {jlink_path(partial_path(paths['tamp_before']))} "
            f"0x{TAMP_ADDRESS:08X} 0x{TAMP_BYTES:08X}"
        ),
        f"mem32 0x{BKP18_ADDRESS:08X} 1",
        "g",
        "exit",
        "",
    ]
    return "\n".join(commands)


def build_write_script(paths: dict[str, Path], record: int) -> str:
    """Verify the pre-read image before the sole target write."""
    commands = [
        "connect",
        "h",
        f"verifybin {jlink_path(paths['tamp_before'])} 0x{TAMP_ADDRESS:08X}",
        f"w4 0x{BKP18_ADDRESS:08X} 0x{record:08X}",
        f"mem32 0x{BKP18_ADDRESS:08X} 1",
        (
            f"savebin {jlink_path(partial_path(paths['tamp_after']))} "
            f"0x{TAMP_ADDRESS:08X} 0x{TAMP_BYTES:08X}"
        ),
        "r",
        "g",
        "exit",
        "",
    ]
    return "\n".join(commands)


def commander_commands(transcript: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"(?im)^\s*J-Link>\s*(\S.*)$", transcript)
    ]


def command_name(command: str) -> str:
    return command.split(maxsplit=1)[0].lower() if command else ""


def common_transport_checks(
    transcript: str,
    returncode: int,
    expected_serial: str,
) -> tuple[list[str], list[str], list[str], list[str], dict[str, object]]:
    lowered = transcript.lower()
    commands = commander_commands(transcript)
    names = [command_name(command) for command in commands]
    forbidden_commands = [
        command
        for command in commands
        if command_name(command) in FORBIDDEN_COMMANDS
    ]
    forbidden_markers = [
        marker for marker in FORBIDDEN_MUTATION_MARKERS if marker in lowered
    ]
    failure_markers = [marker for marker in FAILURE_MARKERS if marker in lowered]
    selected_device_seen = f'device "{TARGET_DEVICE.lower()}" selected.' in lowered
    serial_seen = (
        re.search(
            rf"(?im)^\s*S/N:\s*{re.escape(expected_serial)}\s*$",
            transcript,
        )
        is not None
    )
    required_failures: list[str] = []
    if not selected_device_seen:
        required_failures.append(f"{TARGET_DEVICE} selection missing")
    if not serial_seen:
        required_failures.append("requested J-Link serial was not observed")
    if "cortex-m4 identified." not in lowered:
        required_failures.append("Cortex-M4 identification missing")
    if "script processing completed." not in lowered:
        required_failures.append("script completion missing")
    facts: dict[str, object] = {
        "returncode": returncode,
        "selected_device_seen": selected_device_seen,
        "requested_serial_seen": serial_seen,
        "cortex_m4_seen": "cortex-m4 identified." in lowered,
        "script_completion_seen": "script processing completed." in lowered,
        "connected_under_reset": CONNECT_UNDER_RESET_MARKER in lowered,
        "commander_command_count": len(commands),
    }
    return commands, names, failure_markers, required_failures, {
        **facts,
        "forbidden_commands": forbidden_commands,
        "forbidden_mutation_markers": sorted(set(forbidden_markers)),
    }


def bkp18_readbacks(transcript: str) -> list[int]:
    return [
        int(match.group(1), 16)
        for match in re.finditer(
            rf"(?im)^\s*(?:0x)?{BKP18_ADDRESS:08x}\s*[:=]\s*"
            r"(?:0x)?([0-9a-f]{8})\b",
            transcript,
        )
    ]


def classify_preflight_transcript(
    transcript: str,
    returncode: int,
    *,
    expected_serial: str,
    expected_before_word: int | None = None,
) -> dict[str, object]:
    commands, names, failure_markers, required_failures, facts = (
        common_transport_checks(transcript, returncode, expected_serial)
    )
    writes = [
        command
        for command in commands
        if re.fullmatch(r"w(?:1|2|4|8)", command_name(command))
    ]
    expected_prefix = ["connect", "h", "g", f"sleep {STARTUP_RECOVERY_MS}", "h"]
    normalized_prefix = [
        re.sub(r"\s+", " ", command.strip().lower())
        for command in commands[: len(expected_prefix)]
    ]
    if normalized_prefix != expected_prefix:
        required_failures.append("safe connect-under-reset startup recovery missing")
    if f"sleep({STARTUP_RECOVERY_MS})" not in transcript.lower():
        required_failures.append("startup recovery interval was not completed")
    for name, expected_count in (
        ("connect", 1),
        ("h", 2),
        ("g", 2),
        ("sleep", 1),
        ("savebin", 1),
        ("mem32", 1),
        ("exit", 1),
    ):
        if names.count(name) != expected_count:
            required_failures.append(
                f"expected exactly {expected_count} {name} command(s)"
            )
    if writes:
        required_failures.append("read-only preflight contained a write command")
    readbacks = bkp18_readbacks(transcript)
    if len(readbacks) != 1:
        required_failures.append("preflight did not produce one BKP18 readback")
    elif expected_before_word is not None and readbacks[0] != expected_before_word:
        required_failures.append("preflight BKP18 transcript/file mismatch")

    forbidden_commands = facts["forbidden_commands"]
    forbidden_markers = facts["forbidden_mutation_markers"]
    passed = bool(
        returncode == 0
        and not failure_markers
        and not forbidden_commands
        and not forbidden_markers
        and not required_failures
    )
    return {
        **facts,
        "phase": "read_only_preflight",
        "write_command_count": len(writes),
        "savebin_command_count": names.count("savebin"),
        "readback_values": [f"0x{value:08X}" for value in readbacks],
        "startup_recovery_ms": STARTUP_RECOVERY_MS,
        "startup_recovery_proved": not any(
            "startup recovery" in failure for failure in required_failures
        ),
        "failure_markers": sorted(set(failure_markers)),
        "required_failures": required_failures,
        "passed": passed,
    }


def classify_write_transcript(
    transcript: str,
    returncode: int,
    *,
    expected_serial: str,
    expected_record: int,
) -> dict[str, object]:
    commands, names, failure_markers, required_failures, facts = (
        common_transport_checks(transcript, returncode, expected_serial)
    )
    write_commands = [
        command
        for command in commands
        if re.fullmatch(r"w(?:1|2|4|8)", command_name(command))
    ]
    expected_write = f"w4 0x{BKP18_ADDRESS:08x} 0x{expected_record:08x}"
    normalized_writes = [
        re.sub(r"\s+", " ", command.strip().lower())
        for command in write_commands
    ]
    for name, expected_count in (
        ("connect", 1),
        ("h", 1),
        ("verifybin", 1),
        ("mem32", 1),
        ("savebin", 1),
        ("r", 1),
        ("g", 1),
        ("exit", 1),
    ):
        if names.count(name) != expected_count:
            required_failures.append(
                f"expected exactly {expected_count} {name} command(s)"
            )
    if normalized_writes != [expected_write]:
        required_failures.append("exactly one expected BKP18 w4 was not observed")
    if transcript.lower().count("verify successful") != 1:
        required_failures.append("complete pre-read TAMP verification did not succeed")
    readbacks = bkp18_readbacks(transcript)
    if readbacks != [expected_record]:
        required_failures.append("exact BKP18 mem32 readback was not observed")

    forbidden_commands = facts["forbidden_commands"]
    forbidden_markers = facts["forbidden_mutation_markers"]
    passed = bool(
        returncode == 0
        and not failure_markers
        and not forbidden_commands
        and not forbidden_markers
        and not required_failures
    )
    return {
        **facts,
        "phase": "bounded_write",
        "write_command_count": len(write_commands),
        "verifybin_command_count": names.count("verifybin"),
        "savebin_command_count": names.count("savebin"),
        "readback_values": [f"0x{value:08X}" for value in readbacks],
        "explicit_reset_seen": names.count("r") == 1,
        "run_seen": names.count("g") == 1,
        "failure_markers": sorted(set(failure_markers)),
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


def commit_tamp_capture(
    path: Path,
    noun: str,
    failures: list[str],
) -> bytes | None:
    partial = partial_path(path)
    if not partial.is_file():
        failures.append(f"{noun} is missing")
        return None
    size = partial.stat().st_size
    if size != TAMP_BYTES:
        failures.append(f"{noun} has {size} bytes, expected {TAMP_BYTES}")
        return None
    commit_partial_create_once(partial, path, noun)
    return path.read_bytes()


def manifest_artifact(path: Path, *, private: bool = False) -> dict[str, object] | None:
    return file_record(path, private=private) if path.is_file() else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--region", choices=tuple(REGIONS), required=True)
    parser.add_argument("--jlink-serial", required=True)
    parser.add_argument("--speed-khz", type=int, default=100)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--development-rearm-expired-us915",
        action="store_true",
        help=(
            "manually reauthorize an expired (age >= 1800 s) v2 US915 LAUNCH "
            "record on bench probe 802007563; not automatic firmware renewal "
            "or a launch safety bypass"
        ),
    )
    args = parser.parse_args()

    if not SERIAL.fullmatch(args.jlink_serial):
        raise SystemExit("--jlink-serial must be one exact numeric probe serial")
    if not 1 <= args.speed_khz <= 4000:
        parser.error("--speed-khz must be between 1 and 4000")
    if args.development_rearm_expired_us915 and (
        args.region != "us915" or args.jlink_serial != DEVELOPMENT_US915_SERIAL
    ):
        parser.error(
            "--development-rearm-expired-us915 requires --region us915 "
            f"and --jlink-serial {DEVELOPMENT_US915_SERIAL}"
        )

    state_gate_rule = (
        "development bench opt-in: allow only an expired v2 US915 LAUNCH "
        "authority (age >= 1800 seconds) or the existing blank/corrupt path; "
        "reject fresh LAUNCH, GNSS, legacy, and all other-region authorities"
        if args.development_rearm_expired_us915 else
        "reject every valid legacy lease, v2 GNSS authority, and v2 "
        "LAUNCH authority regardless of age or requested prefix"
    )

    region_id = REGIONS[args.region]
    record = encode_launch_authority(region_id)
    paths = artifact_paths(args.prefix.resolve())
    require_create_once(paths)
    if args.check_only:
        print(
            json.dumps(
                {
                    "ready": True,
                    "region": args.region,
                    "region_id": region_id,
                    "source": "LAUNCH",
                    "age_sec": 0,
                    "record": f"0x{record:08X}",
                    "development_rearm_expired_us915": args.development_rearm_expired_us915,
                    "device_state_gate": state_gate_rule,
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

    executable = shutil.which("JLinkExe")
    if executable is None:
        raise SystemExit("JLinkExe not found; no target access occurred")

    paths["preflight_script"].parent.mkdir(parents=True, exist_ok=True)
    write_exclusive(paths["preflight_script"], build_preflight_script(paths))
    preflight_result = run_jlink(
        executable,
        args.jlink_serial,
        args.speed_khz,
        paths["preflight_script"],
    )
    write_exclusive(paths["preflight_raw"], preflight_result.stdout)

    failures: list[str] = []
    before = commit_tamp_capture(
        paths["tamp_before"], "pre-write TAMP capture", failures
    )
    before_word: int | None = None
    existing_authority: dict[str, object] | None = None
    if before is not None:
        before_word = int.from_bytes(
            before[BKP18_OFFSET : BKP18_OFFSET + 4], "little"
        )
        existing_authority = decode_valid_authority(before_word)
    preflight_transport = classify_preflight_transcript(
        preflight_result.stdout,
        preflight_result.returncode,
        expected_serial=args.jlink_serial,
        expected_before_word=before_word,
    )
    if not preflight_transport["passed"]:
        failures.append("read-only J-Link preflight did not pass")
    development_rearm_eligible = bool(
        args.development_rearm_expired_us915
        and existing_authority is not None
        and existing_authority["format"] == "v2"
        and existing_authority["source_id"] == TAMP_REGION_AUTHORITY_LAUNCH
        and existing_authority["region_id"] == REGIONS["us915"]
        and existing_authority["age_sec"] >= DEVELOPMENT_AUTHORITY_EXPIRY_SEC
    )
    state_gate_passed = before is not None and (
        existing_authority is None or development_rearm_eligible
    )
    if existing_authority is not None and not development_rearm_eligible:
        failures.append(
            "BKP18 already contains a valid retained authority; refusing overwrite"
        )
    elif before is None:
        failures.append("BKP18 state gate could not inspect the retained record")

    write_attempted = bool(preflight_transport["passed"] and state_gate_passed)
    write_transport: dict[str, object] | None = None
    after: bytes | None = None
    after_word: int | None = None
    exact_word_verified = False
    only_bkp18_changed = False
    if write_attempted:
        write_exclusive(paths["write_script"], build_write_script(paths, record))
        write_result = run_jlink(
            executable,
            args.jlink_serial,
            args.speed_khz,
            paths["write_script"],
        )
        write_exclusive(paths["write_raw"], write_result.stdout)
        write_transport = classify_write_transcript(
            write_result.stdout,
            write_result.returncode,
            expected_serial=args.jlink_serial,
            expected_record=record,
        )
        if not write_transport["passed"]:
            failures.append("J-Link transcript did not prove the bounded TAMP write")
        after = commit_tamp_capture(
            paths["tamp_after"], "post-write TAMP capture", failures
        )
        if after is not None:
            after_word = int.from_bytes(
                after[BKP18_OFFSET : BKP18_OFFSET + 4], "little"
            )
            exact_word_verified = after_word == record
            if not exact_word_verified:
                failures.append(
                    "post-write BKP18 does not equal the requested v2 record"
                )
        if before is not None and after is not None:
            before_other = before[:BKP18_OFFSET] + before[BKP18_OFFSET + 4 :]
            after_other = after[:BKP18_OFFSET] + after[BKP18_OFFSET + 4 :]
            only_bkp18_changed = before_other == after_other
            if not only_bkp18_changed:
                failures.append(
                    "a TAMP byte outside BKP18 changed while the CPU was halted"
                )

    passed = bool(
        write_attempted
        and write_transport is not None
        and write_transport["passed"]
        and exact_word_verified
        and only_bkp18_changed
        and not failures
    )
    manifest = {
        "schema": "stratolink.board1_launch_authority.v2",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "payload": "stratolink-1",
        "passed": passed,
        "development_rearm_expired_us915": args.development_rearm_expired_us915,
        "scope": (
            "explicit development bench US915 reauthorization; one BKP18 w4 "
            "only after the expired-LAUNCH state gate and exact TAMP "
            "time-of-check verification; no program, flash, erase, or unlock"
            if args.development_rearm_expired_us915 else
            "device-state-gated write-once retained launch authority; one BKP18 "
            "w4 only after a valid-authority rejection gate and exact TAMP "
            "time-of-check verification; no program, flash, erase, or unlock"
        ),
        "target": {
            "device": TARGET_DEVICE,
            "interface": "SWD",
            "speed_khz": args.speed_khz,
            "jlink_serial": args.jlink_serial,
        },
        "authority": {
            "region": args.region,
            "region_id": region_id,
            "source": "LAUNCH",
            "source_id": TAMP_REGION_AUTHORITY_LAUNCH,
            "age_sec": 0,
            "format": "tamp_region_lease_v2",
            "magic": f"0x{TAMP_REGION_LEASE_MAGIC:03X}",
            "record": f"0x{record:08X}",
            "crc8": f"0x{(record >> 14) & 0xFF:02X}",
        },
        "state_gate": {
            "passed": state_gate_passed,
            "before_word": (
                f"0x{before_word:08X}" if before_word is not None else None
            ),
            "existing_valid_authority": existing_authority,
            "development_rearm_eligible": development_rearm_eligible,
            "rule": state_gate_rule,
            "write_attempted": write_attempted,
        },
        "verification": {
            "bkp18_address": f"0x{BKP18_ADDRESS:08X}",
            "after_word": (
                f"0x{after_word:08X}" if after_word is not None else None
            ),
            "exact_word_verified": exact_word_verified,
            "all_other_tamp_bytes_unchanged": only_bkp18_changed,
            "pre_read_image_verified_immediately_before_write": bool(
                write_transport is not None and write_transport["passed"]
            ),
            "reset_and_run_issued": bool(
                write_transport is not None
                and write_transport["explicit_reset_seen"]
                and write_transport["run_seen"]
            ),
        },
        "transport": {
            "preflight": preflight_transport,
            "write": write_transport,
        },
        "artifacts": {
            "preflight_script": manifest_artifact(paths["preflight_script"]),
            "preflight_raw": manifest_artifact(paths["preflight_raw"], private=True),
            "tamp_before": manifest_artifact(paths["tamp_before"], private=True),
            "write_script": manifest_artifact(paths["write_script"]),
            "write_raw": manifest_artifact(paths["write_raw"], private=True),
            "tamp_after": manifest_artifact(paths["tamp_after"], private=True),
        },
        "failures": failures,
    }
    atomic_manifest(paths["manifest"], manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
