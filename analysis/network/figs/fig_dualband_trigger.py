#!/usr/bin/env python3
"""Side-by-side fine spectrograms (turbo) of the two LoRa chirps the one flight radio
uses: TTN LoRaWAN (SF9 / BW125) and Meshtastic LongFast (SF11 / BW250). LoRa shows as
a sawtooth of diagonal up-chirps; Meshtastic is wider (double bandwidth) and slower
(higher spreading factor). Same radio, two dialects. Style matches the other SDR plots.

Source: T2_tx/{ttn_iq.npy, mesh_iq.npy, dualband_meta.npz} (sdr_dualband_trigger.py /
process_wide_bin.py).
"""
from __future__ import annotations
import pathlib, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
T2 = HERE.parent / "bench" / "T2_tx"
meta = np.load(T2 / "dualband_meta.npz")
RATE = float(meta["rate"])


def stft(x, NS=512, HOP=128):
    w = np.hanning(NS); n = (len(x) - NS) // HOP
    S = np.empty((NS, n))
    for i in range(n):
        S[:, i] = np.fft.fftshift(np.abs(np.fft.fft(x[i * HOP:i * HOP + NS] * w)) ** 2)
    fk = np.fft.fftshift(np.fft.fftfreq(NS, 1 / RATE)) / 1e3
    tm = np.arange(n) * HOP / RATE * 1000.0
    return 10 * np.log10(S + 1e-12), fk, tm


def panel(ax, iq, foff, halfbw, title, sub):
    S, fk, tm = stft(iq)
    # locate the burst in time using power in the foff band
    band = (fk > foff - halfbw) & (fk < foff + halfbw)
    hot = np.where(S[band].mean(axis=0) > np.percentile(S[band].mean(axis=0), 88))[0]
    c = hot[len(hot) // 2] if len(hot) else S.shape[1] // 2
    half = int(0.0275 * RATE / 128)                       # ~55 ms window: enough symbols to see the chirp
    t0, t1 = max(0, c - half), min(S.shape[1], c + half)
    # recentre frequency on the burst energy centroid
    Sb = S[:, t0:t1].mean(axis=1); reg = (fk > foff - 1.4 * halfbw) & (fk < foff + 1.4 * halfbw)
    w = np.clip(Sb[reg] - np.median(Sb), 0, None)
    center = float(np.sum(fk[reg] * w) / (w.sum() + 1e-9)) if w.sum() > 0 else foff
    fsel = (fk > center - halfbw) & (fk < center + halfbw)
    Sz, fkz, tmz = S[fsel][:, t0:t1], fk[fsel] - center, tm[t0:t1] - tm[t0]
    im = ax.imshow(Sz, origin="lower", aspect="auto", cmap="turbo",
                   vmin=np.percentile(Sz, 50), vmax=np.percentile(Sz, 99.8),
                   extent=[tmz[0], tmz[-1], fkz[0], fkz[-1]], interpolation="nearest")
    ax.set_title(f"{title}\n{sub}", fontsize=12, fontweight="bold", linespacing=1.4)
    ax.set_xlabel("time  (ms)"); ax.set_ylabel("frequency offset  (kHz)")
    return im


have_ttn, have_mesh = bool(meta["have_ttn"]), bool(meta["have_mesh"])
fig, axes = plt.subplots(1, 2, figsize=(13, 6))
fig.subplots_adjust(left=0.07, right=0.97, top=0.80, bottom=0.12, wspace=0.22)
if have_ttn:
    im = panel(axes[0], np.load(T2 / "ttn_iq.npy"), float(meta["ttn_off"]), 95,
               "TTN  LoRaWAN  uplink", "SF9 · BW 125 kHz")
    fig.colorbar(im, ax=axes[0], pad=0.02, shrink=0.85)
else:
    axes[0].text(0.5, 0.5, "no TTN burst captured", ha="center"); axes[0].axis("off")
if have_mesh:
    im = panel(axes[1], np.load(T2 / "mesh_iq.npy"), float(meta["mesh_off"]), 165,
               "Meshtastic  LongFast  relay", "SF11 · BW 250 kHz")
    fig.colorbar(im, ax=axes[1], pad=0.02, shrink=0.85)
else:
    axes[1].text(0.5, 0.5, "no Meshtastic burst captured", ha="center"); axes[1].axis("off")

fig.suptitle("Two LoRa dialects, one radio, fine spectrograms of the chirps",
             x=0.07, ha="left", fontsize=14, fontweight="bold", y=0.96)
fig.text(0.07, 0.905, "the same SX1262 captured mid-transmit: a TTN telemetry uplink (left) and a "
         "Meshtastic relay forward (right)", fontsize=9.5, color="#444")
fig.text(0.97, 0.012, "RTL-SDR V4 · 3.2 MHz · stratolink-2 soak 2026-06-03", ha="right",
         color="#777", fontsize=8, style="italic")
fig.savefig(HERE / "fig_dualband_trigger.png", dpi=150)
print("wrote", HERE / "fig_dualband_trigger.png")
