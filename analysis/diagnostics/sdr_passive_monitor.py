#!/usr/bin/env python3
"""Create-once passive 906.875 MHz envelope capture with burst detection."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

import numpy as np

from evidence_provenance import record as provenance_record


def commit_partial_create_once(partial: Path, path: Path) -> None:
    try:
        os.link(partial, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite passive SDR evidence: {path}"
        ) from error
    partial.unlink()


def detect_bursts(
    time_s: np.ndarray,
    power_db: np.ndarray,
    threshold_db: float,
    *,
    merge_gap_ms: float = 120,
    minimum_ms: float = 8,
) -> list[dict[str, float | bool]]:
    if len(time_s) != len(power_db) or len(time_s) < 2:
        raise ValueError("time/power arrays must have equal length >= 2")
    step = float(np.median(np.diff(time_s)))
    if not np.isfinite(step) or step <= 0:
        raise ValueError("time axis is invalid")
    hot = power_db > threshold_db
    gap_limit = max(1, int(round(merge_gap_ms / (step * 1000))))
    bursts: list[dict[str, float | bool]] = []
    i = 0
    while i < len(hot):
        if not hot[i]:
            i += 1
            continue
        start = i
        last_hot = i
        gap = 0
        cursor = i + 1
        while cursor < len(hot):
            if hot[cursor]:
                last_hot = cursor
                gap = 0
            else:
                gap += 1
                if gap >= gap_limit:
                    break
            cursor += 1
        duration_ms = (last_hot - start + 1) * step * 1000
        if duration_ms >= minimum_ms:
            segment = power_db[start:last_hot + 1]
            bursts.append(
                {
                    "start_seconds": round(float(time_s[start]), 6),
                    "duration_ms": round(duration_ms, 3),
                    "peak_db": round(float(np.max(segment)), 3),
                    "longfast_duration_candidate": 350 <= duration_ms <= 850,
                }
            )
        i = max(cursor, last_hot + 1)
    return bursts


def atomic_json(path: Path, value: dict) -> None:
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
        partial = Path(handle.name)
    try:
        os.link(partial, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite passive SDR evidence: {path}"
        ) from error
    finally:
        partial.unlink(missing_ok=True)


def capture_record(path: Path) -> dict[str, str | int]:
    """Bind a binary sample capture without exposing append semantics."""
    provenance = provenance_record(path)
    return {
        "path": provenance["path"],
        "bytes": provenance["bytes"],
        "sha256": provenance["sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--frequency-hz", type=float, default=906.875e6)
    parser.add_argument("--sample-rate", type=float, default=1.024e6)
    parser.add_argument("--gain-db", type=float, default=40.2)
    parser.add_argument("--threshold-above-floor-db", type=float, default=6.0)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 3600:
        parser.error("--seconds must be between 5 and 3600")
    if not 0 < args.sample_rate <= 3.2e6:
        parser.error("--sample-rate must be within (0, 3.2e6]")

    # Keep argument inspection and --help usable on analysis hosts that do not
    # have the optional RTL-SDR Python/native stack installed. Hardware is
    # required only after the complete invocation has been validated.
    from rtlsdr import RtlSdr

    prefix = args.prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    npz_path = prefix.with_suffix(".npz")
    summary_path = prefix.with_suffix(".json")
    collisions = [
        path
        for path in (npz_path, summary_path)
        if path.exists() or path.with_suffix(path.suffix + ".partial").exists()
    ]
    if collisions:
        raise SystemExit(
            "refusing to overwrite passive SDR evidence: "
            + ", ".join(str(path) for path in collisions)
        )

    nfft = 1024
    block = 65536
    chunks_per_block = block // nfft
    bins = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / args.sample_rate))
    signal_band = (np.abs(bins) <= 125_000) & (np.abs(bins) >= 12_000)
    guard_band = (np.abs(bins) >= 250_000) & (np.abs(bins) <= 450_000)
    window = np.hanning(nfft)
    signal_power: list[np.ndarray] = []
    guard_power: list[np.ndarray] = []
    started_utc = datetime.now(timezone.utc)
    sdr = RtlSdr()
    try:
        sdr.sample_rate = args.sample_rate
        sdr.center_freq = args.frequency_hz
        sdr.gain = args.gain_db
        blocks = int(np.ceil(args.seconds * args.sample_rate / block))
        for _ in range(blocks):
            samples = sdr.read_samples(block)
            shaped = samples[:chunks_per_block * nfft].reshape(
                chunks_per_block, nfft
            )
            spectrum = np.fft.fftshift(
                np.abs(np.fft.fft(shaped * window, axis=1)) ** 2,
                axes=1,
            )
            signal_power.append(
                10 * np.log10(np.mean(spectrum[:, signal_band], axis=1) + 1e-12)
            )
            guard_power.append(
                10 * np.log10(np.mean(spectrum[:, guard_band], axis=1) + 1e-12)
            )
    finally:
        sdr.close()

    signal_db = np.concatenate(signal_power)
    guard_db = np.concatenate(guard_power)
    step = nfft / args.sample_rate
    time_s = np.arange(len(signal_db), dtype=np.float64) * step
    keep = time_s < args.seconds
    time_s = time_s[keep]
    signal_db = signal_db[keep]
    guard_db = guard_db[keep]
    floor = float(np.median(signal_db))
    threshold = floor + args.threshold_above_floor_db
    bursts = detect_bursts(time_s, signal_db, threshold)

    npz_partial = npz_path.with_suffix(npz_path.suffix + ".partial")
    with npz_partial.open("xb") as handle:
        np.savez_compressed(
            handle,
            time_seconds=time_s.astype(np.float32),
            signal_power_db=signal_db.astype(np.float32),
            guard_power_db=guard_db.astype(np.float32),
            frequency_hz=args.frequency_hz,
            sample_rate=args.sample_rate,
            gain_db=args.gain_db,
        )
        handle.flush()
        os.fsync(handle.fileno())
    commit_partial_create_once(npz_partial, npz_path)
    summary = {
        "created_utc": started_utc.isoformat(timespec="milliseconds"),
        "scope": (
            "receive-only RTL-SDR energy detection; burst duration is not "
            "protocol demodulation or proof that StratoLink relayed a packet"
        ),
        "frequency_hz": args.frequency_hz,
        "sample_rate": args.sample_rate,
        "gain_db": args.gain_db,
        "duration_seconds": round(float(time_s[-1] + step), 3),
        "time_resolution_ms": round(step * 1000, 6),
        "signal_band_hz": [-125000, -12000, 12000, 125000],
        "floor_db": round(floor, 3),
        "threshold_db": round(threshold, 3),
        "guard_floor_db": round(float(np.median(guard_db)), 3),
        "burst_count": len(bursts),
        "longfast_duration_candidate_count": sum(
            bool(row["longfast_duration_candidate"]) for row in bursts
        ),
        "bursts": bursts,
        "npz": capture_record(npz_path),
    }
    atomic_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
