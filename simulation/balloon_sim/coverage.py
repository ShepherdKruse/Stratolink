"""
Coverage analysis for balloon fleet simulations.

Computes the area covered by balloon sensors and provides
area-weighted coverage statistics.
"""

import numpy as np

from balloon_sim.constants import (
    DEFAULT_COVERAGE_RADIUS_KM,
    KM_PER_DEGREE_LAT,
)
from balloon_sim.coordinates import (
    standard_to_internal,
    internal_to_grid,
    km_per_degree_lon_internal,
)


class CoverageAnalyzer:
    """
    Analyzes coverage of a balloon fleet.

    Coverage is computed on a latitude-longitude grid where each cell
    can be marked as covered. The analyzer handles edge cases like
    longitude wrapping and polar regions.

    All public methods accept standard coordinates:
    - Latitude: -90 to 90 (negative=south)
    - Longitude: -180 to 180 (negative=west)
    """

    def __init__(
        self,
        coverage_radius_km: float = DEFAULT_COVERAGE_RADIUS_KM,
        grid_height: int = 180,
        grid_width: int = 360,
    ):
        """
        Initialize coverage analyzer.

        Args:
            coverage_radius_km: Sensor coverage radius in kilometers
            grid_height: Number of latitude cells in the coverage grid
            grid_width: Number of longitude cells in the coverage grid
        """
        self.coverage_radius_km = coverage_radius_km
        self.grid_height = grid_height
        self.grid_width = grid_width

        # Pre-compute area grid for weighted statistics
        self._area_grid = self._create_area_grid()

    def _create_area_grid(self) -> np.ndarray:
        """
        Create a grid of cell areas in km^2.

        Each cell's area depends on its latitude due to meridian convergence.
        """
        area_grid = np.zeros((self.grid_height, self.grid_width))

        for y in range(self.grid_height):
            # Convert grid y to internal latitude (0-180)
            # Use center of cell for more accurate area calculation
            internal_lat = (y + 0.5) * 180.0 / self.grid_height
            # Convert to standard latitude for area calculation
            standard_lat = internal_lat - 90.0

            # Cell dimensions (degrees per cell)
            lat_degrees_per_cell = 180.0 / self.grid_height
            lon_degrees_per_cell = 360.0 / self.grid_width

            # Cell size in km
            length_km = lon_degrees_per_cell * KM_PER_DEGREE_LAT * np.cos(np.deg2rad(standard_lat))
            width_km = lat_degrees_per_cell * KM_PER_DEGREE_LAT

            # Area in km^2
            area = length_km * width_km
            area_grid[y, :] = area

        return area_grid

    def create_grid(self) -> np.ndarray:
        """
        Create an empty coverage grid.

        Returns:
            Zero-filled numpy array of shape (grid_height, grid_width)
        """
        return np.zeros((self.grid_height, self.grid_width))

    def update_coverage(
        self, lat: float, lon: float, grid: np.ndarray, value: float = 1.0
    ) -> np.ndarray:
        """
        Update coverage grid for a balloon at given position.

        Bug #2 fix: Uses proper if/elif/else for grid wrapping cases.

        Args:
            lat: Balloon latitude in standard format (-90 to 90)
            lon: Balloon longitude in standard format (-180 to 180)
            grid: Coverage grid to update (modified in place)
            value: Value to write to covered cells (typically time step)

        Returns:
            The updated grid
        """
        # Convert to internal coordinates
        internal_lat, internal_lon = standard_to_internal(lat, lon)

        # Calculate coverage extent in degrees
        lat_degrees = self.coverage_radius_km / KM_PER_DEGREE_LAT
        lon_degrees = self.coverage_radius_km / km_per_degree_lon_internal(internal_lat)

        # Coverage bounds in internal coordinates
        min_lat = internal_lat - lat_degrees
        max_lat = internal_lat + lat_degrees
        min_lon = (360 + internal_lon - lon_degrees) % 360
        max_lon = (360 + internal_lon + lon_degrees) % 360

        # Convert bounds to grid indices
        # Latitude: use (grid_height - 1) to map 0-180 to indices 0-(grid_height-1)
        min_y = int(round((self.grid_height - 1) * min_lat / 180.0))
        max_y = int(round((self.grid_height - 1) * max_lat / 180.0))
        # Clamp latitude indices (they don't wrap)
        min_y = max(0, min(min_y, self.grid_height - 1))
        max_y = max(0, min(max_y, self.grid_height - 1))
        # Longitude: wraps around
        min_x = int(round(self.grid_width * min_lon / 360.0)) % self.grid_width
        max_x = int(round(self.grid_width * max_lon / 360.0)) % self.grid_width

        # Handle different wrapping cases with if/elif/else (Bug #2 fix)
        if min_x < max_x and min_y < max_y:
            # Case 1: Normal range, no wrapping
            grid[min_y:max_y, min_x:max_x] = value

        elif min_x > max_x and min_y < max_y:
            # Case 2: Longitude wraps around (crossing antimeridian)
            grid[min_y:max_y, min_x:] = value
            grid[min_y:max_y, :max_x] = value

        elif min_y > max_y and internal_lat > 90:
            # Case 3: Coverage crosses north pole
            # Fill from min_y to top of grid, all longitudes
            grid[min_y:, :] = value
            # Also fill reflected region
            grid[:max_y, :] = value

        elif min_y > max_y and internal_lat <= 90:
            # Case 4: Coverage crosses south pole
            # Fill from bottom of grid to max_y, all longitudes
            grid[:max_y, :] = value
            # Also fill reflected region
            grid[min_y:, :] = value

        elif min_x > max_x and min_y > max_y:
            # Case 5: Both longitude and latitude wrap (rare, near poles)
            # Fill all four quadrants
            grid[min_y:, min_x:] = value
            grid[min_y:, :max_x] = value
            grid[:max_y, min_x:] = value
            grid[:max_y, :max_x] = value

        return grid

    def compute_coverage_percentage(self, grid: np.ndarray) -> float:
        """
        Compute area-weighted coverage percentage.

        Args:
            grid: Coverage grid where non-zero values indicate coverage

        Returns:
            Fraction of total area covered (0 to 1)
        """
        covered_mask = (grid != 0).astype(float)
        covered_area = np.sum(covered_mask * self._area_grid)
        total_area = np.sum(self._area_grid)
        return covered_area / total_area

    def compute_coverage_by_threshold(
        self, grid: np.ndarray, threshold: float
    ) -> float:
        """
        Compute coverage percentage for cells above a threshold value.

        Useful for analyzing "coverage within last N time steps".

        Args:
            grid: Coverage grid with time step values
            threshold: Minimum value for a cell to count as covered

        Returns:
            Fraction of total area with coverage above threshold
        """
        covered_mask = (grid > threshold).astype(float)
        covered_area = np.sum(covered_mask * self._area_grid)
        total_area = np.sum(self._area_grid)
        return covered_area / total_area

    def compute_coverage_statistics(self, grid: np.ndarray) -> dict:
        """
        Compute comprehensive coverage statistics.

        Args:
            grid: Coverage grid

        Returns:
            Dictionary with coverage statistics
        """
        coverage_pct = self.compute_coverage_percentage(grid)
        non_zero = grid[grid != 0]

        stats = {
            "coverage_percentage": coverage_pct * 100,
            "total_cells": grid.size,
            "covered_cells": np.count_nonzero(grid),
            "uncovered_cells": np.sum(grid == 0),
        }

        if len(non_zero) > 0:
            stats.update(
                {
                    "min_coverage_value": float(np.min(non_zero)),
                    "max_coverage_value": float(np.max(non_zero)),
                    "mean_coverage_value": float(np.mean(non_zero)),
                }
            )

        return stats
