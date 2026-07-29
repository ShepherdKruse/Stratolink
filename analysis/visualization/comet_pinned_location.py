#!/usr/bin/env python3
"""High-accuracy location using the REAL COMET gateway positions (Packet Broker Mapper).

We pulled COMET's actual gateways (tenant cometsystem-cloud, netID 000013) from the public
Packet Broker Mapper API — the network that forwarded our join. Now the join is constrained
hard:

  P_comet   the join was heard by ONE COMET gateway at the SF7 cliff (max range ~300 km):
            the balloon sits on a ~300 km RING around the nearest COMET gateway.
  P_shadow  NO community gateway heard it -> the balloon is beyond community reach
            (d to nearest of Caleb's 14,232 community gateways > ~300 km). This kills the
            rings around COMET gateways that sit inside dense community (Czech/Slovak home).
  P_sun     sunlit at 10 km by 02:18 + short warm-up.
  P_lat     jet / flight latitude band.

The surviving region = a ring around whichever COMET gateway is in a community shadow on the
sunlit side. Monte-Carlo marginalises the link range, warm-up, and latitude.

Run: analysis/.venv/bin/python analysis/visualization/comet_pinned_location.py
"""
from __future__ import annotations
from pathlib import Path
import csv, json, math, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature

HERE = Path(__file__).resolve().parent
SC = Path("/private/tmp/claude-501/-Users-twarn-Repositories-Stratolink/1a6e7dc1-9e1f-40f4-9725-077569985574/scratchpad")
RED, YEL, BLU, MAG, INK, FAINT = "#d11d1d", "#f4b400", "#1f6fb2", "#b5179e", "#2b3440", "#9aa6b4"
PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc); DIP = 3.2

cg = list(csv.DictReader(open(SC / "comet_only.csv")))
cla = np.array([float(r["lat"]) for r in cg]); clo = np.array([float(r["lon"]) for r in cg])
gw = json.load(open(SC / "gw.json")); items = gw.get("gateways") if isinstance(gw, dict) else gw
gla = np.array([g["lat"] for g in items if g.get("lat") is not None]); glo = np.array([g["lon"] for g in items if g.get("lon") is not None])
print(f"COMET gateways w/coords: {len(cla)} ; community: {len(gla)}")
print("COMET European (5-60E,35-62N):", sorted(round(float(l),1) for l in clo[(clo>5)&(clo<60)&(cla>35)&(cla<62)]))

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    dec = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam))); gmst = (280.46061837 + 360.98564736629*n) % 360
    return dec, ((ra - gmst + 180) % 360) - 180
decl, sublon = subsolar(PING)

lon = np.linspace(-12, 60, 640); lat = np.linspace(36, 60, 400); LON, LAT = np.meshgrid(lon, lat)
def to_xyz(la, lo):
    la, lo = np.radians(la), np.radians(lo)
    return np.column_stack([np.cos(la)*np.cos(lo), np.cos(la)*np.sin(lo), np.sin(la)])
from scipy.spatial import cKDTree
def dmin(plat, plon):
    tree = cKDTree(to_xyz(plat, plon)); ch, _ = tree.query(to_xyz(LAT.ravel(), LON.ravel()))
    return (2*6371.0*np.arcsin(np.clip(ch/2, 0, 1))).reshape(LAT.shape)
d_comet = dmin(cla, clo); d_comm = dmin(gla, glo)
Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
daylight = (Hc + np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))) / 15.0 * 60.0

rng = np.random.default_rng(20260624); NS = 320; post = np.zeros_like(LON)
for _ in range(NS):
    r_marg = rng.uniform(270, 330); r_sig = rng.uniform(45, 75)   # max-range ring around a COMET gw
    r_hear = rng.uniform(280, 340)                                # community hearing range
    warm = rng.uniform(12, 32); lmu = rng.normal(47, 3); lsig = rng.uniform(5, 8)
    P_comet = np.exp(-0.5*((d_comet - r_marg)/r_sig)**2)
    P_shadow = 1.0/(1.0 + np.exp((r_hear - d_comm)/40.0))         # ~0 inside community reach, ~1 beyond
    P_sun = np.clip(daylight/warm, 0, 1) * (daylight > 0)
    P_lat = np.exp(-0.5*((LAT - lmu)/lsig)**2)
    s = P_comet*P_shadow*P_sun*P_lat; tot = s.sum()
    if tot > 0: post += s/tot
