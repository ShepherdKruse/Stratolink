"""Gateway-density heatmap with Stratolink-3 flight track + LoRa horizon overlay.

Pulls:
- Balloon GPS fixes from Supabase
- TTN gateway locations from TTN Mapper public dumps (cached locally on first run)

Produces a thermal-style map of North American LoRa gateway density with the
balloon track overlaid faintly and a dotted reception-horizon circle at every
recorded altitude. Output: gateway_heatmap.png.
"""
from __future__ import annotations

import os
import io
import json
import math
import gzip
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Circle
from scipy.ndimage import gaussian_filter

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ---- config ----

SUPABASE_URL = "https://iazmnyyfsobucndqncgw.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SBKEY")
DEVICE_ID = "stratolink-3"

CACHE_DIR = Path.home() / ".cache" / "stratolink"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Map bounds: CONUS + parts of Canada + Mexico
LON_MIN, LON_MAX = -135.0, -60.0
LAT_MIN, LAT_MAX = 22.0, 58.0

# Grid for density
GRID_CELL_DEG = 0.18            # ~18 km @ mid-lats — small enough to resolve single gateways,
                                # large enough that one cell can hold several visibly
GAUSSIAN_SMOOTH_SIGMA = 0.45    # minor smoothing for visual continuity; single gateways still pop

# LoRa horizon model
EARTH_RADIUS_KM = 6371.0
K_REFRACTION = 4.0 / 3.0        # standard 4/3-Earth model at 900 MHz

OUTPUT_PATH = Path(__file__).parent / "gateway_heatmap.png"


# ---- data fetchers ----

def fetch_balloon_track() -> pd.DataFrame:
    """Pull all GPS-fix telemetry rows for stratolink-3 from Supabase."""
    if not SUPABASE_KEY:
        raise SystemExit("Set SBKEY or SUPABASE_SERVICE_ROLE_KEY env var.")

    url = f"{SUPABASE_URL}/rest/v1/telemetry"
    params = {
        "device_id": f"eq.{DEVICE_ID}",
        "select": "time,lat,lon,altitude_m,pressure,gps_satellites",
        "order": "time.asc",
        "limit": "5000",
    }
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")

    # Filter to GPS-fix rows in plausible flight range
    df = df[df["lat"].notna() & df["lon"].notna()]
    df = df[(df["lat"].between(-90, 90)) & (df["lon"].between(-180, 180))]
    # Drop pre-launch ground-test garbage (altitude < 100 m)
    df = df[df["altitude_m"] > 100]
    return df.reset_index(drop=True)


def fetch_ttn_gateways() -> pd.DataFrame:
    """Pull TTN Mapper public gateway list. Cached on disk after first fetch."""
    cache = CACHE_DIR / "ttn_gateways.csv"
    if cache.exists() and (cache.stat().st_size > 1000):
        print(f"  using cached gateways: {cache}")
        return pd.read_csv(cache)

    print("  fetching gateway list (this can take a moment)...")
    sources = [
        ("https://mapper.packetbroker.net/api/v2/gateways", _parse_pb_mapper),
        ("https://ttnmapper.org/geojson/", _parse_ttnmapper_geojson),
    ]
    last_err = None
    for url, parser in sources:
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": "stratolink-analysis/1.0"})
            r.raise_for_status()
            df = parser(r)
            print(f"  fetched {len(df)} gateways from {url}")
            df.to_csv(cache, index=False)
            return df
        except Exception as e:
            last_err = e
            print(f"  failed {url}: {e}")
    raise SystemExit(f"All gateway sources failed. Last error: {last_err}")


def _parse_pb_mapper(r: requests.Response) -> pd.DataFrame:
    """Parse the Packet Broker Mapper API response."""
    data = r.json()
    # The endpoint returns a top-level list or {"gateways": [...]}; handle both
    if isinstance(data, dict):
        items = data.get("gateways", data.get("data", []))
    else:
        items = data
    rows = []
    for g in items:
        loc = g.get("location", g)
        lat = loc.get("latitude") if isinstance(loc, dict) else g.get("latitude")
        lon = loc.get("longitude") if isinstance(loc, dict) else g.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            lat = float(lat); lon = float(lon)
        except (TypeError, ValueError):
            continue
        rows.append({"lat": lat, "lon": lon, "id": g.get("id", "")})
    return pd.DataFrame(rows)


