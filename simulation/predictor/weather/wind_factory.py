"""
Orchestrator that builds a runtime :class:`WindField` for a given
target time, duration, and flight altitude.

Source selection
----------------
- **HRRR** (``noaa-hrrr-bdp-pds``): preferred when the entire requested
  trajectory window is **CONUS-inside**, **altitude < ~17 km** (the
  HRRR top is 50 hPa ≈ 20.7 km, but we leave a margin to keep the
  vertical interpolant interior), and the trajectory ends inside
  HRRR's 18 h forecast horizon. 3 km Lambert Conformal grid, hourly
  cycles, ~5 MB per fxx after byte-range partial fetch.
- **GFS** (``noaa-gfs-bdp-pds``): fallback for global coverage, high
  altitudes, or long horizons. 0.25° regular lat/lon grid, 4× daily
  cycles (00/06/12/18Z), runs out to 384 h. Each level subset is a
  few MB per fxx via partial fetch.

The factory function :func:`build_wind_field` returns a ready-to-use
:class:`WindField` and a small metadata dict so the API can echo what
was used back to the caller.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol

from predictor.atmosphere import isa
from predictor.weather.hrrr_client import (
    HRRRCycle,
    download_uv_pressure_levels as hrrr_download,
    latest_for_valid_time as hrrr_latest,
)
from predictor.weather.hrrr_wind_field import HRRRWindField
from predictor.weather import gfs_client
from predictor.weather.wind_field import RegularGridWindField, WindField

logger = logging.getLogger(__name__)


# HRRR coverage envelope (CONUS bounding box, conservative)
HRRR_LAT_MIN = 22.0
HRRR_LAT_MAX = 52.0
HRRR_LON_MIN = -132.0
HRRR_LON_MAX = -62.0
# Pressure level limit — HRRR's top is 50 hPa ≈ 20.7 km. We require
# the float pressure to stay strictly inside the loaded level subset
# so vertical interpolation never extrapolates.
HRRR_TOP_HPA = 75.0  # ≈ 17.7 km — leaves headroom above the float
HRRR_MAX_FXX_DEFAULT = 18

# Default in-memory level subset for HRRR (chosen by flight altitude)
HRRR_LEVEL_HALF_WINDOW = 3  # take 3 levels on each side of the target


# GFS standard isobaric levels in the pgrb2.0p25 product. Hardcoded to
# avoid an extra HEAD request just to read level metadata.
GFS_LEVELS_HPA = (
    1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500,
    450, 400, 350, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10, 7, 5, 3, 2, 1,
)


@dataclass(frozen=True)
class WindFieldMetadata:
    """Identifies which NWP source backed a constructed wind field."""

    source: str                # 'hrrr', 'gfs', or 'constant'
    cycle: Optional[datetime]  # UTC cycle init time
    fxx_start: Optional[int]
    fxx_end: Optional[int]
    levels_hpa: tuple[float, ...]
    region: str                # 'conus' or 'global'
    grid_extent: Optional[dict]


@dataclass(frozen=True)
class _BuildResult:
    wind_field: WindField
    metadata: WindFieldMetadata


def default_cache_dir() -> Path:
    """Default on-disk cache for partial-fetched GRIB files."""
    return Path.home() / ".cache" / "stratolink" / "predictor"


def _inside_conus(lat: float, lon: float) -> bool:
    return (
        HRRR_LAT_MIN <= lat <= HRRR_LAT_MAX
        and HRRR_LON_MIN <= lon <= HRRR_LON_MAX
    )


def _hrrr_levels_for_altitude(altitude_m: float) -> tuple[int, ...]:
    """Pick a small set of HRRR isobaric levels straddling the flight altitude.

    Returns levels in **integer hPa** since HRRR's level selector
    expects integers in millibars. Capped by ``HRRR_TOP_HPA``.
    """
    target_hpa = isa.pressure(altitude_m) / 100.0
    all_levels = [
        1013, 1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 725,
        700, 675, 650, 625, 600, 575, 550, 525, 500, 475, 450, 425, 400,
        375, 350, 325, 300, 275, 250, 225, 200, 175, 150, 125, 100, 75, 50,
    ]
    # Keep only levels with pressure >= HRRR_TOP_HPA (i.e. below the model top)
    candidates = [lv for lv in all_levels if lv >= HRRR_TOP_HPA]
    # Find the 2*HALF_WINDOW + 1 closest
    candidates.sort(key=lambda lv: abs(lv - target_hpa))
    chosen = sorted(candidates[: 2 * HRRR_LEVEL_HALF_WINDOW + 1])
    return tuple(chosen)


def _gfs_levels_for_altitude(altitude_m: float) -> tuple[int, ...]:
    """Pick GFS levels straddling the flight altitude."""
    target_hpa = isa.pressure(altitude_m) / 100.0
    candidates = list(GFS_LEVELS_HPA)
    candidates.sort(key=lambda lv: abs(lv - target_hpa))
    chosen = sorted(candidates[: 2 * HRRR_LEVEL_HALF_WINDOW + 1])
    return tuple(chosen)


def _build_hrrr(
    target_time: datetime,
    duration_hours: float,
    altitude_m: float,
    cache_dir: Path,
) -> _BuildResult:
    """Fetch HRRR cycle + fxx range covering the trajectory window."""
    latest = hrrr_latest(target_time, lookback_hours=24)
    cycle = latest.cycle
    fxx_start = latest.fxx
    fxx_end = min(fxx_start + int(math.ceil(duration_hours)), cycle.max_fxx())
    if fxx_end < fxx_start:
        raise FileNotFoundError(
            f"HRRR cycle {cycle.cycle_dt.isoformat()} can't cover requested window."
        )

    levels = _hrrr_levels_for_altitude(altitude_m)
    paths = []
    for fxx in range(fxx_start, fxx_end + 1):
        p = hrrr_download(cycle, fxx, cache_dir=cache_dir, levels_mb=list(levels))
        paths.append(p)

    wf = HRRRWindField.from_files(
        grib_paths=paths,
        cycle_dt=cycle.cycle_dt,
        fxx_values=list(range(fxx_start, fxx_end + 1)),
        levels_hpa=list(levels),
    )
    meta = WindFieldMetadata(
        source="hrrr",
        cycle=cycle.cycle_dt,
        fxx_start=fxx_start,
        fxx_end=fxx_end,
        levels_hpa=tuple(float(lv) for lv in levels),
        region="conus",
        grid_extent=wf.grid_extent,
    )
    return _BuildResult(wind_field=wf, metadata=meta)


def _build_gfs(
    target_time: datetime,
    duration_hours: float,
    altitude_m: float,
    cache_dir: Path,
) -> _BuildResult:
    """Fetch GFS cycle + fxx range covering the trajectory window.

    GFS forecast hours are integers 0..384 with hourly resolution out
    to 120 h, then 3-hourly. We use only hourly fxx (≤120 h) which
    covers all Stratolink scenarios.
    """
    import xarray as xr

    # Find the most-recent GFS cycle that should be fully uploaded
    cycle = gfs_client.latest_cycle_before(target_time, latency_padding_h=4.0)
    if cycle.cycle_dt > target_time:
        cycle = gfs_client.latest_cycle_before(target_time - timedelta(hours=6))

    elapsed_h = (target_time - cycle.cycle_dt).total_seconds() / 3600.0
    fxx_start = max(0, int(math.floor(elapsed_h)))
    fxx_end = min(fxx_start + int(math.ceil(duration_hours)) + 1, 120)

    levels = _gfs_levels_for_altitude(altitude_m)
    snapshots = []
    fxx_values: list[int] = []
    for fxx in range(fxx_start, fxx_end + 1):
        try:
            p = gfs_client.download_uv_pressure_levels(
                cycle, fxx, cache_dir=cache_dir, levels_mb=list(levels)
            )
        except FileNotFoundError:
            # Some fxx may not yet be uploaded; skip and stop here
            if not snapshots:
                raise
            break
        ds = gfs_client.open_pressure_levels(p)
        ds = ds.sel(isobaricInhPa=list(levels))
        # Drop the per-file scalar coords cfgrib attaches (`time`, `step`,
        # `valid_time`) — their values vary by fxx and break xr.concat.
        # We re-stamp our own time dim below.
        conflicting = [c for c in ("time", "step", "valid_time") if c in ds.coords]
        if conflicting:
            ds = ds.drop_vars(conflicting)
        vt = (cycle.cycle_dt + timedelta(hours=int(fxx))).replace(tzinfo=None)
        import numpy as np
        ds = ds.expand_dims(time=[np.datetime64(vt, "ns")])
        snapshots.append(ds)
        fxx_values.append(fxx)

    if not snapshots:
        raise FileNotFoundError(
            f"No GFS fxx files available for cycle {cycle.cycle_dt.isoformat()}."
        )

    combined = xr.concat(snapshots, dim="time", coords="minimal")
    # Attach valid_time as a non-dim coord for introspection. The
    # sampler targets the dim itself ("time").
    combined = combined.assign_coords(valid_time=("time", combined["time"].values))
    # Use the fast numpy-backed sampler — XarrayWindField's per-call
    # xarray.interp is ~500× slower at the call counts the ensemble drives.
    wf = RegularGridWindField(combined, time_dim="time")

    meta = WindFieldMetadata(
        source="gfs",
        cycle=cycle.cycle_dt,
        fxx_start=fxx_values[0],
        fxx_end=fxx_values[-1],
        levels_hpa=tuple(float(lv) for lv in levels),
        region="global",
        grid_extent=None,
    )
    return _BuildResult(wind_field=wf, metadata=meta)


def build_wind_field(
    target_time: datetime,
    duration_hours: float,
    lat: float,
    lon: float,
    altitude_m: float,
    *,
    cache_dir: Optional[Path] = None,
    prefer_hrrr: bool = True,
) -> _BuildResult:
    """Build a :class:`WindField` for the requested trajectory window.

    Parameters
    ----------
    target_time : datetime
        Start time of the trajectory (UTC, tz-aware).
    duration_hours : float
        Length of the trajectory window [h].
    lat, lon : float
        Launch position. Used to decide CONUS-vs-global source.
    altitude_m : float
        Float altitude. Drives level subset and the HRRR/GFS gate
        (HRRR is only viable if altitude is below ~17 km).
    cache_dir : Path, optional
        Where to store partial-fetched GRIB files. Defaults to
        ``~/.cache/stratolink/predictor``.
    prefer_hrrr : bool
        If False, skip HRRR and go straight to GFS. Useful for tests
        and for the rare CONUS launch where HRRR is unavailable.

    Returns
    -------
    _BuildResult
        ``.wind_field`` is the runtime WindField; ``.metadata`` is the
        provenance dict the API echoes back.

    Raises
    ------
    FileNotFoundError
        If no NWP source can cover the requested window.
    """
    if target_time.tzinfo is None or target_time.tzinfo.utcoffset(target_time) != timedelta(0):
        raise ValueError("target_time must be timezone-aware UTC.")
    cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()

    target_hpa = isa.pressure(altitude_m) / 100.0
    hrrr_viable = (
        prefer_hrrr
        and _inside_conus(lat, lon)
        and target_hpa >= HRRR_TOP_HPA
        and duration_hours <= HRRR_MAX_FXX_DEFAULT
    )

    if hrrr_viable:
        try:
            return _build_hrrr(target_time, duration_hours, altitude_m, cache_dir)
        except Exception as e:
            # If HRRR fails (e.g., cycle not yet uploaded), fall through to GFS
            logger.warning("HRRR fetch failed (%s); falling back to GFS.", e)

    return _build_gfs(target_time, duration_hours, altitude_m, cache_dir)
