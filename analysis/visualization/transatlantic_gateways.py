"""Stratolink-3 transatlantic flight + LoRa gateway coverage.

Minimal-chrome variant of `transatlantic_path.py`:
  • NO wind backdrop / streamlines / colorbar - just the map + path + gateways
  • Same cream reconstructed polyline (per-segment wind-advected + ensemble
    mean across the Atlantic + chord for the long EU gap)
  • Teal gateway-coverage layer matching the dashboard's GatewayLayer.tsx

To keep render time reasonable, the script:
  • Caches the unioned gateway buffer at
    `~/.cache/stratolink/gateway_coverage_v2.pkl` after the first build
  • Caches the reconstructed-path coordinates at
    `~/.cache/stratolink/reconstructed_path.npz` after the first ensemble.
    Subsequent renders skip both expensive steps.
"""
from __future__ import annotations

import os, sys, math, time, json, pickle
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

import cartopy.crs as ccrs
import cartopy.feature as cfeature

import pyproj
from shapely.geometry import MultiPoint, Polygon, MultiPolygon
from shapely.ops import transform as shp_transform

# Reuse the constants + helpers from the main transatlantic script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from transatlantic_path import (  # noqa: E402
    fetch_track, fetch_gfs_wind_field, run_ensemble, summarise_ensemble,
    advect_segment_anchored,
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, N_ENSEMBLE,
)

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
OUT_PNG = Path(__file__).parent / "transatlantic_gateways.png"

# ---- Gateway coverage palette (matches `web/components/maps/GatewayLayer.tsx`)
GW_TEAL = (94 / 255, 234 / 255, 212 / 255)
GW_INNER_FILL = (*GW_TEAL, 0.06)
GW_INNER_LINE = (*GW_TEAL, 0.40)
GW_OUTER_LINE = (*GW_TEAL, 0.45)

PATH_LINE = (0.98, 0.94, 0.86, 1.0)   # cream - matches the original render

CACHE_DIR = Path.home() / ".cache" / "stratolink"
GATEWAY_CSV = CACHE_DIR / "ttn_gateways.csv"
COVERAGE_CACHE = CACHE_DIR / "gateway_coverage_v2.pkl"
PATH_CACHE = CACHE_DIR / "reconstructed_path.npz"


# ---- Gateway coverage builder (cached) --------------------------------------

