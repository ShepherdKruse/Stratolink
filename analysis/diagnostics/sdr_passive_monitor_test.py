#!/usr/bin/env python3
"""Synthetic burst-detector tests for passive RTL-SDR evidence."""

from __future__ import annotations

import numpy as np

from pathlib import Path
import subprocess
import sys
import tempfile

from sdr_passive_monitor import (
    atomic_json,
    capture_record,
    commit_partial_create_once,
    detect_bursts,
)


def main() -> None:
    help_result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("sdr_passive_monitor.py")), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--frequency-hz" in help_result.stdout

    time_s = np.arange(0, 2.0, 0.001)
    power = np.zeros_like(time_s) - 40
    power[100:300] = -28
    power[350:500] = -28
    power[1000:1473] = -25
    bursts = detect_bursts(time_s, power, -34)
    assert len(bursts) == 2
    assert abs(float(bursts[0]["duration_ms"]) - 400) <= 2
    assert bursts[0]["longfast_duration_candidate"] is True
    assert abs(float(bursts[1]["duration_ms"]) - 473) <= 2

    try:
        detect_bursts(time_s[:-1], power, -34)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched arrays were accepted")

    with tempfile.TemporaryDirectory(prefix="stratolink-sdr-atomic-test-") as raw:
        root = Path(raw)
        report = root / "capture.json"
        atomic_json(report, {"capture": 1})
        preserved = report.read_bytes()
        try:
            atomic_json(report, {"capture": 2})
        except SystemExit as error:
            assert "refusing to overwrite passive SDR evidence" in str(error)
        else:
            raise AssertionError("SDR report evidence was replaced")
        assert report.read_bytes() == preserved

        partial = root / "capture.npz.partial"
        final = root / "capture.npz"
        partial.write_bytes(b"new spectrum")
        final.write_bytes(b"old spectrum")
        try:
            commit_partial_create_once(partial, final)
        except SystemExit as error:
            assert "refusing to overwrite passive SDR evidence" in str(error)
        else:
            raise AssertionError("SDR spectrum evidence was replaced")
        assert final.read_bytes() == b"old spectrum"
        assert partial.read_bytes() == b"new spectrum"
        record = capture_record(final)
        assert record["bytes"] == len(b"old spectrum")
        assert len(str(record["sha256"])) == 64

    print(
        "PASS: SDR burst detection, atomic create-once evidence, gap merge, "
        "and duration classification"
    )


if __name__ == "__main__":
    main()
