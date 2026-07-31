#!/usr/bin/env python3
"""Regression-test the strict two-node CTT HIL evidence evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import tempfile

import ctt_two_node_hil


def put_detection(
    queue: bytearray,
    offset: int,
    *,
    raw: int,
    motus: int,
    hits: int,
    motus_valid: bool,
) -> None:
    struct.pack_into("<IIhBBHI", queue, offset, raw, motus, -83, hits,
                     int(motus_valid), 0, 7)


def passing_blobs() -> tuple[bytes, bytes, bytes]:
    stats = bytearray(32)
    struct.pack_into("<IIIIIIh", stats, 0, 24, 1, 21, 1, 0,
                     0x01020304, -83)
    struct.pack_into("<I", stats, 28, 5)

    queue = bytearray(648)
    put_detection(
        queue,
        320,
        raw=ctt_two_node_hil.REFERENCE_RAW,
        motus=0x3256E,
        hits=3,
        motus_valid=True,
    )
    put_detection(
        queue,
        340,
        raw=ctt_two_node_hil.NON_DICTIONARY_RAW,
        motus=0,
        hits=1,
        motus_valid=False,
    )
    queue[640] = 16
    queue[644] = 16

    tx = bytearray(44)
    struct.pack_into("<I", tx, 0, 0x43545831)
    struct.pack_into("<III", tx, 12, 24, 24, 0)
    struct.pack_into("<hh", tx, 24, 0, 0)
    struct.pack_into("<b", tx, 28, -9)
    tx[29] = 24
    tx[30] = 24
    tx[37] = 1
    tx[38] = 1
    return bytes(stats), bytes(queue), bytes(tx)


def evaluate(
    root: Path, stats: bytes, queue: bytes, tx: bytes, name: str
) -> tuple[Path, bool]:
    stats_path = root / f"{name}_stats.bin"
    queue_path = root / f"{name}_queue.bin"
    tx_path = root / f"{name}_tx.bin"
    output = root / f"{name}_result.json"
    stats_path.write_bytes(stats)
    queue_path.write_bytes(queue)
    tx_path.write_bytes(tx)
    args = argparse.Namespace(
        receiver_stats=stats_path,
        receiver_queue=queue_path,
        transmitter_state=tx_path,
        output=output,
    )
    try:
        ctt_two_node_hil.evaluate(args)
    except SystemExit:
        return output, False
    return output, True


def main() -> None:
    read_script = ctt_two_node_hil.savebin_script(
        {
            "s_ctt": {"address": 0x200007E0, "size": 32},
            "s_ctt_queue": {"address": 0x20000558, "size": 648},
        },
        "ctt_receiver",
    )
    assert (
        "savebin ctt_receiver_s_ctt.bin 0x200007E0 0x20" in read_script
    )
    assert (
        "savebin ctt_receiver_s_ctt_queue.bin 0x20000558 0x288"
        in read_script
    )

    stats, queue, tx = passing_blobs()
    with tempfile.TemporaryDirectory(prefix="stratolink-ctt-hil-test-") as tmp:
        root = Path(tmp)

        pass_output, accepted = evaluate(root, stats, queue, tx, "pass")
        assert accepted
        pass_result = json.loads(pass_output.read_text(encoding="utf-8"))
        assert pass_result["passed"] is True
        assert all(pass_result["checks"].values())

        corrupt_tx = bytearray(tx)
        struct.pack_into("<I", corrupt_tx, 16, 23)
        fail_output, accepted = evaluate(
            root, stats, queue, bytes(corrupt_tx), "tx_short"
        )
        assert not accepted
        fail_result = json.loads(fail_output.read_text(encoding="utf-8"))
        assert fail_result["passed"] is False
        assert fail_result["checks"]["tx_all_success"] is False

        corrupt_queue = bytearray(queue)
        corrupt_queue[330] = 2
        fail_output, accepted = evaluate(
            root, stats, bytes(corrupt_queue), tx, "reference_hits"
        )
        assert not accepted
        fail_result = json.loads(fail_output.read_text(encoding="utf-8"))
        assert fail_result["checks"]["rx_reference_aggregated"] is False

    print("PASS: CTT two-node evaluator accepts exact evidence and fails closed")


if __name__ == "__main__":
    main()