def build_gateway_coverage(force: bool = False):
    if COVERAGE_CACHE.exists() and not force:
        with open(COVERAGE_CACHE, "rb") as fh:
            cached = pickle.load(fh)
        if cached.get("extent") == (LON_MIN, LON_MAX, LAT_MIN, LAT_MAX):
            print(f"  using cached coverage: "
                  f"{len(cached['inner'])} inner + {len(cached['outer'])} outer polygons")
            return cached["inner"], cached["outer"]
        print("  cache extent mismatched - rebuilding")

    print(f"  loading gateway CSV: {GATEWAY_CSV.name}")
    df = pd.read_csv(GATEWAY_CSV)
    print(f"  total gateways: {len(df)}")
    buf_deg = 3.0
    mask = ((df.lat >= LAT_MIN - buf_deg) & (df.lat <= LAT_MAX + buf_deg)
            & (df.lon >= LON_MIN - buf_deg) & (df.lon <= LON_MAX + buf_deg))
    df = df[mask].reset_index(drop=True)
    print(f"  gateways in extent (+ {buf_deg:.0f}° buffer): {len(df)}")
    df["lat_q"] = (df.lat * 100).round().astype(int)
    df["lon_q"] = (df.lon * 100).round().astype(int)
    df = df.drop_duplicates(subset=["lat_q", "lon_q"]).reset_index(drop=True)
    print(f"  after 0.01° dedupe: {len(df)} unique antenna locations")

    laea_proj = "+proj=laea +lat_0=40 +lon_0=-60 +x_0=0 +y_0=0 +ellps=WGS84 +no_defs"
    to_laea = pyproj.Transformer.from_crs("EPSG:4326", laea_proj, always_xy=True).transform
    to_latlon = pyproj.Transformer.from_crs(laea_proj, "EPSG:4326", always_xy=True).transform
    xs_laea, ys_laea = to_laea(df.lon.values, df.lat.values)

    def _batched_buffer(xs, ys, radius_m, quad_segs=2, batch=800):
        from shapely.ops import unary_union
        n = len(xs)
        partials = []
        for i in range(0, n, batch):
            mp = MultiPoint(list(zip(xs[i:i+batch], ys[i:i+batch])))
            t0 = time.monotonic()
            buf = mp.buffer(radius_m, quad_segs=quad_segs)
            print(f"      batch {i//batch + 1}/{(n + batch - 1)//batch}: "
                  f"{min(batch, n - i)} pts → {buf.geom_type} in "
                  f"{time.monotonic()-t0:.1f}s", flush=True)
            partials.append(buf)
        if len(partials) == 1:
            return partials[0]
        return unary_union(partials)

    print(f"  buffering 150 km (batched)...")
    t0 = time.monotonic()
    inner_laea = _batched_buffer(xs_laea, ys_laea, 150_000)
    print(f"    inner total: {time.monotonic()-t0:.1f}s")
    t0 = time.monotonic()
    outer_laea = _batched_buffer(xs_laea, ys_laea, 250_000)
    print(f"    outer total: {time.monotonic()-t0:.1f}s")

    inner_ll = shp_transform(to_latlon, inner_laea)
    outer_ll = shp_transform(to_latlon, outer_laea)

    def _to_poly_lists(geom):
        polys = []
        if geom.is_empty:
            return polys
        if isinstance(geom, Polygon):
            polys.append(list(geom.exterior.coords))
        elif isinstance(geom, MultiPolygon):
            for p in geom.geoms:
                polys.append(list(p.exterior.coords))
        return polys

    inner_polys = _to_poly_lists(inner_ll)
    outer_polys = _to_poly_lists(outer_ll)
    print(f"  inner polygons: {len(inner_polys)}, outer polygons: {len(outer_polys)}")
    with open(COVERAGE_CACHE, "wb") as fh:
        pickle.dump({
            "extent": (LON_MIN, LON_MAX, LAT_MIN, LAT_MAX),
            "inner": inner_polys, "outer": outer_polys,
        }, fh)
    return inner_polys, outer_polys


# ---- Reconstructed-path build (mirrors transatlantic_path.py:plot()) --------

