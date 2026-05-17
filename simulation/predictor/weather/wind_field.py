"""
Wind-field abstractions.

A ``WindField`` is anything that can answer "given a lat, lon, pressure
level (Pa), and time, what are the (u, v) wind components in m/s?". Two
concrete implementations live in this module:

- :class:`ConstantWindField` — analytic, used to give Phase 3 onward a
  reproducible test harness with no NWP dependency.
- :class:`XarrayWindField` — wraps an :class:`xarray.Dataset` with
  4-D ``u`` and ``v`` arrays indexed by latitude, longitude,
  isobaric level, and time. This is the runtime class — the NWP
  clients in :mod:`predictor.weather.hrrr_client` and
  :mod:`predictor.weather.gfs_client` produce one of these.

The protocol is intentionally tiny so other sources (sounding profiles,
analytical Rossby modes, persisted ensemble members) can be slotted in
without changing the trajectory integrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import numpy as np

from predictor.atmosphere import isa


@runtime_checkable
class WindField(Protocol):
    """Anything that can sample (u, v) wind at a 4-D query point.

    Implementations must return wind in **m/s** with u = eastward,
    v = northward, regardless of internal storage convention.
    """

    def get_wind(
        self,
        lat: float,
        lon: float,
        pressure_pa: float,
        time: datetime,
    ) -> tuple[float, float]:
        """Return ``(u, v)`` in m/s at the given query point.

        Parameters
        ----------
        lat : float
            Latitude in degrees, range [−90, 90].
        lon : float
            Longitude in degrees, range [−180, 180].
        pressure_pa : float
            Atmospheric pressure level in Pascals.
        time : datetime
            Valid time of the query (timezone-aware UTC).
        """
        ...

    def get_wind_at_altitude(
        self,
        lat: float,
        lon: float,
        altitude_m: float,
        time: datetime,
    ) -> tuple[float, float]:
        """Convenience: like :meth:`get_wind`, but altitude is in metres.

        Implementations may convert with USSA-1976 via
        :func:`predictor.atmosphere.isa.pressure`.
        """
        ...


@dataclass(frozen=True)
class ConstantWindField:
    """Spatially and temporally uniform wind. Used in tests.

    Attributes
    ----------
    u_m_s : float
        Eastward wind component [m/s].
    v_m_s : float
        Northward wind component [m/s].
    """

    u_m_s: float
    v_m_s: float

    def get_wind(
        self,
        lat: float,  # noqa: ARG002 — protocol shape
        lon: float,  # noqa: ARG002
        pressure_pa: float,  # noqa: ARG002
        time: datetime,  # noqa: ARG002
    ) -> tuple[float, float]:
        return (self.u_m_s, self.v_m_s)

    def get_wind_at_altitude(
        self,
        lat: float,  # noqa: ARG002
        lon: float,  # noqa: ARG002
        altitude_m: float,  # noqa: ARG002
        time: datetime,  # noqa: ARG002
    ) -> tuple[float, float]:
        return (self.u_m_s, self.v_m_s)


class XarrayWindField:
    """Generic xarray-backed wind field, used in tests and for diagnostics.

    Convenience wrapper that delegates to :meth:`xarray.Dataset.interp`.
    Convenient but slow — every call walks xarray's indexer-validation
    machinery, so 10k+ calls per request blow past the latency budget.
    Production code paths should use :class:`RegularGridWindField`
    (1-D lat/lon, GFS-shape) or
    :class:`predictor.weather.hrrr_wind_field.HRRRWindField`
    (2-D lat/lon, Lambert grid) instead.

    Expected dataset schema
    -----------------------
    Variables
        - ``u`` (eastward wind, m/s)
        - ``v`` (northward wind, m/s)

    Dims (each variable must carry all four)
        - latitude  — degrees, can be unsorted
        - longitude — degrees in either [−180, 180] or [0, 360]; this
          class normalizes to [−180, 180] internally
        - isobaricInhPa — pressure level in **hPa** (mb), matching the
          GRIB2/cfgrib convention
        - time — datetime64[ns] of valid time
    """

    def __init__(
        self,
        dataset,  # xarray.Dataset; not annotated to keep xarray optional
        *,
        u_var: str = "u",
        v_var: str = "v",
        lat_coord: str = "latitude",
        lon_coord: str = "longitude",
        level_coord: str = "isobaricInhPa",
        time_coord: str = "time",
    ) -> None:
        self._ds = dataset
        self._u_var = u_var
        self._v_var = v_var
        self._lat_coord = lat_coord
        self._lon_coord = lon_coord
        self._level_coord = level_coord
        self._time_coord = time_coord

        # Normalize longitude to [−180, 180] so callers can pass either
        # convention without thinking about it.
        lon = self._ds[lon_coord].values
        if lon.ndim == 1 and float(np.max(lon)) > 180.0:
            new_lon = ((lon + 180.0) % 360.0) - 180.0
            ds2 = self._ds.assign_coords({lon_coord: new_lon})
            self._ds = ds2.sortby(lon_coord)

    def get_wind(
        self,
        lat: float,
        lon: float,
        pressure_pa: float,
        time: datetime,
    ) -> tuple[float, float]:
        """4-D linear interpolation at ``(lat, lon, p, t)``."""
        # Normalize lon to whatever the dataset uses (we already canonicalized
        # the dataset to [−180, 180] in __init__)
        if lon > 180.0:
            lon = lon - 360.0
        elif lon < -180.0:
            lon = lon + 360.0

        level_hpa = pressure_pa / 100.0
        # Convert tz-aware datetime to naive UTC at nanosecond precision
        # to satisfy xarray/pandas (no implicit-precision warnings).
        t_naive = time.replace(tzinfo=None) if time.tzinfo is not None else time
        sel = self._ds.interp(
            {
                self._lat_coord: lat,
                self._lon_coord: lon,
                self._level_coord: level_hpa,
                self._time_coord: np.datetime64(t_naive, "ns"),
            },
            method="linear",
        )
        u = float(sel[self._u_var].values)
        v = float(sel[self._v_var].values)
        return (u, v)

    def get_wind_at_altitude(
        self,
        lat: float,
        lon: float,
        altitude_m: float,
        time: datetime,
    ) -> tuple[float, float]:
        return self.get_wind(lat, lon, isa.pressure(altitude_m), time)


class RegularGridWindField:
    """Fast wind-field sampler for datasets with 1-D lat/lon coords.

    Pre-extracts u/v as eagerly-loaded numpy arrays at construction;
    sampling uses :func:`numpy.searchsorted` for axis lookup and a
    manual 16-point linear-in-(time, level, lat, lon) interp. No
    xarray dispatch per call — measured at < 20 μs per sample on
    GFS-shape data, vs. ~10 ms via :class:`XarrayWindField`.

    Use this for **GFS-shape** data (regular lat/lon grids). For
    HRRR-shape data (2-D ``latitude``/``longitude`` on a Lambert
    Conformal mesh), use
    :class:`predictor.weather.hrrr_wind_field.HRRRWindField`.

    Expected dataset
    ----------------
    Variables ``u`` and ``v`` (m/s) with dims
    ``(time, isobaricInhPa, latitude, longitude)`` in any order
    — the constructor transposes. Coords must be 1-D and monotone
    after the constructor's normalization (longitude is wrapped to
    [−180, 180] and re-sorted; latitude and level are flipped to
    ascending if needed).
    """

    def __init__(
        self,
        dataset,
        *,
        time_dim: str = "time",
        level_dim: str = "isobaricInhPa",
        lat_dim: str = "latitude",
        lon_dim: str = "longitude",
    ) -> None:
        # Normalize longitude convention first, before transpose
        lon = dataset[lon_dim].values
        if lon.ndim == 1 and float(np.max(lon)) > 180.0:
            new_lon = ((lon + 180.0) % 360.0) - 180.0
            dataset = dataset.assign_coords({lon_dim: new_lon}).sortby(lon_dim)

        # Sort lat / level ascending so searchsorted has a monotone target
        if dataset[lat_dim].values[0] > dataset[lat_dim].values[-1]:
            dataset = dataset.sortby(lat_dim)
        if dataset[level_dim].values[0] > dataset[level_dim].values[-1]:
            dataset = dataset.sortby(level_dim)

        # Materialize to numpy in canonical (t, l, y, x) order
        dataset = dataset.transpose(time_dim, level_dim, lat_dim, lon_dim)
        self._lat = np.asarray(dataset[lat_dim].values, dtype=float)
        self._lon = np.asarray(dataset[lon_dim].values, dtype=float)
        self._levels = np.asarray(dataset[level_dim].values, dtype=float)
        self._times_ns = np.asarray(dataset[time_dim].values, dtype="datetime64[ns]")
        if self._times_ns.ndim == 0:
            self._times_ns = self._times_ns.reshape(1)
        self._u = np.asarray(dataset["u"].values, dtype=np.float32)
        self._v = np.asarray(dataset["v"].values, dtype=np.float32)
        # Promote (l, y, x) → (1, l, y, x) for snapshot datasets
        if self._u.ndim == 3:
            self._u = self._u[np.newaxis, ...]
            self._v = self._v[np.newaxis, ...]

    @staticmethod
    def _bracket(axis: np.ndarray, value: float) -> tuple[int, int, float]:
        if value <= axis[0]:
            return 0, 0, 0.0
        if value >= axis[-1]:
            n = len(axis) - 1
            return n, n, 0.0
        idx = int(np.searchsorted(axis, value, side="right")) - 1
        lo_val = float(axis[idx])
        hi_val = float(axis[idx + 1])
        span = hi_val - lo_val
        if span <= 0.0:
            return idx, idx, 0.0
        return idx, idx + 1, (value - lo_val) / span

    def _bracket_time(self, t_ns: np.datetime64) -> tuple[int, int, float]:
        if t_ns <= self._times_ns[0]:
            return 0, 0, 0.0
        if t_ns >= self._times_ns[-1]:
            n = len(self._times_ns) - 1
            return n, n, 0.0
        idx = int(np.searchsorted(self._times_ns, t_ns, side="right")) - 1
        lo = self._times_ns[idx]
        hi = self._times_ns[idx + 1]
        span_ns = (hi - lo) / np.timedelta64(1, "ns")
        if span_ns <= 0:
            return idx, idx, 0.0
        return idx, idx + 1, float((t_ns - lo) / np.timedelta64(1, "ns") / span_ns)

    def _sample_field(self, arr, t_lo, t_hi, l_lo, l_hi, y_lo, y_hi, x_lo, x_hi,
                      w_t, w_l, w_y, w_x) -> float:
        # 4-D linear interp via repeated 1-D blends; cheap and branch-free.
        c000 = arr[t_lo, l_lo, y_lo, x_lo]
        c001 = arr[t_lo, l_lo, y_lo, x_hi]
        c010 = arr[t_lo, l_lo, y_hi, x_lo]
        c011 = arr[t_lo, l_lo, y_hi, x_hi]
        c100 = arr[t_lo, l_hi, y_lo, x_lo]
        c101 = arr[t_lo, l_hi, y_lo, x_hi]
        c110 = arr[t_lo, l_hi, y_hi, x_lo]
        c111 = arr[t_lo, l_hi, y_hi, x_hi]
        d000 = arr[t_hi, l_lo, y_lo, x_lo]
        d001 = arr[t_hi, l_lo, y_lo, x_hi]
        d010 = arr[t_hi, l_lo, y_hi, x_lo]
        d011 = arr[t_hi, l_lo, y_hi, x_hi]
        d100 = arr[t_hi, l_hi, y_lo, x_lo]
        d101 = arr[t_hi, l_hi, y_lo, x_hi]
        d110 = arr[t_hi, l_hi, y_hi, x_lo]
        d111 = arr[t_hi, l_hi, y_hi, x_hi]

        # Lon (x) blend
        c00 = c000 * (1 - w_x) + c001 * w_x
        c01 = c010 * (1 - w_x) + c011 * w_x
        c10 = c100 * (1 - w_x) + c101 * w_x
        c11 = c110 * (1 - w_x) + c111 * w_x
        d00 = d000 * (1 - w_x) + d001 * w_x
        d01 = d010 * (1 - w_x) + d011 * w_x
        d10 = d100 * (1 - w_x) + d101 * w_x
        d11 = d110 * (1 - w_x) + d111 * w_x
        # Lat (y) blend
        c0 = c00 * (1 - w_y) + c01 * w_y
        c1 = c10 * (1 - w_y) + c11 * w_y
        d0 = d00 * (1 - w_y) + d01 * w_y
        d1 = d10 * (1 - w_y) + d11 * w_y
        # Level blend
        c_t = c0 * (1 - w_l) + c1 * w_l
        d_t = d0 * (1 - w_l) + d1 * w_l
        # Time blend
        return float(c_t * (1 - w_t) + d_t * w_t)

    def get_wind(self, lat: float, lon: float, pressure_pa: float, time: datetime) -> tuple[float, float]:
        if lon > 180.0:
            lon -= 360.0
        elif lon < -180.0:
            lon += 360.0
        t_naive = time.replace(tzinfo=None) if time.tzinfo is not None else time
        t_ns = np.datetime64(t_naive, "ns")
        t_lo, t_hi, w_t = self._bracket_time(t_ns)
        l_lo, l_hi, w_l = self._bracket(self._levels, pressure_pa / 100.0)
        y_lo, y_hi, w_y = self._bracket(self._lat, lat)
        x_lo, x_hi, w_x = self._bracket(self._lon, lon)
        u = self._sample_field(self._u, t_lo, t_hi, l_lo, l_hi, y_lo, y_hi, x_lo, x_hi,
                               w_t, w_l, w_y, w_x)
        v = self._sample_field(self._v, t_lo, t_hi, l_lo, l_hi, y_lo, y_hi, x_lo, x_hi,
                               w_t, w_l, w_y, w_x)
        return u, v

    def get_wind_at_altitude(self, lat: float, lon: float, altitude_m: float, time: datetime) -> tuple[float, float]:
        return self.get_wind(lat, lon, isa.pressure(altitude_m), time)
