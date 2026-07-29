#!/usr/bin/env python3
"""Two maps for board #3 at the 2026-06-24 02:18:34 UTC join.

The most-probable balloon region = the OVERLAP of two physical regions:
  A) gateway-network coverage dilated by the SF7 pickup range (~340 km @ 10 km), and
  B) the sunlit-and-warmed-up region: east of the 10 km dawn line, pushed in by the
     cold-start buffer (the balloon needs ~time after sunrise before it can emit).

  comet_overlap_simple.png   -- just that overlap, clean.
  comet_overlap_detailed.png -- the same overlap outlined, with every derivation layer
                                dimmed behind it (coverage, sun/warm-up, dawn line, the
                                fused 50/90 posterior) so you can see how we got there.

Run: analysis/.venv/bin/python analysis/visualization/comet_overlap_maps.py
"""
from __future__ import annotations
from pathlib import Path
import sys, math, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
try:
    import _style as S
    S.use_light(); WARM, DIM = S.WARM, S.TEXT_DIM
except Exception:
    WARM, DIM = "#f4a259", "#7e8aa3"
TEAL, HOT = "#3f8aa3", "#d2691e"

PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc)
DIP = 3.2
TAU_MU, TAU_SIG = 85.0, 50.0       # cold-start (min) for the fused posterior
TAU_EARLY = 40.0                   # earliest-probable emitting (warm-up buffer west edge)
GATEWAY_EAST = 30.0
SF7_KM = 340.0
SF7_DEG = SF7_KM / (111.0*math.cos(math.radians(48)))
COV_EDGE = GATEWAY_EAST + SF7_DEG  # ~34.6E
COV_SOFT = 6.0
LAT_MU, LAT_SIG = 42.0, 7.0

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    decl = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam)))
    gmst = (280.46061837 + 360.98564736629*n) % 360
    return decl, ((ra - gmst + 180) % 360) - 180

decl, sublon = subsolar(PING)
lon = np.linspace(-12, 82, 940); lat = np.linspace(27, 65, 520)
LON, LAT = np.meshgrid(lon, lat)
Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) \
         / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
Hsr = -np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))
daylight = (Hc - Hsr) / 15.0 * 60.0

erf = np.vectorize(math.erf)
P_warm = np.where(daylight > 0, 0.5*(1 + erf((daylight - TAU_MU)/(TAU_SIG*math.sqrt(2)))), 0.0)
P_cov_lon = 1.0/(1.0 + np.exp((LON - COV_EDGE)/COV_SOFT))
P_lat = np.exp(-0.5*((LAT - LAT_MU)/LAT_SIG)**2)
cov_lat = 1.0/(1.0+np.exp((LAT-59)/4.0)) * 1.0/(1.0+np.exp((36-LAT)/4.0))
coverage = P_cov_lon * cov_lat
emitting = (daylight >= TAU_EARLY)                       # sun + warm-up buffer (east of earliest-emit line)

post = P_warm * P_cov_lon * P_lat; post /= post.sum()
flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]

# THE OVERLAP: coverage(+SF7) AND sun/warm-up region AND jet-latitude band
overlap = (coverage >= 0.40) & emitting & (P_lat >= 0.45)
ov = overlap & (LON[0].min() < LON)
b = (LON[overlap].min(), LON[overlap].max(), LAT[overlap].min(), LAT[overlap].max())

def base(ax, extent):
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN, facecolor="#eef3f8", zorder=0)
    ax.add_feature(cfeature.LAND, facecolor="#f7f5f1", zorder=0)
    ax.add_feature(cfeature.BORDERS, edgecolor="#b9c2cf", linewidth=0.6, zorder=4)
    ax.add_feature(cfeature.COASTLINE, edgecolor="#9aa6b4", linewidth=0.6, zorder=4)
    g = ax.gridlines(draw_labels=True, linewidth=0.3, color="#d8dee6", alpha=0.7); g.top_labels = g.right_labels = False

pc = ccrs.PlateCarree()
ofloat = overlap.astype(float)

