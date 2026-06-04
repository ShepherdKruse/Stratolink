#!/usr/bin/env python3
"""One radio, two networks in real RF: a single ~3.2 MHz wide-band RTL-SDR capture
centred at 905.4 MHz spanning BOTH the TTN LoRaWAN uplink sub-band (SF9 / BW125,
~903.9 to 905.3 MHz) and the Meshtastic LongFast channel (SF11 / BW250, 906.875 MHz).
Rainbow (turbo) waterfall, in the style of the other SDR plots.

Source: analysis/network/bench/T2_tx/sdr_wide.npz (process_wide_bin.py).
"""
from __future__ import annotations
import pathlib, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
NPZ = HERE.parent / "bench" / "T2_tx" / "sdr_wide.npz"
CENTER = 905.4

d = np.load(NPZ)
W = d["W"].copy(); fk = d["freqs_khz"]; T = W.shape[0] * float(d["t_row"])
W[:, np.abs(fk) < 10] = np.percentile(W, 1)            # notch the RTL DC spike
vmin, vmax = np.percentile(W, 45), np.percentile(W, 99.8)
def off(mhz): return (mhz - CENTER) * 1000.0

fig, ax = plt.subplots(figsize=(9, 9))
fig.subplots_adjust(left=0.10, right=0.98, top=0.84, bottom=0.08)
im = ax.imshow(W, origin="lower", extent=[fk[0], fk[-1], 0, T], aspect="auto",
               cmap="turbo", vmin=vmin, vmax=vmax, interpolation="nearest")

# band markers (TTN sub-band edges + Meshtastic BW250 edges)
for x in (off(903.9), off(905.3)):
    ax.axvline(x, color="w", ls=":", lw=0.9, alpha=0.8)
ax.axvline(off(906.875) - 125, color="w", ls=":", lw=0.9, alpha=0.8)
ax.axvline(off(906.875) + 125, color="w", ls=":", lw=0.9, alpha=0.8)
ax.text((off(903.9) + off(905.3)) / 2, T * 1.012, "TTN  LoRaWAN\nSF9 · BW125 · uplinks",
        ha="center", va="bottom", color="#111", fontsize=11, fontweight="bold", linespacing=1.4)
ax.text(off(906.875), T * 1.012, "Meshtastic\nSF11 · BW250 · relay",
        ha="center", va="bottom", color="#111", fontsize=11, fontweight="bold", linespacing=1.4)

ax.set_xlabel("frequency offset from 905.4 MHz  (kHz)")
ax.set_ylabel("time  (s)")
ax.set_xlim(fk[0], fk[-1])
fig.colorbar(im, ax=ax, pad=0.015, label="power (dB)", shrink=0.85)
fig.suptitle("One radio, two networks, single 3.2 MHz wide-band capture",
             x=0.10, ha="left", fontsize=14, fontweight="bold", y=0.965)
fig.text(0.10, 0.93, "the same flight SX1262: TTN telemetry on the left, the Meshtastic relay on the "
         "right, ~3 MHz apart, both live", fontsize=9.5, color="#444")
fig.text(0.98, 0.012, "RTL-SDR V4 · 3.2 MHz · stratolink-2 soak 2026-06-03",
         ha="right", color="#777", fontsize=8, style="italic")
fig.savefig(HERE / "fig_dualband_waterfall.png", dpi=150)
print("wrote", HERE / "fig_dualband_waterfall.png")
