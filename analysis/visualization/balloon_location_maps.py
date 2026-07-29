#!/usr/bin/env python3
"""Where was board #3 at the 2026-06-24 02:18:34 UTC join?  Two maps, red/yellow/blue.

We never get a gateway fix (Packet-Broker anonymized: gw=packetbroker, loc=None, no named
gateways), so we fuse three SMOOTH probability fields over (lat, lon) -- no hard thresholds,
so the regions have natural curved edges:

  YELLOW  sun + cold-start : solar-powered, so it must be sunlit at 10 km AND have banked
          enough morning sun to wake.  Flight cold-start is only upper-bounded (100 min
          Arizona / 170 min Spain, both after multi-day coverage gaps; the launch's 190 is
          not a solar wake) -> modeled broad, tau ~ N(85,45) min.  P(awake) = P(tau<=daylight).
          Sets the WEST edge.
  BLUE    gateway coverage : private EU network, gateways densest across Europe, thinning
          east.  Reach = easternmost plausible gateways (~30E) + SF7 pickup range (340 km
          @ 10 km ~ 4.6 deg lon) -> soft edge ~35E.  Sets the EAST edge.
  RED     the fused posterior (yellow x blue x jet-latitude).  Its smooth 50% / 90%
          highest-density regions = the most-probable location.

Run: analysis/.venv/bin/python analysis/visualization/balloon_location_maps.py
"""
from __future__ import annotations
from pathlib import Path
import sys, math, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature

HERE = Path(__file__).resolve().parent

# ---- colours (red / yellow / blue) ----
RED, YEL, BLU = "#d11d1d", "#f4b400", "#1f6fb2"
INK, FAINT = "#2b3440", "#9aa6b4"

# ---- physics constants ----
PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc)
DIP = 3.2                                   # 10 km horizon dip (deg) -> balloon sunrise at elev = -DIP
TAU_MU, TAU_SIG = 85.0, 45.0                # cold-start (min); flight gives upper bounds only -> broad
GATEWAY_EAST, SF7_KM = 30.0, 340.0          # easternmost plausible gateways + SF7 reach
SF7_DEG = SF7_KM / (111.0*math.cos(math.radians(48)))
COV_EDGE, COV_SOFT = GATEWAY_EAST + SF7_DEG, 6.0
LAT_MU, LAT_SIG = 42.0, 7.0                 # jet / flight latitude band

CITIES = [("Kyiv",50.45,30.52),("Moscow",55.75,37.62),("Warsaw",52.23,21.01),
          ("Minsk",53.90,27.57),("Bucharest",44.43,26.10),("Kharkiv",49.99,36.23),
          ("Rostov",47.23,39.70),("Berlin",52.52,13.40)]

def subsolar(when):
    jd = when.timestamp()/86400.0 + 2440587.5; n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003*n) % 360); Ld = (280.460 + 0.9856474*n) % 360
    lam = math.radians((Ld + 1.915*math.sin(g) + 0.020*math.sin(2*g)) % 360); eps = math.radians(23.439 - 3.6e-7*n)
    dec = math.degrees(math.asin(math.sin(eps)*math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps)*math.sin(lam), math.cos(lam)))
    gmst = (280.46061837 + 360.98564736629*n) % 360
    return dec, ((ra - gmst + 180) % 360) - 180

decl, sublon = subsolar(PING)
lon = np.linspace(-14, 82, 720); lat = np.linspace(28, 66, 420)
LON, LAT = np.meshgrid(lon, lat)
Hc = ((LON - sublon + 180) % 360) - 180
cosHsr = (math.sin(math.radians(-DIP)) - np.sin(np.radians(LAT))*math.sin(math.radians(decl))) \
         / (np.cos(np.radians(LAT))*math.cos(math.radians(decl)))
Hsr = -np.degrees(np.arccos(np.clip(cosHsr, -1, 1)))
daylight = (Hc - Hsr) / 15.0 * 60.0                         # minutes of 10 km-sun banked by 02:18
cov_lat = 1.0/(1.0+np.exp((LAT-60)/4.5)) * 1.0/(1.0+np.exp((35-LAT)/4.5))

def verf(x):                                                # vectorised erf (Abramowitz-Stegun 7.1.26)
    s = np.sign(x); ax = np.abs(x); t = 1.0/(1.0 + 0.3275911*ax)
    y = 1.0 - (((((1.061405429*t - 1.453152027)*t) + 1.421413741)*t - 0.284496736)*t + 0.254829592)*t*np.exp(-ax*ax)
    return s*y

