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
LEGACY_LEASE_MAGIC = 0x2D3
REGION_LEASE_V2_MAGIC = 0x16D
REGION_AUTHORITY_SOURCES = {
    0: "GNSS",
    1: "LAUNCH",
}
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

GPS_DIAG_LEGACY_FIELDS = (
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
)
GPS_DIAG_CONTAINMENT_FIELDS = (
    "early_reset_hold_entries",
    "reset_hold_entries",
    "reset_hold_reuses",
    "reset_release_attempts",
    "reset_release_denied_low_rail",
    "reset_release_failures",
    "containment_state",
)
GPS_DIAG_COLD_EXTENSION_FIELDS = (
    "cold_extension_started",
    "cold_extension_exhausted",
    "cold_extension_aborted",
)
DOWNLINK_LEGACY_SIZE = 36
DOWNLINK_LIVENESS_SIZE = 56
LIVENESS_LEGACY_STATE_SIZE = 3
LIVENESS_STATE_SIZE = 5
LIVENESS_DIAG_SIZE = 28
SESSION_RX_DELAY_MASK = 0x0000000F
SESSION_LIVENESS_COUNT_MASK = 0x000001F0
SESSION_LIVENESS_MISS_MASK = 0x00000600
SESSION_LIVENESS_PENDING = 0x00000800
SESSION_LIVENESS_MARKER = 0x00001000
SESSION_SERVER_PROVEN = 0x00002000
SESSION_INITIAL_PROBE_TRIED = 0x00004000
SESSION_META_ALLOWED_MASK = 0x00007FFF
LIVENESS_COUNTDOWN_MAX = 23
LIVENESS_MISSES_BEFORE_RECOVERY = 3


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


def decode_gps_diag(data: bytes) -> dict[str, int | None]:
    """Decode one known append-only gps_diag_t layout without field shifting.

    The frozen v16 manifest ends at dynamic_model_terminal_failures (12 words).
    The containment image appends seven words, and bounded cold reacquisition
    appends three more. Other word counts are rejected so an inserted/removed
    field cannot silently relabel safety evidence. Absent counters remain null.
    """
    values = u32s(data)
    containment_fields = GPS_DIAG_LEGACY_FIELDS + GPS_DIAG_CONTAINMENT_FIELDS
    current_fields = containment_fields + GPS_DIAG_COLD_EXTENSION_FIELDS
    if len(values) not in (len(GPS_DIAG_LEGACY_FIELDS),
                           len(containment_fields), len(current_fields)):
        raise ValueError(
            "unknown gps_diag_t layout: "
            f"{len(values)} words; expected {len(GPS_DIAG_LEGACY_FIELDS)} "
            f"(legacy), {len(containment_fields)} (containment), or "
            f"{len(current_fields)} (cold extension)"
        )
    decoded: dict[str, int | None] = dict.fromkeys(current_fields)
    decoded.update(zip(current_fields, values))
    return decoded


def decode_downlink_stats(data: bytes) -> dict[str, int | None]:
    """Decode only the frozen or current append-only Class-A layout."""
    if len(data) not in (DOWNLINK_LEGACY_SIZE, DOWNLINK_LIVENESS_SIZE):
        raise ValueError(
            "unknown lorawan_downlink_stats_t layout: "
            f"{len(data)} bytes; expected {DOWNLINK_LEGACY_SIZE} (legacy) "
            f"or {DOWNLINK_LIVENESS_SIZE} (server liveness)"
        )
    decoded: dict[str, int | None] = {
        "calls": u32(data, 0),
        "rx1_armed": u32(data, 4),
        "rx2_armed": u32(data, 8),
        "irq_count": u32(data, 12),
        "frame_count": u32(data, 16),
        "last_rx1_start_offset_ms": i32(data, 20),
        "last_rx2_start_offset_ms": i32(data, 24),
        "last_rx1_start_state": i16(data, 28),
        "last_rx2_start_state": i16(data, 30),
        "last_window": u8(data, 32),
        "last_length": u8(data, 33),
        "last_mhdr": u8(data, 34),
        "last_reject": u8(data, 35),
    }
    appended = (
        "authenticated_frames",
        "ack_frames",
        "complete_no_evidence",
        "mission_aborts",
        "local_faults",
    )
    if len(data) == DOWNLINK_LIVENESS_SIZE:
        decoded.update(
            {field: u32(data, 36 + index * 4)
             for index, field in enumerate(appended)}
        )
    else:
        decoded.update({field: None for field in appended})
    return decoded


