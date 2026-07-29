#!/usr/bin/env python3
"""Decode J-Link flight-health/TAMP reads without exposing retained keys."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import zlib


HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "generated/stratolink_flight_hil_manifest.json"
TAMP_WORDS = 20
SESSION_MAGIC = 0x53545241
SESSION_VERSION = 3
SESSION_CRC_WORD = 15
LEASE_MAGIC = 0x2D3
BOOT_MAGIC = 0xB4
COMMAND_STATE_TAG = 0xD7
REGIONS = {
    0: "US915",
    1: "EU868",
    2: "AS923",
    3: "AU915",
    4: "SILENT",
}
MEMORY_LINE = re.compile(
    r"^\s*([0-9A-Fa-f]{8})\s*=\s*"
    r"((?:[0-9A-Fa-f]{2}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{8})"
    r"(?:\s+(?:[0-9A-Fa-f]{2}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{8}))*)\s*$"
)


def parse_memory(path: Path) -> dict[int, int]:
    memory: dict[int, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = MEMORY_LINE.match(line)
        if not match:
            continue
        address = int(match.group(1), 16)
        for token in match.group(2).split():
            width = len(token) // 2
            value = int(token, 16)
            encoded = value.to_bytes(width, "little")
            for byte in encoded:
                if address in memory and memory[address] != byte:
                    raise SystemExit(
                        f"{path}: conflicting memory output at 0x{address:08X}"
                    )
                memory[address] = byte
                address += 1
    if not memory:
        raise SystemExit(f"{path}: no J-Link memory lines found")
    return memory


def read_bytes(memory: dict[int, int], address: int, size: int, label: str) -> bytes:
    missing = [
        candidate
        for candidate in range(address, address + size)
        if candidate not in memory
    ]
    if missing:
        raise SystemExit(
            f"{label}: missing {len(missing)} bytes beginning at "
            f"0x{missing[0]:08X}"
        )
    return bytes(memory[candidate] for candidate in range(address, address + size))


def u8(data: bytes, offset: int = 0) -> int:
    return data[offset]


def u16(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def i16(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def i32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def u32s(data: bytes) -> list[int]:
    if len(data) % 4:
        raise ValueError("u32 array is not word-aligned")
    return list(struct.unpack("<" + "I" * (len(data) // 4), data))


def crc8(data: bytes) -> int:
    """CRC-8/ATM used by the retained command-state record."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def decode_health(manifest: dict, memory: dict[int, int]) -> dict:
    raw: dict[str, bytes] = {}
    for name, entry in manifest["symbols"].items():
        raw[name] = read_bytes(
            memory,
            int(entry["address"]),
            int(entry["size"]),
            name,
        )

    gps = u32s(raw["s_gps_diag"])
    command = raw["s_stats"]
    downlink = raw["s_dl_stats"]
    relay = raw["s_relay"]
    ctt = raw["s_ctt"]
    radio = raw["s_radio_diag"]
    microphone = u32s(raw["s_mic_diag"])
    fix = raw["last_gps_fix"]
    relay_health = {
        "rx_count": u32(relay, 0),
        "forwarded": u32(relay, 4),
        "deduplicated": u32(relay, 8),
        "hop_zero_drop": u32(relay, 12),
        "airtime_cap_skip": u32(relay, 16),
        "rx_arm_failures": u32(relay, 20),
        "last_from": u32(relay, 24),
        "last_rssi_dbm": i16(relay, 28),
    }
    # The corrected relay MAC appends diagnostics while preserving every
    # legacy offset above. This keeps the decoder compatible with precursor
    # snapshots and exposes contention/CAD evidence for the corrected image.
    if len(relay) >= 68:
        relay_health.update(
            {
                "queued": u32(relay, 32),
                "pending_duplicate": u32(relay, 36),
                "directed_next_hop_skip": u32(relay, 40),
                "queue_full": u32(relay, 44),
                "invalid_header": u32(relay, 48),
                "cad_busy": u32(relay, 52),
                "cad_error": u32(relay, 56),
                "tx_error": u32(relay, 60),
                "window_boundary_skip": u32(relay, 64),
            }
        )

    result = {
        "session": {
            "joined": bool(u8(raw["_joined"])),
            "region_id": u8(raw["REGION_ID"]),
            "region": REGIONS.get(u8(raw["REGION_ID"]), "INVALID"),
            "next_fcnt_up": u32(raw["fCntUp"]),
            "next_fcnt_down": u32(raw["fCntDown"]),
            "tx_fail_streak": u8(raw["tx_fail_streak"]),
            "join_retry_skip": u8(raw["join_retry_skip"]),
        },
        "boot": {
            "count": u32(raw["boot_count"]),
            "reset_cause_raw": f"0x{u32(raw['boot_reset_cause']):08X}",
            "reset_cause_code": u8(raw["s_boot_reset_code"]),
        },
        "region_lease": {
            "known": bool(u8(raw["region_known"])),
            "age_seconds": u32(raw["region_fix_age_sec"]),
            "trusted_provenance": (
                bool(u8(raw["region_lease_trusted"]))
                if "region_lease_trusted" in raw else None
            ),
        },
        "burst": {
            "active": bool(u8(raw["burst_mode"])),
            "cycles": u16(raw["burst_cycles"]),
            "cooldown": u8(raw["burst_cooldown"]),
        },
        "freefall_guard": {
            "spurious_wake_streak": u8(raw["spurious_ff_streak"]),
            "suppression_clean_wakes": u8(raw["ff_suppress_clean"]),
            "suppression_latched": bool(u8(raw["s_ff_suppressed"])),
            "wake_pending": bool(u8(raw["s_burst_wake"])),
        },
        "last_gps_fix": {
            "lat_e7": i32(fix, 0),
            "lon_e7": i32(fix, 4),
            "altitude_m": i32(fix, 8),
            "speed_cm_s": u16(fix, 12),
            "heading_cdeg": u16(fix, 14),
            "satellites": u8(fix, 16),
            "valid": bool(u8(fix, 17)),
        },
        "gps_diag": dict(
            zip(
                (
                    "begin_failures",
                    "dynamic_model_failures",
                    "backup_failures",
                    "hardware_resets",
                    "accepted_fixes",
                    "power_aborts",
                    "mission_aborts",
                    "no_fresh_cycles",
                    "backup_confirmations",
                    "backup_terminal_failures",
                    "rejected_value_fixes",
                    "dynamic_model_terminal_failures",
                ),
                gps,
            )
        ),
        "command": {
            "rx_count": u32(command, 0),
            "command_count": u32(command, 4),
            "last_opcode": u8(command, 8),
            "last_sequence": u8(command, 9),
            "last_fport": u8(command, 10),
            "last_length": u8(command, 11),
            "sequence_persist_failures": u32(command, 12)
            if len(command) >= 16 else None,
            "ack_valid": bool(u8(raw["s_have_seq"])),
            "ack_sequence": u8(raw["s_last_seq"])
            if bool(u8(raw["s_have_seq"])) else None,
            "relay_enabled": bool(u8(raw["s_relay_enabled"])),
        },
        "downlink": {
            "calls": u32(downlink, 0),
            "rx1_armed": u32(downlink, 4),
            "rx2_armed": u32(downlink, 8),
            "irq_count": u32(downlink, 12),
            "frame_count": u32(downlink, 16),
            "last_rx1_start_offset_ms": i32(downlink, 20),
            "last_rx2_start_offset_ms": i32(downlink, 24),
            "last_rx1_start_state": i16(downlink, 28),
            "last_rx2_start_state": i16(downlink, 30),
            "last_window": u8(downlink, 32),
            "last_length": u8(downlink, 33),
            "last_mhdr": u8(downlink, 34),
            "last_reject": u8(downlink, 35),
        },
        "meshtastic_relay": relay_health,
        "ctt": {
            "frames_rx": u32(ctt, 0),
            "crc_failures": u32(ctt, 4),
            "tags_seen": u32(ctt, 8),
            "windows": u32(ctt, 12),
            "rx_arm_failures": u32(ctt, 16),
            "last_id": u32(ctt, 20),
            "last_rssi_dbm": i16(ctt, 24),
            "pending_drop": u32(ctt, 28),
        },
        "radio_diag": {
            "begin_failures": u32(radio, 0),
            "config_failures": u32(radio, 4),
            "restore_attempts": u32(radio, 8),
            "restore_recovered": u32(radio, 12),
            "sleep_failures": u32(radio, 16),
            "last_error": i16(radio, 20),
            "allocation_failures": u16(radio, 22),
        },
        "acoustic_diag": dict(
            zip(
                (
                    "attempts",
                    "captures",
                    "capture_failures",
                    "events",
                    "last_variance_x16",
                    "noise_floor_x16",
                ),
                microphone,
            )
        ),
        "sensor_recovery": {
            "tmp117_reinit_attempts": u32(raw["s_tmp117_reinit_attempts"]),
            "ms5611_reinit_attempts": u32(raw["s_ms5611_reinit_attempts"]),
            "ltr390_reinit_attempts": u32(raw["s_ltr390_reinit_attempts"]),
            "ltr390_quiesce_failures": (
                u32(raw["s_ltr390_quiesce_failures"])
                if "s_ltr390_quiesce_failures" in raw else None
            ),
            "ltr390_soft_reset_recoveries": (
                u32(raw["s_ltr390_soft_reset_recoveries"])
                if "s_ltr390_soft_reset_recoveries" in raw else None
            ),
            "optical_quiet_retries": (
                u8(raw["s_optical_quiet_retries"])
                if "s_optical_quiet_retries" in raw else None
            ),
            "optical_quiescence_fault": (
                bool(u8(raw["s_optical_quiescence_fault"]))
                if "s_optical_quiescence_fault" in raw else None
            ),
            "lis2dh12_reconfig_attempts": u32(
                raw["s_lis2dh12_reconfig_attempts"]
            ),
            "i2c_bus_recoveries": (
                u32(raw["s_sensor_i2c_bus_recoveries"])
                if "s_sensor_i2c_bus_recoveries" in raw else None
            ),
        },
        "tmp117_sampling": {
            "direct_reads": u32(raw["s_tmp117_direct_reads"]),
            "fallback_reads": u32(raw["s_tmp117_fallback_reads"]),
            "rejected_poweron_sentinels": u32(
                raw["s_tmp117_poweron_sentinels"]
            ),
        },
        "b2b_queues": {
            "origin_id_ready": bool(u8(raw["s_b2b_origin_id_ready"])),
            "origin_depth": u8(raw["s_b2b_origin_n"]),
            "ttn_uplink_depth": u8(raw["s_b2b_uplink_n"]),
            "crumb_pending": bool(u8(raw["s_b2b_crumb_pending"])),
            "crumb_frame_ready": bool(u8(raw["s_b2b_crumb_frame_ready"])),
        },
        "observability": {
            "fresh_fix_this_boot": bool(u8(raw["s_have_fix_this_boot"])),
            "last_fix_monotonic_seconds": u32(raw["s_last_fix_monotonic_sec"]),
            "reported_relay_forwarded": u32(raw["s_reported_relay_fwd"]),
            "reported_ctt_tags": u32(raw["s_reported_ctt_tags"]),
        },
    }
    return result


