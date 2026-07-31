#!/usr/bin/env python3
"""Generate and evaluate exact-ELF two-node CTT wildlife HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess


RECEIVER_SYMBOLS = {"s_ctt": 32, "s_ctt_queue": 648}
TRANSMITTER_SYMBOLS = {"ctt_tx_diag_state": 44}
REFERENCE_RAW = 0x78554C33
NON_DICTIONARY_RAW = 0xDEADBEEF
FRAME_COUNT = 24


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_nm() -> str:
    candidates = [
        shutil.which("arm-none-eabi-nm"),
        "/Users/twarn/.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-nm",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("arm-none-eabi-nm not found")


def symbol_table(elf: Path) -> dict[str, tuple[int, int]]:
    output = subprocess.check_output(
        [find_nm(), "-S", "-C", "--defined-only", str(elf)], text=True
    )
    result: dict[str, tuple[int, int]] = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) != 4:
            continue
        try:
            address = int(fields[0], 16)
            size = int(fields[1], 16)
        except ValueError:
            continue
        result[fields[3]] = (address, size)
    return result


def require_symbols(
    elf: Path, expected: dict[str, int]
) -> dict[str, dict[str, int]]:
    available = symbol_table(elf)
    result: dict[str, dict[str, int]] = {}
    for name, expected_size in expected.items():
        if name not in available:
            raise SystemExit(f"{name} missing from {elf}")
        address, size = available[name]
        if size != expected_size:
            raise SystemExit(
                f"{name} size {size} != expected {expected_size} in {elf}"
            )
        result[name] = {"address": address, "size": size}
    return result


def savebin_script(items: dict[str, dict[str, int]], prefix: str) -> str:
    lines = ["connect", "h"]
    for name, item in items.items():
        lines.append(
            f"savebin {prefix}_{name}.bin "
            f"0x{item['address']:08X} 0x{item['size']:X}"
        )
    lines.extend(["g", "exit", ""])
    return "\n".join(lines)


def generate(args: argparse.Namespace) -> None:
    receiver = args.receiver_elf.resolve()
    transmitter = args.transmitter_elf.resolve()
    output = args.output_dir.resolve()
    if not receiver.is_file() or not transmitter.is_file():
        raise SystemExit("both exact diagnostic ELFs must exist")

    receiver_symbols = require_symbols(receiver, RECEIVER_SYMBOLS)
    transmitter_symbols = require_symbols(transmitter, TRANSMITTER_SYMBOLS)
    output.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "stratolink-ctt-two-node-hil-v1",
        "scope": (
            "functional 434 MHz protocol/queue test on two identical high-band "
            "RAK3172-9 assemblies; not absolute airborne sensitivity evidence"
        ),
        "receiver": {
            "elf": str(receiver),
            "elf_sha256": sha256(receiver),
            "symbols": receiver_symbols,
        },
        "transmitter": {
            "elf": str(transmitter),
            "elf_sha256": sha256(transmitter),
            "symbols": transmitter_symbols,
        },
        "expect": {
            "frames_rx": FRAME_COUNT,
            "crc_fail": 1,
            "tags_seen": 21,
            "pending_drop": 5,
            "pending_count": 16,
            "reference_hits": 3,
            "tx_power_dbm": -9,
            "tx_attempts": FRAME_COUNT,
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "read_receiver.jlink").write_text(
        savebin_script(receiver_symbols, "ctt_receiver"), encoding="utf-8"
    )
    (output / "read_transmitter.jlink").write_text(
        savebin_script(transmitter_symbols, "ctt_transmitter"), encoding="utf-8"
    )
    print(f"PASS: generated exact-ELF CTT HIL bundle in {output}")


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def detection(data: bytes, offset: int) -> dict[str, int | bool]:
    return {
        "id_raw": u32(data, offset),
        "id_motus": u32(data, offset + 4),
        "rssi_best": i16(data, offset + 8),
        "hits": data[offset + 10],
        "motus_valid": bool(data[offset + 11]),
        "window_idx": struct.unpack_from("<H", data, offset + 12)[0],
        "queued_min": u32(data, offset + 16),
    }


def read_exact(path: Path, size: int) -> bytes:
    data = path.read_bytes()
    if len(data) != size:
        raise SystemExit(f"{path}: {len(data)} bytes, expected {size}")
    return data


def evaluate(args: argparse.Namespace) -> None:
    stats = read_exact(args.receiver_stats, 32)
    queue = read_exact(args.receiver_queue, 648)
    tx = read_exact(args.transmitter_state, 44)

    receiver = {
        "frames_rx": u32(stats, 0),
        "crc_fail": u32(stats, 4),
        "tags_seen": u32(stats, 8),
        "windows": u32(stats, 12),
        "rx_arm_fail": u32(stats, 16),
        "last_id": u32(stats, 20),
        "last_rssi": i16(stats, 24),
        "pending_drop": u32(stats, 28),
        "log_n": queue[640],
        "pending_n": queue[644],
        "first_pending": detection(queue, 320),
        "second_pending": detection(queue, 340),
    }
    transmitter = {
        "magic": u32(tx, 0),
        "tx_attempts": u32(tx, 12),
        "tx_success": u32(tx, 16),
        "tx_fail": u32(tx, 20),
        "config_state": i16(tx, 24),
        "last_tx_state": i16(tx, 26),
        "power_dbm": struct.unpack_from("<b", tx, 28)[0],
        "frame_index": tx[29],
        "frame_count": tx[30],
        "configured": tx[37],
        "complete": tx[38],
    }

    checks = {
        "tx_magic": transmitter["magic"] == 0x43545831,
        "tx_configured": transmitter["configured"] == 1,
        "tx_complete": transmitter["complete"] == 1,
        "tx_exact_attempts": transmitter["tx_attempts"] == FRAME_COUNT,
        "tx_all_success": transmitter["tx_success"] == FRAME_COUNT
        and transmitter["tx_fail"] == 0,
        "tx_states_clean": transmitter["config_state"] == 0
        and transmitter["last_tx_state"] == 0,
        "tx_power_bounded": transmitter["power_dbm"] == -9,
        "rx_exact_frames": receiver["frames_rx"] == FRAME_COUNT,
        "rx_one_bad_crc": receiver["crc_fail"] == 1,
        "rx_expected_distinct": receiver["tags_seen"] == 21,
        "rx_no_arm_failure": receiver["rx_arm_fail"] == 0,
        "rx_one_window": receiver["windows"] == 1,
        "rx_expected_drops": receiver["pending_drop"] == 5,
        "rx_queue_full": receiver["pending_n"] == 16,
        "rx_reference_aggregated": (
            receiver["first_pending"]["id_raw"] == REFERENCE_RAW
            and receiver["first_pending"]["id_motus"] == 0x3256E
            and receiver["first_pending"]["hits"] == 3
            and receiver["first_pending"]["motus_valid"]
        ),
        "rx_nondictionary_explicit": (
            receiver["second_pending"]["id_raw"] == NON_DICTIONARY_RAW
            and receiver["second_pending"]["id_motus"] == 0
            and not receiver["second_pending"]["motus_valid"]
        ),
    }
    passed = all(checks.values())
    result = {
        "schema": "stratolink-ctt-two-node-hil-result-v1",
        "passed": passed,
        "scope": (
            "functional HIL only; identical high-band assemblies do not qualify "
            "absolute 434 MHz airborne-tag sensitivity"
        ),
        "checks": checks,
        "receiver": receiver,
        "transmitter": transmitter,
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not passed:
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise SystemExit(f"FAIL: {failed}")
    print(f"PASS: exact two-node CTT HIL evidence written to {args.output}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--receiver-elf", type=Path, required=True)
    gen.add_argument("--transmitter-elf", type=Path, required=True)
    gen.add_argument("--output-dir", type=Path, required=True)
    gen.set_defaults(func=generate)

    check = sub.add_parser("evaluate")
    check.add_argument("--receiver-stats", type=Path, required=True)
    check.add_argument("--receiver-queue", type=Path, required=True)
    check.add_argument("--transmitter-state", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    check.set_defaults(func=evaluate)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
