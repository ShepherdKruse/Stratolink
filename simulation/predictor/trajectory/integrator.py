"""
Lagrangian trajectory integrator.

Propagates a balloon position by integrating horizontal motion against
a :class:`~predictor.weather.wind_field.WindField`. State is ``(lat, lon)``
in degrees; altitude evolves under a caller-supplied
``altitude_fn(t_offset_s)`` so future ascent-aware modes can swap in
without changing the integrator.

For v1 superpressure operation the default ``altitude_fn`` is constant
at the initial altitude. Phase 1's
:func:`~predictor.buoyancy.ascent_model.simulate_ascent` can eventually
feed a non-constant profile for ascent-leg propagation.

The state derivative converts wind ``(u, v)`` in m/s to lat/lon rate on
a sphere of mean WGS84 radius using the standard ``1 / cos(lat)``
longitude scaling. The pole singularity at ``cos(lat) → 0`` is clamped
defensively since real flights stay below 80° latitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

import numpy as np
from scipy.integrate import solve_ivp

from predictor.weather.wind_field import WindField


R_EARTH_M = 6371008.8  # mean Earth radius (WGS84) [m]


@dataclass(frozen=True)
class GeodeticPosition:
    """A geodetic position with altitude.

    Attributes
    ----------
    lat_deg : float
        Latitude in degrees, range [−90, 90].
    lon_deg : float
        Longitude in degrees, range [−180, 180].
    altitude_m : float
        Altitude above sea level [m].
    """

    lat_deg: float
    lon_deg: float
    altitude_m: float


@dataclass(frozen=True)
class TrajectoryPoint:
    """One sample on a propagated trajectory.

    Attributes
    ----------
    t_offset_s : float
        Seconds since propagation start.
    time : datetime
        Absolute valid time (UTC, tz-aware).
    lat_deg, lon_deg : float
        Geodetic coordinates [degrees].
    altitude_m : float
        Altitude at this sample [m].
    """

    t_offset_s: float
    time: datetime
    lat_deg: float
    lon_deg: float
    altitude_m: float


@dataclass(frozen=True)
class Trajectory:
    """Sequence of trajectory samples produced by :func:`propagate`.

    Attributes
    ----------
    points : list[TrajectoryPoint]
        Samples at ``output_step_seconds`` intervals from t=0 to
        t=``duration_s``.
    start_time : datetime
        Valid time of the initial position.
    duration_s : float
        Total propagation duration [s].
    """

    points: list[TrajectoryPoint]
    start_time: datetime
    duration_s: float


def _normalize_longitude_deg(lon_deg: float) -> float:
    """Wrap a longitude in degrees into ``[−180, 180]``."""
    lon = ((lon_deg + 180.0) % 360.0) - 180.0
    # Edge case: 180.0 after modulo is fine; -180.0 also fine
    return lon


def propagate(
    initial_position: GeodeticPosition,
    wind_field: WindField,
    duration_hours: float,
    start_time: datetime,
    altitude_fn: Optional[Callable[[float], float]] = None,
    step_seconds: float = 60.0,
    output_step_seconds: float = 300.0,
) -> Trajectory:
    """Integrate a horizontal trajectory under the given wind field.

    Parameters
    ----------
    initial_position : GeodeticPosition
        Starting position; ``altitude_m`` seeds the default constant
        altitude profile.
    wind_field : WindField
        Wind source; sampled at every solver substep.
    duration_hours : float
        Total integration time [h]. Must be > 0.
    start_time : datetime
        Valid time of the initial position. UTC, tz-aware.
    altitude_fn : callable, optional
        Function ``t_offset_s -> altitude_m``. Defaults to constant
        ``initial_position.altitude_m`` (superpressure v1). Structured
        as a callable so future ascent-aware modes are a function swap,
        not a refactor.
    step_seconds : float
        Maximum solver step [s]. 60 s matches the balloon TX cadence
        and is well below wind-field decorrelation scales.
    output_step_seconds : float
        Spacing of returned samples [s]. Default 300 (5 min).

    Returns
    -------
    Trajectory
        Samples from t=0 to t=``duration_hours * 3600`` inclusive.
    """
    if duration_hours <= 0:
        raise ValueError("duration_hours must be positive.")
    if step_seconds <= 0:
        raise ValueError("step_seconds must be positive.")
    if output_step_seconds <= 0:
        raise ValueError("output_step_seconds must be positive.")
    if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) != timedelta(0):
        raise ValueError("start_time must be timezone-aware UTC.")

    h_seed = initial_position.altitude_m
    if altitude_fn is None:
        def altitude_fn(_t: float) -> float:
            return h_seed

    duration_s = duration_hours * 3600.0
    deg_per_rad = 180.0 / math.pi

    def rhs(t_s: float, state: np.ndarray) -> np.ndarray:
        lat_deg = float(state[0])
        lon_deg = float(state[1])
        alt_m = altitude_fn(t_s)
        valid_time = start_time + timedelta(seconds=t_s)
        u, v = wind_field.get_wind_at_altitude(lat_deg, lon_deg, alt_m, valid_time)
        dlat_dt = (v / R_EARTH_M) * deg_per_rad  # deg/s
        cos_lat = math.cos(math.radians(lat_deg))
        if abs(cos_lat) < 1e-6:
            # Polar clamp — flights never reach the singularity, but avoid /0
            cos_lat = math.copysign(1e-6, cos_lat) if cos_lat != 0 else 1e-6
        dlon_dt = (u / (R_EARTH_M * cos_lat)) * deg_per_rad
        return np.array([dlat_dt, dlon_dt])

    n_outputs = int(round(duration_s / output_step_seconds)) + 1
    t_eval = np.linspace(0.0, duration_s, n_outputs)
    y0 = np.array([initial_position.lat_deg, initial_position.lon_deg])
    sol = solve_ivp(
        rhs,
        (0.0, duration_s),
        y0,
        method="RK45",
        t_eval=t_eval,
        max_step=step_seconds,
        rtol=1e-6,
        atol=1e-9,
    )
    if not sol.success:
        raise RuntimeError(f"Trajectory integration failed: {sol.message}")

    points: list[TrajectoryPoint] = []
    for i, t_s in enumerate(sol.t):
        lat = float(sol.y[0, i])
        lon = _normalize_longitude_deg(float(sol.y[1, i]))
        points.append(
            TrajectoryPoint(
                t_offset_s=float(t_s),
                time=start_time + timedelta(seconds=float(t_s)),
                lat_deg=lat,
                lon_deg=lon,
                altitude_m=altitude_fn(float(t_s)),
            )
        )
    return Trajectory(points=points, start_time=start_time, duration_s=duration_s)
