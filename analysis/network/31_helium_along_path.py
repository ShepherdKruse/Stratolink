#!/usr/bin/env python3
"""Helium coverage along the RECONSTRUCTED Stratolink-3 path (Shepherd/Caleb's
reconstruction, main branch). Answers: would Helium have heard us where TTN
didn't, and specifically, could it have closed the 8-day Albuquerque->Spain
silence?

Confirmed anchors come from ~/.cache/stratolink/reconstructed_path.npz
(way_lats/way_lons): SF -> coast -> San Diego -> Sonora -> Albuquerque (last
CONUS contact) -> [8-day silence] -> Spain. The long silence is treated as an
under-determined REGION (per the main-branch engine), drawn dashed, not as a
confirmed route.

Run:
  analysis/.venv/bin/python analysis/network/31_helium_along_path.py
"""
from __future__ import annotations
import os
import pathlib
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ANT = HERE.parent / "antenna"
sys.path.insert(0, str(ANT))
from _common import haversine_km  # noqa: E402
import _style as S  # noqa: E402

DATA = HERE / "data"; FIGS = HERE / "figs"
S.use_light()

REACH = 300.0  # km; ~ our real fresh-fix reach, well inside the 412 km horizon


def helium_within(h_arr, lat, lon, reach=REACH):
    dlat = reach / 111.0 + 0.2
    dlon = dlat / max(0.2, np.cos(np.radians(lat)))
    m = ((h_arr[:, 0] > lat - dlat) & (h_arr[:, 0] < lat + dlat)
         & (h_arr[:, 1] > lon - dlon) & (h_arr[:, 1] < lon + dlon))
    return sum(1 for la, lo in h_arr[m]
               if haversine_km(lat, lon, la, lo) <= reach)


