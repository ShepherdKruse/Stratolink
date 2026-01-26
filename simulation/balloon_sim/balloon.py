"""
Balloon class for individual balloon simulation.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from balloon_sim.wind import WindField
from balloon_sim.trajectory import TrajectoryComputer


@dataclass
class Balloon:
    """
    Represents a single stratospheric balloon.

    All coordinates use standard format:
    - Latitude: -90 to 90 (negative=south)
    - Longitude: -180 to 180 (negative=west)

    Attributes:
        lat: Initial latitude in standard format
        lon: Initial longitude in standard format
        balloon_id: Optional identifier string
        lats: Array of latitude values after simulation
        lons: Array of longitude values after simulation
        times: Array of time values after simulation
    """

    lat: float
    lon: float
    balloon_id: Optional[str] = None
    lats: np.ndarray = field(default_factory=lambda: np.array([]))
    lons: np.ndarray = field(default_factory=lambda: np.array([]))
    times: np.ndarray = field(default_factory=lambda: np.array([]))
    _simulated: bool = field(default=False, repr=False)

    def simulate(
        self,
        wind: WindField,
        num_steps: int,
        start_hour: int = 0,
    ) -> "Balloon":
        """
        Simulate the balloon trajectory.

        Args:
            wind: WindField instance with loaded wind data
            num_steps: Number of hourly steps to simulate
            start_hour: Starting hour index in the wind data (default 0)

        Returns:
            Self for method chaining
        """
        computer = TrajectoryComputer(wind)
        self.lats, self.lons = computer.compute_trajectory_arrays(
            self.lat, self.lon, num_steps, start_hour
        )

        # Create time array based on wind data times
        if start_hour + num_steps < len(wind.times) * 6:
            # Map simulation hours to wind data times
            time_indices = np.arange(start_hour, start_hour + num_steps + 1) // 6
            time_indices = np.clip(time_indices, 0, len(wind.times) - 1)
            self.times = wind.times[time_indices]
        else:
            # Generate simple hour indices if we exceed wind data
            self.times = np.arange(start_hour, start_hour + num_steps + 1)

        self._simulated = True
        return self

    def to_dataframe(self) -> pd.DataFrame:
        """
        Export trajectory as a pandas DataFrame.

        Returns:
            DataFrame with columns: lat, lon, time, and optionally balloon_id
        """
        if not self._simulated:
            raise RuntimeError(
                "Balloon has not been simulated yet. Call simulate() first."
            )

        data = {
            "lat": self.lats,
            "lon": self.lons,
            "time": self.times,
        }

        if self.balloon_id is not None:
            data["balloon_id"] = self.balloon_id

        return pd.DataFrame(data)

    @property
    def trajectory(self) -> list[tuple[float, float]]:
        """Return trajectory as list of (lat, lon) tuples."""
        if not self._simulated:
            raise RuntimeError(
                "Balloon has not been simulated yet. Call simulate() first."
            )
        return list(zip(self.lats, self.lons))
