#!/usr/bin/env python3
"""Where could board #3 have been to ping a COMET (Czech) gateway on 2026-06-24,
AND have had solar power to do it?

The 2026-06-24T02:18:34Z join reached TTN via Packet Broker from the forwarder
network `cometsystem-cloud` (COMET SYSTEM s.r.o., Czech Republic). The specific
gateway is anonymized and COMET's TTI network isn't public, so we don't have
individual gateway coordinates -- we model COMET coverage as the Czech footprint
dilated by the SF7 pickup range.

Added overlay: the day/night terminator at the ping instant. The balloon runs on
solar + supercap, so it can only transmit on the sunlit side. At ~10 km float it
sees sunrise ~3.2 deg (about 350 km) before the ground does, so we draw both the
ground terminator (sun elev = 0) and the balloon-at-altitude terminator
(sun elev = -3.2). The balloon could only have pinged where the coverage envelope
overlaps the balloon-sunlit side.

SF7/BW125 @ ~10 km: link budget ~340 km, horizon ~412 km, flight-achieved ~252 km.

Run: analysis/.venv/bin/python analysis/visualization/comet_range_map.py
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
    S.use_light()
    RED, WARM, MINT, DIM = S.RED, S.WARM, S.MINT, S.TEXT_DIM
except Exception:
    RED, WARM, MINT, DIM = "#e0594a", "#f4a259", "#2a9d4e", "#7e8aa3"

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io import shapereader
from shapely.ops import transform as shp_transform
from pyproj import Transformer

PING = dt.datetime(2026, 6, 24, 2, 18, 34, tzinfo=dt.timezone.utc)   # the join instant
ALT_DIP_DEG = 3.2          # horizon dip / earlier-sunrise at ~10 km float
EXTENT = [-12, 42, 33, 61]

# --- Czech Republic polygon (COMET's home network footprint) ---
def load_czechia():
    for res in ("50m", "110m"):
        try:
            fn = shapereader.natural_earth(resolution=res, category="cultural", name="admin_0_countries")
            for rec in shapereader.Reader(fn).records():
                a = rec.attributes
                if a.get("ADM0_A3") == "CZE" or (a.get("NAME") or a.get("NAME_LONG") or "") in ("Czechia", "Czech Republic"):
                    return rec.geometry
        except Exception:
            continue
    raise SystemExit("could not load Czechia polygon")

cz = load_czechia()
to_m   = Transformer.from_crs(4326, 3035, always_xy=True).transform
to_deg = Transformer.from_crs(3035, 4326, always_xy=True).transform
cz_m = shp_transform(to_m, cz)
buf250 = shp_transform(to_deg, cz_m.buffer(250_000))
buf340 = shp_transform(to_deg, cz_m.buffer(340_000))

# --- subsolar point + sun-elevation grid for the ping instant ---
def subsolar(when):
    jd = when.timestamp() / 86400.0 + 2440587.5
    n = jd - 2451545.0
    g = np.radians((357.528 + 0.9856003 * n) % 360)
    Ldeg = (280.460 + 0.9856474 * n) % 360
    lam = np.radians((Ldeg + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g)) % 360)
    eps = np.radians(23.439 - 3.6e-7 * n)
    decl = np.degrees(np.arcsin(np.sin(eps) * np.sin(lam)))
    ra = np.degrees(np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam)))
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    sublon = ((ra - gmst + 180) % 360) - 180
    return decl, sublon

decl, sublon = subsolar(PING)
gx = np.linspace(EXTENT[0], EXTENT[1], 480)
gy = np.linspace(EXTENT[2], EXTENT[3], 360)
LON, LAT = np.meshgrid(gx, gy)
H = np.radians(LON - sublon)
elev = np.degrees(np.arcsin(np.sin(np.radians(LAT)) * np.sin(np.radians(decl)) +
                            np.cos(np.radians(LAT)) * np.cos(np.radians(decl)) * np.cos(H)))

# --- map ---
fig = plt.figure(figsize=(13.5, 9.5))
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
pc = ccrs.PlateCarree()
ax.add_feature(cfeature.OCEAN, facecolor="#eef3f8", zorder=0)
ax.add_feature(cfeature.LAND, facecolor="#f7f5f1", zorder=0)
ax.add_feature(cfeature.BORDERS, edgecolor="#b9c2cf", linewidth=0.6, zorder=4)
ax.add_feature(cfeature.COASTLINE, edgecolor="#9aa6b4", linewidth=0.6, zorder=4)
gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#d8dee6", alpha=0.7)
gl.top_labels = gl.right_labels = False

# night shading: ground-dark (elev<0) cool wash; balloon-dark (elev<-DIP) darker
ax.contourf(LON, LAT, elev, levels=[-90, -ALT_DIP_DEG], colors=["#2b3a4a"], alpha=0.22, transform=pc, zorder=1)
ax.contourf(LON, LAT, elev, levels=[-ALT_DIP_DEG, 0], colors=["#2b3a4a"], alpha=0.10, transform=pc, zorder=1)

# coverage envelope (possible area)
ax.add_geometries([buf340], pc, facecolor=WARM, alpha=0.16, edgecolor=WARM, linewidth=1.0, zorder=2)
ax.add_geometries([buf250], pc, facecolor=WARM, alpha=0.26, edgecolor=WARM, linewidth=0.8, zorder=2)
ax.add_geometries([cz], pc, facecolor=RED, alpha=0.55, edgecolor=RED, linewidth=1.2, zorder=3)

# terminators
ax.contour(LON, LAT, elev, levels=[0], colors=["#33414f"], linewidths=1.6, transform=pc, zorder=5)
ax.contour(LON, LAT, elev, levels=[-ALT_DIP_DEG], colors=["#c98a2b"], linewidths=1.4, linestyles="--", transform=pc, zorder=5)

# markers
ax.plot(18.14, 49.46, marker="*", ms=16, color=RED, mec="white", mew=0.8, transform=pc, zorder=6)
ax.text(18.5, 49.46, "COMET System HQ", fontsize=8.5, color=RED, va="center", transform=pc, zorder=6)
for lon, lat, lbl in [(-4.532, 36.889, "last GPS fix\nMálaga, 29 May"),
                      (-5.306, 40.547, "Salamanca\n28 May")]:
    ax.plot(lon, lat, marker="o", ms=7, color=MINT, mec="white", mew=0.8, transform=pc, zorder=6)
    ax.text(lon + 0.5, lat, lbl, fontsize=8, color="#1f6f47", va="center", transform=pc, zorder=6)

# label day / night sides
ax.text(33, 58.5, "DAYLIGHT", fontsize=11, color="#b07a1e", fontweight="bold", alpha=0.7, transform=pc)
ax.text(-9, 41, "NIGHT", fontsize=11, color="#33414f", fontweight="bold", alpha=0.6, transform=pc)

ax.set_title("Stratolink-3: possible-ping area vs. day/night at the join instant\n"
             "2026-06-24 02:18:34 UTC · COMET (Czech) network · SF7 · solar-powered",
             fontsize=12.5)

legend = [
    Patch(facecolor=RED, alpha=0.55, label="COMET home region (Czech Republic)"),
    Patch(facecolor=WARM, alpha=0.26, label="possible area · SF7 ≈250 km (achieved)"),
    Patch(facecolor=WARM, alpha=0.16, label="possible area · SF7 ≈340 km (link budget)"),
    Line2D([0], [0], color="#33414f", lw=1.6, label="terminator at ground (sun elev 0°)"),
    Line2D([0], [0], color="#c98a2b", lw=1.4, ls="--", label="terminator at 10 km balloon (−3.2°)"),
    Line2D([0], [0], marker="*", color="w", markerfacecolor=RED, ms=13, label="COMET HQ (anchor)"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=MINT, ms=8, label="last GPS fixes (flight)"),
]
ax.legend(handles=legend, loc="lower left", fontsize=8, framealpha=0.92)

fig.text(0.5, 0.012,
         "Solar-powered: the balloon can only transmit on the sunlit side. At 02:18 UTC the dawn line cuts through Central "
         "Europe, so the join most plausibly came from the EAST/sunlit edge of the COMET envelope (it catches sunrise ~3° / "
         "~350 km before the ground). Gateway exact locations unknown; coverage modeled as the Czech footprint + SF7 range.",
         ha="center", fontsize=7.5, color=DIM, wrap=True)

out = HERE / "comet_range_map.png"
fig.savefig(out, dpi=160, bbox_inches="tight")
print(f"wrote {out}  | subsolar pt: lat={decl:.1f} lon={sublon:.1f}")
