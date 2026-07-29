"""Beautiful sharable flight-path image for stratolink-3.

Real GFS-derived wind streamlines at 300 hPa (~9 km, matching our flight
altitude) overlaid with the actual GPS-fix balloon path. Earth.nullschool /
windy.com aesthetic: thermal palette over wind speed, light coastlines, clean.
"""
from __future__ import annotations

import os, sys, math
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.interpolate import griddata

import cartopy.crs as ccrs
import cartopy.feature as cfeature

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
OUT_PNG = Path(__file__).parent / "flight_path_jet.png"

# Map extent — CONUS + Pacific + Mexico bits, matching jet-stream-overflight aesthetic
LON_MIN, LON_MAX = -135.0, -65.0
LAT_MIN, LAT_MAX =  22.0,  52.0

# Wind grid resolution
GRID_STEP = 2.5  # degrees — coarse enough to fetch fast and stay under rate limits
PRESSURE_LEVEL = "300hPa"   # closest to balloon float altitude

# Wind sampling hour — pick a representative time mid-flight at peak altitude
SAMPLE_TIME_UTC = "2026-05-19T15:00"  # ~mid-jet-stream-transit day

CACHE_DIR = Path.home() / ".cache" / "stratolink"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
WIND_CACHE = CACHE_DIR / f"wind_{PRESSURE_LEVEL}_{SAMPLE_TIME_UTC.replace(':','-')}_{GRID_STEP}deg.npz"


