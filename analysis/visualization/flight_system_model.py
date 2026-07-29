#!/usr/bin/env python3
"""Historical Flight-3 silence reconstruction using the earlier coarse geofence.

This file and its `flight_geofence_map.png` output describe the policy that was
under investigation after Flight-3. They are not current StratoLink-2 launch
evidence: the flight candidate now has additional fail-silent country/plan
carve-outs. Use `current_geofence_replay.py` and
`stratolink2_current_geofence_replay.png` for the current compiled policy.

Three real findings drive this:
  1. FIRMWARE GEOFENCE (region_manager.cpp): the LoRaWAN region is picked from GPS
     longitude — US915 in the Americas, EU868 from -30 to +60E (Europe/Africa/Mideast/
     W-Russia), AS923 in Asia, SILENT over China/poles.  REGION defaults US915 at boot
     and is switched from `last_gps_fix` — which is exactly what the stale-GPS-cache bug
     FREEZES.  A frozen fix => a frozen region => transmitting on the wrong band for where
     it actually is => no gateway hears it.
  2. GATEWAY DESERT (Caleb's 14,232 ttnmapper gateways, origin/main): density collapses
     east of ~+25E — W/C Europe has thousands, +30E has 18, +40E has 8.  Over dense Europe
     a 10 km balloon is heard by 13-33 gateways at once (flight data); a SINGLE-gateway
     ping is only possible out in the eastern desert.
  3. THE JOIN: 2026-06-24 02:18 UTC, EU868, ONE anonymized COMET gateway, SNR at the SF7
     cliff (max range), sunlit.

Together: the balloon is in the EU868 band, in the eastern gateway desert (~30-45E),
heard once at max range by a lone COMET customer gateway.  Silence elsewhere = oceans
(no gateways) + wrong-band over the Americas/Asia (frozen region) + the desert itself.

Outputs: flight_geofence_map.png (world: regions + gateways + flight),
         flight_hearability.png (gateway density vs longitude — the cliff).
Run: analysis/.venv/bin/python analysis/visualization/flight_system_model.py
"""
from __future__ import annotations
from pathlib import Path
import csv, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Patch
import cartopy.crs as ccrs
import cartopy.feature as cfeature

HERE = Path(__file__).resolve().parent
SCRATCH = Path("/private/tmp/claude-501/-Users-twarn-Repositories-Stratolink/1a6e7dc1-9e1f-40f4-9725-077569985574/scratchpad")
RED, YEL, BLU, GRN, PUR, GREY, INK = "#d11d1d", "#f4b400", "#1f6fb2", "#2e8b57", "#7b5ea7", "#9aa6b4", "#2b3440"

# --- region_manager.cpp ported exactly ---
def region(lat, lon):
    if lat > 70 or lat < -70: return "SILENT"
    if lon < -170: return "AS923"
    if lon < -30:  return "US915" if lat > 12 else "AU915"
    if lon < 60:   return "EU868"
    if 22 <= lat <= 50 and 73 <= lon <= 123: return "SILENT"
    if lat < 10 and lon >= 110: return "AU915"
    return "AS923"
RCOL = {"US915": BLU, "EU868": GRN, "AS923": YEL, "AU915": PUR, "SILENT": GREY}
RIDX = {k: i for i, k in enumerate(RCOL)}

gx = np.linspace(-180, 180, 720); gy = np.linspace(-80, 80, 320)
LON, LAT = np.meshgrid(gx, gy)
RG = np.vectorize(lambda la, lo: RIDX[region(la, lo)])(LAT, LON)
from matplotlib.colors import ListedColormap
cmap = ListedColormap([RCOL[k] for k in RCOL])

# gateways
gws = []
with open(SCRATCH / "gw.csv") as f:
    for r in csv.DictReader(f): gws.append((float(r["lat"]), float(r["lon"])))
gla = np.array([g[0] for g in gws]); glo = np.array([g[1] for g in gws])

def halo(t, w=2.6): t.set_path_effects([pe.withStroke(linewidth=w, foreground="white")]); return t

# ============ FIG 1: world geofence + gateways + flight ============
fig = plt.figure(figsize=(16, 8.6)); ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_global()
ax.imshow(RG, origin="lower", extent=[-180, 180, -80, 80], transform=ccrs.PlateCarree(),
          cmap=cmap, alpha=0.30, zorder=0, interpolation="nearest")
