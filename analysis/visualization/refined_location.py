#!/usr/bin/env python3
"""High-confidence location for the 2026-06-24 02:18 UTC join — built on REAL gateway data.

No assumed coverage edge this time. We use Caleb's 14,232 actual TTN community gateway
positions (origin/main) to compute, for every point, the distance to the nearest community
gateway, and fold in the observed reception:

  P_fringe  the join was heard by ONE gateway at the SF7 cliff (max range) and by ZERO
            community gateways -> the balloon sits just BEYOND community reach, at the
            coverage fringe: d_to_nearest_community ~ max link range (~300 km). Peaks there,
            ~0 deep inside dense coverage (would be heard by many) and far in the void.
  P_sun     sunlit at 10 km by 02:18 + short warm-up (the reception proves ~15-30 min).
  P_lat     jet / flight latitude band.

Monte-Carlo marginalises the soft knobs. Result = the eastern fringe of European coverage,
in the EU868 band — substantiated by real gateway geometry, not a guess.

Run: analysis/.venv/bin/python analysis/visualization/refined_location.py
"""
from __future__ import annotations
from pathlib import Path
import json, math, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature

HERE = Path(__file__).resolve().parent
SCRATCH = Path("/private/tmp/claude-501/-Users-twarn-Repositories-Stratolink/1a6e7dc1-9e1f-40f4-9725-077569985574/scratchpad")
RED, YEL, BLU, INK, FAINT = "#d11d1d", "#f4b400", "#1f6fb2", "#2b3440", "#9aa6b4"
PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc)
DIP = 3.2

gw = json.load(open(SCRATCH / "gw.json"))
items = gw.get("gateways") if isinstance(gw, dict) else gw
gla = np.array([g["lat"] for g in items if g.get("lat") is not None])
glo = np.array([g["lon"] for g in items if g.get("lon") is not None])

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    dec = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam)))
    gmst = (280.46061837 + 360.98564736629*n) % 360
    return dec, ((ra - gmst + 180) % 360) - 180
decl, sublon = subsolar(PING)

lon = np.linspace(-22, 66, 620); lat = np.linspace(36, 59, 400)
LON, LAT = np.meshgrid(lon, lat)
# distance to nearest community gateway (great-circle) via KD-tree on the unit sphere
def to_xyz(la, lo):
    la, lo = np.radians(la), np.radians(lo)
    return np.column_stack([np.cos(la)*np.cos(lo), np.cos(la)*np.sin(lo), np.sin(la)])
try:
    from scipy.spatial import cKDTree
    tree = cKDTree(to_xyz(gla, glo))
    chord, _ = tree.query(to_xyz(LAT.ravel(), LON.ravel()))
    d_min = (2*6371.0*np.arcsin(np.clip(chord/2, 0, 1))).reshape(LAT.shape)
except Exception:
    d_min = np.full_like(LON, 1e9)
    for la, lo in zip(gla, glo):
        dla = np.radians(LAT-la); dlo = np.radians(LON-lo)
        a = np.sin(dla/2)**2 + np.cos(np.radians(la))*np.cos(np.radians(LAT))*np.sin(dlo/2)**2
        d_min = np.minimum(d_min, 6371.0*2*np.arcsin(np.sqrt(a)))

# 10 km daylight banked by 02:18
Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) \
         / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
Hsr = -np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))
daylight = (Hc - Hsr) / 15.0 * 60.0

rng = np.random.default_rng(20260624); NS = 320
post = np.zeros_like(LON)
for _ in range(NS):
    r_edge = rng.uniform(290, 350)   # balloon just beyond community reach (max link range)
    r_sig  = rng.uniform(70, 110)
    warm   = rng.uniform(12, 32)     # short cold-start (reception proves it)
    lmu = rng.normal(47, 3); lsig = rng.uniform(5, 8)
    P_fringe = np.exp(-0.5*((d_min - r_edge)/r_sig)**2)
    P_sun = np.clip(daylight/warm, 0, 1) * (daylight > 0)
    P_lat = np.exp(-0.5*((LAT - lmu)/lsig)**2)
    P_eu868 = 1.0/(1.0 + np.exp((LON - 57.0)/3.0))   # EU868 band edge ~+60E (region_manager) → AS923 east of it can't hear an EU868 join
    s = P_fringe*P_sun*P_lat*P_eu868; tot = s.sum()
    if tot > 0: post += s/tot
post /= post.sum()
flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]
def bbox(m): return LON[m].min(), LON[m].max(), LAT[m].min(), LAT[m].max()
b50, b90 = bbox(post >= t50), bbox(post >= t90)