# ---- ROBUST posterior: Monte-Carlo marginalise every uncertain prior, AND fold in the
#      near-floor signal (SNR -7.25 dB / ch_rssi -121 dBm at the SF7 cliff): the link was at
#      ~MAX range, so the balloon sat at the coverage FRINGE (peak of cov*(1-cov)), not inside it.
rng = np.random.default_rng(20260624)
NS = 360
post = np.zeros_like(LON)
for _ in range(NS):
    tau_mu = rng.uniform(45, 115); tau_sig = rng.uniform(35, 55)   # cold-start (upper-bounded only)
    g_edge = rng.uniform(26, 34); r_link = rng.uniform(250, 340)   # gateway reach + SF7 max range
    cov_edge = g_edge + r_link/(111.0*math.cos(math.radians(48))); cov_soft = rng.uniform(4, 7)
    lmu = rng.normal(42, 3); lsig = rng.uniform(6, 9)              # jet / flight latitude band
    P_sun = np.where(daylight > 0, 0.5*(1 + verf((daylight-tau_mu)/(tau_sig*math.sqrt(2)))), 0.0)
    cov = 1.0/(1.0 + np.exp((LON-cov_edge)/cov_soft))
    P_fringe = 4.0*cov*(1.0-cov)                                   # marginal link -> at the max-range edge
    P_lat = np.exp(-0.5*((LAT-lmu)/lsig)**2)
    s = P_sun*P_fringe*P_lat; tot = s.sum()
    if tot > 0: post += s/tot
post /= post.sum()
cov_disp = (1.0/(1.0 + np.exp((LON-34.6)/6.0))) * cov_lat          # mean-param coverage, for the blue layer
flat = np.sort(post.ravel())[::-1]; cum = np.cumsum(flat)
t50 = flat[np.searchsorted(cum, 0.50)]; t90 = flat[np.searchsorted(cum, 0.90)]
pk = np.unravel_index(post.argmax(), post.shape); pk_lon, pk_lat = LON[pk], LAT[pk]
def bbox(m): return LON[m].min(), LON[m].max(), LAT[m].min(), LAT[m].max()
b50, b90 = bbox(post >= t50), bbox(post >= t90)

EXT = ccrs.PlateCarree()
def rgba(field, hexcol, amax):
    r, g, bl = (int(hexcol[i:i+2], 16)/255 for i in (1, 3, 5))
    a = np.clip(field, 0, 1) * amax
    return np.dstack([np.full_like(field, r), np.full_like(field, g), np.full_like(field, bl), a])

def basemap(ax, extent, cities=True):
    ax.set_extent(extent, crs=EXT)
    ax.add_feature(cfeature.OCEAN, facecolor="#eaf1f7", zorder=0)
    ax.add_feature(cfeature.LAND, facecolor="#f6f4ef", zorder=0)
    ax.add_feature(cfeature.LAKES, facecolor="#eaf1f7", zorder=0)
    ax.add_feature(cfeature.BORDERS, edgecolor="#c2cad4", linewidth=0.6, zorder=3)
    ax.add_feature(cfeature.COASTLINE, edgecolor="#aab4c0", linewidth=0.6, zorder=3)
    gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#dde3ea", alpha=0.8, zorder=2)
    gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 8, "color": FAINT}
    if cities:
        for nm, la, lo in CITIES:
            if extent[0]+1 < lo < extent[1]-1 and extent[2]+1 < la < extent[3]-1:
                ax.plot(lo, la, "o", ms=2.6, color=INK, alpha=0.55, transform=EXT, zorder=7)
                ax.text(lo+0.5, la+0.25, nm, fontsize=7.5, color=INK, alpha=0.8, transform=EXT, zorder=7)

def halo(t, w=2.5): return t   # text halos removed per preference

def nice_dot(ax, lo, la):
    ax.plot(lo, la, "o", ms=20, color=RED, alpha=0.15, transform=EXT, zorder=7)   # soft glow
    ax.plot(lo, la, "o", ms=10.5, color=RED, mec="white", mew=1.5, transform=EXT, zorder=8)

# ============ MAP A — simple: just the most-probable region ============
figA = plt.figure(figsize=(14, 8.4)); axA = plt.axes(projection=EXT); basemap(axA, [-12, 76, 30, 64])
axA.contourf(LON, LAT, post, levels=[t90, t50], colors=[RED], alpha=0.10, transform=EXT, zorder=4)
axA.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[RED], alpha=0.26, transform=EXT, zorder=4)
axA.contour(LON, LAT, post, levels=[t90], colors=[RED], linewidths=1.2, linestyles="--", transform=EXT, zorder=5)
axA.contour(LON, LAT, post, levels=[t50], colors=[RED], linewidths=2.2, transform=EXT, zorder=5)
nice_dot(axA, pk_lon, pk_lat)
axA.text(pk_lon, pk_lat-2.0, f"most likely  {pk_lat:.0f}°N {pk_lon:.0f}°E", fontsize=9.5, color=RED,
         fontweight="bold", ha="center", va="top", transform=EXT, zorder=8)
axA.text(b50[1]+1.0, b50[3]-1.0, "50% region", fontsize=9.5, color=RED, fontweight="bold", transform=EXT, zorder=8)
axA.text(b90[0]+1.2, b90[2]+1.4, "90% region", fontsize=9, color="#b15a5a", transform=EXT, zorder=8)
axA.set_title("Stratolink-3: most-probable location at the 2026-06-24 02:18 UTC join",
              fontsize=13.5, fontweight="bold", color=INK, pad=10)
