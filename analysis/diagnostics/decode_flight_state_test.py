#!/usr/bin/env python3
"""Synthetic atomic-state regressions, including retained-key redaction."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zlib

from decode_flight_state import (
    GPS_DIAG_CONTAINMENT_FIELDS,
    GPS_DIAG_LEGACY_FIELDS,
    decode_downlink_stats,
    decode_gps_diag,
    decode_health,
    decode_liveness_diag,
    decode_liveness_state,
    decode_region_authority_record,
    decode_session_meta,
    profile_gate,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MANIFEST = HERE / "fixtures/synthetic_flight_state_manifest.json"
DECODER = HERE / "decode_flight_state.py"


def crc8(data: bytes) -> int:
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def command_state_record(sequence: int, relay_enabled: bool) -> int:
    fields = bytes((0xD7, sequence, int(relay_enabled)))
    return int.from_bytes(fields + bytes((crc8(fields),)), "big")


def region_authority_crc8(payload: int) -> int:
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


def v2_region_authority_record(age: int, region_id: int, source_id: int) -> int:
    payload = age | (region_id << 11) | (source_id << 13)
    return (0x16D << 22) | (region_authority_crc8(payload) << 14) | payload


def write(memory: dict[int, int], address: int, data: bytes) -> None:
    for offset, byte in enumerate(data):
        memory[address + offset] = byte


def write_u8(memory: dict[int, int], manifest: dict, name: str, value: int) -> None:
    write(memory, manifest["symbols"][name]["address"], bytes([value]))


def write_u16(memory: dict[int, int], manifest: dict, name: str, value: int) -> None:
    write(memory, manifest["symbols"][name]["address"], struct.pack("<H", value))


def write_u32(memory: dict[int, int], manifest: dict, name: str, value: int) -> None:
    write(memory, manifest["symbols"][name]["address"], struct.pack("<I", value))


def render_symbol(memory: dict[int, int], address: int, size: int) -> str:
    data = bytes(memory[address + offset] for offset in range(size))
    if size == 1:
        tokens = [f"{data[0]:02X}"]
    elif size == 2:
        tokens = [f"{struct.unpack('<H', data)[0]:04X}"]
    elif address % 4 == 0 and size % 4 == 0:
        tokens = [
            f"{struct.unpack_from('<I', data, offset)[0]:08X}"
            for offset in range(0, size, 4)
        ]
    else:
        tokens = [f"{byte:02X}" for byte in data]
    return f"{address:08X} = " + " ".join(tokens)


def fixture(
    crc_valid: bool = True,
    *,
    authority_record: int | None = None,
) -> tuple[dict, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    memory: dict[int, int] = {}
    for entry in manifest["symbols"].values():
        write(memory, entry["address"], bytes(entry["size"]))

    write_u8(memory, manifest, "_joined", 1)
    write_u8(memory, manifest, "REGION_ID", 0)
    write_u32(memory, manifest, "boot_count", 3)
    write_u8(memory, manifest, "s_boot_reset_code", 5)
    write_u32(memory, manifest, "fCntUp", 42)
    write_u32(memory, manifest, "fCntDown", 7)
    write_u32(memory, manifest, "region_fix_age_sec", 600)
    write_u8(memory, manifest, "region_known", 1)
    write_u32(memory, manifest, "s_tmp117_direct_reads", 19)
    write_u32(memory, manifest, "s_tmp117_fallback_reads", 2)
    write_u32(memory, manifest, "s_tmp117_poweron_sentinels", 1)
    write_u8(memory, manifest, "spurious_ff_streak", 3)
    write_u8(memory, manifest, "ff_suppress_clean", 4)
    write_u8(memory, manifest, "s_ff_suppressed", 1)
    write_u8(memory, manifest, "s_burst_wake", 0)
    write_u8(memory, manifest, "s_have_fix_this_boot", 1)
    write_u32(memory, manifest, "s_last_fix_monotonic_sec", 120)
    write_u8(memory, manifest, "s_have_seq", 1)
    write_u8(memory, manifest, "s_last_seq", 42)
    write_u8(memory, manifest, "s_relay_enabled", 0)
    write_u32(memory, manifest, "s_reported_relay_fwd", 8)
    write_u32(memory, manifest, "s_reported_ctt_tags", 3)
    microphone = manifest["symbols"].get("s_mic_diag")
    if microphone:
        write(
            memory,
            microphone["address"],
            struct.pack("<6I", 21, 20, 1, 2, 640, 32),
        )
    liveness_state = manifest["symbols"].get("s_liveness_state")
    if liveness_state:
        encoded_state = (
            bytes((17, 0, 0, 1, 1))
            if liveness_state["size"] == 5
            else bytes((17, 2, 0))
        )
        write(memory, liveness_state["address"], encoded_state)
    liveness_diag = manifest["symbols"].get("s_liveness_diag")
    if liveness_diag:
        write(
            memory,
            liveness_diag["address"],
            struct.pack("<7I", 11, 12, 13, 14, 15, 16, 17),
        )

    words = [0] * 20
    words[0] = 0x53545241
    words[1] = 3
    words[2] = 0
    words[3] = 0x260CACD0
    words[4:12] = [0xDEADBEEF] * 8
    words[12] = 42
    words[13] = 7
    words[14] = 1
    session = struct.pack("<15I", *words[:15])
    words[15] = zlib.crc32(session[4:]) & 0xFFFFFFFF
    if not crc_valid:
        words[15] ^= 1
    words[16] = command_state_record(42, False)
    words[17] = 0xB2B2FA05
    words[18] = authority_record if authority_record is not None else (
        (0x2D3 << 22) | (((~600) & 0x7FF) << 11) | 600
    )
    words[19] = (0xB4 << 24) | (((~3) & 0xFFF) << 12) | 3
    base = manifest["tamp_bkp0_address"]
    write(memory, base, struct.pack("<20I", *words))

    lines = ["SEGGER synthetic atomic state"]
    for name, entry in sorted(
        manifest["symbols"].items(),
        key=lambda item: item[1]["address"],
    ):
        lines.append(render_symbol(memory, entry["address"], entry["size"]))
    for offset in range(0, 20, 8):
        address = base + offset * 4
        lines.append(render_symbol(memory, address, min(8, 20 - offset) * 4))
    return manifest, "\n".join(lines) + "\n"


def run(
    raw: str,
    output: Path,
    *,
    profile: str = "joined-us",
) -> subprocess.CompletedProcess[str]:
    state = output.with_suffix(".txt")
    state.write_text(raw, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(DECODER),
            "--manifest",
            str(MANIFEST),
            "--health-raw",
            str(state),
            "--tamp-raw",
            str(state),
            "--profile",
            profile,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    # The frozen layout remains decodable, but absent containment diagnostics
    # are explicit nulls rather than being confused with zero-valued evidence.
    legacy_values = tuple(range(len(GPS_DIAG_LEGACY_FIELDS)))
    legacy_gps = decode_gps_diag(struct.pack("<12I", *legacy_values))
    for index, field in enumerate(GPS_DIAG_LEGACY_FIELDS):
        assert legacy_gps[field] == index
    for field in GPS_DIAG_CONTAINMENT_FIELDS:
        assert legacy_gps[field] is None

    # Pin every current word to a unique value. In particular, the early-reset
    # counter inserted before reset_hold_entries must not shift the true final
    # containment_state out of the decoder as the previous tuple did.
    current_fields = GPS_DIAG_LEGACY_FIELDS + GPS_DIAG_CONTAINMENT_FIELDS
    current_values = tuple(0x1000 + index for index in range(len(current_fields)))
    current_gps = decode_gps_diag(
        struct.pack(f"<{len(current_values)}I", *current_values)
    )
    assert current_gps == {
        **dict(zip(current_fields, current_values)),
        "cold_extension_started": None,
        "cold_extension_exhausted": None,
        "cold_extension_aborted": None,
    }
    assert current_gps["early_reset_hold_entries"] == 0x100C
    assert current_gps["reset_hold_entries"] == 0x100D
    assert current_gps["reset_release_failures"] == 0x1011
    assert current_gps["containment_state"] == 0x1012

    # Cold-reacquisition firmware appends exactly three counters. Literal
    # offsets keep this regression independent of the decoder's field tuple.
    extended_values = tuple(0x2000 + index for index in range(22))
    extended_gps = decode_gps_diag(struct.pack("<22I", *extended_values))
    assert extended_gps["containment_state"] == 0x2012
    assert extended_gps["cold_extension_started"] == 0x2013
    assert extended_gps["cold_extension_exhausted"] == 0x2014
    assert extended_gps["cold_extension_aborted"] == 0x2015
    assert {key: extended_gps[key] for key in current_fields} == dict(
        zip(current_fields, extended_values[:19])
    )
    for older in (legacy_gps, current_gps):
        for field in ("cold_extension_started", "cold_extension_exhausted",
                      "cold_extension_aborted"):
            assert older[field] is None

    # Exercise the complete health-decoder entry point with a nonoverlapping
    # synthetic 88-byte diagnostic object, not merely its standalone decoder.
    extended_manifest = deepcopy(json.loads(MANIFEST.read_text()))
    extended_manifest["symbols"]["s_gps_diag"].update(address=0x2000F000, size=88)
    extended_memory = {}
    for entry in extended_manifest["symbols"].values():
        write(extended_memory, entry["address"], bytes(entry["size"]))
    write(extended_memory, 0x2000F000, struct.pack("<22I", *extended_values))
    assert decode_health(extended_manifest, extended_memory)["gps_diag"] == extended_gps

    # Unknown intermediate/future layouts fail closed instead of silently
    # relabeling safety-critical counters through a permissive zip().
    for words in (11, 13, 18, 20, 21, 23):
        try:
            decode_gps_diag(bytes(words * 4))
        except ValueError as error:
            assert "unknown gps_diag_t layout" in str(error)
        else:
            raise AssertionError(f"accepted unknown gps_diag_t layout: {words}")

    # Class-A diagnostics are append-only, but only the two exact layouts are
    # accepted so a newly inserted field cannot relabel recovery evidence.
    legacy_downlink = struct.pack(
        "<5I2i2h4B",
        1, 2, 3, 4, 5, -6, -7, -8, -9, 1, 10, 0x60, 7,
    )
    decoded_downlink = decode_downlink_stats(legacy_downlink)
    assert decoded_downlink["calls"] == 1
    assert decoded_downlink["last_rx2_start_state"] == -9
    assert decoded_downlink["authenticated_frames"] is None
    current_downlink = legacy_downlink + struct.pack(
        "<5I", 0x101, 0x102, 0x103, 0x104, 0x105
    )
    decoded_downlink = decode_downlink_stats(current_downlink)
    assert decoded_downlink["authenticated_frames"] == 0x101
    assert decoded_downlink["ack_frames"] == 0x102
    assert decoded_downlink["complete_no_evidence"] == 0x103
    assert decoded_downlink["mission_aborts"] == 0x104
    assert decoded_downlink["local_faults"] == 0x105
    for size in (35, 37, 52, 60):
        try:
            decode_downlink_stats(bytes(size))
        except ValueError as error:
            assert "unknown lorawan_downlink_stats_t layout" in str(error)
        else:
            raise AssertionError(f"accepted unknown downlink layout: {size}")

    assert decode_liveness_state(bytes((23, 3, 0))) == {
        "countdown": 23,
        "qualified_miss_streak": 3,
        "probe_pending": False,
        "server_proven": False,
        "initial_probe_attempted": False,
        "recovery_due": True,
        "state_valid": True,
    }
    assert decode_liveness_state(bytes((0, 2, 1)))["state_valid"] is True
    assert decode_liveness_state(bytes((1, 2, 1)))["state_valid"] is False
    assert decode_liveness_state(bytes((17, 0, 0, 1, 1))) == {
        "countdown": 17,
        "qualified_miss_streak": 0,
        "probe_pending": False,
        "server_proven": True,
        "initial_probe_attempted": True,
        "recovery_due": False,
        "state_valid": True,
    }
    assert not decode_liveness_state(bytes((17, 0, 0, 1, 0)))["state_valid"]
    assert decode_liveness_diag(struct.pack("<7I", *range(7))) == {
        "confirmed_probe_tx": 0,
        "authenticated_downlinks": 1,
        "ack_downlinks": 2,
        "qualified_misses": 3,
        "recoveries": 4,
        "abandoned_probes": 5,
        "persistence_failures": 6,
    }
    for invalid_state in (
        b"", bytes(2), bytes(4), bytes(6), bytes((0, 0, 2)),
        bytes((0, 0, 0, 0, 2)),
    ):
        try:
            decode_liveness_state(invalid_state)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted malformed liveness state")

    # Retained session word 14 must expose the low-nibble RECEIVE_DELAY1 and
    # the exact CRC-covered liveness metadata independently. Legacy 1..15 are
    # accepted as an unproven immediate interval; every reserved/impossible pattern
    # fails exactly as the firmware importer does.
    for delay in range(1, 16):
        decoded_meta = decode_session_meta(delay)
        assert decoded_meta["valid"]
        assert decoded_meta["format"] == "legacy"
        assert decoded_meta["rx_delay_seconds"] == delay
        assert decoded_meta["countdown"] == 0
        assert decoded_meta["qualified_miss_streak"] == 0
        assert decoded_meta["probe_pending"] is False
        assert decoded_meta["server_proven"] is False
        assert decoded_meta["initial_probe_attempted"] is False
    for countdown, misses, pending, proven, attempted in (
        (0, 0, False, False, False),
        (23, 0, False, False, True),
        (0, 2, True, False, True),
        (17, 0, False, True, True),
        (23, 3, False, False, True),
    ):
        word = (
            5 | 0x1000 | (countdown << 4) | (misses << 9)
            | (0x800 if pending else 0)
            | (0x2000 if proven else 0)
            | (0x4000 if attempted else 0)
        )
        decoded_meta = decode_session_meta(word)
        assert decoded_meta["valid"]
        assert decoded_meta["format"] == "v1"
        assert decoded_meta["countdown"] == countdown
        assert decoded_meta["qualified_miss_streak"] == misses
        assert decoded_meta["probe_pending"] is pending
        assert decoded_meta["server_proven"] is proven
        assert decoded_meta["initial_probe_attempted"] is attempted
    for invalid_word in (
        0, 16, 0x1000, 0x1000 | (24 << 4) | 1,
        0x1000 | (1 << 4) | (2 << 9) | 0x800 | 1,
        0x1000 | (3 << 9) | 0x800 | 1,
        0x1000 | (3 << 9) | 1,
        0x2000 | 1,
        0x1000 | 0x2000 | 1,
        0x8000 | 0x1000 | 1,
    ):
        assert not decode_session_meta(invalid_word)["valid"], hex(invalid_word)

    manifest_symbols = set(
        json.loads(MANIFEST.read_text(encoding="utf-8"))["symbols"]
    )
    decoder_source = DECODER.read_text(encoding="utf-8")
    raw_references = {
        first or second
        for first, second in re.findall(
            r"""raw\["([^"]+)"\]|raw\['([^']+)'\]""",
            decoder_source,
        )
    }
    # Source may add a critical diagnostic after the precursor/candidate
    # manifest was frozen. The decoder must tolerate that one create-once
    # manifest until the next candidate regeneration, while the generator
    # already requires the symbol for every new manifest.
    staged_symbols = {
        "region_lease_trusted",
        "region_authority_source",
        "region_authority_region",
        "s_sensor_i2c_bus_recoveries",
        "s_ltr390_quiesce_failures",
        "s_ltr390_soft_reset_recoveries",
        "s_optical_quiet_retries",
        "s_optical_quiescence_fault",
        "s_liveness_state",
        "s_liveness_diag",
    }
    assert raw_references == manifest_symbols | staged_symbols, (
        f"atomic decoder symbol drift: unreferenced="
        f"{sorted((manifest_symbols | staged_symbols) - raw_references)}, unknown="
        f"{sorted(raw_references - (manifest_symbols | staged_symbols))}"
    )

    with tempfile.TemporaryDirectory(prefix="stratolink-state-test-") as raw:
        root = Path(raw)
        _manifest, good_raw = fixture(True)
        good_output = root / "good.json"
        good = run(good_raw, good_output)
        assert good.returncode == 0, good.stdout + good.stderr
        report = json.loads(good_output.read_text(encoding="utf-8"))
        assert report["profile_gate"]["passed"]
        assert report["tamp"]["session"]["valid"]
        assert report["tamp"]["session"]["next_fcnt_up"] == 42
        assert report["tamp"]["session"]["rx_delay_seconds"] == 1
        assert report["tamp"]["session"]["server_liveness"] == {
            "raw": 1,
            "valid": True,
            "format": "legacy",
            "rx_delay_seconds": 1,
            "countdown": 0,
            "qualified_miss_streak": 0,
            "probe_pending": False,
            "server_proven": False,
            "initial_probe_attempted": False,
            "recovery_due": False,
            "reserved_bits": 0,
        }
        assert report["health"]["radio_diag"]["begin_failures"] == 0
        assert report["health"]["radio_diag"]["allocation_failures"] == 0
        assert report["health"]["sensor_recovery"]["optical_quiet_retries"] in (
            None,
            0,
        )
        assert report["health"]["boot"]["reset_cause_code"] == 5
        assert report["health"]["command"]["ack_valid"]
        assert report["health"]["command"]["ack_sequence"] == 42
        assert not report["health"]["command"]["relay_enabled"]
        assert report["health"]["observability"] == {
            "fresh_fix_this_boot": True,
            "last_fix_monotonic_seconds": 120,
            "reported_relay_forwarded": 8,
            "reported_ctt_tags": 3,
        }
        assert report["tamp"]["command_sequence"] == {
            "valid": True,
            "last_applied": 42,
            "relay_enabled": False,
        }
        assert report["tamp"]["region_lease"] == {
            "age_seconds": 600,
            "crc_valid": None,
            "exact_region": False,
            "format": "legacy",
            "region": None,
            "region_id": None,
            "source": "GNSS",
            "source_id": 0,
            "valid": True,
        }
        assert report["health"]["tmp117_sampling"] == {
            "direct_reads": 19,
            "fallback_reads": 2,
            "rejected_poweron_sentinels": 1,
        }
        assert report["health"]["freefall_guard"] == {
            "spurious_wake_streak": 3,
            "suppression_clean_wakes": 4,
            "suppression_latched": True,
            "wake_pending": False,
        }
        if "s_mic_diag" in manifest_symbols:
            assert report["health"]["acoustic_diag"] == {
                "attempts": 21,
                "captures": 20,
                "capture_failures": 1,
                "events": 2,
                "last_variance_x16": 640,
                "noise_floor_x16": 32,
            }
        if "s_liveness_state" in manifest_symbols:
            captured_state = (
                {
                    "countdown": 17,
                    "qualified_miss_streak": 0,
                    "probe_pending": False,
                    "server_proven": True,
                    "initial_probe_attempted": True,
                    "recovery_due": False,
                    "state_valid": True,
                }
                if report["health"]["server_liveness"]["state"][
                    "server_proven"
                ]
                else {
                    "countdown": 17,
                    "qualified_miss_streak": 2,
                    "probe_pending": False,
                    "server_proven": False,
                    "initial_probe_attempted": False,
                    "recovery_due": False,
                    "state_valid": True,
                }
            )
            assert report["health"]["server_liveness"] == {
                "state": captured_state,
                "diagnostics": {
                    "confirmed_probe_tx": 11,
                    "authenticated_downlinks": 12,
                    "ack_downlinks": 13,
                    "qualified_misses": 14,
                    "recoveries": 15,
                    "abandoned_probes": 16,
                    "persistence_failures": 17,
                },
            }
        assert "DEADBEEF" not in good.stdout.upper()
        assert "DEADBEEF" not in good_output.read_text(encoding="utf-8").upper()
        preserved = good_output.read_bytes()
        collision = run(good_raw, good_output)
        assert collision.returncode != 0
        assert "refusing to overwrite" in collision.stderr
        assert good_output.read_bytes() == preserved
        authorized = profile_gate(
            "authorized-us",
            report["health"],
            report["tamp"],
        )
        assert authorized["passed"], authorized
        report["health"]["region_lease"]["known"] = False
        unauthorized = profile_gate(
            "authorized-us",
            report["health"],
            report["tamp"],
        )
        assert not unauthorized["passed"]
        assert "RAM region is not authorized" in unauthorized["failures"]

        mismatched_command = deepcopy(report)
        mismatched_command["health"]["command"]["relay_enabled"] = True
        mismatch = profile_gate(
            "joined-us",
            mismatched_command["health"],
            mismatched_command["tamp"],
        )
        assert not mismatch["passed"]
        assert "RAM and retained command ACK/state differ" in mismatch["failures"]

        corrupt_session = deepcopy(report)
        corrupt_session["health"]["session"]["joined"] = False
        corrupt_session["health"]["region_lease"]["known"] = False
        corrupt_session["tamp"]["session"]["valid"] = False
        corrupt_session["tamp"]["session"]["crc_valid"] = False
        rejected = profile_gate(
            "session-corrupt",
            corrupt_session["health"],
            corrupt_session["tamp"],
        )
        assert rejected["passed"], rejected
        corrupt_session["health"]["session"]["joined"] = True
        imported = profile_gate(
            "session-corrupt",
            corrupt_session["health"],
            corrupt_session["tamp"],
        )
        assert not imported["passed"]
        assert (
            "corrupted retained session was imported into RAM"
            in imported["failures"]
        )

        _manifest, corrupt_raw = fixture(False)
        corrupt_output = root / "corrupt.json"
        corrupt = run(corrupt_raw, corrupt_output)
        assert corrupt.returncode != 0
        failed = json.loads(corrupt_output.read_text(encoding="utf-8"))
        assert not failed["tamp"]["session"]["crc_valid"]
        assert "retained session v3/CRC is invalid" in failed["profile_gate"]["failures"]

        # The current BKP18 format binds age, exact plan, and provenance. Pin
        # every source/region combination and reject a one-bit CRC mutation.
        for source_id, source in ((0, "GNSS"), (1, "LAUNCH")):
            for region_id, region in enumerate(("US915", "EU868", "AS923", "AU915")):
                record = v2_region_authority_record(321, region_id, source_id)
                decoded = decode_region_authority_record(record)
                assert decoded == {
                    "age_seconds": 321,
                    "crc_valid": True,
                    "exact_region": True,
                    "format": "v2",
                    "region": region,
                    "region_id": region_id,
                    "source": source,
                    "source_id": source_id,
                    "valid": True,
                }
                corrupted = decode_region_authority_record(record ^ (1 << 14))
                assert corrupted["format"] == "v2"
                assert corrupted["valid"] is False
                assert corrupted["age_seconds"] is None
                assert corrupted["source"] is None
                assert corrupted["region"] is None

        launch_record = v2_region_authority_record(300, 0, 1)
        _manifest, launch_raw = fixture(authority_record=launch_record)
        launch_output = root / "launch.json"
        launch = run(launch_raw, launch_output, profile="inspect")
        assert launch.returncode == 0, launch.stdout + launch.stderr
        launch_report = json.loads(launch_output.read_text(encoding="utf-8"))
        assert launch_report["tamp"]["region_lease"] == {
            "age_seconds": 300,
            "crc_valid": True,
            "exact_region": True,
            "format": "v2",
            "region": "US915",
            "region_id": 0,
            "source": "LAUNCH",
            "source_id": 1,
            "valid": True,
        }

        # New exact-image manifests expose the corresponding RAM tuple. Build
        # the post-reset state shape explicitly so the launch-specific gate is
        # pinned even while this test remains compatible with an older frozen
        # manifest during candidate transition.
        launch_health = deepcopy(launch_report["health"])
        launch_health["region_lease"].update(
            {
                "age_seconds": 300,
                "exact_region": True,
                "known": True,
                "region": "US915",
                "region_id": 0,
                "source": "LAUNCH",
                "source_id": 1,
                "trusted_provenance": True,
            }
        )
        launch_gate = profile_gate(
            "launch-authorized-us", launch_health, launch_report["tamp"]
        )
        assert launch_gate["passed"], launch_gate
        launch_health["region_lease"]["source"] = "GNSS"
        rejected_launch = profile_gate(
            "launch-authorized-us", launch_health, launch_report["tamp"]
        )
        assert not rejected_launch["passed"]
        assert (
            "RAM authority is not exact US915 LAUNCH provenance"
            in rejected_launch["failures"]
        )

    print(
        "PASS: atomic create-once state decode, joined gate, CRC rejection, "
        "legacy/v2 authority provenance, and key redaction"
    )


if __name__ == "__main__":
    main()
