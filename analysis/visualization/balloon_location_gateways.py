#!/usr/bin/env python3
"""Board #3 location, now built on the REAL COMET gateway constellation (ttnmapper).

Teddy pulled the ~27 gateways of the COMET network off ttnmapper. They run UK -> Spain ->
a dense Central-European cluster (Munich/Prague/Bratislava) trailing east across Slovakia,
with the EASTERNMOST gateway at only ~22E (Kosice area). Coordinates below are read off the
screenshot (approximate; refine with an exact export).

That kills the far-east case. The join was heard at ~MAX SF7 range (SNR -7.25 dB / ch_rssi
-121 dBm, right at the cliff) from ONE gateway, and the balloon had to be SUNLIT at 02:18.
So the balloon sits just EAST of the easternmost gateways, on the sunlit side, ~300 km out.

It also pins the cold-start: at ~24-27E the balloon had only ~15-30 min of 10 km-sun banked
by 02:18, yet it transmitted -> the warm-up is SHORT (~15-30 min), not the 1-2 h the
coverage-confounded flight numbers suggested. The reception itself proves it.

Model (smooth, Monte-Carlo over the soft knobs):
  d_min(x)   distance to nearest real gateway (haversine)
  P_signal   marginal link -> d_min ~ max SF7 range (peak ~290 km, in [250,340])
  P_sun      sunlit at 02:18 + short warm-up floor (daylight >~ 15-30 min)
  P_lat      mild jet/flight band
Run: analysis/.venv/bin/python analysis/visualization/balloon_location_gateways.py
"""
from __future__ import annotations
from pathlib import Path
import math, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature

HERE = Path(__file__).resolve().parent
RED, YEL, BLU, INK, FAINT = "#d11d1d", "#f4b400", "#1f6fb2", "#2b3440", "#9aa6b4"
PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc)
DIP = 3.2

# COMET gateways read off the ttnmapper screenshot (lat, lon) — approximate
GW = [(55.8,-4.3),(51.4,-2.6),(51.5,-0.1),                       # UK
      (39.5,-0.4),                                               # Spain (Valencia)
      (49.4,8.4),(48.1,11.6),                                    # Germany
      (50.1,14.4),(50.4,13.9),(49.7,13.4),(50.7,15.2),           # Czech (Prague cluster)
      (48.2,17.1),(48.5,17.2),(48.7,18.6),(48.9,19.4),           # Slovakia W
      (49.0,20.1),(48.8,20.8),(48.7,21.3),(48.7,21.7)]           # Slovakia E (easternmost ~21.7E)
GWLAT = np.array([g[0] for g in GW]); GWLON = np.array([g[1] for g in GW])

CITIES = [("Prague",50.08,14.44),("Bratislava",48.15,17.11),("Kraków",50.06,19.94),
          ("Lviv",49.84,24.03),("Kyiv",50.45,30.52),("Budapest",47.50,19.04),
          ("Warsaw",52.23,21.01),("Vienna",48.21,16.37),("Ternopil",49.55,25.59)]

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    dec = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam)))
    gmst = (280.46061837 + 360.98564736629*n) % 360
    return dec, ((ra - gmst + 180) % 360) - 180
decl, sublon = subsolar(PING)

lon = np.linspace(-12, 40, 680); lat = np.linspace(39, 58, 460)
LON, LAT = np.meshgrid(lon, lat)
# daylight banked by 02:18 (10 km sunrise at elev = -DIP)
Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) \
         / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
Hsr = -np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))
daylight = (Hc - Hsr) / 15.0 * 60.0
# distance to nearest gateway (km)
def haversine(la, lo, la2, lo2):
    la, la2 = np.radians(la), np.radians(la2); dphi = la2-la; dl = np.radians(lo2-lo)
    a = np.sin(dphi/2)**2 + np.cos(la)*np.cos(la2)*np.sin(dl/2)**2
    return 6371.0*2*np.arcsin(np.sqrt(a))
d_min = np.full_like(LON, 1e9)
for la, lo in GW: d_min = np.minimum(d_min, haversine(LAT, LON, la, lo))

rng = np.random.default_rng(20260624); NS = 300
post = np.zeros_like(LON)
for _ in range(NS):
    r_peak = rng.uniform(255, 320); r_sig = rng.uniform(45, 70)   # marginal link -> near max range
    warm   = rng.uniform(12, 32)                                  # short cold-start floor (min)
    lmu = rng.normal(47, 3); lsig = rng.uniform(5, 8)
    P_signal = np.exp(-0.5*((d_min - r_peak)/r_sig)**2)
    P_sun = np.clip(daylight/warm, 0, 1) * (daylight > 0)
    P_lat = np.exp(-0.5*((LAT - lmu)/lsig)**2)
    s = P_signal*P_sun*P_lat; tot = s.sum()
    if tot > 0: post += s/tot
post /= post.sum()
flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]
def bbox(m): return LON[m].min(), LON[m].max(), LAT[m].min(), LAT[m].max()
b50, b90 = bbox(post >= t50), bbox(post >= t90)

EXT = ccrs.PlateCarree()
def rgba(field, hexcol, amax):
    r, g, bl = (int(hexcol[i:i+2], 16)/255 for i in (1, 3, 5))
    return np.dstack([np.full_like(field, r), np.full_like(field, g), np.full_like(field, bl), np.clip(field,0,1)*amax])
