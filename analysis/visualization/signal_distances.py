"""Balloon locations colored by farthest signal travel distance and best SNR.

Mirror of the published WSPR-grid-square plot, adapted for our LoRaWAN
telemetry instead of WSPR contacts.

For every Stratolink-3 transmission, the Supabase `telemetry.gateways`
JSONB column carries the list of TTN gateways that heard the uplink,
along with each gateway's `(lat, lon, snr, rssi)`. We compute:

  • max_dist_km - the great-circle distance from the balloon to the
    farthest gateway that heard the packet. This is the "signal travel"
    figure on the left panel.
  • max_snr_db - the highest SNR reported by any gateway on the packet.
    Right panel.

The reference plot uses South Polar Stereographic because the WSPR
flights circle Antarctica. Stratolink-3 is N. hemisphere mid-latitudes
(30–50°N) so we mirror the projection to North Polar Stereographic.

Reference physical limits (LoRa at 10 km altitude):
  • Line-of-sight horizon, 10 km balloon → 30 m gateway:
      sqrt(2·R·10) + sqrt(2·R·0.03) ≈ 377 km
  • Refraction (4/3 k-factor) bumps this to ~430 km, which matches the
    farthest contact we observed (433 km from Monterey Bay to LB).
"""
from __future__ import annotations

import os, sys, math, json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

import cartopy.crs as ccrs
import cartopy.feature as cfeature

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
OUT_PNG = Path(__file__).parent / "signal_distances.png"