axA.legend(handles=[Patch(facecolor=RED, alpha=0.50, label="50% credible region"),
                    Patch(facecolor=RED, alpha=0.20, label="90% credible region"),
                    Line2D([0],[0], marker="o", color="w", markerfacecolor=RED, markeredgecolor="white", mew=1.2, ms=11, label=f"most likely ({pk_lat:.0f}°N {pk_lon:.0f}°E)")],
           loc="lower left", fontsize=9, framealpha=0.95)
figA.savefig(HERE / "balloon_location_simple.png", dpi=170, bbox_inches="tight")

# ============ MAP B — detailed: the three fields and their overlap ============
figB = plt.figure(figsize=(15.5, 8.6)); axB = plt.axes(projection=EXT); basemap(axB, [-12, 76, 30, 64])
# yellow sun gradient (brightens east of the dawn line) + blue coverage gradient (fades east)
axB.imshow(rgba(np.clip(daylight/210.0, 0, 1), YEL, 0.28), extent=[-14,82,28,66], origin="lower", transform=EXT, zorder=1)
axB.imshow(rgba(cov_disp, BLU, 0.26), extent=[-14,82,28,66], origin="lower", transform=EXT, zorder=1)
# boundary lines
axB.contour(LON, LAT, daylight, levels=[0], colors=[INK], linewidths=1.3, linestyles="--", alpha=0.7, transform=EXT, zorder=4)
axB.contour(LON, LAT, cov_disp, levels=[0.5], colors=[BLU], linewidths=1.4, transform=EXT, zorder=4)
# red fused region on top
axB.contourf(LON, LAT, post, levels=[t90, t50], colors=[RED], alpha=0.12, transform=EXT, zorder=5)
axB.contourf(LON, LAT, post, levels=[t50, post.max()], colors=[RED], alpha=0.30, transform=EXT, zorder=5)
axB.contour(LON, LAT, post, levels=[t90], colors=[RED], linewidths=1.1, linestyles="--", transform=EXT, zorder=6)
axB.contour(LON, LAT, post, levels=[t50], colors=[RED], linewidths=2.2, transform=EXT, zorder=6)
nice_dot(axB, pk_lon, pk_lat)
# on-map labels
axB.text(0, 39.5, "BLUE: gateway network\n+ SF7 reach (heard here)", fontsize=8.5, color="#155a91", fontweight="bold", ha="center", transform=EXT, zorder=8)
axB.text(60, 59, "YELLOW: sunlit + warmed up\n(power to transmit)", fontsize=8.5, color="#a87503", fontweight="bold", ha="center", transform=EXT, zorder=8)
axB.text(pk_lon+10, pk_lat-7.5, "RED: most-probable location\n(far/max-range edge of coverage)", fontsize=9, color="#a81616", fontweight="bold", ha="center", transform=EXT, zorder=8)
axB.annotate("", xy=(pk_lon+1.4, pk_lat-1.4), xytext=(pk_lon+8.5, pk_lat-6.2), transform=EXT,
             arrowprops=dict(arrowstyle="-|>", color="#a81616", lw=1.4), zorder=8)
axB.set_title("Stratolink-3: how the location is found (sun × coverage × latitude, 2026-06-24 02:18 UTC join)",
              fontsize=12.5, fontweight="bold", color=INK, pad=10)
axB.legend(handles=[
    Patch(facecolor=RED, alpha=0.52, label=f"most-probable region · 50%  ({b50[0]:.0f}–{b50[1]:.0f}°E, {b50[2]:.0f}–{b50[3]:.0f}°N)"),
    Patch(facecolor=RED, alpha=0.22, label=f"90% region  ({b90[0]:.0f}–{b90[1]:.0f}°E, {b90[2]:.0f}–{b90[3]:.0f}°N)"),
    Patch(facecolor=YEL, alpha=0.5, label="sun banked by 02:18 (cold-start buffer)"),
    Patch(facecolor=BLU, alpha=0.42, label="gateway-network coverage (+ SF7 340 km)"),
    Line2D([0],[0], color=INK, lw=1.3, ls=(0,(5,3)), label="dawn line at 02:18 (hard west limit)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor=RED, markeredgecolor="white", mew=1.2, ms=11, label=f"most likely ({pk_lat:.0f}°N {pk_lon:.0f}°E)"),
], loc="lower left", fontsize=8.5, framealpha=0.95)
figB.savefig(HERE / "balloon_location_detailed.png", dpi=170, bbox_inches="tight")

print("wrote balloon_location_simple.png + balloon_location_detailed.png")
print(f"most likely {pk_lat:.1f}N {pk_lon:.1f}E | 50% {b50} | 90% {b90}")
print(f"SF7 = {SF7_DEG:.1f}deg; coverage edge {COV_EDGE:.1f}E")
