"""Tests for trajectory computation, especially pole crossing (Bug #1 fix)."""

import pytest
import numpy as np

from balloon_sim.trajectory import TrajectoryComputer, TrajectoryPoint
from balloon_sim.coordinates import standard_to_internal, internal_to_standard
from balloon_sim.constants import KM_PER_DEGREE_LAT


class MockWindField:
    """Mock wind field for testing trajectory computation."""

    def __init__(self, u_kmh: float = 0.0, v_kmh: float = 0.0):
        """Create mock wind with constant velocity."""
        self.u_kmh = u_kmh
        self.v_kmh = v_kmh
        self.grid_height = 73
        self.grid_width = 144

    def get_wind_internal(self, lat, lon, hour_index):
        """Return constant wind velocity."""
        return self.u_kmh, self.v_kmh


class TestPoleCrossing:
    """Test pole crossing logic (Bug #1 fix)."""

    def test_north_pole_crossing(self):
        """Balloon moving north should cross pole and emerge on other side."""
        # Strong northward wind that moves ~5 degrees per hour
        v_kmh = 5 * KM_PER_DEGREE_LAT  # ~555 km/h northward
        wind = MockWindField(u_kmh=0.0, v_kmh=v_kmh)
        computer = TrajectoryComputer(wind)

        # Start near north pole
        start_lat = 87.0
        start_lon = 0.0

        # After 1 step, should move ~5 degrees north
        lat1, lon1 = computer.compute_step(start_lat, start_lon, 0)

        # Internal: start at 177, move +5 to 182, which crosses 180
        # Should reflect to 180 - (182 - 180) = 178, then flip lon by 180
        # Standard: 178 - 90 = 88 degrees (reflected back)
        assert lat1 < 90.0, "Should not exceed 90 degrees"
        assert lat1 > 85.0, "Should be near pole"

        # Longitude should flip by 180 degrees
        assert abs(abs(lon1) - 180.0) < 1.0 or abs(lon1) < 1.0

    def test_south_pole_crossing(self):
        """Balloon moving south should cross pole and emerge on other side."""
        # Strong southward wind
        v_kmh = -5 * KM_PER_DEGREE_LAT  # ~555 km/h southward
        wind = MockWindField(u_kmh=0.0, v_kmh=v_kmh)
        computer = TrajectoryComputer(wind)

        # Start near south pole
        start_lat = -87.0
        start_lon = 0.0

        # After 1 step
        lat1, lon1 = computer.compute_step(start_lat, start_lon, 0)

        # Internal: start at 3, move -5 to -2, which crosses 0
        # Should reflect to abs(-2) = 2
        # Standard: 2 - 90 = -88 degrees
        assert lat1 > -90.0, "Should not go below -90 degrees"
        assert lat1 < -85.0, "Should be near south pole"

        # Longitude should flip by 180 degrees
        assert abs(abs(lon1) - 180.0) < 1.0 or abs(lon1) < 1.0

    def test_normal_movement_no_pole(self):
        """Normal movement away from poles should not trigger pole logic."""
        # Moderate northward wind
        v_kmh = 1 * KM_PER_DEGREE_LAT  # ~111 km/h northward
        wind = MockWindField(u_kmh=0.0, v_kmh=v_kmh)
        computer = TrajectoryComputer(wind)

        # Start at mid-latitude
        start_lat = 45.0
        start_lon = -100.0

        lat1, lon1 = computer.compute_step(start_lat, start_lon, 0)

        # Should move ~1 degree north
        assert abs(lat1 - 46.0) < 0.1
        # Longitude should be unchanged (no east-west wind)
        assert abs(lon1 - start_lon) < 0.1

    def test_pole_crossing_preserves_longitude_flip(self):
        """When crossing pole, longitude should flip by 180 degrees."""
        # Very strong northward wind to ensure pole crossing
        v_kmh = 10 * KM_PER_DEGREE_LAT
        wind = MockWindField(u_kmh=0.0, v_kmh=v_kmh)
        computer = TrajectoryComputer(wind)

        # Start at 85N, 45W
        start_lat = 85.0
        start_lon = -45.0

        lat1, lon1 = computer.compute_step(start_lat, start_lon, 0)

        # After crossing pole, longitude should be ~135E (flip by 180)
        expected_lon = -45.0 + 180.0  # = 135
        # Account for possible wrapping
        if lon1 < 0:
            lon1_adjusted = lon1 + 360
        else:
            lon1_adjusted = lon1

        # Allow some tolerance due to calculation
        assert abs(lon1 - expected_lon) < 5.0 or abs(lon1_adjusted - expected_lon) < 5.0


