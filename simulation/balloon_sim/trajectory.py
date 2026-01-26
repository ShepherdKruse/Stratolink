"""
Trajectory computation for balloon simulation.

Implements the physics of wind-driven balloon movement using simple
Euler integration with proper handling of pole crossing.
"""

from dataclasses import dataclass

import numpy as np

from balloon_sim.constants import KM_PER_DEGREE_LAT
from balloon_sim.coordinates import (
    standard_to_internal,
    internal_to_standard,
    km_per_degree_lon_internal,
)
from balloon_sim.wind import WindField


@dataclass
class TrajectoryPoint:
    """A single point in a balloon trajectory."""

    lat: float  # Standard coordinates (-90 to 90)
    lon: float  # Standard coordinates (-180 to 180)
    hour: int  # Simulation hour


class TrajectoryComputer:
    """
    Computes balloon trajectories based on wind data.

    Uses simple Euler integration where balloons instantly adopt wind velocity.
    Properly handles pole crossing with correct longitude flip.
    """

    def __init__(self, wind_field: WindField):
        """
        Initialize trajectory computer with wind data.

        Args:
            wind_field: WindField instance with loaded wind data
        """
        self.wind = wind_field

    def compute_step(
        self, lat: float, lon: float, hour_index: int
    ) -> tuple[float, float]:
        """
        Compute a single trajectory step (1 hour).

        Uses internal coordinates for calculation to properly handle
        pole crossing (Bug #1 fix).

        Args:
            lat: Current latitude in standard format (-90 to 90)
            lon: Current longitude in standard format (-180 to 180)
            hour_index: Current simulation hour

        Returns:
            Tuple of (new_lat, new_lon) in standard format
        """
        # Convert to internal coordinates for calculation
        internal_lat, internal_lon = standard_to_internal(lat, lon)

        # Get wind at current position (in km/h)
        u_kmh, v_kmh = self.wind.get_wind_internal(
            internal_lat, internal_lon, hour_index
        )

        # Calculate displacement in degrees
        # v is north-south, u is east-west
        d_lat = v_kmh / KM_PER_DEGREE_LAT
        d_lon = u_kmh / km_per_degree_lon_internal(internal_lat)

        # Compute new position with proper pole handling (Bug #1 fix)
        # Using if/elif/else instead of multiple if statements
        new_internal_lat = internal_lat + d_lat
        new_internal_lon = internal_lon + d_lon

        if new_internal_lat > 180:
            # Crossing north pole: reflect latitude and flip longitude by 180
            new_internal_lat = 180 - (new_internal_lat % 180)
            new_internal_lon = (360 + new_internal_lon + 180) % 360
        elif new_internal_lat < 0:
            # Crossing south pole: reflect latitude and flip longitude by 180
            new_internal_lat = abs(new_internal_lat)
            new_internal_lon = (360 + new_internal_lon + 180) % 360
        else:
            # Normal case: just wrap longitude
            new_internal_lon = (360 + new_internal_lon) % 360

        # Convert back to standard coordinates
        return internal_to_standard(new_internal_lat, new_internal_lon)

    def compute_trajectory(
        self,
        initial_lat: float,
        initial_lon: float,
        num_steps: int,
        start_hour: int = 0,
    ) -> list[TrajectoryPoint]:
        """
        Compute a full trajectory over multiple time steps.

        Args:
            initial_lat: Starting latitude in standard format (-90 to 90)
            initial_lon: Starting longitude in standard format (-180 to 180)
            num_steps: Number of hourly steps to simulate
            start_hour: Starting hour index in the wind data (default 0)

        Returns:
            List of TrajectoryPoint objects representing the trajectory
        """
        trajectory = [TrajectoryPoint(initial_lat, initial_lon, start_hour)]

        lat, lon = initial_lat, initial_lon
        for i in range(num_steps):
            hour = start_hour + i
            lat, lon = self.compute_step(lat, lon, hour)
            trajectory.append(TrajectoryPoint(lat, lon, hour + 1))

        return trajectory

    def compute_trajectory_arrays(
        self,
        initial_lat: float,
        initial_lon: float,
        num_steps: int,
        start_hour: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute trajectory and return as numpy arrays.

        This is more efficient for large simulations and compatible
        with the original notebook's data format.

        Args:
            initial_lat: Starting latitude in standard format
            initial_lon: Starting longitude in standard format
            num_steps: Number of hourly steps to simulate
            start_hour: Starting hour index in the wind data

        Returns:
            Tuple of (latitudes, longitudes) as numpy arrays
        """
        lats = np.zeros(num_steps + 1)
        lons = np.zeros(num_steps + 1)

        lats[0] = initial_lat
        lons[0] = initial_lon

        lat, lon = initial_lat, initial_lon
        for i in range(num_steps):
            hour = start_hour + i
            lat, lon = self.compute_step(lat, lon, hour)
            lats[i + 1] = lat
            lons[i + 1] = lon

        return lats, lons
