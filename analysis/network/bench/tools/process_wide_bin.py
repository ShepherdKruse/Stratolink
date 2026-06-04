#!/usr/bin/env python3
"""Process a wide-band rtl_sdr capture (905.4 MHz, 3.2 MHz, uint8 IQ) into the
dual-network figures' inputs, in one pass plus a seek-back:

  sdr_wide.npz                         downsampled waterfall (both bands)
  ttn_iq.npy / mesh_iq.npy / dualband_meta.npz   burst snippets for the chirps

  python process_wide_bin.py /tmp/wide_dualband.bin
"""
from __future__ import annotations
import sys, pathlib, numpy as np

BIN = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/wide_dualband.bin")
OUT = pathlib.Path(__file__).resolve().parents[1] / "T2_tx"; OUT.mkdir(parents=True, exist_ok=True)
RATE, CENTER, NFFT = 3.2e6, 905.4e6, 512
ROW_SUB = 100                                  # sub-blocks per waterfall row (~16 ms)
SUST = 30                                       # sub-blocks of sustained energy = a packet (~4.8 ms)
fk = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / RATE)) / 1e3
win = np.hanning(NFFT)
def off(mhz): return (mhz - CENTER / 1e6) * 1e3
DC = np.abs(fk) < 12
TTN = (fk > off(903.9)) & (fk < off(905.3)) & ~DC
MESH = (np.abs(fk - off(906.875)) < 150) & ~DC

def chunks(f, n_complex):
    raw = np.fromfile(f, dtype=np.uint8, count=n_complex * 2)
    if len(raw) < NFFT * 2: return None
    return (raw[0::2].astype(np.float32) - 127.5) + 1j * (raw[1::2].astype(np.float32) - 127.5)

# floor from first ~1 s
with open(BIN, "rb") as f:
    iq = chunks(f, int(RATE))
    nsub = len(iq) // NFFT
    X = np.abs(np.fft.fftshift(np.fft.fft(iq[:nsub*NFFT].reshape(nsub, NFFT) * win, axis=1), axes=1)) ** 2
    Pdb = 10 * np.log10(X + 1e-9)
    fl_t, fl_m = np.median(Pdb[:, TTN].max(axis=1)), np.median(Pdb[:, MESH].max(axis=1))
thr_t, thr_m = fl_t + 10, fl_m + 10
print(f"TTN floor {fl_t:.1f} thr {thr_t:.1f} | MESH floor {fl_m:.1f} thr {thr_m:.1f}", flush=True)

rows, acc = [], []
idx = {"ttn": None, "mesh": None}
# track the STRONGEST sustained burst per region (= our close, strong board signal)
st = {n: dict(inrun=False, start=0, peak=-1e9, length=0, best_peak=-1e9, best_idx=None) for n in ("ttn", "mesh")}
sub_global = 0
CHUNK = NFFT * ROW_SUB * 50
with open(BIN, "rb") as f:
    while True:
        iq = chunks(f, CHUNK)
        if iq is None: break
        nsub = len(iq) // NFFT
        X = np.abs(np.fft.fftshift(np.fft.fft(iq[:nsub*NFFT].reshape(nsub, NFFT) * win, axis=1), axes=1)) ** 2
        Pdb = 10 * np.log10(X + 1e-9)
        for s in range(nsub):
            acc.append(Pdb[s])
            if len(acc) >= ROW_SUB:
                rows.append(np.mean(acc, axis=0)); acc = []
        pt = Pdb[:, TTN].max(axis=1); pm = Pdb[:, MESH].max(axis=1)
        for name, p, thr in (("ttn", pt, thr_t), ("mesh", pm, thr_m)):
            s_ = st[name]
            for s in range(nsub):
                if p[s] > thr:
                    if not s_["inrun"]:
                        s_.update(inrun=True, start=sub_global + s, peak=p[s], length=1)
                    else:
                        s_["peak"] = max(s_["peak"], p[s]); s_["length"] += 1
                else:
                    if s_["inrun"] and s_["length"] >= SUST and s_["peak"] > s_["best_peak"]:
                        s_["best_peak"] = s_["peak"]; s_["best_idx"] = s_["start"] * NFFT
                    s_["inrun"] = False; s_["length"] = 0
        sub_global += nsub
if acc: rows.append(np.mean(acc, axis=0))
for name in ("ttn", "mesh"):
    s_ = st[name]
    if s_["inrun"] and s_["length"] >= SUST and s_["peak"] > s_["best_peak"]:
        s_["best_peak"] = s_["peak"]; s_["best_idx"] = s_["start"] * NFFT
    idx[name] = s_["best_idx"]
    if idx[name] is not None:
        print(f"{name.upper()} strongest burst at t={idx[name]/RATE:.1f}s, peak {s_['best_peak']:.1f} dB", flush=True)

W = np.array(rows)
np.savez(OUT / "sdr_wide.npz", W=W, freqs_khz=fk, t_row=ROW_SUB * NFFT / RATE, floor=fl_t, center=CENTER)
print(f"waterfall {W.shape} -> sdr_wide.npz ({W.shape[0]*ROW_SUB*NFFT/RATE:.0f}s)", flush=True)

# seek back and extract ~1.3 s snippets around each burst
def extract(sample_idx):
    pre, span = int(0.5 * RATE), int(1.3 * RATE)
    start = max(0, sample_idx - pre)
    with open(BIN, "rb") as f:
        f.seek(start * 2)
        return chunks(f, span)

meta = dict(rate=RATE, center=CENTER, ttn_off=0.0, mesh_off=0.0, have_ttn=False, have_mesh=False)
for name in ("ttn", "mesh"):
    if idx[name] is None:
        print(f"no {name} burst found", flush=True); continue
    sn = extract(idx[name])
    np.save(OUT / f"{name}_iq.npy", sn)
    mask = TTN if name == "ttn" else MESH
    pre = min(int(0.5 * RATE), idx[name])                   # burst sits ~here in the snippet
    seg = sn[pre:pre + NFFT * 16]                           # measure the channel from the burst itself
    nb = len(seg) // NFFT
    Xb = (np.abs(np.fft.fftshift(np.fft.fft(seg[:nb*NFFT].reshape(nb, NFFT) * win, axis=1), axes=1)) ** 2).mean(axis=0)
    region = np.where(mask)[0]
    meta[f"{name}_off"] = float(fk[region[np.argmax(Xb[region])]])
    meta[f"have_{name}"] = True
    print(f"{name} snippet {len(sn)} samp, peak ~{meta[f'{name}_off']:.0f} kHz", flush=True)
np.savez(OUT / "dualband_meta.npz", **meta)
print("done.", flush=True)
