#!/usr/bin/env python3
"""Pull live Helium IoT hotspot locations and ask: would Helium have heard us
where TTN didn't? Compares Helium hotspot GEOGRAPHY against the TTN gateways
that actually heard Stratolink-3.

Data source (verified live, free, no auth, 2026-06-01):
  GET https://entities.nft.helium.io/v2/hotspots?subnetwork=iot
  -> {cursor, items:[{lat, long, is_active}]}, 10k/page, H3-res8 (~0.7 km) coords.

CAVEATS (important, do not overstate):
  * `is_active` is `false` for EVERY row in this bulk endpoint (0/30k sampled) -
    it is NOT maintained here, so these are REGISTERED (ever-minted) hotspots,
    an UPPER BOUND on live coverage. Per Messari/ByteTree 2025, ~236k of ~385k+
    are actually active, US-heavy; a large fraction of registered hotspots are
    dead post-2022-boom. Treat counts as "registered", geography as the signal.
  * The pull is capped (MAX_PAGES) and may not enumerate the full global set;
    absolute in-window counts are then a LOWER bound. Geography is representative.
So: REGISTERED count = upper bound per hotspot-liveness, lower bound per
enumeration. The robust conclusion is WHERE they are, not HOW MANY.

Run:
  analysis/.venv/bin/python analysis/network/30_helium_coverage.py
"""
from __future__ import annotations
import json
import os
import pathlib
import sys
import time
import urllib.request

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

DATA = HERE / "data"
FIGS = HERE / "figs"; FIGS.mkdir(exist_ok=True)
CACHE = pathlib.Path(os.path.expanduser("~/.cache/stratolink/helium_hotspots_iot.csv"))
API = "https://entities.nft.helium.io/v2/hotspots?subnetwork=iot"
S.use_light()

LAT_MIN, LAT_MAX = 24.0, 52.0
LON_MIN, LON_MAX = -126.0, 6.0
MAX_PAGES = 80


