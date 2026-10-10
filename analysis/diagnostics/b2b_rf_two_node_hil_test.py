#!/usr/bin/env python3
"""Fail-closed vectors for the B2B RF diagnostic evaluator."""

from __future__ import annotations

from pathlib import Path
import struct
import tempfile

import b2b_rf_two_node_hil as hil


def state(role: int) -> bytearray:
    raw = bytearray(hil.STATE_BYTES)
    struct.pack_into("<III", raw, 0, hil.MAGIC, 200000, 20008 if role == 1 else 150008)
    raw[12:17] = bytes((role, 1, 1, 1 if role == 2 else 0, 1 if role == 2 else 0))
    if role == 2:
        raw[17:20] = bytes((0, 3, 7))
        struct.pack_into("<Hhh", raw, 20, hil.EXPECTED_SOURCE,
                         hil.EXPECTED_LAT_CD, hil.EXPECTED_LON_CD)
        raw[26:29] = bytes(
            (hil.EXPECTED_ALT_HM, hil.EXPECTED_AGE_MIN, hil.EXPECTED_WIRE_BYTES)
        )
        raw[32:55] = bytes.fromhex(
            "53420301010703000e0ec1d02f7b02"
            "0011223344556677"
        )
    return raw


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-b2b-rf-hil-") as tmp:
        root = Path(tmp)
        tx_path = root / "tx.bin"
        rx_path = root / "rx.bin"
        tx_path.write_bytes(state(1))
        rx_path.write_bytes(state(2))
        hil.evaluate(tx_path, rx_path, root / "pass.json")

        corrupt = state(2)
        corrupt[27] = 1
        rx_path.write_bytes(corrupt)
        try:
            hil.evaluate(tx_path, rx_path, root / "fail.json")
        except SystemExit:
            pass
        else:
            raise AssertionError("wrong crumb age was accepted")

    print("PASS: B2B RF HIL evaluator accepts exact evidence and fails closed")


if __name__ == "__main__":
    main()
