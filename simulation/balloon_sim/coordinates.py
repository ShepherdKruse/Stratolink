"""
Coordinate transformation utilities.

The simulation internally uses a grid coordinate system where:
- Latitude: 0-180 (0=south pole, 90=equator, 180=north pole)
- Longitude: 0-360

The public API uses standard geographic coordinates:
- Latitude: -90 to 90 (negative=south, positive=north)
- Longitude: -180 to 180 (negative=west, positive=east)

This module provides conversion functions between these systems.
"""

import numpy as np

from balloon_sim.constants import KM_PER_DEGREE_LAT


def standard_to_internal(lat: float, lon: float) -> tuple[float, float]:
    """
    Convert standard coordinates to internal simulation coordinates.

    Args:
        lat: Latitude in standard format (-90 to 90)
        lon: Longitude in standard format (-180 to 180)

    Returns:
        Tuple of (internal_lat, internal_lon) where:
        - internal_lat is in range 0-180
        - internal_lon is in range 0-360
    """
    internal_lat = lat + 90.0
    internal_lon = (lon + 360.0) % 360.0
    return internal_lat, internal_lon


def internal_to_standard(lat: float, lon: float) -> tuple[float, float]:
    """
    Convert internal simulation coordinates to standard coordinates.

    Args:
        lat: Latitude in internal format (0 to 180)
        lon: Longitude in internal format (0 to 360)

    Returns:
        Tuple of (standard_lat, standard_lon) where:
        - standard_lat is in range -90 to 90
        - standard_lon is in range -180 to 180
    """
    standard_lat = lat - 90.0
    # Internal 0-180 maps to standard 0-180
    # Internal 180-360 maps to standard -180 to 0
    if lon > 180.0:
        standard_lon = lon - 360.0
    else:
        standard_lon = lon
    return standard_lat, standard_lon


def standard_to_grid(
    lat: float, lon: float, grid_height: int, grid_width: int
) -> tuple[int, int]:
    """
    Convert standard coordinates to grid indices.

    Uses rounding instead of truncation for better accuracy (Bug #4 fix).

    Args:
        lat: Latitude in standard format (-90 to 90)
        lon: Longitude in standard format (-180 to 180)
        grid_height: Number of latitude points in the grid
        grid_width: Number of longitude points in the grid

    Returns:
        Tuple of (y, x) grid indices
    """
    internal_lat, internal_lon = standard_to_internal(lat, lon)
    return internal_to_grid(internal_lat, internal_lon, grid_height, grid_width)


def grid_to_standard(
    y: int, x: int, grid_height: int, grid_width: int
) -> tuple[float, float]:
    """
    Convert grid indices to standard coordinates.

    Args:
        y: Latitude grid index
        x: Longitude grid index
        grid_height: Number of latitude points in the grid
        grid_width: Number of longitude points in the grid

    Returns:
        Tuple of (lat, lon) in standard format
    """
    internal_lat, internal_lon = grid_to_internal(y, x, grid_height, grid_width)
    return internal_to_standard(internal_lat, internal_lon)


def internal_to_grid(
    lat: float, lon: float, grid_height: int, grid_width: int
) -> tuple[int, int]:
    """
    Convert internal coordinates to grid indices.

    Uses rounding instead of truncation for better accuracy (Bug #4 fix).
    Uses (grid_height - 1) for latitude to avoid pole mapping bug.

    Args:
        lat: Latitude in internal format (0 to 180)
        lon: Longitude in internal format (0 to 360)
        grid_height: Number of latitude points in the grid
        grid_width: Number of longitude points in the grid

    Returns:
        Tuple of (y, x) grid indices
    """
    # Latitude: map 0-180 to indices 0 to (grid_height-1)
    # No modulo - latitude doesn't wrap (poles are distinct)
    y = round((grid_height - 1) * lat / 180.0)
    y = max(0, min(y, grid_height - 1))  # Clamp to valid range

    # Longitude: map 0-360 to indices 0 to (grid_width-1), with wrapping
    x = round((grid_width * lon / 360.0)) % grid_width
    return int(y), int(x)


def grid_to_internal(
    y: int, x: int, grid_height: int, grid_width: int
) -> tuple[float, float]:
    """
    Convert grid indices to internal coordinates.

    Args:
        y: Latitude grid index
        x: Longitude grid index
        grid_height: Number of latitude points in the grid
        grid_width: Number of longitude points in the grid

    Returns:
        Tuple of (lat, lon) in internal format (0-180, 0-360)
    """
    # Latitude: indices 0 to (grid_height-1) map to 0-180
    internal_lat = 180.0 * y / (grid_height - 1) if grid_height > 1 else 90.0

    # Longitude: indices 0 to (grid_width-1) map to 0 to <360
    internal_lon = 360.0 * x / grid_width
    return internal_lat, internal_lon


def km_per_degree_lon(lat: float) -> float:
    """
    Calculate kilometers per degree of longitude at a given latitude.

    Longitude degrees become smaller toward the poles due to convergence.

    Args:
        lat: Latitude in standard format (-90 to 90)

    Returns:
        Kilometers per degree of longitude at the given latitude
    """
    return KM_PER_DEGREE_LAT * np.cos(np.deg2rad(lat))


def km_per_degree_lon_internal(lat: float) -> float:
    """
    Calculate kilometers per degree of longitude at a given internal latitude.

    Args:
        lat: Latitude in internal format (0 to 180, where 90 is equator)

    Returns:
        Kilometers per degree of longitude at the given latitude
    """
    # Convert internal lat to standard for cosine calculation
    standard_lat = lat - 90.0
    return KM_PER_DEGREE_LAT * np.cos(np.deg2rad(standard_lat))