def nice_dot(ax, lo, la, c=RED):
    ax.plot(lo, la, "o", ms=20, color=c, alpha=0.15, transform=EXT, zorder=8)
    ax.plot(lo, la, "o", ms=10.5, color=c, mec="white", mew=1.5, transform=EXT, zorder=9)
def basemap(ax, ext):
    ax.set_extent(ext, crs=EXT)
    ax.add_feature(cfeature.OCEAN, facecolor="#eaf1f7", zorder=0); ax.add_feature(cfeature.LAND, facecolor="#f6f4ef", zorder=0)
    ax.add_feature(cfeature.BORDERS, edgecolor="#c2cad4", linewidth=0.6, zorder=3); ax.add_feature(cfeature.COASTLINE, edgecolor="#aab4c0", linewidth=0.6, zorder=3)
    gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#dde3ea", alpha=0.8, zorder=2); gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 8, "color": FAINT}
    for nm, la, lo in CITIES:
        if ext[0]+0.5 < lo < ext[1]-0.5 and ext[2]+0.5 < la < ext[3]-0.5:
            ax.plot(lo, la, "o", ms=2.4, color=INK, alpha=0.5, transform=EXT, zorder=7)
            ax.text(lo+0.35, la+0.18, nm, fontsize=7.5, color=INK, alpha=0.8, transform=EXT, zorder=7)

# coverage union (for the blue layer): max over gateways of a soft SF7 disk (~340 km)
cov = np.zeros_like(LON)
for la, lo in GW: cov = np.maximum(cov, 1.0/(1.0+np.exp((haversine(LAT,LON,la,lo)-330)/35.0)))

fig = plt.figure(figsize=(14.5, 8.4)); ax = plt.axes(projection=EXT); basemap(ax, [-10, 39, 40, 57])
ax.imshow(rgba(np.clip(daylight/120.0,0,1), YEL, 0.34), extent=[-12,40,39,58], origin="lower", transform=EXT, zorder=1)
ax.imshow(rgba(cov, BLU, 0.30), extent=[-12,40,39,58], origin="lower", transform=EXT, zorder=1)
ax.contour(LON, LAT, daylight, levels=[0], colors=[INK], linewidths=1.3, linestyles="--", alpha=0.7, transform=EXT, zorder=4)
ax.plot(GWLON, GWLAT, "o", ms=5, color=BLU, mec="white", mew=0.7, transform=EXT, zorder=6, label="COMET gateways")
ax.contourf(LON, LAT, post, levels=[t90, t50], colors=[RED], alpha=0.18, transform=EXT, zorder=5)
ax.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[RED], alpha=0.40, transform=EXT, zorder=5)
ax.contour(LON, LAT, post, levels=[t90], colors=[RED], linewidths=1.1, linestyles="--", transform=EXT, zorder=6)
ax.contour(LON, LAT, post, levels=[t50], colors=[RED], linewidths=2.2, transform=EXT, zorder=6)
nice_dot(ax, pk_lon, pk_lat)
ax.text(pk_lon+0.4, pk_lat-1.5, f"most likely\n{pk_lat:.0f}°N {pk_lon:.0f}°E", fontsize=9.5, color=RED, fontweight="bold", ha="center", va="top", transform=EXT, zorder=9)
ax.text(8, 41.2, "YELLOW: sunlit at 02:18 (power)", fontsize=8.5, color="#a87503", fontweight="bold", transform=EXT, zorder=9)
ax.text(-9, 41.0, "BLUE: real COMET gateways + SF7 reach", fontsize=8.5, color="#155a91", fontweight="bold", transform=EXT, zorder=9)
ax.set_title("Stratolink-3 — location from the REAL gateway constellation (2026-06-24 02:18 UTC join)\n"
             "sunlit ∩ max-range from the easternmost COMET gateways  →  western Ukraine borderlands",
             fontsize=12, fontweight="bold", color=INK, pad=10)
ax.legend(handles=[
    Patch(facecolor=RED, alpha=0.40, label=f"most-probable region · 50%  ({b50[0]:.0f}–{b50[1]:.0f}°E, {b50[2]:.0f}–{b50[3]:.0f}°N)"),
    Patch(facecolor=RED, alpha=0.18, label=f"90% region  ({b90[0]:.0f}–{b90[1]:.0f}°E, {b90[2]:.0f}–{b90[3]:.0f}°N)"),
    Patch(facecolor=BLU, alpha=0.30, label="COMET gateway coverage (SF7 ~340 km)"),
    Patch(facecolor=YEL, alpha=0.34, label="sunlit at 10 km by 02:18"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor=BLU, mec="white", ms=7, label="COMET gateways (ttnmapper)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor=RED, mec="white", mew=1.2, ms=11, label=f"most likely ({pk_lat:.0f}°N {pk_lon:.0f}°E)"),
], loc="lower right", fontsize=8.5, framealpha=0.95)
fig.savefig(HERE / "balloon_location_gateways.png", dpi=170, bbox_inches="tight")
print("wrote balloon_location_gateways.png")
print(f"most likely {pk_lat:.1f}N {pk_lon:.1f}E | 50% {tuple(round(float(x),1) for x in b50)} | 90% {tuple(round(float(x),1) for x in b90)}")
print(f"easternmost gateway {GWLON.max():.1f}E ; daylight at peak = {daylight[pk]:.0f} min (=> cold-start ~ that)")
