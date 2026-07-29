#!/usr/bin/env python3
"""Testing the geofence-bug hypothesis with EARLY flight data.

Hypothesis (Teddy): the stale-GPS bug freezes the region, so the balloon transmits on the
wrong LoRaWAN band for where it actually is, missing pings.

Measured from the flight (Supabase telemetry, fresh GPS fixes):
  * eastward drift = 9.6 deg/day (35 km/h) -> a full 360 deg loop takes ~38 days, so by the
    06-24 ping (26 d after Spain) it is NOT a clean circumnavigation.
  * GPS wedges: 12 frozen runs, mostly ~1 h, longest 32 h.
  * region bands are WIDE: EU868 spans 90 deg of longitude (-30..+60E).

Model: a wedge only flips the band if the balloon drifts across a boundary while frozen.
At 9.6 deg/day even the 32 h wedge drifts only ~13 deg << the 90 deg band, so under the
MEASURED cycle the bug mis-bands the balloon only a few % of the time -> it is NOT the
primary cause of the silence (the gateway desert + oceans are). The bug would dominate ONLY
in a multi-day DEEP freeze (no GPS recovery), which we cannot rule out over the silent leg.

Run: analysis/.venv/bin/python analysis/visualization/wedge_wrongband.py
"""
from __future__ import annotations
from pathlib import Path
import os, requests, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
BLU, GRN, RED, YEL, INK, FAINT = "#1f6fb2", "#2e8b57", "#d11d1d", "#f4b400", "#2b3440", "#9aa6b4"
SB, K = os.environ["SUPABASE_URL"], os.environ["SBKEY"]; H = {"apikey": K, "Authorization": f"Bearer {K}"}
rows = []
for dev in ["stratolink-3", "stratolink-3-eu"]:
    off = 0
    while True:
        r = requests.get(f"{SB}/rest/v1/telemetry", params={"device_id": f"eq.{dev}", "select": "time,lat,lon,gps_satellites", "order": "time.asc", "limit": 1000, "offset": off}, headers=H, timeout=40); r.raise_for_status()
        b = r.json(); rows += b
        if len(b) < 1000: break
        off += 1000
def P(t): return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
ups = sorted([(P(x["time"]), x["lat"], x["lon"]) for x in rows], key=lambda z: z[0])
posups = [(t, la, lo) for (t, la, lo) in ups if la is not None and not (la == 0 and lo == 0) and abs(la) <= 90]
t0 = posups[0][0]
def hrs(t): return (t - t0).total_seconds() / 3600
fr = [(hrs(t), la, lo) for (t, la, lo) in posups]

# wedge runs (frozen position)
def moved(a, b): return abs(a[1]-b[1]) > 0.002 or abs(a[2]-b[2]) > 0.002
runs = []; i = 0
while i < len(posups)-1:
    j = i
    while j+1 < len(posups) and not moved(posups[j+1], posups[i]): j += 1
    if j > i: runs.append((hrs(posups[i][0]), (posups[j][0]-posups[i][0]).total_seconds()/3600))
    i = j+1
V = 9.6  # deg/day measured drift

fig, (axA, axB) = plt.subplots(2, 1, figsize=(13.5, 10), gridspec_kw={"height_ratios": [1.15, 1]})

# ---- Panel A: longitude vs time, region bands, wedges ----
T = np.array([h for h, _, _ in fr]); LO = np.array([lo for _, _, lo in fr])
axA.axhspan(-180, -30, color=BLU, alpha=0.10); axA.axhspan(-30, 60, color=GRN, alpha=0.10)
axA.axhline(-30, color=INK, lw=1.2, ls="--", alpha=0.7)
axA.text(T.max()*0.5, -90, "US915 band  (Americas)", color=BLU, fontsize=10, fontweight="bold", ha="center")
axA.text(T.max()*0.5, 15, "EU868 band  (−30°E → +60°E)", color=GRN, fontsize=10, fontweight="bold", ha="center")
axA.text(2, -27, "US915↔EU868 boundary (−30°E)", color=INK, fontsize=8, va="bottom")
axA.plot(T, LO, "-", color=INK, lw=0.8, alpha=0.5, zorder=2)
axA.scatter(T, LO, s=14, color=INK, zorder=3, label="GPS fix (longitude)")
for h0, d in runs:
    axA.axvspan(h0, h0+d, color=RED, alpha=0.18, zorder=1)
axA.scatter([], [], color=RED, alpha=0.4, marker="s", s=60, label="GPS frozen (wedge)")
axA.annotate(f"drift {V:.1f}°/day east\n(full loop ≈ 38 days)", xy=(T[-1], LO[-1]), xytext=(T[-1]*0.62, -55),
             fontsize=9, color=INK, fontweight="bold", arrowprops=dict(arrowstyle="->", color=INK))
axA.set_ylim(-130, 70); axA.set_xlabel("hours since first fix (2026-05-15)", fontsize=10); axA.set_ylabel("longitude (°E)", fontsize=10)
axA.set_title("Early flight: the balloon drifted US915 → EU868, with brief GPS wedges (red)\n"
              "region tracked the band correctly while GPS recovered — wedges were short", fontsize=12, fontweight="bold", color=INK)
axA.legend(loc="lower right", fontsize=9); axA.grid(alpha=0.2)

# ---- Panel B: wedge duration → band-flip risk ----
wd = np.array([d for _, d in runs])
axB.scatter(wd, V*wd/24, s=70, color=RED, zorder=4, label="measured wedges (this flight)")
xx = np.logspace(np.log10(0.1), np.log10(400), 200)
axB.plot(xx, V*xx/24, color=INK, lw=1.5, alpha=0.7, label=f"drift = {V:.1f}°/day × duration")
axB.axhline(90, color=GRN, lw=1.6, ls="--"); axB.text(0.12, 96, "90° = full EU868 band width (must drift this far to leave it)", color=GRN, fontsize=9, fontweight="bold")
axB.axhspan(0, 13, color=YEL, alpha=0.12); axB.text(0.12, 4, "measured wedges → <13° drift → almost never flips the band", color="#a87503", fontsize=9, fontweight="bold")
for Tf, lab in [(24, "1-day deep\nfreeze"), (120, "5-day deep\nfreeze")]:
    axB.scatter([Tf], [V*Tf/24], s=90, marker="X", color="#7a1f1f", zorder=5)
    axB.annotate(lab, xy=(Tf, V*Tf/24), xytext=(Tf*0.7, V*Tf/24*1.6), fontsize=8, color="#7a1f1f", fontweight="bold", ha="center")
axB.set_xscale("log"); axB.set_xlim(0.1, 400); axB.set_ylim(0, 130)
axB.set_xlabel("GPS wedge / freeze duration (hours, log)", fontsize=10); axB.set_ylabel("balloon longitude drift during freeze (°)", fontsize=10)
axB.set_title("Wrong-band risk: a wedge mis-bands the balloon only if it drifts across a boundary while frozen\n"
              "MEASURED wedges are far too short → bug is a few-% effect, NOT the cause; only a multi-day DEEP freeze would dominate",
              fontsize=11.5, fontweight="bold", color=INK)
axB.legend(loc="center right", fontsize=9); axB.grid(alpha=0.2, which="both")
fig.tight_layout()
fig.savefig(HERE / "wedge_wrongband.png", dpi=160, bbox_inches="tight")
print("wrote wedge_wrongband.png  | wedges:", len(runs), " longest:", round(max(d for _,d in runs),1), "h")
