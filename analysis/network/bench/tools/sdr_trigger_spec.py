#!/usr/bin/env python3
"""Triggered fine spectrogram: wait for a strong burst in our LongFast band (±150 kHz
around 906.875, DC bin excluded), grab ~0.7 s of IQ around it, and render a high-time-
resolution spectrogram. LoRa = repeating diagonal up-chirps (a sawtooth); the chirp
duration/slope reveals SF/BW. This is the definitive "is that a LoRa signal at our
frequency" check that the coarse waterfall + power detector can't give.

Outputs analysis/network/bench/T2_tx/sdr_trigger_spec.png (+ the IQ .npy).

Run:
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
    analysis/.venv/bin/python analysis/network/bench/tools/sdr_trigger_spec.py --secs 70
"""
from __future__ import annotations
import argparse, sys, pathlib, collections
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
try:
    from rtlsdr import RtlSdr
except Exception as e:
    sys.exit("need pyrtlsdr+librtlsdr: " + str(e))

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "T2_tx"; OUT.mkdir(parents=True, exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--freq", type=float, default=906.875e6)
ap.add_argument("--secs", type=float, default=70, help="max wait for a trigger")
ap.add_argument("--rate", type=float, default=1.024e6)
ap.add_argument("--gain", default="40.2")
ap.add_argument("--trig_db", type=float, default=12.0, help="trigger = center-band floor+this")
a = ap.parse_args()

sdr = RtlSdr()
sdr.sample_rate = a.rate; sdr.center_freq = a.freq
try: sdr.gain = float(a.gain)
except Exception: sdr.gain = a.gain
BLK = 16384                              # 16 ms
NF = BLK
f = np.fft.fftshift(np.fft.fftfreq(NF, 1/a.rate))
band = (np.abs(f) < 150e3) & (np.abs(f) > 5e3)   # ±150 kHz, exclude DC spike
win = np.hanning(NF)

def cpow(x):
    X = np.fft.fftshift(np.abs(np.fft.fft(x*win))**2)
    return 10*np.log10(X[band].mean()+1e-12)

# estimate center-band floor from first ~0.5s
floor_samps = [cpow(sdr.read_samples(BLK)) for _ in range(30)]
floor = np.median(floor_samps); thr = floor + a.trig_db
print(f"center-band floor {floor:.1f} dB | trigger {thr:.1f} dB | waiting up to {a.secs:.0f}s for a burst…")

roll = collections.deque(maxlen=12)     # ~190 ms pre-trigger
captured = None; t_trig = None; consec = 0
nblk = int(a.secs*a.rate/BLK)
for b in range(nblk):
    x = sdr.read_samples(BLK)
    roll.append(x.astype(np.complex64))
    if cpow(x) > thr:
        consec += 1
        if consec >= 8:      # ~128 ms SUSTAINED center energy = LoRa-packet-shaped, not an impulse
            t_trig = b*BLK/a.rate
            post = [sdr.read_samples(BLK).astype(np.complex64) for _ in range(40)]  # ~0.64 s
            captured = np.concatenate(list(roll)+post)
            print(f"SUSTAINED TRIGGER at t={t_trig:.1f}s, captured {len(captured)/a.rate*1000:.0f} ms IQ")
            break
    else:
        consec = 0
sdr.close()
if captured is None:
    sys.exit(f"no burst > {thr:.1f} dB in {a.secs:.0f}s, band quiet or beacons not in a TX window")

np.save(OUT / "trigger_iq.npy", captured)
# fine spectrogram
NS = 256; HOP = 64
nfr = (len(captured)-NS)//HOP
w2 = np.hanning(NS)
spec = np.empty((NS, nfr))
for i in range(nfr):
    seg = captured[i*HOP:i*HOP+NS]*w2
    spec[:, i] = np.fft.fftshift(np.abs(np.fft.fft(seg))**2)
sdb = 10*np.log10(spec+1e-12)
fk = np.fft.fftshift(np.fft.fftfreq(NS, 1/a.rate))/1e3
tm = np.arange(nfr)*HOP/a.rate*1000

fig, ax = plt.subplots(figsize=(13, 6))
im = ax.imshow(sdb, aspect="auto", origin="lower", cmap="turbo",
               extent=[tm[0], tm[-1], fk[0], fk[-1]],
               vmin=np.percentile(sdb,40), vmax=np.percentile(sdb,99.9))
ax.axhline(125, color="w", ls=":", lw=0.6); ax.axhline(-125, color="w", ls=":", lw=0.6)
ax.set_xlabel("time (ms)"); ax.set_ylabel("freq offset from 906.875 MHz (kHz)")
ax.set_title("Triggered fine spectrogram, LoRa = repeating diagonal up-chirps "
             "(±125 kHz dotted = BW250). SF11 symbol ≈ 8.2 ms")
fig.colorbar(im, ax=ax, label="dB")
fig.tight_layout(); fig.savefig(OUT / "sdr_trigger_spec.png", dpi=140); plt.close(fig)
print("wrote", OUT/"sdr_trigger_spec.png")