ax.add_feature(cfeature.COASTLINE, edgecolor="#8893a2", linewidth=0.5, zorder=2)
ax.add_feature(cfeature.BORDERS, edgecolor="#c2cad4", linewidth=0.3, zorder=2)
ax.scatter(glo, gla, s=1.6, color=INK, alpha=0.5, transform=ccrs.PlateCarree(), zorder=3, label="TTN community gateways (14,232)")
gl = ax.gridlines(draw_labels=True, linewidth=0.25, color="#dde3ea", alpha=0.7)
gl.top_labels = gl.right_labels = False
# EU868 band edges
for x in (-30, 60):
    ax.plot([x, x], [-80, 80], color=GRN, lw=1.4, ls="--", alpha=0.8, transform=ccrs.PlateCarree(), zorder=4)
ax.plot([25, 25], [30, 62], color=RED, lw=1.6, ls=":", transform=ccrs.PlateCarree(), zorder=4)
# flight context
def star(lon, lat, c, txt, dy=-7):
    ax.plot(lon, lat, marker="*", ms=17, color=c, mec="white", mew=1.0, transform=ccrs.PlateCarree(), zorder=6)
    halo(ax.text(lon, lat+dy, txt, fontsize=8.5, color=c, fontweight="bold", ha="center", va="top", transform=ccrs.PlateCarree(), zorder=6))
star(-120.5, 34.5, BLU, "LAUNCH (Calif.)\nUS915 · heard", dy=-6)
star(-4.5, 36.9, GRN, "last fix (Spain)\nEU868 · heard by ~15 gw", dy=8.5)
star(37, 48, RED, "2026-06-24 join\nEU868 · 1 COMET gw\n(eastern desert)", dy=-6)
halo(ax.text(15, 64, "EU868 band  (−30°E → +60°E): the only band the frozen balloon can be heard on", fontsize=8.5, color=GRN, fontweight="bold", ha="center", transform=ccrs.PlateCarree(), zorder=6))
halo(ax.text(45, 24, "gateway desert\n(east of ~+25°E)", fontsize=8, color=RED, fontweight="bold", ha="center", transform=ccrs.PlateCarree(), zorder=6))
ax.set_title("Stratolink-3 — the geofence + coverage system: where the balloon CAN be heard\n"
             "firmware picks band from GPS longitude; a frozen GPS freezes the band; only EU868∩gateways is audible",
             fontsize=12.5, fontweight="bold", color=INK, pad=10)
handles = [Patch(facecolor=RCOL[k], alpha=0.45, label=f"{k} region") for k in RCOL]
handles += [plt.Line2D([0],[0], marker="o", color="w", markerfacecolor=INK, ms=5, label="community gateways (14,232)")]
ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.92, ncol=2)
fig.savefig(HERE / "flight_geofence_map.png", dpi=160, bbox_inches="tight")
print("wrote flight_geofence_map.png")

# ============ FIG 2: gateway density vs longitude (the cliff) ============
fig2, ax2 = plt.subplots(figsize=(14, 6))
bins = np.arange(-180, 181, 10)
band = (gla >= 30) & (gla <= 60)
cnt, _ = np.histogram(glo[band], bins=bins)
centers = bins[:-1] + 5
cols = [RCOL[region(45, c)] for c in centers]
ax2.bar(centers, cnt, width=9, color=cols, alpha=0.85, edgecolor="white", linewidth=0.4)
ax2.axvspan(-30, 60, color=GRN, alpha=0.08, zorder=0)
ax2.axvline(25, color=RED, ls=":", lw=1.8);
halo(ax2.text(27, ax2.get_ylim()[1]*0.8, "gateway cliff ~+25°E\n→ east = desert", fontsize=9, color=RED, fontweight="bold"))
for lon, lab, c in [(-120, "launch\n(US915)", BLU), (-4, "Spain\n(EU868)", GRN), (37, "06-24 join\n(1 gw!)", RED)]:
    ax2.annotate(lab, xy=(lon, 5), xytext=(lon, ax2.get_ylim()[1]*0.55), fontsize=8, color=c, fontweight="bold",
                 ha="center", arrowprops=dict(arrowstyle="->", color=c, lw=1.3))
ax2.set_xlim(-180, 180); ax2.set_xlabel("longitude (°E)", fontsize=10); ax2.set_ylabel("TTN community gateways  (30–60°N band, per 10°)", fontsize=10)
ax2.set_title("Why so few pings: a 10 km balloon is heard by 13–33 gateways over dense Europe,\n"
              "but the single-gateway 06-24 ping can only happen in the eastern gateway desert (~30–45°E)",
              fontsize=12, fontweight="bold", color=INK)
ax2.set_xticks(range(-180, 181, 30)); ax2.grid(axis="y", alpha=0.25)
fig2.savefig(HERE / "flight_hearability.png", dpi=160, bbox_inches="tight")
print("wrote flight_hearability.png")
print("gateways 0-10E:", int(cnt[(centers>0)&(centers<10)].sum()), " | 30-50E:", int(cnt[(centers>=30)&(centers<50)].sum()))
