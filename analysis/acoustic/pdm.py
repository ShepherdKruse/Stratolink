"""
PDM / decimation toolkit for the Stratolink T3902 mic bench work.

Two jobs:
  1. Model the mic without hardware: `sigma_delta_modulate()` turns a PCM signal
     into a PDM bitstream (so the host pipeline + decoders can be validated today).
  2. Decode PDM -> PCM two ways for comparison:
       - decode_sinc1()  : EXACTLY what the firmware does (count ones over 320
                           bits, subtract 160).  1st-order sinc, no DC block.
       - decode_proper() : polyphase decimation with a real anti-alias FIR + a
                           DC block - the front-end we should port to firmware.

PDM clock 3.000 MHz, decimation 320 -> 9375 Hz PCM (matches mic_acoustic.cpp).
"""
from __future__ import annotations
import numpy as np
from scipy import signal

PDM_CLK_HZ = 3_000_000
DECIM = 320
PCM_HZ = PDM_CLK_HZ // DECIM        # 9375


def sigma_delta_modulate(x: np.ndarray, order: int = 2) -> np.ndarray:
    """Model a PDM MEMS mic: PCM in [-1,1] at PDM_CLK_HZ -> packed uint8 PDM bits.
    `x` must already be sampled at PDM_CLK_HZ. Keep |x|<=0.5 for 2nd-order stability."""
    x = np.clip(x, -0.95, 0.95).astype(np.float64)
    n = x.size
    bits = np.empty(n, dtype=np.uint8)
    if order == 1:
        integ = 0.0; last = 1.0
        for i in range(n):
            integ += x[i] - last
            b = 1 if integ >= 0 else 0
            bits[i] = b; last = 1.0 if b else -1.0
    else:
        i1 = i2 = 0.0; last = 1.0
        for i in range(n):
            i1 += x[i] - last
            i2 += i1 - last
            b = 1 if i2 >= 0 else 0
            bits[i] = b; last = 1.0 if b else -1.0
    # pack MSB-first into bytes, exactly how SPI shifts them in
    pad = (-n) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, np.uint8)])
    return np.packbits(bits)


def _unpack(pdm_bytes: np.ndarray) -> np.ndarray:
    return np.unpackbits(np.asarray(pdm_bytes, dtype=np.uint8))


def decode_sinc1(pdm_bytes: np.ndarray, decim: int = DECIM,
                 center: int = 160) -> np.ndarray:
    """Firmware decode: ones-per-`decim`-bits minus `center` (= decim/2)."""
    bits = _unpack(pdm_bytes)
    nfull = (bits.size // decim) * decim
    ones = bits[:nfull].reshape(-1, decim).sum(axis=1)
    return ones.astype(np.float64) - center


def decode_proper(pdm_bytes: np.ndarray, decim: int = DECIM,
                  fc_hz: float = 4200.0, dc_block: bool = True) -> np.ndarray:
    """Proper decode: +/-1 bitstream -> anti-aliased polyphase decimation + DC block."""
    pm1 = _unpack(pdm_bytes).astype(np.float64) * 2.0 - 1.0
    # multi-stage to keep the AA FIR short: 320 = 8 * 8 * 5
    y = pm1
    for r in (8, 8, 5):
        y = signal.resample_poly(y, 1, r, window=("kaiser", 8.0))
    if dc_block:
        # 1st-order HPF at ~20 Hz to kill the mic DC offset
        b, a = signal.butter(1, 20.0 / (PCM_HZ / 2), btype="high")
        y = signal.filtfilt(b, a, y)
    return y * decim  # scale to ~comparable amplitude units as sinc1


def welch_psd(x: np.ndarray, fs: int = PCM_HZ, nperseg: int = 1024):
    f, p = signal.welch(x - np.mean(x), fs=fs, nperseg=min(nperseg, len(x)))
    return f, 10 * np.log10(p + 1e-20)


def inband_noise_floor_db(x: np.ndarray, fs: int, sig_hz, guard=200.0) -> float:
    """Median PSD (dB) excluding bins near the known signal tones - a noise-floor proxy."""
    f, pdb = welch_psd(x, fs)
    mask = (f > 50)
    for s in np.atleast_1d(sig_hz):
        mask &= np.abs(f - s) > guard
    return float(np.median(pdb[mask]))


if __name__ == "__main__":  # self-test: round-trip a two-tone through both decoders
    tones = [300.0, 1500.0]
    dur = 0.20
    t = np.arange(int(dur * PDM_CLK_HZ)) / PDM_CLK_HZ
    x = 0.3 * np.sin(2*np.pi*tones[0]*t) + 0.15 * np.sin(2*np.pi*tones[1]*t)
    pdm = sigma_delta_modulate(x, order=2)
    y1 = decode_sinc1(pdm); yp = decode_proper(pdm)
    nf1 = inband_noise_floor_db(y1, PCM_HZ, tones)
    nfp = inband_noise_floor_db(yp, PCM_HZ, tones)
    print(f"PDM bytes={pdm.size}  PCM out: sinc1={y1.size} proper={yp.size} @ {PCM_HZ} Hz")
    print(f"in-band noise floor:  sinc1 {nf1:6.1f} dB   proper {nfp:6.1f} dB   "
          f"penalty = {nf1 - nfp:+.1f} dB (firmware decimator)")