# ---------- MAP A: simple ----------
figA = plt.figure(figsize=(12, 8)); axA = plt.axes(projection=pc); base(axA, [8, 58, 35, 59])
axA.contourf(LON, LAT, ofloat, levels=[0.5, 1.5], colors=[WARM], alpha=0.55, transform=pc, zorder=3)
axA.contour(LON, LAT, ofloat, levels=[0.5], colors=[HOT], linewidths=2.4, transform=pc, zorder=5)
axA.plot(pk_lon, pk_lat, marker="x", ms=13, mew=2.8, color="#7a1f1f", transform=pc, zorder=6)
axA.text(pk_lon, b[3]+0.6, "most-probable balloon region", fontsize=11, color=HOT, fontweight="bold", ha="center", transform=pc, zorder=6)
axA.set_title("Stratolink-3 · 2026-06-24 02:18 UTC join — most-probable region\n"
              "overlap of (gateway network + SF7 reach) ∩ (sunlit + warm-up)", fontsize=12.5)
figA.savefig(HERE / "comet_overlap_simple.png", dpi=160, bbox_inches="tight")

# ---------- MAP B: detailed (overlap + dimmed derivation) ----------
figB = plt.figure(figsize=(15, 8.2)); axB = plt.axes(projection=pc); base(axB, [-8, 74, 29, 63])
# dim derivation layers
axB.contourf(LON, LAT, coverage, levels=[0.25, 1.01], colors=[TEAL], alpha=0.10, transform=pc, zorder=1)
axB.contour(LON, LAT, coverage, levels=[0.5], colors=[TEAL], linewidths=0.9, alpha=0.55, transform=pc, zorder=4)
axB.contourf(LON, LAT, emitting.astype(float), levels=[0.5, 1.5], colors=[WARM], alpha=0.07, transform=pc, zorder=1)
axB.contour(LON, LAT, daylight, levels=[0], colors=["#33414f"], linewidths=1.2, linestyles="--", alpha=0.7, transform=pc, zorder=4)
axB.contour(LON, LAT, daylight, levels=[TAU_EARLY], colors=[WARM], linewidths=1.0, linestyles=":", alpha=0.8, transform=pc, zorder=4)
axB.contour(LON, LAT, post, levels=[t90, t50], colors=["#b8893a"], linewidths=0.8, alpha=0.45, transform=pc, zorder=4)
# hero overlap
axB.contourf(LON, LAT, ofloat, levels=[0.5, 1.5], colors=[WARM], alpha=0.42, transform=pc, zorder=3)
axB.contour(LON, LAT, ofloat, levels=[0.5], colors=[HOT], linewidths=2.4, transform=pc, zorder=6)
axB.plot(pk_lon, pk_lat, marker="x", ms=12, mew=2.6, color="#7a1f1f", transform=pc, zorder=7)
axB.set_title("Stratolink-3 · 2026-06-24 02:18 UTC join — how the region is derived\n"
              "most-probable overlap (bold) = gateway+SF7 coverage ∩ sunlit+warm-up; derivation layers dimmed", fontsize=12)
legend = [
    Line2D([0],[0], color=HOT, lw=2.4, label="most-probable region (the overlap)"),
    Patch(facecolor=TEAL, alpha=0.18, label="gateway-network coverage (+ SF7 reach)"),
    Patch(facecolor=WARM, alpha=0.12, label="sunlit + warmed-up (east of earliest-emit)"),
    Line2D([0],[0], color="#33414f", lw=1.2, ls="--", label="dawn line at 02:18 (sunlit limit)"),
    Line2D([0],[0], color=WARM, lw=1.0, ls=":", label=f"earliest-emit line (~{TAU_EARLY:.0f} min warm-up)"),
    Line2D([0],[0], color="#b8893a", lw=0.8, alpha=0.6, label="fused 50 / 90% posterior (context)"),
    Line2D([0],[0], marker="x", color="#7a1f1f", lw=0, mew=2.4, ms=10, label=f"most likely ({pk_lat:.0f}°N {pk_lon:.0f}°E)"),
]
axB.legend(handles=legend, loc="lower left", fontsize=8.5, framealpha=0.93)
figB.savefig(HERE / "comet_overlap_detailed.png", dpi=160, bbox_inches="tight")

print("wrote comet_overlap_simple.png + comet_overlap_detailed.png")
print(f"overlap bbox: lon {b[0]:.1f}-{b[1]:.1f}E, lat {b[2]:.1f}-{b[3]:.1f}N")
print(f"most likely: {pk_lat:.1f}N {pk_lon:.1f}E")
