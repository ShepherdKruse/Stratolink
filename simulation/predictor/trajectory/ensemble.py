"""
Ensemble trajectory uncertainty.

Runs N perturbed trajectories with:

- **Initial position**: isotropic Gaussian in the horizontal,
  σ = ``initial_position_sigma_m`` (default 500 m).
- **Wind field**: piecewise-constant Brownian-noise perturbation,
  σ = ``wind_sigma_m_s`` per ``step_seconds`` segment, applied
  independently to u and v.
- **Float altitude**: per-member Gaussian offset
  σ = ``altitude_sigma_m`` (default 100 m), held constant for the
  member's flight.

For each output time bin we report the median (lat, lon) plus the
great-circle 1σ and 2σ radii of the ensemble's spread. These feed the
uncertainty cone the dashboard will eventually consume.

Implementation note
-------------------
The deterministic propagator (:func:`predictor.trajectory.integrator.propagate`)
uses adaptive RK45, which is inappropriate for SDE-style integration —
the adaptive controller mis-reads the discontinuous Brownian wind
perturbation as solver error and shrinks the step, which then changes
the noise discretization. We use a fixed-step Euler-Maruyama scheme
here instead. For 60 s steps over a 10 h horizon at superpressure
altitudes the deterministic-part discretization error is well below
the noise-driven spread, so the order reduction is not a concern.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from predictor.trajectory.integrator import (
    GeodeticPosition,
    R_EARTH_M,
    Trajectory,
    TrajectoryPoint,
    _normalize_longitude_deg,
)
from predictor.weather.wind_field import WindField


# Default perturbation magnitudes. The HRRR 6 h wind RMSE (~2 m/s) seeds
# wind_sigma_m_s indirectly; the absolute CEP calibration is an open-data
# exercise once real flight tracks land.
DEFAULT_N_MEMBERS = 50
DEFAULT_INITIAL_POSITION_SIGMA_M = 500.0
DEFAULT_WIND_SIGMA_M_S = 4.0
DEFAULT_ALTITUDE_SIGMA_M = 100.0


@dataclass(frozen=True)
class EnsemblePoint:
    """Median + uncertainty radius at one output time.

    Attributes
    ----------
    t_offset_s : float
        Seconds since the start time.
    time : datetime
        Absolute valid time (UTC).
    lat_deg, lon_deg : float
        Median position (component-wise across ensemble members).
    altitude_m : float
        Mean altitude across members at this step.
    sigma1_radius_km : float
        Great-circle distance from the median containing 68 % of
        members' positions.
    sigma2_radius_km : float
        Same for 95 %.
    """

    t_offset_s: float
    time: datetime
    lat_deg: float
    lon_deg: float
    altitude_m: float
    sigma1_radius_km: float
    sigma2_radius_km: float


@dataclass(frozen=True)
class EnsembleResult:
    """Result of :func:`run_ensemble`.

    Attributes
    ----------
    members : list[Trajectory]
        Per-member trajectories.
    summary : list[EnsemblePoint]
        Median + 1σ/2σ envelope at each output bin.
    n_members : int
    start_time : datetime
    duration_s : float
    """

    members: list[Trajectory]
    summary: list[EnsemblePoint]
    n_members: int
    start_time: datetime
    duration_s: float


class _NoisyWindField:
    """Wraps a :class:`WindField` and adds a member-specific noise process.

    Noise is piecewise-constant on the integrator's fixed step grid so
    the per-step perturbations are iid Gaussian. Position spread then
    grows as ``σ_w · √(T · dt)`` (Brownian-motion scaling), giving the
    √t shape required by the Phase 4 verification gate.
    """

    def __init__(
        self,
        base: WindField,
        rng: np.random.Generator,
        sigma_m_s: float,
        n_steps: int,
    ) -> None:
        self._base = base
        # Two perturbation arrays — u and v independent
        self._du = rng.normal(0.0, sigma_m_s, size=n_steps)
        self._dv = rng.normal(0.0, sigma_m_s, size=n_steps)

    def perturb(self, step_idx: int) -> tuple[float, float]:
        idx = min(max(step_idx, 0), len(self._du) - 1)
        return float(self._du[idx]), float(self._dv[idx])

    # Pass-through for protocol compatibility (not used by ensemble's
    # custom stepper, but useful if someone runs `propagate` against
    # a noisy field directly).
    def get_wind(self, lat, lon, pressure_pa, time):
        return self._base.get_wind(lat, lon, pressure_pa, time)

    def get_wind_at_altitude(self, lat, lon, altitude_m, time):
        return self._base.get_wind_at_altitude(lat, lon, altitude_m, time)


def _meters_to_lat_lon_deg(
    lat_deg: float, dx_east_m: float, dy_north_m: float
) -> tuple[float, float]:
    """Convert an (east, north) metric offset to (Δlat, Δlon) in degrees."""
    deg_per_rad = 180.0 / math.pi
    dlat = (dy_north_m / R_EARTH_M) * deg_per_rad
    cos_lat = math.cos(math.radians(lat_deg))
    dlon = (dx_east_m / (R_EARTH_M * max(cos_lat, 1e-6))) * deg_per_rad
    return dlat, dlon


def _great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points [km]."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * R_EARTH_M * math.asin(math.sqrt(a)) / 1000.0


def _propagate_member(
    initial_position: GeodeticPosition,
    wind_field: WindField,
    noise: _NoisyWindField,
    duration_s: float,
    start_time: datetime,
    altitude_m_const: float,
    step_seconds: float,
    output_step_seconds: float,
) -> Trajectory:
    """Fixed-step Euler-Maruyama propagator for one ensemble member.

    Records output at every ``output_step_seconds``; the integration
    proceeds at ``step_seconds`` (which must divide ``output_step_seconds``
    for clean alignment, otherwise output is taken at the nearest step).
    """
    deg_per_rad = 180.0 / math.pi
    n_outputs = int(round(duration_s / output_step_seconds)) + 1
    output_times_s = [i * output_step_seconds for i in range(n_outputs)]

    lat = initial_position.lat_deg
    lon = initial_position.lon_deg
    t_s = 0.0
    step_idx = 0

    points: list[TrajectoryPoint] = []
    next_out_i = 0

    while next_out_i < n_outputs:
        # Capture output samples that fall in [t_s, t_s + step_seconds)
        while (
            next_out_i < n_outputs
            and output_times_s[next_out_i] <= t_s + 1e-6
        ):
            ot = output_times_s[next_out_i]
            points.append(
                TrajectoryPoint(
                    t_offset_s=ot,
                    time=start_time + timedelta(seconds=ot),
                    lat_deg=lat,
                    lon_deg=_normalize_longitude_deg(lon),
                    altitude_m=altitude_m_const,
                )
            )
            next_out_i += 1
        if next_out_i >= n_outputs:
            break

        valid_time = start_time + timedelta(seconds=t_s)
        u, v = wind_field.get_wind_at_altitude(lat, lon, altitude_m_const, valid_time)
        du, dv = noise.perturb(step_idx)
        u_total = u + du
        v_total = v + dv

        cos_lat = math.cos(math.radians(lat))
        cos_lat = max(abs(cos_lat), 1e-6) * (1.0 if cos_lat >= 0 else -1.0)
        dlat_dt = (v_total / R_EARTH_M) * deg_per_rad
        dlon_dt = (u_total / (R_EARTH_M * cos_lat)) * deg_per_rad

        lat += dlat_dt * step_seconds
        lon += dlon_dt * step_seconds
        t_s += step_seconds
        step_idx += 1

    return Trajectory(points=points, start_time=start_time, duration_s=duration_s)


def run_ensemble(
    initial_position: GeodeticPosition,
    wind_field: WindField,
    duration_hours: float,
    start_time: datetime,
    n_members: int = DEFAULT_N_MEMBERS,
    initial_position_sigma_m: float = DEFAULT_INITIAL_POSITION_SIGMA_M,
    wind_sigma_m_s: float = DEFAULT_WIND_SIGMA_M_S,
    altitude_sigma_m: float = DEFAULT_ALTITUDE_SIGMA_M,
    step_seconds: float = 60.0,
    output_step_seconds: float = 300.0,
    seed: Optional[int] = None,
) -> EnsembleResult:
    """Run a perturbed-input ensemble and summarize position uncertainty.

    Parameters
    ----------
    initial_position : GeodeticPosition
        Median starting position (lat, lon, altitude).
    wind_field : WindField
        Underlying wind source; perturbations are added on top per member.
    duration_hours : float
        Total propagation length [h].
    start_time : datetime
        Valid time of the initial position, UTC tz-aware.
    n_members : int
        Ensemble size. Default 50 per spec.
    initial_position_sigma_m : float
        1σ initial-position uncertainty in horizontal distance [m].
    wind_sigma_m_s : float
        1σ per-step wind perturbation [m/s]. Drives the √t position spread.
    altitude_sigma_m : float
        1σ float-altitude uncertainty [m].
    step_seconds : float
        Fixed integration step [s]. Default 60 s.
    output_step_seconds : float
        Spacing of returned samples [s]. Default 300 (5 min).
    seed : int, optional
        Master RNG seed for reproducibility.

    Returns
    -------
    EnsembleResult
    """
    if n_members < 2:
        raise ValueError("n_members must be at least 2.")
    if step_seconds <= 0 or output_step_seconds <= 0:
        raise ValueError("step_seconds and output_step_seconds must be positive.")
    if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) != timedelta(0):
        raise ValueError("start_time must be timezone-aware UTC.")

    duration_s = duration_hours * 3600.0
    n_steps = int(math.ceil(duration_s / step_seconds)) + 2

    rng = np.random.default_rng(seed)

    members: list[Trajectory] = []
    for _ in range(n_members):
        # Initial-position perturbation: isotropic Gaussian in horizontal distance
        dist_m = rng.normal(0.0, initial_position_sigma_m)
        bearing_rad = rng.uniform(0.0, 2.0 * math.pi)
        dx_east_m = dist_m * math.sin(bearing_rad)
        dy_north_m = dist_m * math.cos(bearing_rad)
        dlat_deg, dlon_deg = _meters_to_lat_lon_deg(
            initial_position.lat_deg, dx_east_m, dy_north_m
        )
        member_initial = GeodeticPosition(
            lat_deg=initial_position.lat_deg + dlat_deg,
            lon_deg=initial_position.lon_deg + dlon_deg,
            altitude_m=initial_position.altitude_m,
        )

        # Altitude offset (constant for this member's flight)
        alt_offset_m = rng.normal(0.0, altitude_sigma_m)
        member_altitude = initial_position.altitude_m + alt_offset_m

        # Independent noise stream per member, seeded from the master RNG
        member_rng = np.random.default_rng(rng.integers(0, 2**63 - 1))
        noisy = _NoisyWindField(
            base=wind_field,
            rng=member_rng,
            sigma_m_s=wind_sigma_m_s,
            n_steps=n_steps,
        )

        traj = _propagate_member(
            initial_position=member_initial,
            wind_field=wind_field,  # base, deterministic
            noise=noisy,
            duration_s=duration_s,
            start_time=start_time,
            altitude_m_const=member_altitude,
            step_seconds=step_seconds,
            output_step_seconds=output_step_seconds,
        )
        members.append(traj)

    # Summarize: at each output bin, compute median and 1σ/2σ spread radii
    n_points = len(members[0].points)
    summary: list[EnsemblePoint] = []
    for i in range(n_points):
        lats = np.array([m.points[i].lat_deg for m in members])
        lons = np.array([m.points[i].lon_deg for m in members])
        med_lat = float(np.median(lats))
        med_lon = float(np.median(lons))
        dists_km = np.array(
            [_great_circle_km(med_lat, med_lon, la, lo) for la, lo in zip(lats, lons)]
        )
        sigma1 = float(np.percentile(dists_km, 68.27))
        sigma2 = float(np.percentile(dists_km, 95.45))
        ref = members[0].points[i]
        # Mean altitude (offsets are zero-mean Gaussian → ≈ initial alt)
        alts = np.array([m.points[i].altitude_m for m in members])
        summary.append(
            EnsemblePoint(
                t_offset_s=ref.t_offset_s,
                time=ref.time,
                lat_deg=med_lat,
                lon_deg=med_lon,
                altitude_m=float(np.mean(alts)),
                sigma1_radius_km=sigma1,
                sigma2_radius_km=sigma2,
            )
        )

    return EnsembleResult(
        members=members,
        summary=summary,
        n_members=n_members,
        start_time=start_time,
        duration_s=duration_s,
    )


def cep_radius_km(spread_km: list[float], horizons_h: list[float],
                  output_step_seconds: float = 300.0) -> dict[float, float]:
    """Look up the 1σ spread at requested horizon times.

    Parameters
    ----------
    spread_km : list[float]
        Sigma1 (or sigma2) radii from an :class:`EnsembleResult.summary`.
    horizons_h : list[float]
        Horizons of interest in hours (e.g. [3, 6, 10]).
    output_step_seconds : float
        Spacing of the spread samples.

    Returns
    -------
    dict[float, float]
        Mapping ``hours -> CEP radius (km)`` using nearest-bin sampling.
    """
    out: dict[float, float] = {}
    for h in horizons_h:
        idx = int(round(h * 3600.0 / output_step_seconds))
        idx = max(0, min(idx, len(spread_km) - 1))
        out[h] = spread_km[idx]
    return out
