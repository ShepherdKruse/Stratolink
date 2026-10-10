#!/usr/bin/env python3
"""Spectral waterfall of the band around 906.875 MHz, to SEE what's on air
(ambient carriers vs LoRa chirps vs our beacons) when power-thresholding can't
separate them. LoRa shows as diagonal chirp streaks; a continuous interferer shows
as a horizontal line at its offset; our LongFast beacons (if in a TX window) appear
as SF11/BW250 chirp bursts centered at 0 offset, ~every 4 s.

Outputs analysis/network/bench/T2_tx/sdr_waterfall.png (+ .npz) and a stats block.

Run:
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
    analysis/.venv/bin/python analysis/network/bench/tools/sdr_waterfall.py --secs 90
"""
from __future__ import annotations
import argparse, sys, pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
try:
    from rtlsdr import RtlSdr
except Exception as e:
    sys.exit("need pyrtlsdr+librtlsdr: " + str(e))

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "T2_tx"; OUT.mkdir(parents=True, exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--freq", type=float, default=906.875e6)
ap.add_argument("--secs", type=float, default=90)
ap.add_argument("--rate", type=float, default=1.024e6)
ap.add_argument("--gain", default="40.2")     # fixed gain (auto-AGC hid weak signals)
ap.add_argument("--nfft", type=int, default=512)
ap.add_argument("--row_ms", type=float, default=16.0)
a = ap.parse_args()

sdr = RtlSdr()
sdr.sample_rate = a.rate; sdr.center_freq = a.freq
try: sdr.gain = float(a.gain)
except Exception: sdr.gain = a.gain
BLK = 65536
NF = a.nfft
sub_per_row = max(1, int(a.row_ms*1e-3*a.rate/NF))
freqs_khz = np.fft.fftshift(np.fft.fftfreq(NF, 1/a.rate))/1e3
win = np.hanning(NF)

print(f"waterfall {a.secs:.0f}s @ {a.freq/1e6:.3f} MHz, gain {sdr.gain}, "
      f"{NF}-pt FFT, ~{a.row_ms:.0f} ms/row …")
rows = []
nblk = int(a.secs * a.rate / BLK)
acc = []
for b in range(nblk):
    x = sdr.read_samples(BLK)
    nchunk = len(x)//NF
    X = x[:nchunk*NF].reshape(nchunk, NF) * win
    P = np.fft.fftshift(np.abs(np.fft.fft(X, axis=1))**2, axes=1)
    # group chunks into rows
    for c in range(nchunk):
        acc.append(P[c])
        if len(acc) >= sub_per_row:
            rows.append(10*np.log10(np.mean(acc, axis=0)+1e-12)); acc=[]
sdr.close()
W = np.array(rows)                      # [time, freq]
t_row = a.row_ms/1000.0
T = W.shape[0]*t_row
print(f"waterfall {W.shape} ({T:.0f}s × {NF} bins, {a.rate/NF/1e3:.1f} kHz/bin)")

# average spectrum -> find carriers; column at center (our beacon freq)
avg_spec = W.mean(axis=0)
floor = np.median(W)
ctr = NF//2
ctr_band = slice(ctr-int(125e3/(a.rate/NF)), ctr+int(125e3/(a.rate/NF)))  # ±125 kHz (BW250)
ctr_power = W[:, ctr_band].mean(axis=1)
print(f"floor {floor:.1f} dB | avg-spectrum peak {avg_spec.max():.1f} dB at "
      f"{freqs_khz[avg_spec.argmax()]:.0f} kHz offset")
# strongest persistent carriers (avg spectrum local maxima well above floor)
strong = np.where(avg_spec > floor+6)[0]
if len(strong):
    grp = freqs_khz[strong]
    print(f"persistent energy at offsets (kHz): {np.round(np.unique(np.round(grp/20)*20),0)}")
print(f"center ±125 kHz (our LongFast slot) power: median {np.median(ctr_power):.1f} dB, "
      f"max {ctr_power.max():.1f} dB, frac>floor+6: {100*(ctr_power>floor+6).mean():.1f}%")

# ---- figure ----
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw={"width_ratios":[3,1]})
vmin = np.percentile(W, 30); vmax = np.percentile(W, 99.9)
im = ax1.imshow(W, aspect="auto", origin="lower", cmap="turbo",
                extent=[freqs_khz[0], freqs_khz[-1], 0, T], norm=Normalize(vmin, vmax))
ax1.axvline(0, color="w", ls=":", lw=0.8)
ax1.axvline(-125, color="w", ls=":", lw=0.4); ax1.axvline(125, color="w", ls=":", lw=0.4)
ax1.set_xlabel("freq offset from 906.875 MHz (kHz)"); ax1.set_ylabel("time (s)")
ax1.set_title(f"Waterfall @906.875 MHz, LoRa=diagonal chirps, carrier=vertical line\n"
              f"(white dotted = LongFast ±125 kHz / BW250)")
fig.colorbar(im, ax=ax1, shrink=0.7, label="dB")
ax2.plot(avg_spec, freqs_khz, color="#1a8fe3")
ax2.axhline(0, color="#d11149", ls=":", lw=0.8)
ax2.set_ylim(freqs_khz[0], freqs_khz[-1]); ax2.set_xlabel("avg power (dB)")
ax2.set_title("Avg spectrum\n(carriers = peaks)")
fig.tight_layout()
fig.savefig(OUT / "sdr_waterfall.png", dpi=130); plt.close(fig)
np.savez(OUT / "sdr_waterfall.npz", W=W, freqs_khz=freqs_khz, t_row=t_row, floor=floor)
print("wrote", OUT/"sdr_waterfall.png")