def main():
    h = pd.read_csv(os.path.expanduser("~/.cache/stratolink/helium_hotspots_iot.csv"))
    harr = h[["lat", "lon"]].to_numpy()
    npz = np.load(os.path.expanduser("~/.cache/stratolink/reconstructed_path.npz"))
    wlat, wlon = npz["way_lats"], npz["way_lons"]
    ttn = pd.read_csv(DATA / "gateway_census_located.csv")
    ttn = ttn[ttn["final_lat"].notna()]

    # confirmed anchors = up to Albuquerque (last CONUS), then Spain cluster.
    # index 29 ~ Albuquerque (34.78,-106.13); 30+ = Spain. The 29->30 jump = gap.
    GAP_FROM = int(np.argmin([abs(la - 34.78) + abs(lo + 106.13)
                              for la, lo in zip(wlat, wlon)]))
    print(f"gap starts after anchor {GAP_FROM} = ({wlat[GAP_FROM]:.2f},{wlon[GAP_FROM]:.2f}) "
          f"[Albuquerque, last CONUS contact]")

    # Helium within reach at each CONFIRMED land anchor (SF..Albuquerque)
    print(f"\n==== Helium hotspots within {REACH:.0f} km of each confirmed LAND anchor ====")
    labels = {0: "SF launch", 23: "Monterey (freeze)", 24: "San Diego",
              28: "Sonora MX", 29: "Albuquerque (LAST CONTACT)"}
    land_reach = []
    for i in range(GAP_FROM + 1):
        n = helium_within(harr, wlat[i], wlon[i])
        land_reach.append(n)
        if i in labels:
            print(f"  anchor {i:2d} {labels[i]:28s} ({wlat[i]:6.2f},{wlon[i]:8.2f}): "
                  f"{n:6d} Helium hotspots in reach")
    print(f"  --> confirmed US/MX land legs: Helium-in-reach median "
          f"{int(np.median(land_reach))}, min {min(land_reach)}, max {max(land_reach)}")

    # Spain anchors
    print("\n==== Helium within reach at Spain anchors ====")
    for i in range(GAP_FROM + 1, len(wlat)):
        n = helium_within(harr, wlat[i], wlon[i])
        print(f"  anchor {i:2d} ({wlat[i]:6.2f},{wlon[i]:8.2f}): {n:5d} Helium in reach")

    # The gap as a great-circle sample (Albuquerque->Spain): Helium along it.
    a_lat, a_lon = wlat[GAP_FROM], wlon[GAP_FROM]
    b_lat, b_lon = wlat[GAP_FROM + 1], wlon[GAP_FROM + 1]
    print(f"\n==== Helium along the great-circle of the 8-day gap "
          f"(Albuquerque->first Spain fix, {haversine_km(a_lat,a_lon,b_lat,b_lon):.0f} km) ====")
    print("  (NB: true route is an under-determined REGION; this GC is illustrative)")
    fr = np.linspace(0, 1, 12)
    for f in fr:
        la = a_lat + (b_lat - a_lat) * f
        lo = a_lon + (b_lon - a_lon) * f
        n = helium_within(harr, la, lo)
        tag = "OCEAN" if -60 < lo < -12 else ("land" )
        print(f"    {f*100:3.0f}% ({la:5.1f},{lo:7.1f}) {tag:5s}: {n:5d} Helium in reach")

    # ---- figure: Helium density + confirmed path (solid) + gap (dashed) ----
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except Exception as e:
        print("cartopy unavailable:", e); return
    fig = plt.figure(figsize=(13, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([-125, 5, 28, 50], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="#eef1f4")
    ax.add_feature(cfeature.OCEAN, facecolor="#dce6ee")
    ax.add_feature(cfeature.COASTLINE, lw=0.5, edgecolor=S.TEXT_DIM)
    ax.add_feature(cfeature.BORDERS, lw=0.3, edgecolor=S.DIM)
    lon_bins = np.arange(-125, 5.25, 0.25); lat_bins = np.arange(28, 50.25, 0.25)
    Hh, xe, ye = np.histogram2d(h["lon"], h["lat"], bins=[lon_bins, lat_bins])
    pm = ax.pcolormesh(xe, ye, Hh.T, norm=LogNorm(vmin=1, vmax=max(10, Hh.max())),
                       cmap="magma_r", alpha=0.85, transform=ccrs.PlateCarree(),
                       shading="auto", zorder=2)
    cb = fig.colorbar(pm, ax=ax, shrink=0.6, pad=0.01)
    cb.set_label("Helium registered hotspots / 0.25° cell (log)")
    # confirmed land path solid
    ax.plot(wlon[:GAP_FROM + 1], wlat[:GAP_FROM + 1], "-", color=S.L_ACCENT, lw=2.0,
            zorder=6, transform=ccrs.Geodetic(), label="confirmed track (GPS/baro)")
    # Spain confirmed
    ax.plot(wlon[GAP_FROM + 1:], wlat[GAP_FROM + 1:], "-", color=S.L_ACCENT, lw=2.0,
            zorder=6, transform=ccrs.Geodetic())
    # gap dashed (under-determined region)
    ax.plot([wlon[GAP_FROM], wlon[GAP_FROM + 1]], [wlat[GAP_FROM], wlat[GAP_FROM + 1]],
            "--", color=S.RED, lw=1.6, zorder=5, transform=ccrs.Geodetic(),
            label="~8-day silence (under-determined)")
    for i, lbl in labels.items():
        ax.plot(wlon[i], wlat[i], "o", color=S.L_ACCENT, ms=5, zorder=7,
                transform=ccrs.PlateCarree())
    ax.annotate("Albuquerque\nLAST CONTACT", (wlon[29], wlat[29]), xytext=(-99, 39),
                fontsize=8.5, color=S.RED, ha="center",
                bbox=dict(boxstyle="round", fc="white", ec=S.RED, alpha=0.9),
                transform=ccrs.PlateCarree(), zorder=8)
    ax.text(-45, 41, "8-day silence is mostly OCEAN -\nno gateways, either network",
            fontsize=9.5, color=S.TEXT_DIM, ha="center", style="italic",
            transform=ccrs.PlateCarree())
    ax.legend(loc="lower left", fontsize=8.5)
    ax.set_title("Helium hotspot density vs Stratolink-3's reconstructed path, "
                 "Helium blankets the US land legs, but the silence was the Atlantic",
                 fontsize=11.5, pad=10)
    S.footer(fig, "31_helium_along_path.py · Helium Entity API (registered) · "
             "path: reconstructed_path.npz (Shepherd/Caleb)", light=True)
    fig.tight_layout()
    fig.savefig(FIGS / "N6_helium_along_path.png", dpi=140); plt.close(fig)
    print("\nwrote N6_helium_along_path.png")


if __name__ == "__main__":
    main()
