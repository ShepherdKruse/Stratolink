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

from decode_flight_state import profile_gate


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MANIFEST = HERE / "generated/stratolink_flight_hil_manifest.json"
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


def fixture(crc_valid: bool = True) -> tuple[dict, str]:
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
    words[18] = (0x2D3 << 22) | (((~600) & 0x7FF) << 11) | 600
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


def run(raw: str, output: Path) -> subprocess.CompletedProcess[str]:
    state = output.with_suffix(".txt")
    state.write_text(raw, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(DECODER),
            "--health-raw",
            str(state),
            "--tamp-raw",
            str(state),
            "--profile",
            "joined-us",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
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
        "s_sensor_i2c_bus_recoveries",
        "s_ltr390_quiesce_failures",
        "s_ltr390_soft_reset_recoveries",
        "s_optical_quiet_retries",
        "s_optical_quiescence_fault",
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

    print(
        "PASS: atomic create-once state decode, joined gate, CRC rejection, "
        "key redaction"
    )


if __name__ == "__main__":
    main()
