"""
HRRR-backed wind field with KDTree nearest-neighbor spatial sampling.

The HRRR grid is Lambert Conformal Conic — ``latitude`` and ``longitude``
are 2-D arrays of shape ``(y, x)`` rather than 1-D dim coords. That
makes :class:`predictor.weather.wind_field.XarrayWindField`'s
``Dataset.interp`` approach unusable: ``interp`` requires monotone
1-D dim coords for ``method="linear"``.

This module supplies the missing piece — a wind field that:

- Builds a single :class:`scipy.spatial.KDTree` over the flattened
  ``(latitude, longitude)`` grid at construction time and caches it.
  Nearest-neighbor lookup is exact and runs in microseconds.
- Interpolates linearly across **isobaricInhPa** for the vertical
  axis and across **valid_time** for the temporal axis.
- Restricts the in-memory dataset to a caller-supplied subset of
  pressure levels and forecast hours so that a typical 6 h request
  consumes a few hundred MB rather than tens of GB.

Longitude convention is normalized to ``[−180, 180]`` at construction
so callers don't have to think about it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

import numpy as np

from predictor.atmosphere import isa

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _GridIndex:
    """Cached spatial index over a 2-D HRRR grid."""

    lat2d: np.ndarray         # shape (y, x), degrees
    lon2d: np.ndarray         # shape (y, x), degrees in [-180, 180]
    kdtree: object            # scipy.spatial.KDTree
    shape: tuple[int, int]    # (y, x)


def _build_grid_index(lat2d: np.ndarray, lon2d: np.ndarray) -> _GridIndex:
    """Normalize lon to [-180, 180] and build a KDTree over (lat, lon)."""
    from scipy.spatial import KDTree

    lon2d = np.where(lon2d > 180.0, lon2d - 360.0, lon2d)
    shape = lat2d.shape
    points = np.column_stack([lat2d.ravel(), lon2d.ravel()])
    tree = KDTree(points)
    return _GridIndex(lat2d=lat2d, lon2d=lon2d, kdtree=tree, shape=shape)


class HRRRWindField:
    """Wind field backed by one or more HRRR pressure-level snapshots.

    Construction-time inputs
    ------------------------
    The dataset must carry:

    - Variables ``u`` and ``v`` (m/s, eastward and northward) with
      shape ``(time, isobaricInhPa, y, x)``.
    - 2-D coords ``latitude(y, x)`` and ``longitude(y, x)``.
    - 1-D coord ``isobaricInhPa(level)`` in hPa.
    - 1-D coord ``valid_time(time)`` of valid timestamps.

    A typical construction goes through :func:`HRRRWindField.from_files`,
    which opens one or more cycle/fxx GRIB files with
    :func:`predictor.weather.hrrr_client.open_pressure_levels`, concats
    along ``time``, and subsets to the requested pressure levels.

    Sampling
    --------
    ``get_wind`` and ``get_wind_at_altitude`` perform:

    1. Nearest-neighbor lookup in the 2-D lat/lon grid via KDTree.
    2. Linear interpolation across ``isobaricInhPa``.
    3. Linear interpolation across ``valid_time``.

    Queries outside the time window are clamped to the nearest end.
    Queries outside the level range are clamped similarly (the
    integrator should never query above the highest level we loaded —
    the wind factory subsets levels around the flight altitude so
    this is a safety net, not an expected path).
    """

    def __init__(self, dataset) -> None:
        """``dataset`` is an :class:`xarray.Dataset` with the layout above."""
        self._ds = dataset
        lat2d = dataset["latitude"].values
        lon2d = dataset["longitude"].values
        self._grid = _build_grid_index(lat2d, lon2d)

        # Pre-extract ascending-sorted level + time axes for fast clamping
        self._levels_hpa = np.asarray(dataset["isobaricInhPa"].values, dtype=float)
        self._level_ascending = bool(self._levels_hpa[0] < self._levels_hpa[-1])
        if not self._level_ascending:
            # Flip so we always work in ascending hPa (low altitude → high altitude)
            self._ds = self._ds.sortby("isobaricInhPa")
            self._levels_hpa = np.asarray(self._ds["isobaricInhPa"].values, dtype=float)
            self._level_ascending = True

        # Time axis: either 'valid_time' (preferred) or 'time' + 'step'
        if "valid_time" in self._ds.coords:
            t_axis = self._ds["valid_time"].values
        elif "time" in self._ds.dims:
            t_axis = self._ds["time"].values
        else:
            raise ValueError(
                "Dataset must have 'valid_time' or 'time' coord."
            )
        self._times_ns = np.asarray(t_axis, dtype="datetime64[ns]")
        # If single-time snapshot, time axis has size 1 → all queries return that snapshot
        if self._times_ns.ndim == 0:
            self._times_ns = self._times_ns.reshape(1)

        # Cache numpy views of u and v for speed (avoids repeated DataArray ops)
        self._u = np.asarray(self._ds["u"].values, dtype=np.float32)
        self._v = np.asarray(self._ds["v"].values, dtype=np.float32)
        # Expected shape: (time, level, y, x). Re-order if necessary.
        u_dims = self._ds["u"].dims
        expected_order = ("time", "isobaricInhPa", "y", "x")
        if tuple(u_dims) != expected_order:
            # Best-effort reorder via transpose
            try:
                self._u = np.asarray(
                    self._ds["u"].transpose(*expected_order).values, dtype=np.float32
                )
                self._v = np.asarray(
                    self._ds["v"].transpose(*expected_order).values, dtype=np.float32
                )
            except Exception as e:
                raise ValueError(
                    f"u/v have unexpected dims {u_dims!r}; expected {expected_order}: {e}"
                )
        # If u/v lack a 'time' dim entirely (single-fxx open) — promote.
        if self._u.ndim == 3:
            self._u = self._u[np.newaxis, ...]
            self._v = self._v[np.newaxis, ...]

    # ---------- construction helpers ----------

    @classmethod
    def from_files(
        cls,
        grib_paths: Sequence,
        cycle_dt: datetime,
        fxx_values: Sequence[int],
        levels_hpa: Sequence[float] | None = None,
    ) -> "HRRRWindField":
        """Open one or more cycle/fxx GRIB files and assemble a single field.

        Parameters
        ----------
        grib_paths : sequence of Path
            Local paths, one per forecast hour. Must be aligned with
            ``fxx_values``.
        cycle_dt : datetime
            HRRR cycle initialization time (UTC).
        fxx_values : sequence of int
            Forecast hours, aligned with ``grib_paths``. ``valid_time``
            for each snapshot is computed as ``cycle_dt + fxx * 1 h``.
        levels_hpa : sequence of float, optional
            Restrict the in-memory dataset to these pressure levels (hPa).
            Strongly recommended — opening all 40 HRRR levels uses
            ~2 GB per fxx.

        Returns
        -------
        HRRRWindField
        """
        import xarray as xr

        from predictor.weather.hrrr_client import open_pressure_levels

        if len(grib_paths) != len(fxx_values):
            raise ValueError("grib_paths and fxx_values must be the same length.")
        if not grib_paths:
            raise ValueError("Need at least one GRIB file.")

        snapshots: list = []
        for path, fxx in zip(grib_paths, fxx_values):
            ds = open_pressure_levels(path)
            if levels_hpa is not None:
                ds = ds.sel(isobaricInhPa=list(levels_hpa))
            # Drop the per-file scalar coords cfgrib attaches (`time`,
            # `step`, `valid_time`) — their values vary by fxx and break
            # xr.concat. We restamp a single time dim below.
            conflicting = [c for c in ("time", "step", "valid_time") if c in ds.coords]
            if conflicting:
                ds = ds.drop_vars(conflicting)
            vt = (cycle_dt + timedelta(hours=int(fxx))).replace(tzinfo=None)
            ds = ds.expand_dims(time=[np.datetime64(vt, "ns")])
            snapshots.append(ds)

        combined = xr.concat(snapshots, dim="time", coords="minimal")
        combined = combined.assign_coords(valid_time=("time", combined["time"].values))
        return cls(combined)

    # ---------- sampling ----------

    def _nearest_yx(self, lat: float, lon: float) -> tuple[int, int]:
        _, idx = self._grid.kdtree.query([lat, lon])
        j, i = np.unravel_index(int(idx), self._grid.shape)
        return int(j), int(i)

    def _time_weights(self, t_ns: np.datetime64) -> tuple[int, int, float]:
        """Return ``(t_low_idx, t_high_idx, weight_to_high)`` for the given query time."""
        # Clamp to the available range
        if t_ns <= self._times_ns[0]:
            return 0, 0, 0.0
        if t_ns >= self._times_ns[-1]:
            n = len(self._times_ns) - 1
            return n, n, 0.0
        # searchsorted: returns the index where t_ns would be inserted
        idx = int(np.searchsorted(self._times_ns, t_ns, side="right")) - 1
        t_lo = self._times_ns[idx]
        t_hi = self._times_ns[idx + 1]
        span_ns = (t_hi - t_lo) / np.timedelta64(1, "ns")
        if span_ns <= 0:
            return idx, idx, 0.0
        weight = float((t_ns - t_lo) / np.timedelta64(1, "ns") / span_ns)
        return idx, idx + 1, weight

    def _level_weights(self, level_hpa: float) -> tuple[int, int, float]:
        """Return ``(lo_idx, hi_idx, weight_to_hi)`` for the given hPa level."""
        levels = self._levels_hpa
        if level_hpa <= levels[0]:
            return 0, 0, 0.0
        if level_hpa >= levels[-1]:
            n = len(levels) - 1
            return n, n, 0.0
        idx = int(np.searchsorted(levels, level_hpa, side="right")) - 1
        lo = levels[idx]
        hi = levels[idx + 1]
        return idx, idx + 1, float((level_hpa - lo) / (hi - lo))

    def _sample(self, lat: float, lon: float, level_hpa: float, time: datetime) -> tuple[float, float]:
        if lon > 180.0:
            lon -= 360.0
        elif lon < -180.0:
            lon += 360.0
        j, i = self._nearest_yx(lat, lon)
        t_naive = time.replace(tzinfo=None) if time.tzinfo is not None else time
        t_ns = np.datetime64(t_naive, "ns")
        t_lo, t_hi, w_t = self._time_weights(t_ns)
        l_lo, l_hi, w_l = self._level_weights(level_hpa)

        # u[time, level, y, x]
        u00 = float(self._u[t_lo, l_lo, j, i])
        u01 = float(self._u[t_lo, l_hi, j, i])
        u10 = float(self._u[t_hi, l_lo, j, i])
        u11 = float(self._u[t_hi, l_hi, j, i])
        v00 = float(self._v[t_lo, l_lo, j, i])
        v01 = float(self._v[t_lo, l_hi, j, i])
        v10 = float(self._v[t_hi, l_lo, j, i])
        v11 = float(self._v[t_hi, l_hi, j, i])

        # Bilinear in (time, level)
        u_lo_t = u00 * (1 - w_l) + u01 * w_l
        u_hi_t = u10 * (1 - w_l) + u11 * w_l
        u = u_lo_t * (1 - w_t) + u_hi_t * w_t
        v_lo_t = v00 * (1 - w_l) + v01 * w_l
        v_hi_t = v10 * (1 - w_l) + v11 * w_l
        v = v_lo_t * (1 - w_t) + v_hi_t * w_t
        return u, v

    def get_wind(self, lat: float, lon: float, pressure_pa: float, time: datetime) -> tuple[float, float]:
        return self._sample(lat, lon, pressure_pa / 100.0, time)

    def get_wind_at_altitude(self, lat: float, lon: float, altitude_m: float, time: datetime) -> tuple[float, float]:
        return self.get_wind(lat, lon, isa.pressure(altitude_m), time)

    # ---------- introspection ----------

    @property
    def grid_extent(self) -> dict:
        """Lat/lon bounding box of the loaded grid (for region-of-validity checks)."""
        return {
            "lat_min": float(self._grid.lat2d.min()),
            "lat_max": float(self._grid.lat2d.max()),
            "lon_min": float(self._grid.lon2d.min()),
            "lon_max": float(self._grid.lon2d.max()),
        }

    @property
    def levels_hpa(self) -> np.ndarray:
        return self._levels_hpa.copy()

    @property
    def time_range(self) -> tuple[datetime, datetime]:
        t0 = self._times_ns[0].astype("datetime64[s]").astype(object).replace(tzinfo=timezone.utc)
        t1 = self._times_ns[-1].astype("datetime64[s]").astype(object).replace(tzinfo=timezone.utc)
        return t0, t1
