#!/usr/bin/env python3
"""Warm-up-narrowed location for the 2026-06-24 02:18:34 UTC join.

Flight data gives the lag from 10 km-sunrise to first emission: ~100 min (Arizona,
19 May) and ~170 min (Spain, 28 May), mean ~135 min (the launch's 190 min is
excluded — hand-powered, not a solar warm-up). The balloon runs on solar+supercap,
so it emits ~this long AFTER its sunrise.

So at the 02:18 UTC join, the balloon's 10 km-sunrise was ~100-170 min earlier
(~23:28-00:38 UTC). Sunrise sweeps east->west, so "sunrise 2 h ago" is a longitude
band well EAST of Central Europe. We shade the band where 10 km-sunrise fell in the
measured warm-up window (best estimate) plus a lighter band toward the 02:18
terminator (if the warm-up was shorter / cap not fully drained).

COMET System is Czech-HQ'd but runs a private TTI network with gateways at customer
sites; an eastern customer's gateway forwarded this join via Packet Broker.

Run: analysis/.venv/bin/python analysis/visualization/comet_warmup_map.py
"""
from __future__ import annotations
from pathlib import Path
import sys, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
try:
    import _style as S
    S.use_light(); RED, WARM, MINT, DIM = S.RED, S.WARM, S.MINT, S.TEXT_DIM
except Exception:
    RED, WARM, MINT, DIM = "#e0594a", "#f4a259", "#2a9d4e", "#7e8aa3"

import cartopy.crs as ccrs
import cartopy.feature as cfeature

PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc)
DIP = 3.2                        # 10 km horizon dip (deg) -> sun elev at balloon sunrise
WARM_MIN, WARM_MAX = 100, 170    # measured warm-up lag (min), flight data
EXTENT = [4, 73, 33, 63]

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = np.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = np.radians((Ld + 1.915*np.sin(g) + 0.020*np.sin(2*g)) % 360); eps = np.radians(23.439 - 3.6e-7*n)
    decl = np.degrees(np.arcsin(np.sin(eps)*np.sin(lam)))
    ra = np.degrees(np.arctan2(np.cos(eps)*np.sin(lam), np.cos(lam)))
    gmst = (280.46061837 + 360.98564736629*n) % 360
    return decl, ((ra - gmst + 180) % 360) - 180

gx = np.linspace(EXTENT[0], EXTENT[1], 560); gy = np.linspace(EXTENT[2], EXTENT[3], 380)
LON, LAT = np.meshgrid(gx, gy)
def elev_at(when):
    d, sl = subsolar(when); Hh = np.radians(LON - sl)
    return np.degrees(np.arcsin(np.sin(np.radians(LAT))*np.sin(np.radians(d)) +
                                np.cos(np.radians(LAT))*np.cos(np.radians(d))*np.cos(Hh)))
e_ping = elev_at(PING)
e_min  = elev_at(PING - dt.timedelta(minutes=WARM_MIN))   # 00:38
e_max  = elev_at(PING - dt.timedelta(minutes=WARM_MAX))   # 23:28
# balloon lit when elev > -DIP. sunrise time = when elev crosses -DIP rising.
best_band  = (e_max < -DIP) & (e_min > -DIP)              # sunrise in [WARM_MIN,WARM_MAX] before ping
quick_band = (e_min < -DIP) & (e_ping > -DIP)             # sunrise in [0,WARM_MIN] before ping (west ext.)

fig = plt.figure(figsize=(14, 8.6)); ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent(EXTENT, crs=ccrs.PlateCarree()); pc = ccrs.PlateCarree()
ax.add_feature(cfeature.OCEAN, facecolor="#eef3f8", zorder=0)
ax.add_feature(cfeature.LAND, facecolor="#f7f5f1", zorder=0)
ax.add_feature(cfeature.BORDERS, edgecolor="#b9c2cf", linewidth=0.6, zorder=4)
ax.add_feature(cfeature.COASTLINE, edgecolor="#9aa6b4", linewidth=0.6, zorder=4)
gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#d8dee6", alpha=0.7); gl.top_labels = gl.right_labels = False

ax.contourf(LON, LAT, quick_band.astype(float), levels=[0.5, 1.5], colors=[WARM], alpha=0.16, transform=pc, zorder=2)
ax.contourf(LON, LAT, best_band.astype(float),  levels=[0.5, 1.5], colors=[WARM], alpha=0.42, transform=pc, zorder=2)
# 02:18 balloon terminator = hard western limit (west of it was dark at the join)
ax.contour(LON, LAT, e_ping, levels=[-DIP], colors=["#33414f"], linewidths=1.6, transform=pc, zorder=5)

ax.plot(18.14, 49.46, marker="*", ms=15, color=RED, mec="white", mew=0.8, transform=pc, zorder=6)
ax.text(15.6, 51.2, "COMET HQ\n(operator base —\nballoon shifted E\nby warm-up)", fontsize=8, color=RED, va="center", transform=pc, zorder=6)

ax.text(52, 60.5, "← balloon's dawn was here\n(sunrise ~2 h before the ping)", fontsize=9, color="#b07a1e", fontweight="bold", ha="center", transform=pc)

ax.set_title("Stratolink-3: warm-up-narrowed location for the 2026-06-24 02:18 UTC join\n"
             "balloon emits ~135 min (100–170) after its 10 km-sunrise → it was where dawn fell ~2 h before the ping",
             fontsize=12)
legend = [
    Patch(facecolor=WARM, alpha=0.42, label="best estimate · sunrise 100–170 min before ping (measured warm-up)"),
    Patch(facecolor=WARM, alpha=0.16, label="possible · shorter warm-up (toward the 02:18 dawn line)"),
    Line2D([0],[0], color="#33414f", lw=1.6, label="10 km dawn line at 02:18 (hard western limit)"),
    Line2D([0],[0], marker="*", color="w", markerfacecolor=RED, ms=13, label="COMET HQ (Czech operator base)"),
]
ax.legend(handles=legend, loc="lower left", fontsize=8, framealpha=0.92)
fig.text(0.5, 0.012,
         "Warm-up lag measured from 2 flight mornings (100 & 170 min; launch excluded) — sparse + confounded by coverage gaps, "
         "so the band is approximate. It rules OUT Central Europe for this ping (still dark) and shifts the estimate east into "
         "Eastern Europe / European Russia, where a COMET-network customer gateway forwarded the join.",
         ha="center", fontsize=7.5, color=DIM, wrap=True)
out = HERE / "comet_warmup_map.png"
fig.savefig(out, dpi=160, bbox_inches="tight")
print("wrote", out)
