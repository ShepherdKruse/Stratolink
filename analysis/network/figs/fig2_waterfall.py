#!/usr/bin/env python3
"""Sleek monochrome waterfall of the 906.875 MHz LongFast band, the live RF the
balloon's relay listens to and transmits in.  White -> ink (no rainbow heatmap),
to sit in the same minimal family as the coverage schematics.

Source: analysis/network/bench/T2_tx/sdr_waterfall.npz (RTL-SDR V4, 480 s, fixed gain).
"""
from __future__ import annotations
import pathlib, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

HERE = pathlib.Path(__file__).resolve().parent
NPZ  = HERE.parent / "bench" / "T2_tx" / "sdr_waterfall.npz"
INK, MID, FAINT = "#1a1a1a", "#777777", "#b9b9b9"
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Latin Modern Roman", "CMU Serif", "Georgia", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "figure.facecolor": "white", "savefig.facecolor": "white", "axes.facecolor": "white",
})

d = np.load(NPZ)
W = d["W"]; fk = d["freqs_khz"]; T = W.shape[0] * float(d["t_row"]); floor = float(d["floor"])
sel = np.abs(fk) <= 256                      # zoom to ±256 kHz around 906.875
W = W[:, sel]; fk = fk[sel]

cmap = LinearSegmentedColormap.from_list("ink", ["#ffffff", "#e7ebef", "#9aa6b4", "#1a1a1a"])
vmin, vmax = floor + 4.0, np.percentile(W, 99.7)   # floor -> white; only real bursts/carriers ink in

fig, ax = plt.subplots(figsize=(7.2, 8.6))
fig.subplots_adjust(left=0.12, right=0.97, top=0.86, bottom=0.08)
ax.imshow(W, origin="lower", extent=[fk[0], fk[-1], 0, T], aspect="auto",
          cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
# LongFast band edges (BW250 = ±125 kHz) + centre
for x in (-125, 125):
    ax.axvline(x, color=INK, ls=(0, (4, 3)), lw=0.8, alpha=0.7)
ax.axvline(0, color=INK, ls=":", lw=0.7, alpha=0.5)
ax.text(0, T * 1.012, "906.875 MHz", ha="center", va="bottom", color=INK, fontsize=10, style="italic")
ax.text(125, T * 0.5, "  LongFast band, BW 250 kHz", rotation=90, va="center", ha="left",
        color=MID, fontsize=9.5)

ax.set_xlabel("frequency offset from 906.875 MHz  (kHz)", fontsize=11)
ax.set_ylabel("time  (s)", fontsize=11)
ax.set_xlim(-256, 256)
ax.tick_params(colors=INK, labelsize=9)
for s in ("top", "right"): ax.spines[s].set_visible(False)
for s in ("left", "bottom"): ax.spines[s].set_color(MID)

fig.text(0.12, 0.945, "T H E   B A N D   T H E   R E L A Y   L I V E S   I N", fontsize=14.5, color=INK)
fig.text(0.12, 0.908, "8 min on 906.875 MHz, the live Meshtastic LongFast channel the balloon",
         fontsize=10.8, color="#333333")
fig.text(0.12, 0.886, "received 8 frames from and relayed 7 of, all on the one flight radio.",
         fontsize=10.8, color="#333333")
fig.text(0.97, 0.02, "RTL-SDR V4 · 480 s · stratolink-2 soak 2026-06-03", ha="right",
         color=MID, fontsize=8, style="italic")
fig.savefig(HERE / "fig2_waterfall.png", dpi=160)
print("wrote", HERE / "fig2_waterfall.png")
