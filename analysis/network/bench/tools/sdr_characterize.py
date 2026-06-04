#!/usr/bin/env python3
"""Proper RTL-SDR characterization of the diag's Meshtastic TX (vs ambient).

Streams IQ at 906.875 MHz, builds a 1 ms-resolution power envelope, detects + merges
bursts, and classifies them by DURATION, our beacons have a known signature the naive
power detector missed: LongFast ≈ 473 ms and BW500 ≈ 237 ms bursts, emitted every ~4 s
during the diag's TXBEACON / BW500 phases (which recur ~every 100 s). It also grabs the
raw IQ of one long burst and renders a spectrogram so we can SEE the LoRa chirp (confirms
it's LoRa, the bandwidth, and the center-frequency offset).

Outputs (analysis/network/bench/T2_tx/):
  sdr_envelope.npz      time + power envelope + burst table
  sdr_characterize.png  envelope timeline, burst-duration histogram, beacon spectrogram
Prints a stats block.

Run (note the dylib path for Apple-Silicon brew librtlsdr):
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
    analysis/.venv/bin/python analysis/network/bench/tools/sdr_characterize.py --secs 150
"""
from __future__ import annotations
import argparse, sys, time, pathlib, collections
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
sys.path.insert(0, str(HERE.parent.parent / "antenna"))
try:
    import _style as S; S.use_light()
except Exception:
    pass

ap = argparse.ArgumentParser()
ap.add_argument("--freq", type=float, default=906.875e6)
ap.add_argument("--secs", type=float, default=150)
ap.add_argument("--rate", type=float, default=1.024e6)
ap.add_argument("--gain", default="auto")
ap.add_argument("--thresh_db", type=float, default=6.0)
a = ap.parse_args()

sdr = RtlSdr()
sdr.sample_rate = a.rate; sdr.center_freq = a.freq; sdr.gain = a.gain
BLK = 65536                       # 64 ms @ 1.024 Msps
SUB = 1024                        # 1 ms power bins
ms_per_sub = SUB / a.rate * 1000.0

env = []                          # (t_s, power_db) at 1 ms resolution
ts0 = time.time()
roll = collections.deque(maxlen=40)   # ~2.5 s rolling IQ for triggered save
beacon_iq = None; beacon_t = None

print(f"capturing {a.secs:.0f}s @ {a.freq/1e6:.3f} MHz, {a.rate/1e6:.3f} Msps …")
nblk = int(a.secs * a.rate / BLK)
for b in range(nblk):
    x = sdr.read_samples(BLK)
    roll.append(x.astype(np.complex64))
    t_blk = b * BLK / a.rate
    p = np.abs(x.reshape(-1, SUB))**2
    pdb = 10*np.log10(p.mean(axis=1) + 1e-12)
    for i, v in enumerate(pdb):
        env.append((t_blk + i*ms_per_sub/1000.0, v))
sdr.close()

env = np.array(env)
t = env[:,0]; pdb = env[:,1]
floor = np.median(pdb)
thr = floor + a.thresh_db

# burst detect on the 1 ms envelope, merge gaps < 120 ms
hot = pdb > thr
bursts = []
i = 0; n = len(hot)
GAP = int(120/ms_per_sub)
while i < n:
    if hot[i]:
        j = i
        gap = 0
        k = i
        while k < n and (hot[k] or gap < GAP):
            if hot[k]: gap = 0; j = k
            else: gap += 1
            k += 1
        dur_ms = (t[j]-t[i])*1000.0
        pk = pdb[i:j+1].max() if j > i else pdb[i]
        if dur_ms >= 8:
            bursts.append((t[i], dur_ms, pk))
        i = k
    else:
        i += 1
bursts = np.array(bursts) if bursts else np.zeros((0,3))

# classify by duration
def cls(d):
    if 400 <= d <= 560: return "LongFast(~473)"
    if 180 <= d <= 300: return "BW500(~237)"
    return "ambient/other"
labels = [cls(d) for d in bursts[:,1]] if len(bursts) else []
n_lf = labels.count("LongFast(~473)"); n_bw = labels.count("BW500(~237)")
n_amb = labels.count("ambient/other")

