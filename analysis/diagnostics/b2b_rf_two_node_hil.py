#!/usr/bin/env python3
"""Strict evaluator for the bounded two-node B2B RF integration diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


STATE_BYTES = 85
MAGIC = 0x42524631
EXPECTED_WIRE_BYTES = 23
EXPECTED_SOURCE = 0x0101
EXPECTED_LAT_CD = 3777
EXPECTED_LON_CD = -12241
EXPECTED_ALT_HM = 123
EXPECTED_AGE_MIN = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) != STATE_BYTES:
        raise SystemExit(f"{path}: {len(raw)} bytes, expected {STATE_BYTES}")
    return {
        "raw": raw,
        "magic": struct.unpack_from("<I", raw, 0)[0],
        "uptime_ms": struct.unpack_from("<I", raw, 4)[0],
        "window_ms": struct.unpack_from("<I", raw, 8)[0],
        "role": raw[12],
        "radio_init_ok": raw[13],
        "complete": raw[14],
        "pending_count": raw[15],
        "frame_valid": raw[16],
        "frame_type": raw[17],
        "frame_ttl": raw[18],
        "frame_msg_id": raw[19],
        "frame_src": struct.unpack_from("<H", raw, 20)[0],
        "crumb_lat_cd": struct.unpack_from("<h", raw, 22)[0],
        "crumb_lon_cd": struct.unpack_from("<h", raw, 24)[0],
        "crumb_alt_hm": raw[26],
        "crumb_age_min": raw[27],
        "wire_len": raw[28],
        "wire": raw[32:],
    }


def wire_shape_ok(receiver: dict) -> bool:
    wire = receiver["wire"][: receiver["wire_len"]]
    return (
        len(wire) == EXPECTED_WIRE_BYTES
        and wire[:3] == b"SB\x03"
        and wire[3:5] == b"\x01\x01"
        and wire[5] == receiver["frame_msg_id"]
        and wire[6] == 3
        and wire[7] == 0
        and wire[8] == 14
        and wire[9:15] == bytes.fromhex("0ec1d02f7b02")
    )


def evaluate(tx_path: Path, rx_path: Path, output: Path) -> None:
    tx = decode(tx_path)
    rx = decode(rx_path)
    checks = {
        "tx_magic": tx["magic"] == MAGIC,
        "tx_role": tx["role"] == 1,
        "tx_radio_initialized": tx["radio_init_ok"] == 1,
        "tx_complete": tx["complete"] == 1,
        "tx_window_bounded": 20000 <= tx["window_ms"] <= 20100,
        "rx_magic": rx["magic"] == MAGIC,
        "rx_role": rx["role"] == 2,
        "rx_radio_initialized": rx["radio_init_ok"] == 1,
        "rx_complete": rx["complete"] == 1,
        "rx_window_bounded": 150000 <= rx["window_ms"] <= 150100,
        "rx_one_authenticated_pending": (
            rx["pending_count"] == 1 and rx["frame_valid"] == 1
        ),
        "rx_crumb_identity": (
            rx["frame_type"] == 0
            and rx["frame_ttl"] == 3
            and rx["frame_src"] == EXPECTED_SOURCE
        ),
        "rx_crumb_value": (
            rx["crumb_lat_cd"] == EXPECTED_LAT_CD
            and rx["crumb_lon_cd"] == EXPECTED_LON_CD
            and rx["crumb_alt_hm"] == EXPECTED_ALT_HM
        ),
        "rx_delayed_age": rx["crumb_age_min"] == EXPECTED_AGE_MIN,
        "rx_wire_shape": wire_shape_ok(rx),
    }
    passed = all(checks.values())
    result = {
        "schema": "stratolink-b2b-two-node-rf-hil-v1",
        "passed": passed,
        "scope": (
            "two identical StratoLink boards using a public diagnostic key; "
            "proves the production LongFast B2B radio/auth/queue/age path, "
            "not flight-key secrecy or multi-hop range"
        ),
        "checks": checks,
        "transmitter": {
            key: value
            for key, value in tx.items()
            if key not in {"raw", "wire"}
        },
        "receiver": {
            key: value
            for key, value in rx.items()
            if key not in {"raw", "wire"}
        },
        "artifacts": {
            "transmitter_state": {
                "path": str(tx_path.resolve()),
                "bytes": tx_path.stat().st_size,
                "sha256": sha256(tx_path),
            },
            "receiver_state": {
                "path": str(rx_path.resolve()),
                "bytes": rx_path.stat().st_size,
                "sha256": sha256(rx_path),
            },
        },
    }
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as error:
        raise SystemExit(f"refusing to overwrite {output}") from error
    if not passed:
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise SystemExit(f"FAIL: {failed}")
    print(f"PASS: exact two-node B2B RF HIL written to {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transmitter-state", type=Path, required=True)
    parser.add_argument("--receiver-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.transmitter_state, args.receiver_state, args.output)


if __name__ == "__main__":
    main()
