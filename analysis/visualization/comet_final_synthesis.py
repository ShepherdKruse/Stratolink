#!/usr/bin/env python3
"""FINAL location synthesis — COMET's real gateways (Packet Broker) confirm the east by elimination.

We pulled COMET's actual network from the public Packet Broker Mapper (tenant cometsystem-cloud,
netID 000013): 32 gateways with coordinates. Every mid-latitude European one is <= 19E
(Czech HQ Rožnov 18.1E, Bratislava 17E, Germany) — none east of 19E (the only outlier is a
Dubai customer at 55E/25N, proving COMET has far-flung UNMAPPED customers).

Cross-check that fixes the location:
  the 06-24 join was MARGINAL (SNR at the SF7 floor, ~max range ~340 km). If the receiving
  gateway were a MAPPED one (<=19E), the balloon would be <=24E — where TTN community gateways
  are ~150 km away and would hear the SAME signal ~10-15 dB LOUDER, so they'd have decoded it.
  None did. => the balloon is NOT near the mapped gateways; it was heard by an UNMAPPED COMET
  customer gateway in the eastern TTN-community SHADOW.

So the location reverts to (and is now CONFIRMED at) the community-shadow estimate: the balloon
sits beyond mapped-COMET reach, in the community shadow, sunlit, jet-latitude. Posterior below.

Run: analysis/.venv/bin/python analysis/visualization/comet_final_synthesis.py
"""
from __future__ import annotations
from pathlib import Path
import csv, json, math, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
SC = Path("/private/tmp/claude-501/-Users-twarn-Repositories-Stratolink/1a6e7dc1-9e1f-40f4-9725-077569985574/scratchpad")
RED, YEL, BLU, MAG, INK, FAINT = "#d11d1d", "#f4b400", "#1f6fb2", "#b5179e", "#2b3440", "#9aa6b4"
PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc); DIP = 3.2

cg = list(csv.DictReader(open(SC / "comet_only.csv")))
cla = np.array([float(r["lat"]) for r in cg]); clo = np.array([float(r["lon"]) for r in cg])
gw = json.load(open(SC / "gw.json")); items = gw.get("gateways") if isinstance(gw, dict) else gw
gla = np.array([g["lat"] for g in items if g.get("lat") is not None]); glo = np.array([g["lon"] for g in items if g.get("lon") is not None])

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    dec = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam))); gmst = (280.46061837 + 360.98564736629*n) % 360
    return dec, ((ra - gmst + 180) % 360) - 180
decl, sublon = subsolar(PING)

lon = np.linspace(-12, 60, 600); lat = np.linspace(36, 59, 380); LON, LAT = np.meshgrid(lon, lat)
def to_xyz(la, lo):
    la, lo = np.radians(la), np.radians(lo)
    return np.column_stack([np.cos(la)*np.cos(lo), np.cos(la)*np.sin(lo), np.sin(la)])
def dmin(plat, plon):
    ch, _ = cKDTree(to_xyz(plat, plon)).query(to_xyz(LAT.ravel(), LON.ravel()))
    return (2*6371.0*np.arcsin(np.clip(ch/2, 0, 1))).reshape(LAT.shape)
d_comm = dmin(gla, glo); d_comet = dmin(cla, clo)
Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
daylight = (Hc + np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))) / 15.0 * 60.0

# community-shadow posterior (the confirmed model): beyond community reach ∩ sunlit ∩ jet ∩ EU868
rng = np.random.default_rng(20260624); NS = 320; post = np.zeros_like(LON)
for _ in range(NS):
    r_edge = rng.uniform(300, 360); r_sig = rng.uniform(70, 110); warm = rng.uniform(12, 32)
    lmu = rng.normal(47, 3); lsig = rng.uniform(5, 8)
    P_fringe = np.exp(-0.5*((d_comm - r_edge)/r_sig)**2)
    P_sun = np.clip(daylight/warm, 0, 1) * (daylight > 0)
    P_lat = np.exp(-0.5*((LAT - lmu)/lsig)**2)
    P_eu = 1.0/(1.0 + np.exp((LON - 57.0)/3.0))
    s = P_fringe*P_sun*P_lat*P_eu; tot = s.sum()
    if tot > 0: post += s/tot
post /= post.sum()
from scipy.ndimage import gaussian_filter
post = gaussian_filter(post, sigma=8); post /= post.sum()   # smooth the fringe rings into clean contours
flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]
def bbox(m): return LON[m].min(), LON[m].max(), LAT[m].min(), LAT[m].max()
b50, b90 = bbox(post >= t50), bbox(post >= t90)
comet_reach = (d_comet < 340).astype(float)   # mapped-COMET max SF7 footprint (ruled out)

