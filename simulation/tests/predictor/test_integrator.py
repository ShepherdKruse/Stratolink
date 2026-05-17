"""Tests for the Lagrangian trajectory integrator.

Primary verification gate (per ``predictor-spec.md`` §Verification at each phase):
a constant 10 m/s east wind for 1 h must move the balloon ~36 km east.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from predictor.trajectory.integrator import (
    GeodeticPosition,
    R_EARTH_M,
    Trajectory,
    propagate,
)
from predictor.weather.wind_field import ConstantWindField


T0 = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def _great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points (degrees) [km]."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * R_EARTH_M * math.asin(math.sqrt(a)) / 1000.0


def test_ten_ms_east_wind_one_hour_moves_36km_east():
    """Phase 3 verification gate.

    A 10 m/s eastward wind for 3600 s should produce ~36 km eastward
    displacement, no northward displacement.
    """
    start = GeodeticPosition(lat_deg=40.0, lon_deg=-105.0, altitude_m=20000.0)
    wind = ConstantWindField(u_m_s=10.0, v_m_s=0.0)
    traj = propagate(
        initial_position=start,
        wind_field=wind,
        duration_hours=1.0,
        start_time=T0,
        step_seconds=60.0,
        output_step_seconds=300.0,
    )
    final = traj.points[-1]
    # Expected: 10 m/s × 3600 s = 36000 m = 36 km east
    east_km = _great_circle_km(start.lat_deg, start.lon_deg,
                               start.lat_deg, final.lon_deg)
    north_km = _great_circle_km(start.lat_deg, start.lon_deg,
                                final.lat_deg, start.lon_deg)
    assert east_km == pytest.approx(36.0, rel=0.005), (
        f"east displacement {east_km:.3f} km vs expected 36 km"
    )
    assert north_km < 0.01, (
        f"northward drift {north_km:.3f} km should be ~0 for pure east wind"
    )
    # Longitude should increase (eastward = +lon)
    assert final.lon_deg > start.lon_deg


def test_ten_ms_north_wind_one_hour_moves_36km_north():
    """Sister check on the v component (no cos(lat) scaling)."""
    start = GeodeticPosition(lat_deg=40.0, lon_deg=-105.0, altitude_m=20000.0)
    wind = ConstantWindField(u_m_s=0.0, v_m_s=10.0)
    traj = propagate(
        initial_position=start,
        wind_field=wind,
        duration_hours=1.0,
        start_time=T0,
    )
    final = traj.points[-1]
    north_km = _great_circle_km(start.lat_deg, start.lon_deg,
                                final.lat_deg, start.lon_deg)
    east_km = _great_circle_km(start.lat_deg, start.lon_deg,
                               start.lat_deg, final.lon_deg)
    assert north_km == pytest.approx(36.0, rel=0.005)
    assert east_km < 0.01


def test_zero_wind_keeps_position_static():
    start = GeodeticPosition(lat_deg=40.0, lon_deg=-105.0, altitude_m=20000.0)
    wind = ConstantWindField(u_m_s=0.0, v_m_s=0.0)
    traj = propagate(start, wind, duration_hours=2.0, start_time=T0)
    for p in traj.points:
        assert p.lat_deg == pytest.approx(start.lat_deg, abs=1e-9)
        assert p.lon_deg == pytest.approx(start.lon_deg, abs=1e-9)


def test_output_step_count_matches_spec():
    """1-hour duration at 5-min output step → 13 samples (t=0, 5, …, 60)."""
    start = GeodeticPosition(0.0, 0.0, 20000.0)
    wind = ConstantWindField(0.0, 0.0)
    traj = propagate(start, wind, duration_hours=1.0, start_time=T0,
                     output_step_seconds=300.0)
    assert len(traj.points) == 13
    assert traj.points[0].t_offset_s == 0.0
    assert traj.points[-1].t_offset_s == pytest.approx(3600.0)


def test_times_are_absolute_and_monotone():
    start = GeodeticPosition(0.0, 0.0, 20000.0)
    wind = ConstantWindField(5.0, 0.0)
    traj = propagate(start, wind, duration_hours=2.0, start_time=T0)
    assert traj.points[0].time == T0
    for prev, curr in zip(traj.points, traj.points[1:]):
        assert curr.time > prev.time


def test_altitude_fn_swappable():
    """altitude_fn must be honored (used to query the wind field)."""
    captured: list[float] = []

    class RecordingWind:
        def get_wind_at_altitude(self, lat, lon, altitude_m, time):
            captured.append(altitude_m)
            return (0.0, 0.0)

        def get_wind(self, lat, lon, pressure_pa, time):
            return (0.0, 0.0)

    start = GeodeticPosition(0.0, 0.0, 5000.0)
    propagate(
        initial_position=start,
        wind_field=RecordingWind(),
        duration_hours=1.0,
        start_time=T0,
        altitude_fn=lambda t: 25000.0,  # constant override
    )
    assert all(a == 25000.0 for a in captured), (
        f"expected altitude_fn=25000 m to be used; got {set(captured)}"
    )


def test_default_altitude_fn_uses_initial_altitude():
    captured: list[float] = []

    class RecordingWind:
        def get_wind_at_altitude(self, lat, lon, altitude_m, time):
            captured.append(altitude_m)
            return (0.0, 0.0)

        def get_wind(self, lat, lon, pressure_pa, time):
            return (0.0, 0.0)

    start = GeodeticPosition(0.0, 0.0, 17500.0)
    propagate(start, RecordingWind(), duration_hours=1.0, start_time=T0)
    assert all(a == 17500.0 for a in captured)


def test_naive_start_time_raises():
    start = GeodeticPosition(0.0, 0.0, 20000.0)
    with pytest.raises(ValueError, match="UTC"):
        propagate(
            start,
            ConstantWindField(0.0, 0.0),
            duration_hours=1.0,
            start_time=datetime(2026, 5, 17, 12, 0),  # naive
        )


def test_invalid_duration_raises():
    start = GeodeticPosition(0.0, 0.0, 20000.0)
    with pytest.raises(ValueError, match="duration_hours"):
        propagate(start, ConstantWindField(0.0, 0.0), 0.0, start_time=T0)


def test_longitude_wrap_at_dateline():
    """Crossing the antimeridian should produce a continuous trajectory in
    physical space, with longitudes wrapped into [−180, 180]."""
    start = GeodeticPosition(0.0, 179.5, 20000.0)
    # 50 m/s east for 1 h → ~180 km east; well past the antimeridian at the equator
    wind = ConstantWindField(u_m_s=50.0, v_m_s=0.0)
    traj = propagate(start, wind, duration_hours=1.0, start_time=T0)
    for p in traj.points:
        assert -180.0 <= p.lon_deg <= 180.0
    # The final position should be near −178.4° (= 181.6° east of start
    # = 179.5 + 1.6° at the equator since 1° ≈ 111 km)
    final = traj.points[-1]
    expected_lon_unwrapped = 179.5 + 180.0 / 111.319
    expected_lon_wrapped = ((expected_lon_unwrapped + 180) % 360) - 180
    assert final.lon_deg == pytest.approx(expected_lon_wrapped, abs=0.05)
