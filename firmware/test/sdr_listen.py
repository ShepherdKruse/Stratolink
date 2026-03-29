#!/usr/bin/env python3
"""Listen for LoRa transmissions on US915 sub-band 2 using RTL-SDR.

Monitors 903.9-905.3 MHz for energy bursts consistent with LoRa chirps.
Prints a live power spectrum and flags potential transmissions.
"""
import sys, time, numpy as np
from rtlsdr import RtlSdr

CENTER_FREQ = 904.6e6   # Center of US915 FSB2 (903.9-905.3 MHz)
SAMPLE_RATE = 2.4e6     # 2.4 MHz covers the full sub-band
GAIN = 40               # Moderate gain
FFT_SIZE = 1024
LISTEN_SEC = 120        # Listen for 2 minutes (at least 2 TX cycles)

sdr = RtlSdr()
sdr.sample_rate = SAMPLE_RATE
sdr.center_freq = CENTER_FREQ
sdr.gain = GAIN

print(f"RTL-SDR listening on {CENTER_FREQ/1e6:.1f} MHz +/- {SAMPLE_RATE/2e6:.1f} MHz")
print(f"Covering {(CENTER_FREQ - SAMPLE_RATE/2)/1e6:.1f} - {(CENTER_FREQ + SAMPLE_RATE/2)/1e6:.1f} MHz")
print(f"Gain: {GAIN} dB, FFT: {FFT_SIZE} bins")
print(f"Listening for {LISTEN_SEC}s. LoRa TX should appear every ~60s.\n")

# Collect baseline noise floor
print("Measuring noise floor...", end=" ", flush=True)
baseline_samples = sdr.read_samples(FFT_SIZE * 64)
baseline_power = np.mean(np.abs(baseline_samples) ** 2)
print(f"baseline power: {10*np.log10(baseline_power+1e-12):.1f} dB\n")

threshold_db = 6  # dB above noise floor to flag as potential TX
start = time.time()
tx_count = 0

print("Time       | Peak dB | Above BL | Status")
print("-" * 50)

try:
    while time.time() - start < LISTEN_SEC:
        samples = sdr.read_samples(FFT_SIZE * 16)
        power = np.mean(np.abs(samples) ** 2)
        power_db = 10 * np.log10(power + 1e-12)
        baseline_db = 10 * np.log10(baseline_power + 1e-12)
        above = power_db - baseline_db

        # Also check spectral peak (LoRa chirps sweep across bandwidth)
        fft_vals = np.fft.fftshift(np.fft.fft(samples[:FFT_SIZE]))
        fft_mag = np.abs(fft_vals) ** 2
        peak_db = 10 * np.log10(np.max(fft_mag) + 1e-12)
        mean_db = 10 * np.log10(np.mean(fft_mag) + 1e-12)
        spectral_peak = peak_db - mean_db

        elapsed = time.time() - start
        ts = f"{int(elapsed):3d}s"

        if above > threshold_db or spectral_peak > 15:
            tx_count += 1
            print(f"{ts}        | {power_db:+6.1f}  | {above:+5.1f} dB  | ** TX DETECTED ** (spectral peak {spectral_peak:.0f} dB)")
        else:
            # Print periodic status every 5 seconds
            if int(elapsed) % 5 == 0:
                print(f"{ts}        | {power_db:+6.1f}  | {above:+5.1f} dB  | quiet", end="\r", flush=True)

        time.sleep(0.2)

except KeyboardInterrupt:
    pass

sdr.close()
print(f"\n\nDone. Detected {tx_count} potential TX events in {int(time.time()-start)}s.")
if tx_count == 0:
    print("No transmissions detected. Check:")
    print("  - Board is powered and running")
    print("  - LoRaWAN keys in secrets.h are valid")
    print("  - Antenna is connected to the board")