def fetch_hotspots() -> pd.DataFrame:
    if CACHE.exists():
        df = pd.read_csv(CACHE)
        print(f"loaded cached Helium hotspots: {len(df)} in-window rows from {CACHE}")
        return df
    rows, cursor, pages, total = [], None, 0, 0
    while pages < MAX_PAGES:
        url = API + (f"&cursor={cursor}" if cursor else "")
        req = urllib.request.Request(url, headers={"User-Agent": "stratolink-research/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        items = d.get("items", [])
        total += len(items)
        for it in items:
            la, lo = it.get("lat"), it.get("long")
            if la is None or lo is None:
                continue
            if LAT_MIN <= la <= LAT_MAX and LON_MIN <= lo <= LON_MAX:
                rows.append((la, lo))
        pages += 1
        cursor = d.get("cursor")
        print(f"  page {pages}: total {total}, kept-in-window {len(rows)}", flush=True)
        if not cursor or not items:
            break
        time.sleep(0.15)
    capped = pages >= MAX_PAGES and bool(cursor)
    df = pd.DataFrame(rows, columns=["lat", "lon"])
    df.attrs["capped"] = capped
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE, index=False)
    print(f"fetched {total} global; kept {len(df)} in-window"
          + (" (CAPPED, lower bound)" if capped else "") + f"; wrote {CACHE}")
    return df


BOXES = {
    "California launch corridor (32-39N,-123..-117)": (32, 39, -123, -117),
    "CONUS overall (25-50N,-125..-66)":               (25, 50, -125, -66),
    "Atlantic (25-50N,-60..-12)":                     (25, 50, -60, -12),
    "Iberia overall (36-43N,-9..1)":                  (36, 43, -9, 1),
    "Extremadura EU leg (38-41N,-7..-4.5)":           (38, 41, -7, -4.5),
}


def fig_map(hr, ttn, track):
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except Exception as e:
        print("cartopy unavailable, skipping map:", e); return
    fig = plt.figure(figsize=(13, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([-125, 5, 28, 48], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="#eef1f4")
    ax.add_feature(cfeature.OCEAN, facecolor="#dce6ee")
    ax.add_feature(cfeature.COASTLINE, lw=0.5, edgecolor=S.TEXT_DIM)
    ax.add_feature(cfeature.BORDERS, lw=0.3, edgecolor=S.DIM)
    # Helium registered-hotspot density (2D histogram, log color)
    lon_bins = np.arange(-125, 5.25, 0.25)
    lat_bins = np.arange(28, 48.25, 0.25)
    Hh, xe, ye = np.histogram2d(hr["lon"], hr["lat"], bins=[lon_bins, lat_bins])
    pm = ax.pcolormesh(xe, ye, Hh.T, norm=LogNorm(vmin=1, vmax=max(10, Hh.max())),
                       cmap="magma_r", alpha=0.85, transform=ccrs.PlateCarree(),
                       shading="auto", zorder=2)
    cb = fig.colorbar(pm, ax=ax, shrink=0.6, pad=0.01)
    cb.set_label("Helium registered hotspots per 0.25° cell (log)")
    # TTN gateways that heard us
    ax.scatter(ttn["final_lon"], ttn["final_lat"], s=24, facecolor="none",
               edgecolor=S.L_ACCENT, linewidth=1.1, zorder=5,
               transform=ccrs.PlateCarree(), label="TTN gw that heard us (75)")
    # balloon track (broken across gaps)
    t = track.sort_values("time")
    gap = t["time"].diff().dt.total_seconds().fillna(0) > 6 * 3600
    for _, g in t.groupby(gap.cumsum()):
        ax.plot(g["balloon_lon"], g["balloon_lat"], "-", color=S.RED, lw=1.2,
                alpha=0.9, zorder=6, transform=ccrs.Geodetic())
    ax.scatter([], [], color=S.RED, label="balloon fresh-fix track")
    ax.legend(loc="lower left", fontsize=8.5)
    ax.set_title("Helium registered hotspots vs the 75 TTN gateways that heard us "
                 "(Helium: dense US land, ~0 ocean)", fontsize=11.5, pad=10)
    ax.text(-30, 44.5, "Atlantic: no hotspots, either network",
            fontsize=9.5, color=S.TEXT_DIM, ha="center", style="italic",
            transform=ccrs.PlateCarree())
    S.footer(fig, "30_helium_coverage.py · Helium Entity API (REGISTERED, incl. inactive; "
             "partial enumeration) · TTN: gateways that decoded our uplinks", light=True)
    fig.tight_layout()
    fig.savefig(FIGS / "N5_helium_vs_ttn.png", dpi=140); plt.close(fig)
    print("wrote N5_helium_vs_ttn.png")


def main() -> int:
    h = fetch_hotspots()
    print(f"\nin-window REGISTERED Helium hotspots: {len(h)} "
          f"(is_active unusable in bulk API, these include inactive)")

    print("\n==== REGISTERED Helium hotspots by flight sub-region (upper bound on live) ====")
    for name, (a, b, c, d) in BOXES.items():
        n = int(((h.lat >= a) & (h.lat <= b) & (h.lon >= c) & (h.lon <= d)).sum())
        print(f"  {name}: {n}")

    ttn = pd.read_csv(DATA / "gateway_census_located.csv")
    ttn = ttn[ttn["final_lat"].notna()]
    print("\n==== TTN gateways that HEARD US (geolocated) by sub-region ====")
    for name, (a, b, c, d) in BOXES.items():
        n = int(((ttn.final_lat >= a) & (ttn.final_lat <= b)
                 & (ttn.final_lon >= c) & (ttn.final_lon <= d)).sum())
        print(f"  {name}: {n}")

    # per-fresh-fix: registered Helium within reach + nearest distance
    rec = pd.read_csv(DATA / "receptions.csv", parse_dates=["time"])
    fresh = (rec[rec["fresh"].astype(bool)]
             .dropna(subset=["balloon_lat", "balloon_lon"])
             .drop_duplicates(["balloon_lat", "balloon_lon"]).copy())
    REACH = 300.0
    hl = h[["lat", "lon"]].to_numpy()
    cnt, nearest = [], []
    for _, f in fresh.iterrows():
        dlat, dlon = 3.0, 3.0 / max(0.2, np.cos(np.radians(f.balloon_lat)))
        m = ((hl[:, 0] > f.balloon_lat - dlat) & (hl[:, 0] < f.balloon_lat + dlat)
             & (hl[:, 1] > f.balloon_lon - dlon) & (hl[:, 1] < f.balloon_lon + dlon))
        ds = [haversine_km(f.balloon_lat, f.balloon_lon, la, lo) for la, lo in hl[m]]
        cnt.append(sum(1 for x in ds if x <= REACH))
        nearest.append(min(ds) if ds else np.nan)
    fresh["helium_within_300km"] = cnt
    fresh["nearest_helium_km"] = nearest
    print(f"\n==== Registered Helium within {REACH:.0f} km of each FRESH fix (n={len(fresh)}) ====")
    print(f"  NOTE: fresh fixes cluster at the California launch (32 US / 7 EU), "
          f"NOT representative of the sparse mid-CONUS/ocean/rural legs.")
    print(f"  by region:")
    for reg in ("US", "EU"):
        s = fresh[fresh.region == reg]
        if len(s):
            print(f"    {reg}: n={len(s)}  within300 median={np.nanmedian(s.helium_within_300km):.0f} "
                  f"max={int(np.nanmax(s.helium_within_300km))}  "
                  f"nearest_km median={np.nanmedian(s.nearest_helium_km):.0f}")
    fresh[["time", "balloon_lat", "balloon_lon", "region",
           "helium_within_300km", "nearest_helium_km"]].to_csv(
        DATA / "fresh_helium_reach.csv", index=False)

    track = fresh  # already fresh, deduped
    fig_map(h, ttn, track)
    return 0


if __name__ == "__main__":
    sys.exit(main())