def _parse_ttnmapper_geojson(r: requests.Response) -> pd.DataFrame:
    """Parse TTN Mapper's geojson dump."""
    data = r.json()
    rows = []
    for feat in data.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates")
        props = feat.get("properties", {})
        if not coords or len(coords) < 2:
            continue
        rows.append({"lon": float(coords[0]), "lat": float(coords[1]),
                     "id": props.get("gateway_id", "")})
    return pd.DataFrame(rows)


# ---- physics ----

def lora_horizon_km(altitude_m: float, k: float = K_REFRACTION) -> float:
    """Radio horizon distance for an altitude h above Earth's surface.
    Uses 4/3-Earth refraction model (standard at 900 MHz)."""
    h_km = altitude_m / 1000.0
    Re = k * EARTH_RADIUS_KM
    return math.sqrt(2.0 * Re * h_km + h_km * h_km)


def km_to_deg_lat(km: float) -> float:
    return km / 111.0


def km_to_deg_lon(km: float, lat_deg: float) -> float:
    return km / (111.0 * max(math.cos(math.radians(lat_deg)), 0.01))


# ---- plotting ----

def make_density_grid(gateways: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """2D histogram of gateways within map bounds, smoothed."""
    in_box = gateways[
        gateways["lat"].between(LAT_MIN, LAT_MAX) &
        gateways["lon"].between(LON_MIN, LON_MAX)
    ]
    print(f"  gateways inside bbox: {len(in_box)} / {len(gateways)}")

    lon_edges = np.arange(LON_MIN, LON_MAX + GRID_CELL_DEG, GRID_CELL_DEG)
    lat_edges = np.arange(LAT_MIN, LAT_MAX + GRID_CELL_DEG, GRID_CELL_DEG)
    counts, _, _ = np.histogram2d(
        in_box["lat"].values, in_box["lon"].values,
        bins=[lat_edges, lon_edges]
    )
    smoothed = gaussian_filter(counts, sigma=GAUSSIAN_SMOOTH_SIGMA)
    # Keep on raw-count scale so the colorbar reads as "gateways per cell."
    # The small sigma just softens the pixel grid without merging neighbors.
    density = smoothed
    return density, lon_edges, lat_edges, counts


def plot(track: pd.DataFrame, gateways: pd.DataFrame, density, lon_edges, lat_edges, raw_counts):
    fig = plt.figure(figsize=(20, 12), facecolor="white")
    proj = ccrs.AlbersEqualArea(central_longitude=-100, standard_parallels=(29.5, 45.5))
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())
    ax.set_facecolor("white")

    # Blue gradient: white (0) → sky blue → cobalt → deep navy (densest)
    # First "lit" color is a saturated sky blue so single gateways are still
    # easily visible against the white background.
    thermal_colors = [
        (1.00, 1.00, 1.00),   # pure white — zero gateways
        (0.62, 0.82, 0.96),   # sky blue — single gateway, still pops on white
        (0.36, 0.66, 0.92),   # bright blue
        (0.16, 0.46, 0.82),   # clear blue
        (0.07, 0.30, 0.68),   # royal blue
        (0.04, 0.18, 0.48),   # deep blue
        (0.02, 0.08, 0.28),   # navy
        (0.00, 0.02, 0.12),   # near-black
    ]
    thermal_cmap = mcolors.LinearSegmentedColormap.from_list("blue_density", thermal_colors)
    # vmin = 0 means zero-count cells get the first color (white) — clean white background
    thermal_cmap.set_under((1, 1, 1, 1))  # below vmin = white

    # Heatmap — clip vmax so single gateways pop with visible orange while
    # dense urban areas saturate to deep red.  Saturate at 6 gateways/cell
    # so the 1-to-6 gradient gets most of the visual range.
    VMAX = 6.0
    VMIN = 0.35  # below this = treat as zero (white)
    lon_centers = 0.5 * (lon_edges[:-1] + lon_edges[1:])
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    LON, LAT = np.meshgrid(lon_centers, lat_centers)
    # Apply gamma to bias more color into the low end (1-2 gateways)
    pcm = ax.pcolormesh(
        LON, LAT, density,
        cmap=thermal_cmap,
        norm=mcolors.PowerNorm(gamma=0.55, vmin=VMIN, vmax=VMAX),
        shading="auto",
        transform=ccrs.PlateCarree(),
        zorder=2,
    )

    # Density-key tick labels: gateways per ~18 km cell
    tick_vals = [VMIN, 1, 2, 3, 4, VMAX]
    tick_labels = ["0", "1", "2", "3", "4", "6+"]

    # Coastlines + borders — darker for visibility on white background
    ax.add_feature(cfeature.OCEAN.with_scale("50m"),
                   facecolor=(0.93, 0.96, 0.99), edgecolor="none", zorder=1)
    ax.add_feature(cfeature.LAND.with_scale("50m"),
                   facecolor="white", edgecolor="none", zorder=0.5)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.7,
                   edgecolor=(0.35, 0.35, 0.40), zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.55,
                   edgecolor=(0.45, 0.45, 0.50), zorder=3)
    ax.add_feature(cfeature.STATES.with_scale("50m"), linewidth=0.3,
                   edgecolor=(0.60, 0.60, 0.65), zorder=3)
    ax.add_feature(cfeature.LAKES.with_scale("50m"),
                   facecolor=(0.93, 0.96, 0.99),
                   edgecolor=(0.55, 0.60, 0.65), linewidth=0.35, zorder=3)

    # Balloon track — warm coral/orange for contrast on white + blue heatmap
    track_color = (0.95, 0.35, 0.15, 0.80)
    if len(track) > 1:
        ax.plot(track["lon"], track["lat"],
                color=track_color,
                linewidth=1.4,
                solid_capstyle="round",
                transform=ccrs.PlateCarree(),
                zorder=5)
        # Start and end markers
        ax.scatter(track["lon"].iloc[0], track["lat"].iloc[0],
                   s=80, c="#1ca36b", marker="^",
                   edgecolors="white", linewidths=1.2,
                   transform=ccrs.PlateCarree(), zorder=7)
        ax.scatter(track["lon"].iloc[-1], track["lat"].iloc[-1],
                   s=110, c="#d62a1a", marker="o",
                   edgecolors="white", linewidths=1.2,
                   transform=ccrs.PlateCarree(), zorder=7)

    # Reception-horizon circles at each fix (dotted, same warm tone)
    n_fixes = len(track)
    stride = max(1, n_fixes // 60)
    for _, r in track.iloc[::stride].iterrows():
        alt = r["altitude_m"]
        if not (alt and alt > 0):
            continue
        radius_km = lora_horizon_km(alt)
        t = np.linspace(0, 2 * np.pi, 73)
        dlat = km_to_deg_lat(radius_km) * np.cos(t)
        dlon = km_to_deg_lon(radius_km, r["lat"]) * np.sin(t)
        ax.plot(r["lon"] + dlon, r["lat"] + dlat,
                color=(0.95, 0.35, 0.15, 0.45),
                linewidth=0.85,
                linestyle=(0, (1.5, 2.2)),
                transform=ccrs.PlateCarree(),
                zorder=6)

    # Density key (the only label on the plot)
    cbar = fig.colorbar(pcm, ax=ax, orientation="vertical",
                        pad=0.02, shrink=0.5, aspect=22, extend="max")
    cbar.set_ticks(tick_vals)
    cbar.set_ticklabels(tick_labels)
    cbar.set_label("gateways per ~18 km cell",
                   color="#333333", fontsize=11)
    cbar.ax.yaxis.set_tick_params(color="#666666", labelcolor="#333333", labelsize=10)
    cbar.outline.set_edgecolor("#999999")

    plt.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"  wrote {OUTPUT_PATH}")


def main():
    print("Stratolink gateway heatmap")
    print("==========================")
    print("[1/3] Fetching balloon track...")
    track = fetch_balloon_track()
    print(f"  {len(track)} GPS-fix rows, lon [{track['lon'].min():.2f}, {track['lon'].max():.2f}], "
          f"lat [{track['lat'].min():.2f}, {track['lat'].max():.2f}], "
          f"alt max {track['altitude_m'].max():.0f}m")

    print("[2/3] Fetching TTN gateway locations...")
    gateways = fetch_ttn_gateways()
    print(f"  total gateways available: {len(gateways)}")

    print("[3/3] Building heatmap...")
    density, lon_edges, lat_edges, raw_counts = make_density_grid(gateways)
    plot(track, gateways, density, lon_edges, lat_edges, raw_counts)


if __name__ == "__main__":
    main()
