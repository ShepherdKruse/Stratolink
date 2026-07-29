#!/usr/bin/env python3
"""Take one self-healing PPK2 source-meter snapshot for the launch bench.

The two macOS CDC interface suffixes are not stable across reconnects.  Probe
both interfaces for the metadata/control endpoint instead of assuming that E4
is always control and E2 is always samples.  The rail is intentionally left on
after capture so reconnecting the PPK2 does not reset the payload.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import time

import serial
from serial.tools import list_ports

from ppk2_api.ppk2_api import PPK2_API

from evidence_provenance import write_create_once


def ppk2_ports() -> list[str]:
    return sorted(
        port.device
        for port in list_ports.comports()
        if port.product == "PPK2" and port.device.startswith("/dev/cu.")
    )


def open_endpoints() -> tuple[PPK2_API, str, str]:
    ports = ppk2_ports()
    if len(ports) != 2:
        raise RuntimeError(f"expected two PPK2 CDC interfaces, found {ports}")

    for control_port in ports:
        control = PPK2_API(control_port)
        try:
            # Recover a profiler whose previous host vanished while sampling:
            # stop the stream, discard trailing binary frames, then request
            # human-readable metadata on a clean input buffer.
            control.stop_measuring()
            time.sleep(0.1)
            control.ser.reset_input_buffer()
            if control.get_modifiers():
                data_port = next(port for port in ports if port != control_port)
                return control, control_port, data_port
        except (UnicodeDecodeError, IndexError, ValueError):
            # The sample endpoint is a raw binary stream; interpreting it as
            # metadata can fail UTF-8 decoding. That positively identifies it
            # as the non-control side, so continue to the other interface.
            pass
        control.ser.close()

    raise RuntimeError("neither PPK2 CDC interface answered the metadata probe")


def snapshot(seconds: float, source_mv: int) -> dict[str, float | int | str]:
    control, control_port, data_port = open_endpoints()
    raw = None
    sample_bytes = bytearray()
    sample_port = ""
    try:
        # A previous host can disappear while streaming and leave the PPK2
        # sampler latched. Stop first so a fresh snapshot always begins from a
        # known transport state.
        control.stop_measuring()
        time.sleep(0.1)
        control.use_source_meter()
        control.set_source_voltage(source_mv)
        time.sleep(0.2)
        control.toggle_DUT_power("ON")
        time.sleep(0.5)

        raw = serial.Serial(data_port, timeout=0)
        raw.reset_input_buffer()
        control.ser.reset_input_buffer()
        control.remainder = {"sequence": b"", "len": 0}
        control.rolling_avg = None
        control.rolling_avg4 = None
        control.start_measuring()

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            # PPK2 firmware revisions expose samples either on the second CDC
            # endpoint or on the same endpoint that accepts commands. Detect
            # the active stream once per fresh connection and stay on it.
            if not sample_port:
                if raw.in_waiting:
                    sample_port = data_port
                elif control.ser.in_waiting:
                    sample_port = control_port
            stream = raw if sample_port == data_port else control.ser
            waiting = stream.in_waiting if sample_port else 0
            if waiting:
                # Drain the CDC endpoint as fast as possible and decode only
                # after capture.  Decoding 100 ksample/s in the hot loop can
                # overflow macOS's CDC buffer, drop one byte, and permanently
                # shift every subsequent 32-bit PPK2 frame.
                sample_bytes.extend(stream.read(waiting))
            else:
                time.sleep(0.001)
        control.stop_measuring()
    finally:
        if raw is not None:
            raw.close()
        control.ser.close()

    if not sample_bytes:
        raise RuntimeError("PPK2 returned no decoded samples")

    # A stream may begin 1-3 bytes into a USB frame.  Score all four phases by
    # the PPK2's 3-bit range field: valid hardware ranges are 0..4, while a
    # shifted byte stream produces 5..7 about 3/8 of the time.  This prevents a
    # byte-phase error from masquerading as a 20 mA board load.
    phase_invalid: list[float] = []
    phase_logic_nonzero: list[float] = []
    phase_range_histograms: list[list[int]] = []
    for phase in range(4):
        values = [
            int.from_bytes(sample_bytes[i : i + 4], "little")
            for i in range(phase, len(sample_bytes) - 3, 4)
        ]
        ranges = [((value >> 14) & 0x7) for value in values]
        phase_range_histograms.append(
            [ranges.count(rng) for rng in range(8)]
        )
        phase_invalid.append(
            sum(1 for value in ranges if value > 4) / max(1, len(ranges))
        )
        # Logic inputs occupy the high byte and are all low in this harness.
        # Bits 17..23 cannot be used as a framing invariant: this PPK2 firmware
        # puts a rolling sequence there even though the Python API ignores it.
        phase_logic_nonzero.append(
            sum(1 for value in values if ((value >> 24) & 0xFF) != 0)
            / max(1, len(values))
        )
    frame_phase = min(
        range(4),
        key=lambda phase: phase_invalid[phase] + phase_logic_nonzero[phase],
    )
    aligned_len = (len(sample_bytes) - frame_phase) // 4 * 4
    selected_words = [
        int.from_bytes(sample_bytes[i : i + 4], "little")
        for i in range(frame_phase, frame_phase + aligned_len, 4)
    ]
    range_histogram = [
        sum(1 for value in selected_words if ((value >> 14) & 0x7) == rng)
        for rng in range(8)
    ]
    control.remainder = {"sequence": b"", "len": 0}
    control.rolling_avg = None
    control.rolling_avg4 = None
    samples, _ = control.get_samples(
        bytes(sample_bytes[frame_phase : frame_phase + aligned_len])
    )

    # Real board peaks are below 250 mA. Values outside this range are decoder
    # desynchronization artifacts, not physical current.
    good = [sample for sample in samples if -500 <= sample < 250_000]
    if not good:
        raise RuntimeError("all PPK2 samples were outside the physical range")
    ordered = sorted(good)
    floor = ordered[: max(1, len(ordered) // 5)]
    samples_per_bin = max(1, int(len(samples) / max(seconds, 0.1) * 5.0))
    bin_medians = []
    for start in range(0, len(samples), samples_per_bin):
        physical = [
            sample
            for sample in samples[start : start + samples_per_bin]
            if -500 <= sample < 250_000
        ]
        if physical:
            bin_medians.append(round(statistics.median(physical), 3))
    return {
        "control_port": control_port,
        "data_port": data_port,
        "sample_port": sample_port,
        "frame_phase": frame_phase,
        "phase_invalid_fraction": [round(value, 6) for value in phase_invalid],
        "phase_logic_nonzero_fraction": [
            round(value, 6) for value in phase_logic_nonzero
        ],
        "phase_range_histograms": phase_range_histograms,
        "range_histogram": range_histogram,
        "raw_prefix_hex": bytes(sample_bytes[:32]).hex(),
        "source_mv": source_mv,
        "seconds": seconds,
        "samples": len(samples),
        "artifact_fraction": round(1.0 - len(good) / len(samples), 6),
        "mean_ua": round(statistics.fmean(good), 3),
        "median_ua": round(statistics.median(good), 3),
        "floor_ua": round(statistics.fmean(floor), 3),
        "p95_ua": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
        "max_ua": round(ordered[-1], 3),
        "five_second_median_ua": bin_medians[: math.ceil(seconds / 5.0)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--source-mv", type=int, default=4660)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional create-once JSON evidence path",
    )
    args = parser.parse_args()
    if not 800 <= args.source_mv <= 5000:
        parser.error("--source-mv must be within the PPK2 800-5000 mV range")
    if not 0.1 <= args.seconds <= 120:
        parser.error("--seconds must be between 0.1 and 120")
    result = snapshot(args.seconds, args.source_mv)
    if args.output is not None:
        payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
        write_create_once(args.output, payload)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
