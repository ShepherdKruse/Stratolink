"""Phase 2 verification: fetch a real recent HRRR cycle and print shape + sample wind.

Run with ``python -m scripts.verify_phase2_hrrr`` from the ``simulation/`` directory.

What this script does, end-to-end, per the spec's Phase 2 gate:
  1. Locate the most recent HRRR cycle whose wrfprs f00 file is in
     ``s3://noaa-hrrr-bdp-pds`` (HEAD-checks the .idx sidecar).
  2. Partial-fetch only the u/v isobaric messages (~10 MB) via HTTP
     byte-range GETs into a local cache.
  3. Open with cfgrib + xarray and print the dataset shape, pressure
     levels, and grid extent.
  4. Sample (u, v) near Denver (39.74 N, -104.99 W) at 500 hPa.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from predictor.weather.hrrr_client import (
    download_uv_pressure_levels,
    latest_for_valid_time,
    open_pressure_levels,
)


def _denver_uv_at_500hpa(ds) -> tuple[float, float, float, float]:
    """Nearest-neighbor (u, v) at Denver, 500 hPa."""
    target_lat = 39.74
    target_lon = -104.99

    # HRRR lat/lon are 2-D on the Lambert grid; canonicalize lon to [-180, 180]
    lat2d = ds["latitude"].values
    lon2d = ds["longitude"].values
    lon2d = np.where(lon2d > 180.0, lon2d - 360.0, lon2d)

    dist2 = (lat2d - target_lat) ** 2 + (lon2d - target_lon) ** 2
    j, i = np.unravel_index(np.argmin(dist2), dist2.shape)

    u500 = float(ds["u"].sel(isobaricInhPa=500).isel(y=j, x=i).values)
    v500 = float(ds["v"].sel(isobaricInhPa=500).isel(y=j, x=i).values)
    return u500, v500, float(lat2d[j, i]), float(lon2d[j, i])


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Target valid time: 12 h ago (well past HRRR's ~1 h upload latency)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    valid_time = now.replace()
    print(f"Looking for HRRR cycle covering valid_time={valid_time.isoformat()} (UTC)")

    try:
        latest = latest_for_valid_time(valid_time, lookback_hours=24)
    except FileNotFoundError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"  → cycle={latest.cycle.cycle_dt.isoformat()}  fxx={latest.fxx}")

    cache_dir = Path("./hrrr_cache")
    grib_path = download_uv_pressure_levels(
        latest.cycle, latest.fxx, cache_dir=cache_dir,
    )
    size_mb = grib_path.stat().st_size / 1e6
    print(f"  → cached at {grib_path}  ({size_mb:.1f} MB)")

    ds = open_pressure_levels(grib_path)
    print()
    print(f"Dataset dims: {dict(ds.sizes)}")
    print(f"Pressure levels (hPa): {ds['isobaricInhPa'].values.tolist()}")
    lat2d = ds["latitude"].values
    lon2d = ds["longitude"].values
    print(
        f"Lat range: [{lat2d.min():.2f}, {lat2d.max():.2f}]  "
        f"Lon range (raw): [{lon2d.min():.2f}, {lon2d.max():.2f}]"
    )
    print(f"u dtype: {ds['u'].dtype}")

    u500, v500, lat_sample, lon_sample = _denver_uv_at_500hpa(ds)
    speed = (u500 ** 2 + v500 ** 2) ** 0.5
    print()
    print(
        f"Denver 500 hPa wind (nearest cell at lat={lat_sample:.3f}, "
        f"lon={lon_sample:.3f}):"
    )
    print(f"  u = {u500:+.2f} m/s   v = {v500:+.2f} m/s   |wind| = {speed:.2f} m/s")

    # Sanity check: 500 hPa CONUS winds in May are typically 5–40 m/s.
    if not (1.0 <= speed <= 80.0):
        print(f"WARN: wind speed {speed:.1f} m/s is outside the typical range.")
        return 2
    print()
    print("Phase 2 verification: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
