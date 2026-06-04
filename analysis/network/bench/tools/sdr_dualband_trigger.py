#!/usr/bin/env python3
"""Wide-band dual-network trigger capture: from one 3.2 MHz capture centred at
905.4 MHz, grab a short IQ snippet of a TTN LoRaWAN uplink (SF9/BW125, ~903.9 to
905.3 MHz) AND a Meshtastic LongFast burst (SF11/BW250, 906.875 MHz), for
side-by-side fine spectrograms of the two chirps.

Saves T2_tx/{ttn_iq.npy, mesh_iq.npy, dualband_meta.npz}.  Runs until both are
captured or --secs elapses (TTN uplinks are ~20 min apart, so default is long).

  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
    analysis/.venv/bin/python analysis/network/bench/tools/sdr_dualband_trigger.py --secs 1500
"""
from __future__ import annotations
import argparse, pathlib, collections
import numpy as np
from rtlsdr import RtlSdr

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "T2_tx"; OUT.mkdir(parents=True, exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--center", type=float, default=905.4e6)
ap.add_argument("--rate", type=float, default=3.2e6)
ap.add_argument("--secs", type=float, default=1500)
ap.add_argument("--gain", default="25")            # board is inches away; keep it from saturating
a = ap.parse_args()

sdr = RtlSdr(); sdr.sample_rate = a.rate; sdr.center_freq = a.center
try: sdr.gain = float(a.gain)
except Exception: sdr.gain = a.gain

BLK = 16384
fk = np.fft.fftshift(np.fft.fftfreq(BLK, 1 / a.rate)) / 1e3      # kHz offset
win = np.hanning(BLK)
def off(mhz): return (mhz - a.center / 1e6) * 1e3
DC = np.abs(fk) < 12
TTN = (fk > off(903.9)) & (fk < off(905.3)) & ~DC
MESH = (np.abs(fk - off(906.875)) < 150) & ~DC

def spec(x): return np.fft.fftshift(np.abs(np.fft.fft(x * win)) ** 2)
def bp(X, m): return 10 * np.log10(X[m].mean() + 1e-12)

fl_t, fl_m = [], []
for _ in range(30):
    X = spec(sdr.read_samples(BLK)); fl_t.append(bp(X, TTN)); fl_m.append(bp(X, MESH))
thr_t, thr_m = np.median(fl_t) + 9, np.median(fl_m) + 9
print(f"TTN floor {np.median(fl_t):.1f} thr {thr_t:.1f} | MESH floor {np.median(fl_m):.1f} thr {thr_m:.1f}", flush=True)

roll = collections.deque(maxlen=150)        # ~0.77 s
ttn_iq = mesh_iq = None; ttn_off = mesh_off = 0.0; ct = cm = 0
nblk = int(a.secs * a.rate / BLK)
for b in range(nblk):
    x = sdr.read_samples(BLK).astype(np.complex64); roll.append(x)
    X = spec(x); pt = bp(X, TTN); pm = bp(X, MESH)
    if ttn_iq is None:
        ct = ct + 1 if pt > thr_t else 0
        if ct >= 8:
            post = [sdr.read_samples(BLK).astype(np.complex64) for _ in range(120)]
            ttn_iq = np.concatenate(list(roll) + post)
            idx = np.where(TTN)[0]; ttn_off = float(fk[idx[np.argmax(X[idx])]])
            print(f"TTN burst @ ~{ttn_off:.0f} kHz ({a.center/1e6 + ttn_off/1e3:.3f} MHz)", flush=True)
            ct = 0
    if mesh_iq is None:
        cm = cm + 1 if pm > thr_m else 0
        if cm >= 8:
            post = [sdr.read_samples(BLK).astype(np.complex64) for _ in range(120)]
            mesh_iq = np.concatenate(list(roll) + post)
            idx = np.where(MESH)[0]; mesh_off = float(fk[idx[np.argmax(X[idx])]])
            print(f"MESH burst @ ~{mesh_off:.0f} kHz ({a.center/1e6 + mesh_off/1e3:.3f} MHz)", flush=True)
            cm = 0
    if ttn_iq is not None and mesh_iq is not None:
        break
sdr.close()
if ttn_iq is not None: np.save(OUT / "ttn_iq.npy", ttn_iq)
if mesh_iq is not None: np.save(OUT / "mesh_iq.npy", mesh_iq)
np.savez(OUT / "dualband_meta.npz", rate=a.rate, center=a.center,
         ttn_off=ttn_off, mesh_off=mesh_off,
         have_ttn=ttn_iq is not None, have_mesh=mesh_iq is not None)
print(f"done. ttn={ttn_iq is not None} mesh={mesh_iq is not None}", flush=True)