post /= post.sum()
flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]
def bbox(m): return LON[m].min(), LON[m].max(), LAT[m].min(), LAT[m].max()
b50, b90 = bbox(post >= t50), bbox(post >= t90)

EXT = ccrs.PlateCarree()
fig = plt.figure(figsize=(15, 8.4)); ax = plt.axes(projection=EXT); ax.set_extent([-11, 59, 37, 59], crs=EXT)
ax.add_feature(cfeature.OCEAN, facecolor="#eaf1f7", zorder=0); ax.add_feature(cfeature.LAND, facecolor="#f6f4ef", zorder=0)
ax.add_feature(cfeature.BORDERS, edgecolor="#c2cad4", linewidth=0.6, zorder=3); ax.add_feature(cfeature.COASTLINE, edgecolor="#aab4c0", linewidth=0.6, zorder=3)
gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#dde3ea", alpha=0.8); gl.top_labels = gl.right_labels = False
gl.xlabel_style = gl.ylabel_style = {"size": 8, "color": FAINT}
cm = (glo > -12) & (glo < 60) & (gla > 36) & (gla < 60)
ax.scatter(glo[cm], gla[cm], s=1.4, color=BLU, alpha=0.30, transform=EXT, zorder=2, label="community gateways (14k)")
ax.contour(LON, LAT, daylight, levels=[0], colors=[INK], linewidths=1.2, linestyles="--", alpha=0.7, transform=EXT, zorder=4)
ax.contourf(LON, LAT, post, levels=[t90, t50], colors=[RED], alpha=0.20, transform=EXT, zorder=5)
ax.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[RED], alpha=0.45, transform=EXT, zorder=5)
ax.contour(LON, LAT, post, levels=[t50], colors=[RED], linewidths=2.0, transform=EXT, zorder=6)
ax.scatter(clo, cla, s=42, marker="D", color=MAG, edgecolors="white", linewidth=0.6, transform=EXT, zorder=7, label="COMET gateways (real, Packet Broker)")
ax.plot(pk_lon, pk_lat, "o", ms=11, color=RED, mec="white", mew=1.5, transform=EXT, zorder=8)
ax.text(pk_lon, pk_lat-1.6, f"most likely\n{pk_lat:.0f}°N {pk_lon:.0f}°E", fontsize=10, color=RED, fontweight="bold", ha="center", va="top", transform=EXT, zorder=8)
ax.set_title("Stratolink-3 — pinned on REAL COMET gateways (Packet Broker Mapper)  ·  2026-06-24 02:18 UTC join\n"
             "max-range ring around a COMET gateway ∩ community shadow ∩ sunlit ∩ jet latitude",
             fontsize=12.5, fontweight="bold", color=INK, pad=10)
ax.legend(handles=[
    Patch(facecolor=RED, alpha=0.45, label=f"50% region ({b50[0]:.0f}–{b50[1]:.0f}°E, {b50[2]:.0f}–{b50[3]:.0f}°N)"),
    Patch(facecolor=RED, alpha=0.20, label=f"90% region ({b90[0]:.0f}–{b90[1]:.0f}°E, {b90[2]:.0f}–{b90[3]:.0f}°N)"),
    Line2D([0],[0], marker="D", color="w", markerfacecolor=MAG, ms=9, label="COMET gateways (real positions)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor=BLU, ms=6, label="community gateways (shadow test)"),
    Line2D([0],[0], color=INK, lw=1.2, ls="--", label="dawn line at 02:18"),
], loc="lower left", fontsize=8.5, framealpha=0.95)
fig.savefig(HERE / "comet_pinned_location.png", dpi=170, bbox_inches="tight")
print(f"wrote comet_pinned_location.png | most likely {pk_lat:.1f}N {pk_lon:.1f}E | 50% {tuple(round(float(x),1) for x in b50)} | 90% {tuple(round(float(x),1) for x in b90)}")
print(f"d_comet at peak={d_comet[pk]:.0f}km d_community at peak={d_comm[pk]:.0f}km daylight={daylight[pk]:.0f}min")