def liveness_state_is_valid(
    countdown: int,
    qualified_miss_streak: int,
    probe_pending: bool,
    server_proven: bool = False,
    initial_probe_attempted: bool = False,
) -> bool:
    if countdown > LIVENESS_COUNTDOWN_MAX:
        return False
    if qualified_miss_streak > LIVENESS_MISSES_BEFORE_RECOVERY:
        return False
    if server_proven and (
        not initial_probe_attempted
        or probe_pending
        or qualified_miss_streak != 0
    ):
        return False
    if probe_pending and (
        countdown != 0
        or qualified_miss_streak >= LIVENESS_MISSES_BEFORE_RECOVERY
    ):
        return False
    if (
        qualified_miss_streak >= LIVENESS_MISSES_BEFORE_RECOVERY
        and countdown != LIVENESS_COUNTDOWN_MAX
    ):
        return False
    return True


def decode_liveness_state(data: bytes) -> dict[str, int | bool]:
    if len(data) not in (LIVENESS_LEGACY_STATE_SIZE, LIVENESS_STATE_SIZE):
        raise ValueError(
            "unknown lorawan_liveness_state_t layout: "
            f"{len(data)} bytes; expected "
            f"{LIVENESS_LEGACY_STATE_SIZE} or {LIVENESS_STATE_SIZE}"
        )
    if any(value not in (0, 1) for value in data[2:]):
        raise ValueError("invalid bool representation in liveness state")
    countdown = u8(data, 0)
    misses = u8(data, 1)
    pending = bool(u8(data, 2))
    server_proven = bool(u8(data, 3)) if len(data) == LIVENESS_STATE_SIZE else False
    initial_probe_attempted = (
        bool(u8(data, 4)) if len(data) == LIVENESS_STATE_SIZE else False
    )
    return {
        "countdown": countdown,
        "qualified_miss_streak": misses,
        "probe_pending": pending,
        "server_proven": server_proven,
        "initial_probe_attempted": initial_probe_attempted,
        "recovery_due": (
            not pending and misses >= LIVENESS_MISSES_BEFORE_RECOVERY
        ),
        "state_valid": liveness_state_is_valid(
            countdown,
            misses,
            pending,
            server_proven,
            initial_probe_attempted,
        ),
    }


def decode_liveness_diag(data: bytes) -> dict[str, int]:
    if len(data) != LIVENESS_DIAG_SIZE:
        raise ValueError(
            "unknown lorawan_liveness_diag_t layout: "
            f"{len(data)} bytes; expected {LIVENESS_DIAG_SIZE}"
        )
    fields = (
        "confirmed_probe_tx",
        "authenticated_downlinks",
        "ack_downlinks",
        "qualified_misses",
        "recoveries",
        "abandoned_probes",
        "persistence_failures",
    )
    return dict(zip(fields, u32s(data)))


def decode_session_meta(word: int) -> dict[str, int | bool | str | None]:
    """Mirror lorawan_session_meta_decode() for retained-state HIL."""
    rx_delay = word & SESSION_RX_DELAY_MASK
    reserved_bits = word & ~SESSION_META_ALLOWED_MASK
    high = word & ~SESSION_RX_DELAY_MASK
    legacy = high == 0
    marker = bool(word & SESSION_LIVENESS_MARKER)
    countdown = 0 if legacy else (word & SESSION_LIVENESS_COUNT_MASK) >> 4
    misses = 0 if legacy else (word & SESSION_LIVENESS_MISS_MASK) >> 9
    pending = False if legacy else bool(word & SESSION_LIVENESS_PENDING)
    server_proven = False if legacy else bool(word & SESSION_SERVER_PROVEN)
    initial_probe_attempted = (
        False if legacy else bool(word & SESSION_INITIAL_PROBE_TRIED)
    )
    valid = (
        reserved_bits == 0
        and 1 <= rx_delay <= 15
        and (legacy or marker)
        and liveness_state_is_valid(
            countdown,
            misses,
            pending,
            server_proven,
            initial_probe_attempted,
        )
    )
    return {
        "raw": word,
        "valid": valid,
        "format": "legacy" if legacy else ("v1" if marker else "invalid"),
        "rx_delay_seconds": rx_delay if valid else None,
        "countdown": countdown if valid else None,
        "qualified_miss_streak": misses if valid else None,
        "probe_pending": pending if valid else None,
        "server_proven": server_proven if valid else None,
        "initial_probe_attempted": (
            initial_probe_attempted if valid else None
        ),
        "recovery_due": (
            valid and not pending
            and misses >= LIVENESS_MISSES_BEFORE_RECOVERY
        ),
        "reserved_bits": reserved_bits,
    }


