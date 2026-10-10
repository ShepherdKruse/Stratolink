"""Offline-only bounded CTT 2-FSK analyzer. Never accesses radio hardware.

Input is interleaved unsigned-8-bit I,Q. Timing/frequency use the supplied
sample clock and LO metadata: these are not calibrated absolute measurements.
Only preamble/sync are known; all five payload bytes are reconstructed from IQ.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

MAX_SAMPLES = 12_000_000
PREFIX = np.unpackbits(np.frombuffer(bytes.fromhex("AAAAAAD391"), dtype=np.uint8))


def crc8(data):
    """CRC-8/SMBUS, init 0, polynomial 0x07, no reflection/final XOR."""
    remainder = 0
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            remainder = ((remainder << 1) ^ (7 if remainder & 128 else 0)) & 255
    return remainder


def runs(mask):
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    return zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1))


def timing_fit(frequency, bits, start, period, midpoint):
    edges = np.flatnonzero(bits[1:] != bits[:-1]) + 1
    indices, crossings = [], []
    for edge in edges:
        expected = start + edge * period
        lo = max(0, int(expected - period * 0.35))
        hi = min(len(frequency) - 1, int(expected + period * 0.35))
        values = frequency[lo:hi + 1] - midpoint
        hits = np.flatnonzero(values[:-1] * values[1:] < 0)
        if len(hits):
            cross = lo + hits - values[hits] / (values[hits + 1] - values[hits])
            crossings.append(float(cross[np.argmin(abs(cross - expected))]))
            indices.append(int(edge))
    if len(indices) < 20:
        return None
    slope, intercept = np.polyfit(indices, crossings, 1)
    rms = float(np.sqrt(np.mean((np.asarray(crossings) -
                                (intercept + slope * np.asarray(indices))) ** 2)))
    if not 0.96 * period < slope < 1.04 * period or rms > period * 0.12:
        return None
    return float(intercept), float(slope), rms, len(indices)


def decode_carrier(frequency, sample_rate):
    # Histogram peaks find the two measured tones despite a long single-tone tail.
    counts, edges = np.histogram(frequency, bins=np.arange(-150000, 150001, 1000))
    first = int(np.argmax(counts))
    centers = (edges[:-1] + edges[1:]) / 2
    other = counts.copy()
    other[abs(centers - centers[first]) < 15000] = 0
    second = int(np.argmax(other))
    if other[second] < 5 or abs(centers[first] - centers[second]) > 100000:
        return []
    midpoint = (centers[first] + centers[second]) / 2
    cumulative = np.r_[0.0, np.cumsum(frequency)]
    axis = np.arange(len(cumulative))
    candidates = []
    for baud in (24875, 25000, 25125):
        period = sample_rate / baud
        for phase in np.linspace(period * 0.25, period * 1.25, 20, endpoint=False):
            centers_sample = np.arange(phase, len(frequency) - period / 2, period)
            averages = (np.interp(centers_sample + period / 4, axis, cumulative) -
                        np.interp(centers_sample - period / 4, axis, cumulative)) / (period / 2)
            high_bits = (averages > midpoint).astype(np.int16)
            for polarity in (1, -1):
                bits = high_bits if polarity == 1 else 1 - high_bits
                if len(bits) < 80:
                    continue
                correlation = np.correlate(2 * bits - 1,
                                           2 * PREFIX.astype(np.int16) - 1, "valid")
                for index in np.flatnonzero(correlation == 40):
                    if index + 80 > len(bits):
                        continue
                    packet = bits[index:index + 80]
                    begin = centers_sample[index] - period / 2
                    if begin + 80 * period > len(frequency) + period * 0.15:
                        continue
                    packet_values = averages[index:index + 80]
                    low = float(np.median(packet_values[high_bits[index:index + 80] == 0]))
                    high = float(np.median(packet_values[high_bits[index:index + 80] == 1]))
                    # Fit the observed preamble/sync edges before reading payload.
                    # A coarse rate hypothesis must not shift the last payload bits.
                    fit = timing_fit(frequency, packet[:40], begin, period, (low + high) / 2)
                    if fit is None:
                        continue
                    actual_start, actual_period, rms, edges_count = fit
                    if actual_start + 80 * actual_period > len(frequency) + period * 0.2:
                        continue
                    actual_centers = actual_start + (np.arange(80) + 0.5) * actual_period
                    actual_values = (np.interp(actual_centers + actual_period / 4, axis, cumulative) -
                                     np.interp(actual_centers - actual_period / 4, axis, cumulative)) / (actual_period / 2)
                    actual_high = actual_values > (low + high) / 2
                    packet = actual_high if polarity == 1 else ~actual_high
                    if not np.array_equal(packet[:40], PREFIX):
                        continue
                    low = float(np.median(actual_values[~actual_high]))
                    high = float(np.median(actual_values[actual_high]))
                    packed = np.packbits(packet.astype(np.uint8)).tobytes()
                    candidates.append({
                        "start_sample": actual_start, "period_samples": actual_period,
                        "on_air_hex": packed.hex(), "payload_hex": packed[5:].hex(),
                        "crc_received": packed[-1], "crc_computed": crc8(packed[5:9]),
                        "crc_ok": crc8(packed[5:9]) == packed[-1],
                        "one_tone": "upper" if polarity == 1 else "lower",
                        "lower_tone_offset_hz": low, "upper_tone_offset_hz": high,
                        "carrier_offset_hz": (low + high) / 2,
                        "deviation_hz": (high - low) / 2,
                        "estimated_bitrate": sample_rate / actual_period,
                        "timing_rms_samples": rms, "timing_edges": edges_count,
                        "packet_duration_ms": 80 * actual_period / sample_rate * 1000,
                    })
    # Timing quality chooses among phase hypotheses; CRC never chooses/corrects data.
    selected = []
    for candidate in sorted(candidates, key=lambda value: value["timing_rms_samples"]):
        if not any(abs(candidate["start_sample"] - old["start_sample"]) <
                   sample_rate * 0.001 for old in selected):
            selected.append(candidate)
    return sorted(selected, key=lambda value: value["start_sample"])


def analyze(raw, *, sample_rate, center_hz):
    if (not math.isfinite(sample_rate) or not 200000 <= sample_rate <= 2400000 or
            not math.isfinite(center_hz) or center_hz <= 0 or len(raw) % 2 or
            not 1024 <= len(raw) // 2 <= MAX_SAMPLES):
        raise ValueError("Require paired u8 IQ, 1024..12000000 samples, 0.2..2.4 Msps, finite LO")
    iq = np.frombuffer(raw, dtype=np.uint8).astype(np.float64).reshape(-1, 2) - 127.5
    signal = iq[:, 0] + 1j * iq[:, 1]
    energy_window = max(8, round(sample_rate / 25000))
    energy = np.convolve(abs(signal) ** 2, np.ones(energy_window) / energy_window, "same")
    floor = float(np.percentile(energy, 1))
    threshold = max(9.0, floor * 8)
    frequency = np.angle(signal[1:] * signal[:-1].conj()) * sample_rate / (2 * np.pi)
    smooth = max(3, round(sample_rate / 25000 / 4))
    frequency = np.convolve(frequency, np.ones(smooth) / smooth, "same")
    carriers, frames = [], []
    for start, end in runs(energy > threshold):
        if end - start < sample_rate * 0.001:
            continue
        start, end = int(start), min(int(end), len(frequency))
        complete = start > energy_window and end < len(frequency) - energy_window
        carrier = {"start_seconds": start / sample_rate, "end_seconds": end / sample_rate,
                   "duration_ms": (end - start) / sample_rate * 1000, "complete": complete,
                   "left_clipped": start <= energy_window,
                   "right_clipped": end >= len(frequency) - energy_window}
        carrier_index = len(carriers)
        carriers.append(carrier)
        for frame in decode_carrier(frequency[start:end], sample_rate):
            frame["carrier_index"] = carrier_index
            frame["start_seconds"] = (start + frame.pop("start_sample")) / sample_rate
            frame["post_packet_carrier_ms"] = max(0.0, carrier["end_seconds"] * 1000 -
                frame["start_seconds"] * 1000 - frame["packet_duration_ms"])
            frame["packet_end_basis"] = "80 reconstructed bits and fitted clock; not measured RF-off"
            frames.append(frame)
    return {"schema": "stratolink.ctt_offline_iq.v1", "rf_provenance_verified": False,
            "phy_profile_qualified": False, "verified_quiet": False,
            "decode_status": "decoded_frames" if frames else "inconclusive",
            "baseline_limit": "Absent quiet samples can hide a continuous carrier in the inferred energy floor; empty carriers/frames are inconclusive, not verified silence",
            "sample_rate": sample_rate, "center_hz": center_hz, "complex_samples": len(signal),
            "sample_clock_calibrated": False, "frequency_reference": "relative to supplied receiver LO",
            "iq_convention": "I + jQ; positive phase rotation is positive frequency",
            "energy_floor_u8_squared": floor, "energy_threshold_u8_squared": threshold,
            "carrier_duration_basis": "Observed above-threshold envelope, not calibrated RF power/off proof",
            "carrier_edge_resolution_ms": energy_window / sample_rate * 1000,
            "clipped_sample_byte_fraction": float(np.mean((iq <= -127.5) | (iq >= 127.5))),
            "carriers": carriers, "frames": frames, "valid_crc_count": sum(f["crc_ok"] for f in frames),
            "scope": "Offline bit/CRC evidence only; no proof of transmitter identity, receiver acceptance, or relay"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iq", required=True, type=Path)
    parser.add_argument("--sample-rate", required=True, type=float)
    parser.add_argument("--center-hz", required=True, type=float)
    parser.add_argument("--provenance", required=True, choices=("synthetic", "captured-unverified"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Refusing to overwrite existing output")
    if args.iq.stat().st_size > MAX_SAMPLES * 2:
        parser.error("Input exceeds finite analysis limit")
    raw = args.iq.read_bytes()
    result = analyze(raw, sample_rate=args.sample_rate, center_hz=args.center_hz)
    result.update(input_provenance=args.provenance, input_path=str(args.iq.resolve()),
                  input_sha256=hashlib.sha256(raw).hexdigest())
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "frames": len(result["frames"]),
                      "valid_crc_count": result["valid_crc_count"],
                      "decode_status": result["decode_status"],
                      "phy_profile_qualified": False, "verified_quiet": False,
                      "input_provenance": args.provenance}))


if __name__ == "__main__":
    main()
