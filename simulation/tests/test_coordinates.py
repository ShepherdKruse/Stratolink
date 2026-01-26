"""Tests for coordinate transformation functions."""

import pytest
import numpy as np

from balloon_sim.coordinates import (
    standard_to_internal,
    internal_to_standard,
    standard_to_grid,
    grid_to_standard,
    internal_to_grid,
    km_per_degree_lon,
    km_per_degree_lon_internal,
)
from balloon_sim.constants import KM_PER_DEGREE_LAT


class TestCoordinateConversions:
    """Test coordinate conversion between standard and internal formats."""

    def test_standard_to_internal_equator(self):
        """Equator should convert to internal lat 90."""
        lat, lon = standard_to_internal(0.0, 0.0)
        assert lat == 90.0
        assert lon == 0.0

    def test_standard_to_internal_north_pole(self):
        """North pole (90) should convert to internal lat 180."""
        lat, lon = standard_to_internal(90.0, 0.0)
        assert lat == 180.0
        assert lon == 0.0

    def test_standard_to_internal_south_pole(self):
        """South pole (-90) should convert to internal lat 0."""
        lat, lon = standard_to_internal(-90.0, 0.0)
        assert lat == 0.0
        assert lon == 0.0

    def test_standard_to_internal_negative_lon(self):
        """Negative longitude should wrap to positive."""
        lat, lon = standard_to_internal(0.0, -90.0)
        assert lat == 90.0
        assert lon == 270.0

    def test_internal_to_standard_roundtrip(self):
        """Converting back and forth should preserve values."""
        test_cases = [
            (45.0, 90.0),
            (-45.0, -90.0),
            (0.0, 180.0),
            (89.0, -179.0),
            (-89.0, 179.0),
        ]
        for std_lat, std_lon in test_cases:
            int_lat, int_lon = standard_to_internal(std_lat, std_lon)
            result_lat, result_lon = internal_to_standard(int_lat, int_lon)
            assert abs(result_lat - std_lat) < 1e-10
            assert abs(result_lon - std_lon) < 1e-10


class TestGridConversions:
    """Test grid coordinate conversions."""

    def test_standard_to_grid_center(self):
        """Center of grid should be equator, prime meridian."""
        # Grid with 180 lat points and 360 lon points
        y, x = standard_to_grid(0.0, 0.0, 180, 360)
        assert y == 90  # Middle of latitude
        assert x == 0  # Prime meridian

    def test_standard_to_grid_rounding(self):
        """Grid conversion should use rounding, not truncation (Bug #4 fix)."""
        # Value that would truncate to 44 but should round to 45
        y, x = standard_to_grid(0.0, 44.9, 180, 360)
        # 44.9 degrees should round to grid index 45
        assert x == 45

        # Value that would truncate to 44 but should round to 45
        y, x = standard_to_grid(-44.6, 0.0, 180, 360)
        # Standard lat -44.6 -> internal 45.4 -> grid y = round(45.4 * 180/180) = 45
        assert y == 45

    def test_grid_to_standard_roundtrip(self):
        """Converting grid coords back should give approximate original values."""
        grid_height, grid_width = 180, 360

        # Test several grid positions
        test_points = [(90, 180), (45, 90), (135, 270), (0, 0), (179, 359)]
        for y, x in test_points:
            lat, lon = grid_to_standard(y, x, grid_height, grid_width)
            y2, x2 = standard_to_grid(lat, lon, grid_height, grid_width)
            # Allow small error due to discretization
            assert abs(y2 - y) <= 1
            assert abs(x2 - x) <= 1


class TestKmPerDegreeLon:
    """Test longitude scaling calculation."""

    def test_km_per_degree_lon_equator(self):
        """At equator, lon degrees should equal lat degrees."""
        km = km_per_degree_lon(0.0)
        assert abs(km - KM_PER_DEGREE_LAT) < 0.01

    def test_km_per_degree_lon_poles(self):
        """At poles, lon degrees should approach zero."""
        km_north = km_per_degree_lon(90.0)
        km_south = km_per_degree_lon(-90.0)
        assert km_north < 0.01
        assert km_south < 0.01

    def test_km_per_degree_lon_midlatitude(self):
        """At 60 degrees, lon should be half the equator value."""
        km = km_per_degree_lon(60.0)
        expected = KM_PER_DEGREE_LAT * 0.5  # cos(60) = 0.5
        assert abs(km - expected) < 0.01

    def test_km_per_degree_lon_internal(self):
        """Internal coordinate version should give same results."""
        # Internal lat 135 = standard lat 45
        km_internal = km_per_degree_lon_internal(135.0)
        km_standard = km_per_degree_lon(45.0)
        assert abs(km_internal - km_standard) < 0.01