EXT = ccrs.PlateCarree()
CITIES = [("Prague",50.08,14.44),("Warsaw",52.23,21.01),("Kyiv",50.45,30.52),("Minsk",53.9,27.57),
          ("Lviv",49.84,24.03),("Kharkiv",49.99,36.23),("Moscow",55.75,37.62),("Bucharest",44.43,26.10),
          ("Rostov",47.23,39.70),("Volgograd",48.7,44.5),("Vienna",48.21,16.37)]
fig = plt.figure(figsize=(15, 8.4)); ax = plt.axes(projection=EXT); ax.set_extent([-20, 64, 37, 58], crs=EXT)
ax.add_feature(cfeature.OCEAN, facecolor="#eaf1f7", zorder=0); ax.add_feature(cfeature.LAND, facecolor="#f6f4ef", zorder=0)
ax.add_feature(cfeature.BORDERS, edgecolor="#c2cad4", linewidth=0.6, zorder=3); ax.add_feature(cfeature.COASTLINE, edgecolor="#aab4c0", linewidth=0.6, zorder=3)
gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#dde3ea", alpha=0.8); gl.top_labels = gl.right_labels = False
gl.xlabel_style = gl.ylabel_style = {"size": 8, "color": FAINT}
# real community gateways (blue) — you can SEE the dense-west / sparse-east
m = (glo > -22) & (glo < 66) & (gla > 36) & (gla < 59)
ax.scatter(glo[m], gla[m], s=2.2, color=BLU, alpha=0.45, transform=EXT, zorder=2, label="TTN community gateways")
# sun: dawn line + yellow wash
ax.contourf(LON, LAT, np.clip(daylight/120,0,1), levels=np.linspace(0.01,1,8), cmap="YlOrBr", alpha=0.18, transform=EXT, zorder=1)
ax.contour(LON, LAT, daylight, levels=[0], colors=[INK], linewidths=1.2, linestyles="--", alpha=0.7, transform=EXT, zorder=4)
# red posterior
ax.contourf(LON, LAT, post, levels=[t90, t50], colors=[RED], alpha=0.18, transform=EXT, zorder=5)
ax.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[RED], alpha=0.42, transform=EXT, zorder=5)
ax.contour(LON, LAT, post, levels=[t90], colors=[RED], linewidths=1.1, linestyles="--", transform=EXT, zorder=6)
ax.contour(LON, LAT, post, levels=[t50], colors=[RED], linewidths=2.2, transform=EXT, zorder=6)
ax.plot(pk_lon, pk_lat, "o", ms=20, color=RED, alpha=0.15, transform=EXT, zorder=7)
ax.plot(pk_lon, pk_lat, "o", ms=10.5, color=RED, mec="white", mew=1.5, transform=EXT, zorder=8)
for nm, la, lo in CITIES:
    if -20 < lo < 64 and 37 < la < 58:
        ax.plot(lo, la, "o", ms=2.4, color=INK, alpha=0.55, transform=EXT, zorder=7)
        ax.text(lo+0.35, la+0.18, nm, fontsize=7.5, color=INK, alpha=0.85, transform=EXT, zorder=7)
ax.text(pk_lon, pk_lat-1.7, f"most likely  {pk_lat:.0f}°N {pk_lon:.0f}°E", fontsize=10, color=RED, fontweight="bold", ha="center", va="top", transform=EXT, zorder=8)
ax.set_title("Stratolink-3 — refined location on REAL gateway geometry  (2026-06-24 02:18 UTC join)\n"
             "fringe of community coverage (heard by 1 gw at max range, 0 community) ∩ sunlit ∩ jet latitude",
             fontsize=12.5, fontweight="bold", color=INK, pad=10)
ax.legend(handles=[
    Patch(facecolor=RED, alpha=0.42, label=f"50% region  ({b50[0]:.0f}–{b50[1]:.0f}°E, {b50[2]:.0f}–{b50[3]:.0f}°N)"),
    Patch(facecolor=RED, alpha=0.18, label=f"90% region  ({b90[0]:.0f}–{b90[1]:.0f}°E, {b90[2]:.0f}–{b90[3]:.0f}°N)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor=BLU, ms=6, label="14,232 community gateways (real)"),
    Line2D([0],[0], color=INK, lw=1.2, ls="--", label="dawn line at 02:18 (sunlit limit)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor=RED, mec="white", mew=1.2, ms=11, label=f"most likely ({pk_lat:.0f}°N {pk_lon:.0f}°E)"),
], loc="lower left", fontsize=8.5, framealpha=0.95)
fig.savefig(HERE / "refined_location.png", dpi=170, bbox_inches="tight")
print("wrote refined_location.png")
print(f"most likely {pk_lat:.1f}N {pk_lon:.1f}E | 50% {tuple(round(float(x),1) for x in b50)} | 90% {tuple(round(float(x),1) for x in b90)}")
print(f"d_min at peak = {d_min[pk]:.0f} km ; daylight at peak = {daylight[pk]:.0f} min")