def decode_tamp(manifest: dict, memory: dict[int, int]) -> dict:
    base = int(manifest["tamp_bkp0_address"])
    data = read_bytes(memory, base, 4 * TAMP_WORDS, "TAMP")
    words = list(struct.unpack("<" + "I" * TAMP_WORDS, data))
    session_bytes = data[: 15 * 4]
    calculated_crc = zlib.crc32(session_bytes[4:]) & 0xFFFFFFFF
    session_valid = (
        words[0] == SESSION_MAGIC
        and words[1] == SESSION_VERSION
        and words[SESSION_CRC_WORD] == calculated_crc
    )
    b2b = words[17]
    b2b_value = b2b & 0xFF
    b2b_check = (b2b >> 8) & 0xFF
    b2b_valid = (b2b & 0xFFFF0000) == 0xB2B20000 and b2b_check == (
        (~b2b_value) & 0xFF
    )
    command_record = words[16]
    command_tag = (command_record >> 24) & 0xFF
    command_sequence = (command_record >> 16) & 0xFF
    command_flags = (command_record >> 8) & 0xFF
    command_sequence_valid = (
        command_tag == COMMAND_STATE_TAG
        and command_flags <= 1
        and (command_record & 0xFF)
        == crc8(bytes((command_tag, command_sequence, command_flags)))
    )
    lease_record = words[18]
    lease_age = lease_record & 0x7FF
    lease_check = (lease_record >> 11) & 0x7FF
    lease_valid = (
        (lease_record >> 22) == LEASE_MAGIC
        and lease_check == ((~lease_age) & 0x7FF)
    )
    boot_record = words[19]
    boot_count = boot_record & 0xFFF
    boot_check = (boot_record >> 12) & 0xFFF
    boot_valid = (
        (boot_record >> 24) == BOOT_MAGIC
        and boot_check == ((~boot_count) & 0xFFF)
    )
    return {
        "session": {
            "valid": session_valid,
            "magic_valid": words[0] == SESSION_MAGIC,
            "version": words[1],
            "crc_valid": words[SESSION_CRC_WORD] == calculated_crc,
            "region_id": words[2],
            "region": REGIONS.get(words[2], "INVALID"),
            "dev_addr": f"{words[3]:08X}",
            "network_key_present": any(words[4:8]),
            "application_key_present": any(words[8:12]),
            "next_fcnt_up": words[12],
            "next_fcnt_down": words[13],
            "rx_delay_seconds": words[14],
        },
        "b2b_origin_id": {
            "valid": b2b_valid,
            "next_id": b2b_value if b2b_valid else None,
        },
        "command_sequence": {
            "valid": command_sequence_valid,
            "last_applied": command_sequence if command_sequence_valid else None,
            "relay_enabled": bool(command_flags) if command_sequence_valid else None,
        },
        "region_lease": {
            "valid": lease_valid,
            "age_seconds": lease_age,
        },
        "boot": {
            "valid": boot_valid,
            "count": boot_count if boot_valid else None,
        },
    }


