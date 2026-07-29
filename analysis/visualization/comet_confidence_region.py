#!/usr/bin/env python3
"""Fused 50% / 90% location region for board #3 at the 2026-06-24 02:18:34 UTC join.

The receiving gateway is Packet-Broker anonymized (loc=None, no named gateways), so we
cannot draw a real SF7 circle around a known site. Instead we fuse the constraints we
DO have into a posterior over (lat, lon):

  1. SUN floor (hard): solar-powered, so it must be sunlit at 10 km at 02:18 -> east of
     the altitude dawn line (sun elev > -3.2 deg). P=0 west of it.

  2. WARM-UP (cold-start): flight data says it needs time after its 10 km sunrise before
     it can transmit (100 min Arizona, 170 min Spain -- both UPPER bounds, they follow
     long out-of-coverage gaps). Modeled tau ~ N(85,50) min; chance of transmitting at a
     point = P(tau <= daylight-so-far). Rises east -> sets the WEST edge.

  3. GATEWAY-NETWORK COVERAGE (east edge): the receiver is on a private EU LoRaWAN
     network; gateways sit at customer sites, densest across Europe and thinning toward
     the east. Coverage reach = easternmost plausible gateways (~30E) DILATED by the SF7
     pickup range (~340 km at 10 km float, link budget) -> effective edge ~35E. THIS is
     the SF7 accounting, and it caps the east.

  4. LATITUDE: jet-stream / flight band ~N(42N, 7deg).

Posterior = sun x P_warmup(daylight) x P_coverage(lon) x P_lat(lat). The 50%/90%
highest-density regions are model-based credible regions, not a hard fix -- a second
named-gateway ping collapses them to a near-fix.

Run: analysis/.venv/bin/python analysis/visualization/comet_confidence_region.py
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
DIP = 3.2
TAU_MU, TAU_SIG = 85.0, 50.0      # cold-start (min): measured 100/170 are upper bounds
GATEWAY_EAST = 30.0               # easternmost plausible gateways (EU/W-CIS industrial belt)
SF7_KM = 340.0                    # SF7 pickup range at ~10 km float (link budget)
SF7_DEG = SF7_KM / (111.0*math.cos(math.radians(48)))   # ~4.6 deg lon -> coverage dilation
COV_EDGE = GATEWAY_EAST + SF7_DEG # effective coverage east edge ~34.6E
COV_SOFT = 6.0
LAT_MU, LAT_SIG = 42.0, 7.0       # jet/flight latitude band
TEAL = "#3f8aa3"
EXTENT = [-8, 74, 29, 63]

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    decl = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam)))
    gmst = (280.46061837 + 360.98564736629*n) % 360
    return decl, ((ra - gmst + 180) % 360) - 180

decl, sublon = subsolar(PING)
lon = np.linspace(EXTENT[0], EXTENT[1], 760); lat = np.linspace(EXTENT[2], EXTENT[3], 460)
LON, LAT = np.meshgrid(lon, lat)

Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) \
         / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
Hsr = -np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))
daylight = (Hc - Hsr) / 15.0 * 60.0

erf = np.vectorize(math.erf)
P_warm = np.where(daylight > 0, 0.5*(1 + erf((daylight - TAU_MU)/(TAU_SIG*math.sqrt(2)))), 0.0)
P_cov_lon = 1.0 / (1.0 + np.exp((LON - COV_EDGE)/COV_SOFT))               # SF7-buffered east edge
P_lat = np.exp(-0.5*((LAT - LAT_MU)/LAT_SIG)**2)
post = P_warm * P_cov_lon * P_lat
post /= post.sum()

# coverage region to DRAW (network reach): SF7-buffered east edge x broad Europe latitudes
cov_lat = 1.0/(1.0+np.exp((LAT-59)/4.0)) * 1.0/(1.0+np.exp((36-LAT)/4.0))
coverage = P_cov_lon * cov_lat

flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]
def bbox(m): return LON[m].min(), LON[m].max(), LAT[m].min(), LAT[m].max()
b50, b90 = bbox(post >= t50), bbox(post >= t90)

fig = plt.figure(figsize=(15, 8.2)); ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent(EXTENT, crs=ccrs.PlateCarree()); pc = ccrs.PlateCarree()
ax.add_feature(cfeature.OCEAN, facecolor="#eef3f8", zorder=0)
ax.add_feature(cfeature.LAND, facecolor="#f7f5f1", zorder=0)
ax.add_feature(cfeature.BORDERS, edgecolor="#b9c2cf", linewidth=0.6, zorder=4)
ax.add_feature(cfeature.COASTLINE, edgecolor="#9aa6b4", linewidth=0.6, zorder=4)
gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#d8dee6", alpha=0.7); gl.top_labels = gl.right_labels = False

# gateway-network coverage (the region we could have been heard from), SF7-buffered
ax.contourf(LON, LAT, coverage, levels=[0.25, 1.01], colors=[TEAL], alpha=0.13, transform=pc, zorder=1)
ax.contour(LON, LAT, coverage, levels=[0.5], colors=[TEAL], linewidths=1.0, alpha=0.8, transform=pc, zorder=4)
# sun hard floor
ax.contour(LON, LAT, daylight, levels=[0], colors=["#33414f"], linewidths=1.4, linestyles="--", transform=pc, zorder=5)
# fused 50 / 90 region
ax.contourf(LON, LAT, post, levels=[t90, t50], colors=[WARM], alpha=0.24, transform=pc, zorder=2)
ax.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[WARM], alpha=0.52, transform=pc, zorder=2)
ax.contour(LON, LAT, post, levels=[t90], colors=["#b07a1e"], linewidths=1.0, linestyles="--", transform=pc, zorder=5)
ax.contour(LON, LAT, post, levels=[t50], colors=["#b07a1e"], linewidths=1.3, transform=pc, zorder=5)
ax.plot(pk_lon, pk_lat, marker="x", ms=12, mew=2.6, color="#7a1f1f", transform=pc, zorder=6)

ax.set_title("Stratolink-3: fused 50% / 90% location region · 2026-06-24 02:18 UTC join\n"
             "sun + cold-start (west) × gateway-network coverage incl. SF7 reach (east) × jet-stream latitude",
             fontsize=12.5)
legend = [
    Patch(facecolor=WARM, alpha=0.52, label="50% region"),
    Patch(facecolor=WARM, alpha=0.24, label="90% region"),
    Patch(facecolor=TEAL, alpha=0.16, label="gateway-network coverage (SF7-buffered)"),
    Line2D([0],[0], color="#33414f", lw=1.4, ls="--", label="sunlit limit at 02:18 (hard west edge)"),
    Line2D([0],[0], marker="x", color="#7a1f1f", lw=0, mew=2.4, ms=11, label=f"most likely ({pk_lat:.0f}°N {pk_lon:.0f}°E)"),
]
ax.legend(handles=legend, loc="lower left", fontsize=9, framealpha=0.93)

out = HERE / "comet_confidence_region.png"
fig.savefig(out, dpi=160, bbox_inches="tight")
print(f"wrote {out}")
print(f"most likely: {pk_lat:.1f}N {pk_lon:.1f}E")
print(f"50% region: lon {b50[0]:.1f}-{b50[1]:.1f}E, lat {b50[2]:.1f}-{b50[3]:.1f}N")
print(f"90% region: lon {b90[0]:.1f}-{b90[1]:.1f}E, lat {b90[2]:.1f}-{b90[3]:.1f}N")
print(f"SF7 buffer = {SF7_DEG:.1f} deg lon; coverage east edge = {COV_EDGE:.1f}E")
