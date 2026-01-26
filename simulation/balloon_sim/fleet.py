"""
Fleet management for multiple balloon simulations.
"""

from typing import Optional

import numpy as np
import pandas as pd

from balloon_sim.balloon import Balloon
from balloon_sim.wind import WindField
from balloon_sim.coverage import CoverageAnalyzer


class Fleet:
    """
    Manages a collection of balloons for fleet simulation.

    All coordinates use standard format:
    - Latitude: -90 to 90 (negative=south)
    - Longitude: -180 to 180 (negative=west)
    """

    def __init__(self, balloons: Optional[list[Balloon]] = None):
        """
        Initialize a fleet with optional list of balloons.

        Args:
            balloons: Optional list of Balloon instances
        """
        self.balloons = balloons or []
        self._simulated = False

    def add_balloon(self, balloon: Balloon) -> "Fleet":
        """
        Add a balloon to the fleet.

        Args:
            balloon: Balloon instance to add

        Returns:
            Self for method chaining
        """
        self.balloons.append(balloon)
        return self

    @classmethod
    def create_random(
        cls,
        n_balloons: int,
        lat_range: tuple[float, float],
        lon_range: tuple[float, float],
        seed: Optional[int] = None,
    ) -> "Fleet":
        """
        Create a fleet with randomly positioned balloons.

        Args:
            n_balloons: Number of balloons to create
            lat_range: (min_lat, max_lat) in standard format
            lon_range: (min_lon, max_lon) in standard format
            seed: Optional random seed for reproducibility

        Returns:
            Fleet instance with randomly positioned balloons
        """
        if seed is not None:
            np.random.seed(seed)

        balloons = []
        for i in range(n_balloons):
            lat = np.random.uniform(lat_range[0], lat_range[1])
            lon = np.random.uniform(lon_range[0], lon_range[1])
            balloon = Balloon(lat=lat, lon=lon, balloon_id=f"B{i:03d}")
            balloons.append(balloon)

        return cls(balloons)

    @classmethod
    def create_grid(
        cls,
        lat_range: tuple[float, float],
        lon_range: tuple[float, float],
        lat_spacing: float,
        lon_spacing: float,
    ) -> "Fleet":
        """
        Create a fleet with balloons arranged in a grid pattern.

        Args:
            lat_range: (min_lat, max_lat) in standard format
            lon_range: (min_lon, max_lon) in standard format
            lat_spacing: Degrees between balloons in latitude
            lon_spacing: Degrees between balloons in longitude

        Returns:
            Fleet instance with grid-positioned balloons
        """
        balloons = []
        balloon_id = 0

        lat = lat_range[0]
        while lat <= lat_range[1]:
            lon = lon_range[0]
            while lon <= lon_range[1]:
                balloon = Balloon(lat=lat, lon=lon, balloon_id=f"B{balloon_id:03d}")
                balloons.append(balloon)
                balloon_id += 1
                lon += lon_spacing
            lat += lat_spacing

        return cls(balloons)

    def simulate(
        self,
        wind: WindField,
        num_steps: int,
        start_hours: Optional[list[int]] = None,
    ) -> "Fleet":
        """
        Simulate all balloons in the fleet.

        Args:
            wind: WindField instance with loaded wind data
            num_steps: Number of hourly steps to simulate
            start_hours: Optional list of start hours for each balloon.
                        If None, all balloons start at hour 0.

        Returns:
            Self for method chaining
        """
        if start_hours is None:
            start_hours = [0] * len(self.balloons)
        elif len(start_hours) != len(self.balloons):
            raise ValueError(
                f"start_hours length ({len(start_hours)}) must match "
                f"number of balloons ({len(self.balloons)})"
            )

        for balloon, start_hour in zip(self.balloons, start_hours):
            balloon.simulate(wind, num_steps, start_hour)

        self._simulated = True
        return self

    def to_dataframe(self) -> pd.DataFrame:
        """
        Export all trajectories as a single DataFrame.

        Returns:
            DataFrame with columns: lat, lon, time, balloon_id
        """
        if not self._simulated:
            raise RuntimeError(
                "Fleet has not been simulated yet. Call simulate() first."
            )

        dfs = [balloon.to_dataframe() for balloon in self.balloons]
        return pd.concat(dfs, ignore_index=True)

    def compute_coverage(
        self, analyzer: CoverageAnalyzer, time_step: Optional[int] = None
    ) -> np.ndarray:
        """
        Compute coverage grid for the fleet.

        Args:
            analyzer: CoverageAnalyzer instance
            time_step: If provided, compute coverage at a specific time step.
                      If None, compute cumulative coverage over all time steps.

        Returns:
            Coverage grid as numpy array
        """
        if not self._simulated:
            raise RuntimeError(
                "Fleet has not been simulated yet. Call simulate() first."
            )

        grid = analyzer.create_grid()

        for balloon in self.balloons:
            if time_step is not None:
                # Single time step
                if time_step < len(balloon.lats):
                    analyzer.update_coverage(
                        balloon.lats[time_step],
                        balloon.lons[time_step],
                        grid,
                        time_step,
                    )
            else:
                # All time steps
                for i, (lat, lon) in enumerate(zip(balloon.lats, balloon.lons)):
                    analyzer.update_coverage(lat, lon, grid, i)

        return grid

    def __len__(self) -> int:
        """Return number of balloons in fleet."""
        return len(self.balloons)

    def __iter__(self):
        """Iterate over balloons."""
        return iter(self.balloons)

    def __getitem__(self, index) -> Balloon:
        """Get balloon by index."""
        return self.balloons[index]