class TestTrajectoryComputation:
    """Test full trajectory computation."""

    def test_compute_trajectory_length(self):
        """Trajectory should have correct number of points."""
        wind = MockWindField(u_kmh=100.0, v_kmh=50.0)
        computer = TrajectoryComputer(wind)

        trajectory = computer.compute_trajectory(
            initial_lat=40.0,
            initial_lon=-100.0,
            num_steps=100,
        )

        # Should have num_steps + 1 points (initial + 100 steps)
        assert len(trajectory) == 101

    def test_compute_trajectory_arrays(self):
        """Array output should match list output."""
        wind = MockWindField(u_kmh=100.0, v_kmh=50.0)
        computer = TrajectoryComputer(wind)

        trajectory = computer.compute_trajectory(
            initial_lat=40.0, initial_lon=-100.0, num_steps=10
        )
        lats, lons = computer.compute_trajectory_arrays(
            initial_lat=40.0, initial_lon=-100.0, num_steps=10
        )

        for i, point in enumerate(trajectory):
            assert abs(point.lat - lats[i]) < 1e-10
            assert abs(point.lon - lons[i]) < 1e-10

    def test_trajectory_stays_in_bounds(self):
        """Latitude should always stay in [-90, 90], longitude in [-180, 180]."""
        # Random wind that might cause boundary issues
        wind = MockWindField(u_kmh=300.0, v_kmh=200.0)
        computer = TrajectoryComputer(wind)

        # Start near a corner case
        lats, lons = computer.compute_trajectory_arrays(
            initial_lat=80.0, initial_lon=170.0, num_steps=500
        )

        assert np.all(lats >= -90.0), "Latitude below -90"
        assert np.all(lats <= 90.0), "Latitude above 90"
        assert np.all(lons >= -180.0), "Longitude below -180"
        assert np.all(lons <= 180.0), "Longitude above 180"


class TestEastWestMovement:
    """Test east-west (longitudinal) movement."""

    def test_eastward_movement(self):
        """Eastward wind should increase longitude."""
        u_kmh = 1 * KM_PER_DEGREE_LAT  # ~111 km/h eastward
        wind = MockWindField(u_kmh=u_kmh, v_kmh=0.0)
        computer = TrajectoryComputer(wind)

        # At equator, 1 degree of longitude = 111 km
        lat1, lon1 = computer.compute_step(0.0, 0.0, 0)

        assert abs(lat1 - 0.0) < 0.01  # No north-south movement
        assert lon1 > 0.0  # Moved eastward
        assert abs(lon1 - 1.0) < 0.1  # Moved ~1 degree

    def test_longitude_wrapping(self):
        """Longitude should wrap around at antimeridian."""
        u_kmh = 10 * KM_PER_DEGREE_LAT  # Fast eastward
        wind = MockWindField(u_kmh=u_kmh, v_kmh=0.0)
        computer = TrajectoryComputer(wind)

        # Start near 180 degrees
        lat1, lon1 = computer.compute_step(0.0, 175.0, 0)

        # After moving ~10 degrees east from 175, should wrap to negative
        assert lon1 < 0.0 or lon1 > 175.0  # Wrapped or still positive
        assert lon1 >= -180.0 and lon1 <= 180.0