def fetch_telemetry_with_gateways() -> pd.DataFrame:
    r = requests.get(
        f"{SBURL}/rest/v1/telemetry",
        params={
            "device_id": "in.(stratolink-3,stratolink-3-eu)",
            "select": "time,device_id,lat,lon,altitude_m,snr,rssi,gateways",
            "order": "time.asc",
            "limit": "5000",
        },
        headers={"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    # Keep only fixes with sane lat/lon/altitude
    df = df[df["lat"].notna() & df["lon"].notna()
            & (df["altitude_m"] > 1000)
            & (df["lat"].abs() <= 90) & (df["lon"].abs() <= 180)]
    return df.reset_index(drop=True)


def _hav_km(la1, lo1, la2, lo2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((la2-la1)*p)/2
         + math.cos(la1*p)*math.cos(la2*p)*(1-math.cos((lo2-lo1)*p))/2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def per_fix_max_distance_and_snr(df: pd.DataFrame):
    """For each row, return (lat, lon, max_dist_km, max_snr_db). Skips rows
    whose gateways list is empty or has no positioned gateway."""
    fixes = []
    for _, row in df.iterrows():
        gws = row.get("gateways") or []
        if not gws:
            continue
        max_d = None
        max_snr = None
        for g in gws:
            snr = g.get("snr")
            if snr is not None and (max_snr is None or snr > max_snr):
                max_snr = float(snr)
            if g.get("lat") is None or g.get("lon") is None:
                continue
            d = _hav_km(row["lat"], row["lon"], g["lat"], g["lon"])
            if max_d is None or d > max_d:
                max_d = d
        if max_d is None and max_snr is None:
            continue
        fixes.append({
            "time": row["time"],
            "lat": row["lat"],
            "lon": row["lon"],
            "altitude_m": row["altitude_m"],
            "max_dist_km": max_d if max_d is not None else float("nan"),
            "max_snr_db": max_snr if max_snr is not None else float("nan"),
        })
    return pd.DataFrame(fixes)


def plot(fixes: pd.DataFrame):
    fig = plt.figure(figsize=(20, 10.5), facecolor="white")
    proj = ccrs.NorthPolarStereo(central_longitude=-60)

    def _setup_polar(ax):
        # Tight polar cap centered on the actual flight (N. Atlantic). The
        # whole flight sits between 25°N and 60°N; using a full
        # 20°N–90° extent leaves the flight as a tiny arc at the rim.
        ax.set_extent([-140, 15, 25, 70], crs=ccrs.PlateCarree())
        ax.set_facecolor("black")
        ax.add_feature(cfeature.OCEAN.with_scale("50m"),
                       facecolor="black", edgecolor="none")
        ax.add_feature(cfeature.LAND.with_scale("50m"),
                       facecolor=(0.32, 0.32, 0.32), edgecolor="none")
        ax.add_feature(cfeature.COASTLINE.with_scale("50m"),
                       linewidth=0.4, edgecolor=(0.10, 0.10, 0.10))
        gl = ax.gridlines(draw_labels=False, linewidth=0.5,
                          color=(1, 1, 1, 0.30), linestyle="-")
        gl.xlocator = plt.matplotlib.ticker.FixedLocator(np.arange(-180, 181, 20))
        gl.ylocator = plt.matplotlib.ticker.FixedLocator(np.arange(20, 91, 10))

    # ---- Left: signal travel distance -----------------------------------
    ax1 = fig.add_subplot(1, 2, 1, projection=proj)
    _setup_polar(ax1)
    # Diverging palette with white near the LOS-horizon distance.
    # Our LoRa-at-10km range is bounded by ~430 km line of sight; use
    # 0..500 km, white at 250 km (matches the reference where white sits
    # mid-range between pole-to-equator and zero).
    dist_norm = mcolors.TwoSlopeNorm(vmin=0, vcenter=250, vmax=500)
    sc1 = ax1.scatter(
        fixes["lon"].values, fixes["lat"].values,
        c=fixes["max_dist_km"].values, cmap="seismic", norm=dist_norm,
        s=85, edgecolors=(0.10, 0.10, 0.10, 0.45), linewidths=0.4,
        transform=ccrs.PlateCarree(), zorder=10,
    )
    ax1.set_title("Balloon locations and signal travel distance",
                   fontsize=14, pad=12, color="black")
    cbar1 = plt.colorbar(sc1, ax=ax1, orientation="vertical",
                          fraction=0.03, pad=0.04)
    cbar1.set_label("Distance (km)", fontsize=11)
    cbar1.ax.tick_params(labelsize=9)

    # ---- Right: signal SNR ------------------------------------------------
    ax2 = fig.add_subplot(1, 2, 2, projection=proj)
    _setup_polar(ax2)
    # SNR colormap matching the reference: blue (weak) → red (strong)
    snr_min, snr_max = -30, 10
    sc2 = ax2.scatter(
        fixes["lon"].values, fixes["lat"].values,
        c=fixes["max_snr_db"].values, cmap="jet",
        vmin=snr_min, vmax=snr_max,
        s=85, edgecolors=(0.10, 0.10, 0.10, 0.45), linewidths=0.4,
        transform=ccrs.PlateCarree(), zorder=10,
    )
    ax2.set_title("Balloon locations and signal SNR",
                   fontsize=14, pad=12, color="black")
    cbar2 = plt.colorbar(sc2, ax=ax2, orientation="vertical",
                          fraction=0.03, pad=0.04)
    cbar2.set_label("SNR", fontsize=11)
    cbar2.ax.tick_params(labelsize=9)

    fig.suptitle("", fontsize=1)  # spacer; titles are on each panel
    plt.subplots_adjust(left=0.02, right=0.96, top=0.94, bottom=0.04,
                         wspace=0.10)
    plt.savefig(OUT_PNG, dpi=240, bbox_inches="tight", pad_inches=0.15,
                facecolor=fig.get_facecolor())
    print(f"  wrote {OUT_PNG}")


def main():
    if not SBKEY: sys.exit("Set SBKEY env")
    print("[1/3] Fetching telemetry with gateway reception data...")
    df = fetch_telemetry_with_gateways()
    print(f"  {len(df)} valid fixes with sane lat/lon/altitude")

    print("[2/3] Computing per-fix max distance and SNR...")
    fixes = per_fix_max_distance_and_snr(df)
    print(f"  {len(fixes)} fixes have gateway reception data")
    if len(fixes):
        print(f"  max signal distance: {fixes['max_dist_km'].max():.1f} km "
              f"(median {fixes['max_dist_km'].median():.1f})")
        print(f"  max SNR observed:    {fixes['max_snr_db'].max():.1f} dB "
              f"(median {fixes['max_snr_db'].median():.1f})")

    print("[3/3] Rendering side-by-side polar plot...")
    plot(fixes)


if __name__ == "__main__":
    main()