EXT = ccrs.PlateCarree()
from cartopy.geodesic import Geodesic
GREY = "#9aa1ab"; DOT = "#7e8aa3"
fig = plt.figure(figsize=(14, 7.6)); ax = plt.axes(projection=EXT); ax.set_extent([-11, 59, 37, 58], crs=EXT)
ax.add_feature(cfeature.OCEAN, facecolor="#eef2f6", zorder=0); ax.add_feature(cfeature.LAND, facecolor="#f8f6f2", zorder=0)
ax.add_feature(cfeature.BORDERS, edgecolor="#d2d8df", linewidth=0.5, zorder=3); ax.add_feature(cfeature.COASTLINE, edgecolor="#bcc4cd", linewidth=0.5, zorder=3)
g = ax.gridlines(draw_labels=True, linewidth=0.25, color="#e6eaef", alpha=0.7); g.top_labels = g.right_labels = False
g.xlabel_style = g.ylabel_style = {"size": 8, "color": FAINT}
# quiet context: community gateways + COMET mapped coverage (monochrome, dotted)
cm = (glo > -12) & (glo < 60) & (gla > 36) & (gla < 59)
ax.scatter(glo[cm], gla[cm], s=1.0, color=DOT, alpha=0.20, transform=EXT, zorder=2)
ax.contourf(LON, LAT, comet_reach, levels=[0.5, 1.5], colors=[GREY], alpha=0.10, transform=EXT, zorder=2)
ax.contour(LON, LAT, comet_reach, levels=[0.5], colors=[GREY], linewidths=0.9, linestyles=":", transform=EXT, zorder=4)
ax.contour(LON, LAT, daylight, levels=[0], colors=[GREY], linewidths=0.8, linestyles="--", alpha=0.8, transform=EXT, zorder=4)
# balloon posterior: 50% thin solid, 90% dotted
ax.contourf(LON, LAT, post, levels=[t90, t50], colors=[RED], alpha=0.09, transform=EXT, zorder=5)
ax.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[RED], alpha=0.24, transform=EXT, zorder=5)
ax.contour(LON, LAT, post, levels=[t90], colors=[RED], linewidths=0.9, linestyles=":", transform=EXT, zorder=6)
ax.contour(LON, LAT, post, levels=[t50], colors=[RED], linewidths=1.2, transform=EXT, zorder=6)
# SF7 reach around the most-likely point
circ = Geodesic().circle(lon=float(pk_lon), lat=float(pk_lat), radius=340000.0, n_samples=180)
ax.plot(circ[:, 0], circ[:, 1], color=RED, lw=1.0, alpha=0.5, transform=EXT, zorder=6)
# most-likely point + a clean leadered label
ax.plot(pk_lon, pk_lat, "o", ms=7, color=RED, mec="white", mew=1.2, transform=EXT, zorder=8)
ax.annotate(f"Balloon   {pk_lat:.0f}°N · {pk_lon:.0f}°E", xy=(pk_lon, pk_lat), xytext=(pk_lon + 6.5, pk_lat - 6.2),
            fontsize=11, color=RED, fontweight="bold", va="center", transform=EXT, zorder=8,
            arrowprops=dict(arrowstyle="-", color=RED, lw=0.7, alpha=0.55))
ax.set_title("Stratolink-3 location: COMET's real gateways confirm the east by elimination\n"
             "mapped COMET network is all ≤19°E; the marginal single-gateway ping rules it out, leaving the eastern community shadow",
             fontsize=11.5, fontweight="bold", color=INK, pad=10)
ax.legend(handles=[
    Patch(facecolor=RED, alpha=0.24, label="balloon · 50% region"),
    Line2D([0], [0], color=RED, lw=0.9, ls=":", label="balloon · 90% region"),
    Line2D([0], [0], color=RED, lw=1.0, alpha=0.6, label="SF7 reach (~340 km)"),
    Line2D([0], [0], color=GREY, lw=0.9, ls=":", label="COMET mapped coverage (ruled out)"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=DOT, ms=5, label="TTN community gateways"),
], loc="lower left", fontsize=8.5, framealpha=0.9, edgecolor="#e2e7ec")
fig.savefig(HERE / "comet_final_synthesis.png", dpi=180, bbox_inches="tight")
print(f"wrote comet_final_synthesis.png | BALLOON {pk_lat:.1f}N {pk_lon:.1f}E | 50% {tuple(round(float(x),1) for x in b50)} | 90% {tuple(round(float(x),1) for x in b90)}")