def _hav_km(la1, lo1, la2, lo2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((la2-la1)*p)/2
         + math.cos(la1*p)*math.cos(la2*p)*(1-math.cos((lo2-lo1)*p))/2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def build_full_path(track: pd.DataFrame, wf, ens_summary):
    """Bit-for-bit copy of the path-build logic in transatlantic_path.plot().
    Returns (full_lon, full_lat, way_lons, way_lats)."""
    raw_lats = track["lat"].values
    raw_lons = track["lon"].values
    raw_times = pd.to_datetime(track["time"].values)

    SPEED_CAP_MPS = 80.0
    keep_mask = [True]
    for i in range(1, len(raw_lats)):
        j = i - 1
        while j >= 0 and not keep_mask[j]:
            j -= 1
        if j < 0:
            keep_mask.append(True); continue
        dt_s = (raw_times[i] - raw_times[j]).total_seconds()
        if dt_s <= 0:
            keep_mask.append(False); continue
        dd_m = _hav_km(raw_lats[i], raw_lons[i], raw_lats[j], raw_lons[j]) * 1000.0
        keep_mask.append(dd_m / dt_s <= SPEED_CAP_MPS)
    keep_arr = np.array(keep_mask)
    way_lats = raw_lats[keep_arr]
    way_lons = raw_lons[keep_arr]
    way_times = raw_times[keep_arr]
    print(f"  raw fixes {len(raw_lats)}, dropped {int((~keep_arr).sum())}, "
          f"waypoints {len(way_lats)}")

    gaps_h = np.diff(way_times) / np.timedelta64(1, "h")
    big_idx = int(np.argmax(gaps_h))
    LONG_GAP_HRS = 8.0

    segments_lon, segments_lat = [], []
    n_chord = n_wind = 0
    for i in range(len(way_lats) - 1):
        pa = (float(way_lats[i]),     float(way_lons[i]))
        pb = (float(way_lats[i + 1]), float(way_lons[i + 1]))
        ta = pd.to_datetime(way_times[i]).to_pydatetime()
        tb = pd.to_datetime(way_times[i + 1]).to_pydatetime()
        if ta.tzinfo is None: ta = ta.replace(tzinfo=timezone.utc)
        if tb.tzinfo is None: tb = tb.replace(tzinfo=timezone.utc)
        gap_hr = (tb - ta).total_seconds() / 3600.0
        if i == big_idx and ens_summary is not None:
            rec_lon = np.array(ens_summary["mean_lon"], dtype=float)
            rec_lat = np.array(ens_summary["mean_lat"], dtype=float)
            rec_lon[0]  = pa[1]; rec_lat[0]  = pa[0]
            rec_lon[-1] = pb[1]; rec_lat[-1] = pb[0]
            seg_lo = rec_lon.tolist(); seg_la = rec_lat.tolist()
        elif gap_hr > LONG_GAP_HRS:
            seg_lo = [pa[1], pb[1]]; seg_la = [pa[0], pb[0]]
            n_chord += 1
        else:
            gap_min = gap_hr * 60.0
            dt_min = max(1.0, min(30.0, gap_min / 10.0))
            seg = advect_segment_anchored(wf, pa, ta, pb, tb,
                                            pressure=300.0, dt_minutes=dt_min)
            seg_lo = [s[2] for s in seg]
            seg_la = [s[1] for s in seg]
            n_wind += 1
        segments_lon.append(seg_lo)
        segments_lat.append(seg_la)
    print(f"  segments: ensemble=1 wind-advected={n_wind} chord={n_chord}")

    full_lon = list(segments_lon[0])
    full_lat = list(segments_lat[0])
    for slo, sla in zip(segments_lon[1:], segments_lat[1:]):
        full_lon.extend(slo[1:])
        full_lat.extend(sla[1:])
    return np.array(full_lon), np.array(full_lat), way_lons, way_lats


def get_or_build_path(track):
    """Try the cache first; if missing, run the full pipeline + write cache."""
    if PATH_CACHE.exists():
        d = np.load(PATH_CACHE, allow_pickle=False)
        print(f"  using cached reconstructed path "
              f"({len(d['full_lon'])} pts, {len(d['way_lons'])} waypoints)")
        return d["full_lon"], d["full_lat"], d["way_lons"], d["way_lats"]

    print("  no cached path - running full reconstruction pipeline")
    flight_start = track["time"].iloc[0].to_pydatetime()
    flight_end   = track["time"].iloc[-1].to_pydatetime()
    if flight_start.tzinfo is None: flight_start = flight_start.replace(tzinfo=timezone.utc)
    if flight_end.tzinfo is None:   flight_end   = flight_end.replace(tzinfo=timezone.utc)
    print("  fetching GFS wind covering the whole flight...")
    wf = fetch_gfs_wind_field(
        start_time=flight_start - timedelta(hours=6),
        end_time=flight_end + timedelta(hours=12),
        altitude_m=10000.0,
        lat_min=LAT_MIN, lat_max=LAT_MAX,
        lon_min=LON_MIN, lon_max=LON_MAX,
        cache_dir=Path.home() / ".cache" / "stratolink" / "predictor",
    )

    print(f"  running {N_ENSEMBLE}-member ensemble for the Atlantic crossing...")
    gaps = track["time"].diff().dt.total_seconds() / 3600
    biggest = gaps.idxmax()
    gap_start = track["time"].iloc[biggest - 1].to_pydatetime()
    gap_end   = track["time"].iloc[biggest].to_pydatetime()
    last_us_pos  = (track["lat"].iloc[biggest - 1], track["lon"].iloc[biggest - 1])
    first_eu_pos = (track["lat"].iloc[biggest],     track["lon"].iloc[biggest])
    members = run_ensemble(wf, last_us_pos, gap_start, gap_end, first_eu_pos,
                            n=N_ENSEMBLE)
    summary = summarise_ensemble(members,
                                  target_pos=first_eu_pos,
                                  start_pos_known=last_us_pos)
    if summary:
        print(f"  best endpoint error: {summary['errs'].min():.0f} km")

    full_lon, full_lat, way_lons, way_lats = build_full_path(track, wf, summary)
    np.savez(PATH_CACHE,
              full_lon=full_lon, full_lat=full_lat,
              way_lons=way_lons, way_lats=way_lats)
    print(f"  cached path → {PATH_CACHE.name}")
    return full_lon, full_lat, way_lons, way_lats


# ---- plotting ---------------------------------------------------------------

def plot(full_lon, full_lat, way_lons, way_lats, inner_polys, outer_polys):
    fig = plt.figure(figsize=(22, 7.8), facecolor="#0a0a14")
    proj = ccrs.PlateCarree(central_longitude=-60)
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())
    ax.set_anchor("N")
    ax.set_facecolor("#0a0a14")

    # Map base: coastlines, borders, lakes. No wind, no streamlines.
    ax.add_feature(cfeature.LAND.with_scale("50m"),
                   facecolor=(0.10, 0.12, 0.18, 1.0), edgecolor="none", zorder=1)
    ax.add_feature(cfeature.OCEAN.with_scale("50m"),
                   facecolor=(0.04, 0.07, 0.14, 1.0), edgecolor="none", zorder=1)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"),
                   linewidth=0.75, edgecolor=(0.88, 0.90, 0.96, 0.75), zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"),
                   linewidth=0.45, edgecolor=(0.78, 0.82, 0.90, 0.40), zorder=3)
    ax.add_feature(cfeature.LAKES.with_scale("50m"),
                   facecolor=(0.04, 0.07, 0.14, 0.9),
                   edgecolor=(0.50, 0.55, 0.65, 0.35), linewidth=0.3, zorder=3)

    # ---- Gateway coverage -------------------------------------------------
    # Outer (250 km) dashed first.
    for poly in outer_polys:
        xs = [c[0] for c in poly]
        ys = [c[1] for c in poly]
        ax.plot(xs, ys, color=GW_OUTER_LINE, linewidth=0.9,
                linestyle=(0, (3, 2)),
                transform=ccrs.PlateCarree(), zorder=5)
    # Inner (150 km) filled + solid outline.
    for poly in inner_polys:
        xs = [c[0] for c in poly]
        ys = [c[1] for c in poly]
        ax.fill(xs, ys, color=GW_INNER_FILL, edgecolor="none",
                transform=ccrs.PlateCarree(), zorder=6)
        ax.plot(xs, ys, color=GW_INNER_LINE, linewidth=0.7,
                transform=ccrs.PlateCarree(), zorder=7)

    # ---- Reconstructed cream flight path ----------------------------------
    ax.plot(full_lon, full_lat, color=PATH_LINE,
            linewidth=2.5, solid_capstyle="round", solid_joinstyle="round",
            transform=ccrs.PlateCarree(), zorder=10)

    # Subtle dots at every recorded fix
    ax.scatter(way_lons, way_lats,
               s=9, c=[(1.00, 0.95, 0.78, 0.75)],
               edgecolors=(0.10, 0.10, 0.14, 0.7), linewidths=0.4,
               transform=ccrs.PlateCarree(), zorder=11)

    # Launch + current
    ax.scatter([way_lons[0]], [way_lats[0]],
               s=130, c="white", marker="o",
               edgecolors=(0.10, 0.10, 0.14, 0.9), linewidths=1.2,
               transform=ccrs.PlateCarree(), zorder=13)
    ax.scatter([way_lons[-1]], [way_lats[-1]],
               s=150, c="white", marker="o",
               edgecolors=(0.10, 0.10, 0.14, 0.9), linewidths=1.2,
               transform=ccrs.PlateCarree(), zorder=13)

    plt.subplots_adjust(top=1.0, bottom=0.0, left=0.0, right=1.0)
    plt.savefig(OUT_PNG, dpi=240, bbox_inches="tight", pad_inches=0.04,
                facecolor=fig.get_facecolor())
    print(f"  wrote {OUT_PNG}")


def main():
    if not SBKEY: sys.exit("Set SBKEY env")
    print("[1/3] Fetching track...")
    track = fetch_track()
    print(f"  {len(track)} fresh GPS fixes")

    print("[2/3] Building gateway coverage union (cached after first run)...")
    inner_polys, outer_polys = build_gateway_coverage()

    print("[3/3] Loading reconstructed path (running pipeline if not cached)...")
    full_lon, full_lat, way_lons, way_lats = get_or_build_path(track)

    print("[Render] Drawing map + gateway coverage + cream path...")
    plot(full_lon, full_lat, way_lons, way_lats, inner_polys, outer_polys)


if __name__ == "__main__":
    main()