def profile_gate(profile: str, health: dict | None, tamp: dict | None) -> dict:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    if profile == "inspect":
        return {"profile": profile, "passed": True, "failures": []}
    require(health is not None, "health state is required")
    require(tamp is not None, "TAMP state is required")
    if health is None or tamp is None:
        return {"profile": profile, "passed": False, "failures": failures}

    require(health["session"]["region_id"] == 0, "RAM region is not US915")
    require(
        health["radio_diag"]["begin_failures"] == 0
        and health["radio_diag"]["config_failures"] == 0
        and health["radio_diag"]["sleep_failures"] == 0
        and health["radio_diag"]["allocation_failures"] == 0
        and health["radio_diag"]["restore_attempts"]
        == health["radio_diag"]["restore_recovered"],
        "radio diagnostics contain an unaccounted failure",
    )
    require(
        not health["last_gps_fix"]["valid"]
        or health["last_gps_fix"]["satellites"] >= 4,
        "RAM GPS fix is internally inconsistent",
    )
    optical_fault = health["sensor_recovery"]["optical_quiescence_fault"]
    optical_retries = health["sensor_recovery"]["optical_quiet_retries"]
    if optical_retries is not None:
        require(optical_retries <= 5, "LTR390 fast-retry counter exceeds its cap")
        if optical_fault is False:
            require(
                optical_retries == 0,
                "LTR390 recovered but its fast-retry counter did not clear",
            )
    if optical_fault is not None:
        require(not optical_fault, "LTR390 standby remains unconfirmed")
    require(tamp["boot"]["valid"], "retained boot counter is invalid")
    require(
        tamp["boot"]["count"] == health["boot"]["count"],
        "RAM and retained boot counters differ",
    )
    require(
        0 <= health["boot"]["reset_cause_code"] <= 6,
        "compact reset-cause code is outside the wire contract",
    )
    if tamp["command_sequence"]["valid"]:
        require(
            health["command"]["ack_valid"]
            and health["command"]["ack_sequence"]
            == tamp["command_sequence"]["last_applied"]
            and health["command"]["relay_enabled"]
            == tamp["command_sequence"]["relay_enabled"],
            "RAM and retained command ACK/state differ",
        )
    else:
        require(
            not health["command"]["ack_valid"],
            "RAM acknowledges an invalid retained command state",
        )

    if profile == "cold-fail-closed":
        require(not health["region_lease"]["known"], "region is unexpectedly authorized")
    elif profile == "session-corrupt":
        require(
            not health["session"]["joined"],
            "corrupted retained session was imported into RAM",
        )
        require(
            not tamp["session"]["valid"]
            and tamp["session"]["magic_valid"]
            and tamp["session"]["version"] == SESSION_VERSION
            and not tamp["session"]["crc_valid"],
            "retained session is not a controlled CRC-only rejection",
        )
        require(
            not health["region_lease"]["known"],
            "session rejection did not restore fail-closed RF state",
        )
        require(
            tamp["region_lease"]["valid"],
            "session corruption unexpectedly damaged the independent region lease",
        )
    elif profile == "authorized-us":
        require(health["region_lease"]["known"], "RAM region is not authorized")
        require(tamp["region_lease"]["valid"], "retained region lease is invalid")
        require(
            health["region_lease"]["age_seconds"]
            == tamp["region_lease"]["age_seconds"],
            "RAM and retained region ages differ",
        )
    elif profile == "joined-us":
        require(health["session"]["joined"], "RAM session is not joined")
        require(tamp["session"]["valid"], "retained session v3/CRC is invalid")
        require(tamp["session"]["region_id"] == 0, "retained region is not US915")
        require(tamp["region_lease"]["valid"], "retained region lease is invalid")
        require(health["region_lease"]["known"], "RAM region is not authorized")
        require(
            health["region_lease"]["age_seconds"]
            == tamp["region_lease"]["age_seconds"],
            "RAM and retained region ages differ",
        )
        require(
            health["session"]["next_fcnt_up"]
            == tamp["session"]["next_fcnt_up"],
            "RAM and retained FCntUp differ",
        )
        require(
            health["session"]["next_fcnt_down"]
            == tamp["session"]["next_fcnt_down"],
            "RAM and retained FCntDown differ",
        )
    else:
        raise ValueError(f"unknown profile: {profile}")
    return {"profile": profile, "passed": not failures, "failures": failures}


def atomic_json(path: Path, value: dict) -> None:
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
        raise SystemExit(
            f"refusing to overwrite decoded flight-state evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--health-raw", type=Path)
    parser.add_argument("--tamp-raw", type=Path)
    parser.add_argument(
        "--profile",
        choices=(
            "inspect",
            "cold-fail-closed",
            "session-corrupt",
            "authorized-us",
            "joined-us",
        ),
        default="inspect",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.health_raw is None and args.tamp_raw is None:
        parser.error("provide --health-raw and/or --tamp-raw")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    health = (
        decode_health(manifest, parse_memory(args.health_raw))
        if args.health_raw else None
    )
    tamp = (
        decode_tamp(manifest, parse_memory(args.tamp_raw))
        if args.tamp_raw else None
    )
    gate = profile_gate(args.profile, health, tamp)
    result = {
        "scope": (
            "decoded J-Link RAM/TAMP state; session keys are intentionally "
            "redacted and never emitted"
        ),
        "manifest_elf_sha256": manifest["elf_sha256"],
        "health": health,
        "tamp": tamp,
        "profile_gate": gate,
    }
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not gate["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