print(f"\nnoise floor {floor:.1f} dB | threshold {thr:.1f} dB | bursts {len(bursts)}")
print(f"  LongFast(~473ms): {n_lf}   BW500(~237ms): {n_bw}   ambient/other: {n_amb}")
if n_lf:
    lf_t = bursts[[l=='LongFast(~473)' for l in labels],0]
    lf_d = bursts[[l=='LongFast(~473)' for l in labels],1]
    print(f"  LongFast dur: mean {lf_d.mean():.0f} ms (firmware ToA was 473 ms)")
    if len(lf_t) > 1:
        gaps = np.diff(np.sort(lf_t))
        near4 = gaps[(gaps>2)&(gaps<6)]
        print(f"  LongFast inter-arrival near 4 s: {len(near4)} gaps, mean {near4.mean():.2f} s"
              if len(near4) else "  (no ~4 s cadence found among LongFast bursts)")
if n_bw:
    bw_d = bursts[[l=='BW500(~237)' for l in labels],1]
    print(f"  BW500 dur: mean {bw_d.mean():.0f} ms (firmware ToA was 237 ms)")

# grab IQ of the first long burst for a spectrogram (from the rolling buffer end)
if len(roll) and len(bursts):
    longb = bursts[bursts[:,1] >= 350]
    if len(longb):
        beacon_iq = np.concatenate(list(roll))   # ~last 2.5 s captured
        beacon_t = longb[0,0]

# ---- figures ----
fig = plt.figure(figsize=(13, 8))
ax1 = fig.add_subplot(3,1,1)
ax1.plot(t, pdb, lw=0.4, color="#1a8fe3")
ax1.axhline(thr, color="#d11149", ls="--", lw=1, label=f"burst thr {thr:.0f} dB")
for (bt,bd,bp),lb in zip(bursts, labels):
    c = {"LongFast(~473)":"#0a9396","BW500(~237)":"#f17105"}.get(lb)
    if c: ax1.axvspan(bt, bt+bd/1000, color=c, alpha=0.5)
ax1.set_xlabel("time (s)"); ax1.set_ylabel("power (dB)")
ax1.set_title(f"906.875 MHz power envelope, teal=LongFast(~473ms) orange=BW500(~237ms) beacons vs ambient")
ax1.legend(loc="upper right", fontsize=8)

ax2 = fig.add_subplot(3,2,3)
if len(bursts):
    ax2.hist(bursts[:,1], bins=np.logspace(0.8, 3.0, 40), color="#6a4c93", alpha=0.85)
    for d,c,l in [(473,"#0a9396","LongFast 473"),(237,"#f17105","BW500 237")]:
        ax2.axvline(d, color=c, ls="--", lw=1.5, label=l)
ax2.set_xscale("log"); ax2.set_xlabel("burst duration (ms, log)"); ax2.set_ylabel("count")
ax2.set_title("Burst-duration histogram (our beacons = peaks at 473 / 237 ms)")
ax2.legend(fontsize=8)

ax3 = fig.add_subplot(3,2,4)
if beacon_iq is not None:
    NF = 512
    seg = beacon_iq
    win = np.hanning(NF)
    nfr = len(seg)//NF
    spec = np.zeros((NF, nfr))
    for fr in range(nfr):
        chunk = seg[fr*NF:(fr+1)*NF]*win
        spec[:,fr] = np.fft.fftshift(np.abs(np.fft.fft(chunk)))
    spec_db = 20*np.log10(spec + 1e-9)
    extent=[0, nfr*NF/a.rate*1000, -a.rate/2e3, a.rate/2e3]
    ax3.imshow(spec_db, aspect="auto", origin="lower", extent=extent, cmap="turbo",
               vmin=spec_db.max()-45, vmax=spec_db.max())
    ax3.set_xlabel("time (ms)"); ax3.set_ylabel("freq offset from 906.875 (kHz)")
    ax3.set_title("Spectrogram of a captured burst (LoRa = diagonal chirps)")
else:
    ax3.text(0.5,0.5,"no long burst captured for spectrogram", ha="center")
fig.tight_layout()
fig.savefig(OUT / "sdr_characterize.png", dpi=140); plt.close(fig)
np.savez(OUT / "sdr_envelope.npz", t=t, pdb=pdb, bursts=bursts, floor=floor, freq=a.freq)
print("\nwrote", OUT/"sdr_characterize.png", "and sdr_envelope.npz")
