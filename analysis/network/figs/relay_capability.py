#!/usr/bin/env python3
"""Shareable figures: the Stratolink flight firmware relaying a live Meshtastic
mesh in TTN's idle time, one SX1262, two networks.

Every number here is measured/real:
  - TTN cadence 1200 s, SF9 35 B uplink ToA ~308 ms        (firmware config.h)
  - Meshtastic LongFast ToA 473 ms                          (bench, RESULTS.md)
  - This soak, flight firmware, J-Link s_relay:
        rx=8  fwd=7  dedup=0  hop0=0  cap_skip=1            (2026-06-03)
  - Bench live-mesh validation: fwd=11 dedup=10 hop0=3      (RESULTS.md)
  - TTN uplink confirmed in Supabase: stratolink-2, SF9, 904.1 MHz, gw RSSI -61

Outputs (analysis/network/figs/):
  fig1_dual_network_timeline.png   "one radio, two networks" airtime story
  fig3_relay_validation.png        what the relay did to real traffic
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "antenna"))
import _style as S; S.use_light()
OUT = pathlib.Path(__file__).resolve().parent; OUT.mkdir(parents=True, exist_ok=True)

# ---------- measured constants ----------
CYCLE_S = 1200.0     # FULL-tier TTN cadence
TTN_TOA = 0.308      # SF9 uplink time-on-air (s)
LF_TOA  = 0.473      # Meshtastic LongFast time-on-air (s)
RX, FWD, CAP = 8, 7, 1                 # this soak (J-Link)
B_FWD, B_DEDUP, B_HOP = 11, 10, 3      # bench live-mesh
UPLINKS_DAY = round(86400 / CYCLE_S)   # 72
TTN_AIRTIME_DAY = UPLINKS_DAY * TTN_TOA # 22.2 s
TTN_DUTY = TTN_TOA / CYCLE_S           # 0.000257 -> 0.026 %

# ================================================================= FIG 1
# A one-hour radio-occupancy timeline: TTN telemetry is a few sub-second
# blips; the Meshtastic relay owns everything in between.
fig, (axA, axB) = plt.subplots(2, 1, figsize=(13, 5.6),
                               gridspec_kw={"height_ratios": [3, 2], "hspace": 0.55})

HOUR = 3600.0
axA.set_xlim(0, HOUR); axA.set_ylim(0, 2.0)
# relay band (fills the whole hour, behind everything)
axA.add_patch(Rectangle((0, 0.12), HOUR, 0.76, color=S.TEAL7, alpha=0.20, lw=0, zorder=1))
axA.text(HOUR/2, 0.5, "MESHTASTIC  RELAY ,  listening on 906.875 MHz  +  forwarding the mesh",
         ha="center", va="center", color=S.TEAL7, fontsize=11.5, fontweight="bold", zorder=3)
# representative forward ticks across the hour (count is real; placement illustrative)
rng = np.linspace(70, HOUR-70, 11)
for x in rng:
    axA.plot([x, x], [0.16, 0.84], color=S.MINT, lw=1.4, alpha=0.55, zorder=2)
# TTN uplinks: 3 per hour, drawn at min visible width with a true-scale callout
for t in (0, 1200, 2400, 3600):
    axA.add_patch(Rectangle((t, 1.05), 14, 0.7, color=S.RED, lw=0, zorder=4))
axA.text(1200, 1.95, "TTN telemetry uplink  ·  SF9  ·  308 ms  ·  every 1200 s  → cached to Supabase",
         ha="center", va="center", color=S.RED, fontsize=11, fontweight="bold")
axA.annotate("(bars widened ~45× to be visible -\ntrue width is 308 ms: a sliver)",
             xy=(1200, 1.05), xytext=(1700, 0.05), fontsize=8.2, color=S.TEXT_DIM,
             ha="left", va="bottom",
             arrowprops=dict(arrowstyle="->", color=S.TEXT_DIM, lw=0.8))
axA.set_yticks([])
axA.set_xticks(np.arange(0, HOUR+1, 600))
axA.set_xticklabels([f"{int(t/60)}" for t in np.arange(0, HOUR+1, 600)])
axA.set_xlabel("time within one hour of flight (minutes)")
axA.set_title("One radio, two networks, what the SX1262 does over an hour", loc="left")
for s in ("top", "right", "left"): axA.spines[s].set_visible(False)
axA.grid(False)

# lower panel: the airtime split as a single 100% bar (log-ish callout)
axB.set_xlim(0, 100); axB.set_ylim(0, 1); axB.axis("off")
axB.add_patch(Rectangle((0, 0.3), 100, 0.4, color=S.TEAL7, alpha=0.30, lw=0))
axB.add_patch(Rectangle((0, 0.3), TTN_DUTY*100, 0.4, color=S.RED, lw=0))
axB.text(50, 0.5, f"Meshtastic relay fills {100-TTN_DUTY*100:.2f}% of the radio's time",
         ha="center", va="center", color=S.TEAL7, fontsize=12, fontweight="bold")
axB.annotate(f"TTN telemetry = {TTN_DUTY*100:.3f}% "
             f"({UPLINKS_DAY} uplinks/day = {TTN_AIRTIME_DAY:.0f} s, 74% of the 30 s/day fair-use cap)",
             xy=(0.05, 0.7), xytext=(2, 0.92), fontsize=9.5, color=S.RED, ha="left", va="center",
             arrowprops=dict(arrowstyle="->", color=S.RED, lw=0.9))
axB.text(50, 0.07, "The relay is a pure surplus: power-gated to full-cap + sunlight, "
         "self-capped at 5% airtime, and it yields instantly to every telemetry uplink.",
         ha="center", va="center", color=S.TEXT_DIM, fontsize=9.5, style="italic")

fig.suptitle("Stratolink: a pico-balloon relaying Meshtastic in the gaps between TTN telemetry",
             fontsize=14.5, fontweight="bold")
S.footer(fig, "stratolink-2 · flight firmware soak 2026-06-03 · TTN uplink in Supabase + relay rx=8/fwd=7 (J-Link) · ToA SF9 308 ms / LongFast 473 ms",
         light=True)
fig.savefig(OUT / "fig1_dual_network_timeline.png", dpi=150, bbox_inches="tight")
plt.close(fig); print("wrote", OUT / "fig1_dual_network_timeline.png")

# ================================================================= FIG 3
# What the relay did to REAL traffic, disposition of every frame it heard.
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [5, 4], "wspace": 0.28})

# left: stacked disposition bar of all frames the relay handled (soak + bench)
cats = ["forwarded\n(hop-1, opaque)", "deduped\n(already relayed)", "dropped\n(hop exhausted)", "skipped\n(5% airtime cap)"]
vals = [FWD + B_FWD, B_DEDUP, B_HOP, CAP]          # 18, 10, 3, 1
cols = [S.TEAL7, S.TEAL10, S.DIM, S.WARM]
total = sum(vals)
left = 0
for v, c, lab in zip(vals, cols, cats):
    ax1.barh(0, v, left=left, color=c, edgecolor="white", lw=1.2)
    ax1.text(left + v/2, 0, f"{v}", ha="center", va="center", color="white",
             fontsize=13, fontweight="bold")
    left += v
ax1.set_xlim(0, total); ax1.set_ylim(-1.1, 0.7); ax1.set_yticks([])
ax1.set_xticks(np.arange(0, total+1, 5))
ax1.set_title(f"What the relay did with {total} live mesh frames", loc="left")
for s in ("top", "right", "left"): ax1.spines[s].set_visible(False)
ax1.grid(False)
# legend just below the bar (inside ax1's lower band, no collision with footer)
handles = [plt.Rectangle((0,0),1,1, color=c) for c in cols]
ax1.legend(handles, [c.replace("\n"," ") for c in cats], loc="upper center",
           bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=9.5, frameon=False,
           handlelength=1.4, columnspacing=2.2)

# right: the keyless-relay principle, as text on a panel
ax2.axis("off")
ax2.add_patch(Rectangle((0.02, 0.05), 0.96, 0.9, transform=ax2.transAxes,
              facecolor=S.PANEL, edgecolor=S.GRID, lw=1.0))
ax2.text(0.5, 0.86, "header-only · keyless · opaque", transform=ax2.transAxes,
         ha="center", fontsize=12.5, fontweight="bold", color=S.MINT)
lines = [
    "The 16-byte Meshtastic header is plaintext -",
    "so the balloon reads (from, id, hop) and",
    "re-transmits the encrypted payload untouched.",
    "",
    "It registers NOTHING on the network:",
    "no node ID, no keys, no channel membership.",
    "It just relays what it hears, then forgets it.",
    "",
    "Validated on the flight hardware against a",
    "real neighbourhood mesh (nodes at -113 dBm).",
]
for i, ln in enumerate(lines):
    ax2.text(0.5, 0.74 - i*0.066, ln, transform=ax2.transAxes, ha="center",
             fontsize=9.6, color=(S.TEXT if ln and not ln.startswith("It registers") else S.TEXT),
             fontweight=("bold" if ln.startswith("It registers") else "normal"))
ax2.set_title(" ", loc="left")

fig.suptitle("Relay validation, opaque, keyless, and correct on real traffic",
             fontsize=14.5, fontweight="bold")
S.footer(fig, "soak (J-Link): rx 8 / fwd 7 / cap-skip 1  +  bench live-mesh: fwd 11 / dedup 10 / hop0 3  =  32 frames",
         light=True)
fig.savefig(OUT / "fig3_relay_validation.png", dpi=150, bbox_inches="tight")
plt.close(fig); print("wrote", OUT / "fig3_relay_validation.png")