def crc8(data: bytes) -> int:
    """CRC-8/ATM used by the retained command-state record."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def tamp_region_lease_crc8(payload: int) -> int:
    """CRC-8/ATM over the 14-bit v2 payload, matching tamp_record.h."""
    if not 0 <= payload <= 0x3FFF:
        raise ValueError("TAMP v2 region-authority payload is not 14 bits")
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


def decode_region_authority_record(record: int) -> dict:
    """Decode legacy age-only and v2 exact-region BKP18 records."""
    magic = record >> 22
    if magic == REGION_LEASE_V2_MAGIC:
        payload = record & 0x3FFF
        stored_crc = (record >> 14) & 0xFF
        valid = stored_crc == tamp_region_lease_crc8(payload)
        age = payload & 0x7FF
        region_id = (payload >> 11) & 0x03
        source_id = (payload >> 13) & 0x01
        return {
            "valid": valid,
            "format": "v2",
            "age_seconds": age if valid else None,
            "exact_region": True if valid else None,
            "source_id": source_id if valid else None,
            "source": REGION_AUTHORITY_SOURCES[source_id] if valid else None,
            "region_id": region_id if valid else None,
            "region": REGIONS[region_id] if valid else None,
            "crc_valid": valid,
        }

    if magic == LEGACY_LEASE_MAGIC:
        age = record & 0x7FF
        check = (record >> 11) & 0x7FF
        valid = check == ((~age) & 0x7FF)
        return {
            "valid": valid,
            "format": "legacy",
            "age_seconds": age if valid else None,
            "exact_region": False if valid else None,
            "source_id": 0 if valid else None,
            "source": "GNSS" if valid else None,
            "region_id": None,
            "region": None,
            "crc_valid": None,
        }

    return {
        "valid": False,
        "format": "unknown",
        "age_seconds": None,
        "exact_region": None,
        "source_id": None,
        "source": None,
        "region_id": None,
        "region": None,
        "crc_valid": None,
    }


def decode_health(manifest: dict, memory: dict[int, int]) -> dict:
    raw: dict[str, bytes] = {}
    for name, entry in manifest["symbols"].items():
        raw[name] = read_bytes(
            memory,
            int(entry["address"]),
            int(entry["size"]),
            name,
        )

    gps = decode_gps_diag(raw["s_gps_diag"])
    command = raw["s_stats"]
    downlink = decode_downlink_stats(raw["s_dl_stats"])
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

    authority_source_id = (
        u8(raw["region_authority_source"])
        if "region_authority_source" in raw else None
    )
    authority_region_id = (
        u8(raw["region_authority_region"])
        if "region_authority_region" in raw else None
    )
    authority_tuple_valid = (
        authority_source_id in REGION_AUTHORITY_SOURCES
        and authority_region_id in REGIONS
        and authority_region_id != 4
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
            "exact_region": authority_tuple_valid
            if authority_source_id is not None and authority_region_id is not None
            else None,
            "source_id": authority_source_id,
            "source": REGION_AUTHORITY_SOURCES.get(authority_source_id),
            "region_id": authority_region_id,
            "region": REGIONS.get(authority_region_id),
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
        "gps_diag": gps,
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
        "downlink": downlink,
        "server_liveness": {
            "state": (
                decode_liveness_state(raw["s_liveness_state"])
                if "s_liveness_state" in raw else None
            ),
            "diagnostics": (
                decode_liveness_diag(raw["s_liveness_diag"])
                if "s_liveness_diag" in raw else None
            ),
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
    session_meta = decode_session_meta(words[14])
    session_valid = (
        words[0] == SESSION_MAGIC
        and words[1] == SESSION_VERSION
        and words[SESSION_CRC_WORD] == calculated_crc
        and words[2] in (0, 1, 2, 3)
        and session_meta["valid"]
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
    region_authority = decode_region_authority_record(words[18])
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
            "rx_delay_seconds": session_meta["rx_delay_seconds"],
            "server_liveness": session_meta,
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
        "region_lease": region_authority,
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
    elif profile == "launch-authorized-us":
        require(health["region_lease"]["known"], "RAM region is not authorized")
        require(
            health["region_lease"]["trusted_provenance"] is True,
            "RAM region authority is not trusted",
        )
        require(
            health["region_lease"]["exact_region"] is True
            and health["region_lease"]["source"] == "LAUNCH"
            and health["region_lease"]["region_id"] == 0,
            "RAM authority is not exact US915 LAUNCH provenance",
        )
        require(
            tamp["region_lease"]["valid"]
            and tamp["region_lease"]["format"] == "v2"
            and tamp["region_lease"]["exact_region"] is True
            and tamp["region_lease"]["source"] == "LAUNCH"
            and tamp["region_lease"]["region_id"] == 0,
            "retained authority is not exact US915 LAUNCH v2",
        )
        require(
            health["region_lease"]["age_seconds"]
            == tamp["region_lease"]["age_seconds"],
            "RAM and retained launch-authority ages differ",
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
            "launch-authorized-us",
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