def fetch_track() -> pd.DataFrame:
    """Pull the balloon's fresh-GPS-fix track."""
    r = requests.get(
        f"{SBURL}/rest/v1/telemetry",
        params={
            "device_id": "eq.stratolink-3",
            "select": "time,lat,lon,altitude_m",
            "order": "time.asc",
            "limit": "5000",
        },
        headers={"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    df = df[df["lat"].notna() & df["lon"].notna() & (df["altitude_m"] > 1000)]
    # Drop stale-GPS rows (identical to prior fresh fix)
    df = df.reset_index(drop=True)
    keep = []
    last = None
    for _, row in df.iterrows():
        cur = (round(row["lat"], 6), round(row["lon"], 6), int(row["altitude_m"]))
        if last is None or cur != last:
            keep.append(True)
            last = cur
        else:
            keep.append(False)
    df = df[keep].reset_index(drop=True)
    return df


def fetch_wind_grid() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Fetch a wind speed/direction grid from Open-Meteo archive at 300 hPa."""
    lats = np.arange(LAT_MIN, LAT_MAX + GRID_STEP, GRID_STEP)
    lons = np.arange(LON_MIN, LON_MAX + GRID_STEP, GRID_STEP)
    LON, LAT = np.meshgrid(lons, lats)
    flat_lats = LAT.flatten()
    flat_lons = LON.flatten()

    if WIND_CACHE.exists():
        print(f"  loading cached wind grid: {WIND_CACHE}")
        d = np.load(WIND_CACHE)
        return d["lons"], d["lats"], d["U"], d["V"], d["S"]

    # Open-Meteo accepts comma-separated coordinate arrays
    # Chunk to ~80 points per request to be safe and slow to respect rate limit
    print(f"  fetching wind at {len(flat_lats)} grid points ({GRID_STEP}° spacing)")
    target_date = SAMPLE_TIME_UTC[:10]
    speeds = np.full(len(flat_lats), np.nan)
    dirs = np.full(len(flat_lats), np.nan)
    CHUNK = 80
    import time
    for start in range(0, len(flat_lats), CHUNK):
        end = min(start + CHUNK, len(flat_lats))
        chunk_lats = flat_lats[start:end]
        chunk_lons = flat_lons[start:end]
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": ",".join(f"{x:.3f}" for x in chunk_lats),
            "longitude": ",".join(f"{x:.3f}" for x in chunk_lons),
            "hourly": f"wind_speed_{PRESSURE_LEVEL},wind_direction_{PRESSURE_LEVEL}",
            "wind_speed_unit": "ms",
            "timezone": "UTC",
            "past_days": 10,
            "forecast_days": 1,
        }
        for attempt in range(5):
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 429:
                wait = 12 + attempt * 8
                print(f"    rate-limited, sleeping {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError("Persistent 429 from Open-Meteo")
        data = r.json()
        if isinstance(data, dict):
            data = [data]
        for k, item in enumerate(data):
            hourly = item.get("hourly", {})
            times = hourly.get("time", [])
            try:
                idx = times.index(SAMPLE_TIME_UTC)
            except ValueError:
                continue
            sp = hourly.get(f"wind_speed_{PRESSURE_LEVEL}", [])
            di = hourly.get(f"wind_direction_{PRESSURE_LEVEL}", [])
            if idx < len(sp): speeds[start + k] = sp[idx] if sp[idx] is not None else np.nan
            if idx < len(di): dirs[start + k] = di[idx] if di[idx] is not None else np.nan
        print(f"    chunk {start}-{end}: ok ({end}/{len(flat_lats)})")
        time.sleep(1.5)  # be polite

    # Convert direction (degrees FROM, meteorological) to U, V vector components
    # U is east (positive), V is north (positive)
    # Wind direction = where wind comes FROM, so wind vector points 180° from that
    dirs_rad = np.radians(dirs)
    U_flat = -speeds * np.sin(dirs_rad)   # east-component of wind vector
    V_flat = -speeds * np.cos(dirs_rad)   # north-component of wind vector

    U = U_flat.reshape(LAT.shape)
    V = V_flat.reshape(LAT.shape)
    S = speeds.reshape(LAT.shape)
    np.savez(WIND_CACHE, lons=lons, lats=lats, U=U, V=V, S=S)
    print(f"  cached to {WIND_CACHE}")
    return lons, lats, U, V, S


def plot(track, lons, lats, U, V, S):
    fig = plt.figure(figsize=(18, 11), facecolor="#0a0a14")
    proj = ccrs.AlbersEqualArea(central_longitude=-100, standard_parallels=(29.5, 45.5))
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())
    ax.set_facecolor("#0a0a14")

    # Earth.nullschool-style wind palette
    # 0   m/s  → dark navy
    # 5   m/s  → deep blue
    # 10  m/s  → cyan-blue
    # 20  m/s  → green
    # 30  m/s  → yellow
    # 40  m/s  → orange
    # 50  m/s  → red
    # 60+ m/s → magenta / purple
    wind_colors = [
        (0.04, 0.08, 0.18),   # near-black navy
        (0.07, 0.18, 0.40),   # deep blue
        (0.08, 0.40, 0.55),   # blue-cyan
        (0.18, 0.65, 0.50),   # cyan-green
        (0.42, 0.82, 0.38),   # green
        (0.86, 0.88, 0.20),   # yellow
        (0.98, 0.60, 0.10),   # orange
        (0.95, 0.25, 0.18),   # red
        (0.85, 0.20, 0.55),   # magenta
        (0.75, 0.40, 0.85),   # purple
    ]
    wind_cmap = mcolors.LinearSegmentedColormap.from_list("wind_nullschool", wind_colors, N=512)

    # Background: filled wind-speed mesh
    LON_grid, LAT_grid = np.meshgrid(lons, lats)
    valid = np.isfinite(S)
    S_filled = np.where(valid, S, 0)
    pcm = ax.pcolormesh(
        LON_grid, LAT_grid, S_filled,
        cmap=wind_cmap,
        vmin=0, vmax=60,
        shading="gouraud",
        transform=ccrs.PlateCarree(),
        zorder=1,
        alpha=0.65,
    )

    # Streamlines on top — thin, faint, lots of them for that "moving air" feel
    # Need to interpolate to a finer regular grid for streamplot
    lon_fine = np.linspace(LON_MIN, LON_MAX, 200)
    lat_fine = np.linspace(LAT_MIN, LAT_MAX, 100)
    LON_fine, LAT_fine = np.meshgrid(lon_fine, lat_fine)
    pts = np.column_stack([LON_grid[valid], LAT_grid[valid]])
    U_fine = griddata(pts, U[valid], (LON_fine, LAT_fine), method="cubic")
    V_fine = griddata(pts, V[valid], (LON_fine, LAT_fine), method="cubic")
    S_fine = np.sqrt(U_fine**2 + V_fine**2)

    ax.streamplot(
        LON_fine, LAT_fine, U_fine, V_fine,
        density=4.5,
        linewidth=0.42,
        color=(1, 1, 1, 0.55),
        arrowsize=0,
        transform=ccrs.PlateCarree(),
        zorder=2,
    )

    # Coastlines and borders — bumped up so they read cleanly through the wind
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"),
                   linewidth=0.85, edgecolor=(0.92, 0.94, 0.99, 0.85), zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"),
                   linewidth=0.65, edgecolor=(0.88, 0.91, 0.97, 0.75), zorder=3)
    ax.add_feature(cfeature.STATES.with_scale("50m"),
                   linewidth=0.45, edgecolor=(0.82, 0.86, 0.93, 0.55), zorder=3)
    ax.add_feature(cfeature.LAKES.with_scale("50m"),
                   facecolor=(0.04, 0.06, 0.10, 0.55),
                   edgecolor=(0.65, 0.70, 0.80, 0.55), linewidth=0.4, zorder=3)

    # Flight path — warm bright color for contrast
    if len(track) > 1:
        ax.plot(
            track["lon"].values, track["lat"].values,
            color=(1.00, 0.95, 0.85, 0.95),
            linewidth=2.6,
            solid_capstyle="round",
            solid_joinstyle="round",
            transform=ccrs.PlateCarree(),
            zorder=10,
        )
        # Subtle darker outline for separation against bright wind cells
        ax.plot(
            track["lon"].values, track["lat"].values,
            color=(0.10, 0.10, 0.18, 0.95),
            linewidth=4.2,
            solid_capstyle="round",
            solid_joinstyle="round",
            transform=ccrs.PlateCarree(),
            zorder=9,
        )

        # Start and end markers
        ax.scatter(track["lon"].iloc[0], track["lat"].iloc[0],
                   s=160, c="#4ee0a8", marker="o",
                   edgecolors="white", linewidths=1.8,
                   transform=ccrs.PlateCarree(), zorder=11)
        ax.scatter(track["lon"].iloc[-1], track["lat"].iloc[-1],
                   s=200, c="#ff5a78", marker="o",
                   edgecolors="white", linewidths=1.8,
                   transform=ccrs.PlateCarree(), zorder=11)

    # Colorbar for wind speed
    cbar = fig.colorbar(pcm, ax=ax, orientation="horizontal",
                        pad=0.04, shrink=0.35, aspect=30)
    cbar.set_label("wind speed at 300 hPa (≈ 9 km altitude)  •  m/s",
                   color="#e6e6f0", fontsize=10)
    cbar.ax.xaxis.set_tick_params(color="#a8a8b8", labelcolor="#cccce0", labelsize=9)
    cbar.outline.set_edgecolor("#444450")

    # Title
    fig.text(0.5, 0.93,
             "Stratolink-3 — Flight Path through the Jet Stream",
             color="#f0f0fa", fontsize=22, fontweight="light",
             ha="center", va="center",
             family="sans-serif")
    fig.text(0.5, 0.895,
             f"Launched 2026-05-17 from Dolores Park, SF.   "
             f"Wind background: GFS reanalysis at 300 hPa, "
             f"{SAMPLE_TIME_UTC.replace('T', ' ')} UTC",
             color="#b0b0c0", fontsize=10,
             ha="center", va="center")

    # Minimal corner attribution
    ax.text(0.99, 0.012,
            "data: open-meteo (GFS) + stratolink.org",
            transform=ax.transAxes, color="#888898", fontsize=8,
            va="bottom", ha="right")

    plt.savefig(OUT_PNG, dpi=240, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"  wrote {OUT_PNG}")


def main():
    if not SBKEY: sys.exit("Set SBKEY env")
    print("[1/3] Fetching balloon track...")
    track = fetch_track()
    print(f"  {len(track)} fresh GPS fixes")
    print(f"  lon {track['lon'].min():.2f} → {track['lon'].max():.2f}, "
          f"lat {track['lat'].min():.2f} → {track['lat'].max():.2f}")

    print("[2/3] Fetching wind grid...")
    lons, lats, U, V, S = fetch_wind_grid()
    print(f"  wind grid: {S.shape}, speed range {np.nanmin(S):.1f}-{np.nanmax(S):.1f} m/s")

    print("[3/3] Rendering...")
    plot(track, lons, lats, U, V, S)


if __name__ == "__main__":
    main()
