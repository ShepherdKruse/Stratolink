"""SYNTHETIC offline IQ regression tests; none of these fixtures are RF evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

SCRIPT = Path(__file__).with_name("flipper_ctt_iq_test_20261009.py")
SPEC = importlib.util.spec_from_file_location("ctt_iq", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FS = 1_024_000
GOOD = bytes.fromhex("AA AA AA D3 91 78 55 4C 33 58")
BAD = bytes.fromhex("AA AA AA D3 91 78 55 4C 33 5A")


def synthetic_iq(frame=GOOD, *, baud=25000, offset=0, polarity=1,
                 tail=0.009, amplitude=35, noise=1.2, truncate_bits=0,
                 cw=False, seed=4, leading=0.008013):
    """Independent CPFSK waveform generator using literal bytes, not decoder helpers."""
    bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
    bits = bits[:len(bits) - truncate_bits] if truncate_bits else bits
    packet_s = len(bits) / baud
    t = np.arange(int((leading + packet_s + tail + 0.008) * FS)) / FS
    index = np.floor((t - leading) * baud).astype(int)
    inside = (t >= leading) & (t < leading + packet_s + tail)
    symbols = bits[np.clip(index, 0, len(bits) - 1)]
    frequency = offset + polarity * 25390.625 * (2 * symbols.astype(float) - 1)
    if cw:
        frequency[:] = offset + 25390.625
    phase = 0.713 + 2 * np.pi * np.cumsum(frequency) / FS
    envelope = amplitude * (0.8 + 0.2 * np.cos(2 * np.pi * t / 0.011))
    signal = inside * envelope * np.exp(1j * phase)
    rng = np.random.default_rng(seed)
    signal += noise * (rng.normal(size=len(t)) + 1j * rng.normal(size=len(t)))
    values = np.column_stack((signal.real, signal.imag)) + 127.5
    return np.clip(np.rint(values), 0, 255).astype(np.uint8).tobytes()


class DecoderTest(unittest.TestCase):
    def analyze(self, raw, **kwargs):
        return MODULE.analyze(raw, sample_rate=FS, center_hz=434e6, **kwargs)

    def test_good_reconstructs_measured_bytes_and_crc(self):
        # Catches reversed bit order, constant/no frame return, or wrong CRC polynomial.
        result = self.analyze(synthetic_iq())
        self.assertEqual(len(result["frames"]), 1)
        frame = result["frames"][0]
        self.assertEqual(frame["on_air_hex"], GOOD.hex())
        self.assertTrue(frame["crc_ok"])
        self.assertAlmostEqual(frame["deviation_hz"], 25390.625, delta=1200)
        self.assertAlmostEqual(frame["estimated_bitrate"], 25000, delta=100)
        self.assertLess(frame["timing_rms_samples"], 3)
        self.assertFalse(result["rf_provenance_verified"])

    def test_bad_crc_is_reported_not_corrected_or_dropped(self):
        # Catches CRC bypass or replacing measured bytes with the expected fixture.
        frames = self.analyze(synthetic_iq(BAD))["frames"]
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["on_air_hex"], BAD.hex())
        self.assertFalse(frames[0]["crc_ok"])

    def test_other_payload_not_expected_fixture(self):
        # Catches a matcher which manufactures only the requested tag ID/CRC.
        frames = self.analyze(synthetic_iq(bytes.fromhex("AA AA AA D3 91 00 00 00 00 00")))["frames"]
        self.assertEqual(frames[0]["payload_hex"], "0000000000")
        self.assertTrue(frames[0]["crc_ok"])

    def test_phase_cfo_rate_noise_and_amplitude_variation(self):
        # Catches fixed 41-sample slicing, zero-CFO thresholding, or nominal-only timing.
        frame = self.analyze(synthetic_iq(baud=24910, offset=11200, amplitude=22,
                                        noise=2.0, leading=0.009027))["frames"][0]
        self.assertEqual(frame["on_air_hex"], GOOD.hex())
        self.assertAlmostEqual(frame["estimated_bitrate"], 24910, delta=120)
        self.assertAlmostEqual(frame["carrier_offset_hz"], 11200, delta=1600)

    def test_inverted_frequency_polarity_is_explicit(self):
        # Catches silently assuming high frequency is always bit one.
        frame = self.analyze(synthetic_iq(polarity=-1, offset=-7300))["frames"][0]
        self.assertEqual(frame["on_air_hex"], GOOD.hex())
        self.assertEqual(frame["one_tone"], "lower")
        self.assertAlmostEqual(frame["carrier_offset_hz"], -7300, delta=1200)

    def test_long_carrier_tail_not_mislabeled_as_packet_duration(self):
        # Catches using the full burst's tail-dominated tone distribution or 80/25k airtime.
        result = self.analyze(synthetic_iq(tail=0.333))
        self.assertEqual(len(result["frames"]), 1)
        burst = result["carriers"][0]
        self.assertTrue(burst["complete"])
        self.assertAlmostEqual(burst["duration_ms"], 336.2, delta=0.2)
        self.assertAlmostEqual(result["frames"][0]["packet_duration_ms"], 3.2, delta=0.03)
        self.assertGreater(result["frames"][0]["post_packet_carrier_ms"], 332)

    def test_noise_cw_and_wrong_sync_produce_no_frame(self):
        # Catches fabricating a frame from RF energy alone or ignoring sync.
        for raw in (synthetic_iq(amplitude=0), synthetic_iq(cw=True),
                    synthetic_iq(bytes.fromhex("AA AA AA D3 90 78 55 4C 33 58"))):
            with self.subTest(length=len(raw)):
                self.assertEqual(self.analyze(raw)["frames"], [])

    def test_wrong_symbol_rates_are_not_reinterpreted_as_ctt(self):
        # Catches identifying the known bytes without enforcing observed CTT timing.
        for baud in (20000, 30000):
            self.assertEqual(self.analyze(synthetic_iq(baud=baud))["frames"], [])

    def test_corrupted_payload_not_just_the_crc_byte_is_rejected(self):
        frame = self.analyze(synthetic_iq(bytes.fromhex("AA AA AA D3 91 79 55 4C 33 58")))["frames"][0]
        self.assertEqual(frame["payload_hex"], "79554c3358")
        self.assertFalse(frame["crc_ok"])

    def test_truncated_payload_does_not_borrow_quiet_noise(self):
        # Catches unbounded slicing beyond the actual carrier.
        self.assertEqual(self.analyze(synthetic_iq(truncate_bits=9, tail=0))["frames"], [])

    def test_clipped_carrier_does_not_claim_complete_duration(self):
        # Catches confusing capture boundaries with RF-off observations.
        raw = synthetic_iq(tail=0.333)
        result = self.analyze(raw[:-int(0.02 * FS) * 2])
        self.assertEqual(len(result["frames"]), 1)
        self.assertFalse(result["carriers"][0]["complete"])

    def test_carrier_at_left_capture_edge_is_marked_clipped(self):
        # Catches treating the first captured sample as an observed RF-on edge.
        result = self.analyze(synthetic_iq()[int(0.008 * FS) * 2:])
        self.assertEqual(len(result["frames"]), 1)
        self.assertTrue(result["carriers"][0]["left_clipped"])
        self.assertFalse(result["carriers"][0]["complete"])

    def test_all_active_carrier_without_baseline_is_inconclusive_not_quiet(self):
        # Catches treating a baseline-induced detection miss as verified silence.
        raw = synthetic_iq(tail=0.333)[8207 * 2:352472 * 2]
        result = self.analyze(raw)
        self.assertEqual(result["carriers"], [])
        self.assertEqual(result["frames"], [])
        self.assertIs(result.get("verified_quiet", True), False)
        self.assertEqual(result["decode_status"], "inconclusive")

    def test_crc_success_does_not_qualify_frequency_or_phy_profile(self):
        # Catches promoting decoded bytes to PHY qualification with wrong LO metadata.
        result = MODULE.analyze(synthetic_iq(), sample_rate=FS, center_hz=433e6)
        self.assertEqual(result["valid_crc_count"], 1)
        self.assertIs(result.get("phy_profile_qualified", True), False)

    def test_multiple_frames_are_not_merged_or_phase_duplicates(self):
        result = self.analyze(synthetic_iq() + synthetic_iq(BAD, seed=7))
        self.assertEqual([f["crc_ok"] for f in result["frames"]], [True, False])

    def test_malformed_and_unbounded_inputs_rejected(self):
        for raw, rate in ((b"x", FS), (b"", FS), (bytes(200), float("nan")),
                          (bytes(200), 1), (bytes(200), FS)):
            with self.subTest(length=len(raw), rate=rate), self.assertRaises(ValueError):
                MODULE.analyze(raw, sample_rate=rate, center_hz=434e6)

    def test_cli_marks_synthetic_and_refuses_overwrite(self):
        # Catches treating fixture bytes as actual RF evidence or truncating prior reports.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.u8"
            output = Path(temp) / "result.json"
            path.write_bytes(synthetic_iq())
            command = [sys.executable, str(SCRIPT), "--iq", str(path), "--sample-rate",
                       str(FS), "--center-hz", "434000000", "--provenance", "synthetic",
                       "--output", str(output)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            saved = output.read_bytes()
            report = json.loads(saved)
            self.assertEqual(report["input_provenance"], "synthetic")
            self.assertEqual(report["input_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), saved)

    def test_actual_pinned_flight_crc_acceptance_crosscheck(self):
        # Independent C++ production implementation checks only reconstructed bytes.
        repo = SCRIPT.parents[2]
        source = repo / "firmware/src/ctt_decode.cpp"
        header = source.with_suffix(".h")
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         "171f1c6dea5d5a1e6f647e378cbd307e6fa848bd4385b4341575d107a21611b7")
        self.assertEqual(hashlib.sha256(header.read_bytes()).hexdigest(),
                         "2d28d76205f96993b83e98f76392d9987e5be5b89f49916809fae9c8601d2f01")
        with tempfile.TemporaryDirectory() as temp:
            harness = Path(temp) / "check.cpp"
            executable = Path(temp) / "check"
            harness.write_text('''#include "ctt_decode.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
int main(int argc, char** argv) {
    if (argc != 2 || std::strlen(argv[1]) != 10) return 2;
    uint8_t payload[5] = {};
    for (unsigned i = 0; i < 5; ++i) {
        char pair[3] = {argv[1][2*i], argv[1][2*i+1], 0};
        payload[i] = static_cast<uint8_t>(std::strtoul(pair, nullptr, 16));
    }
    ctt_frame_t frame = {};
    std::printf("%u\\n", ctt_decode(payload, &frame) ? 1u : 0u);
    return 0;
}
''')
            compile_run = subprocess.run([
                "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                "-I", str(source.parent), str(harness), str(source), "-o", str(executable),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_run.returncode, 0, compile_run.stderr)
            for wire, accepted in ((GOOD, True), (BAD, False),
                                   (bytes.fromhex("AA AA AA D3 91 00 00 00 00 00"), True),
                                   (bytes.fromhex("AA AA AA D3 91 01 02 03 04 E3"), True)):
                frame = self.analyze(synthetic_iq(wire))["frames"][0]
                self.assertEqual(frame["on_air_hex"], wire.hex())
                run = subprocess.run([str(executable), frame["payload_hex"]],
                                     capture_output=True, text=True, timeout=5,
                                     env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                                          "UBSAN_OPTIONS": "halt_on_error=1"})
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), "1" if accepted else "0")
                self.assertEqual(frame["crc_ok"], accepted)


if __name__ == "__main__":
    unittest.main()
