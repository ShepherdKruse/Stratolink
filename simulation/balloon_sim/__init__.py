"""
Stratospheric Balloon Simulation Package

A modular package for simulating stratospheric balloon trajectories
driven by wind data, with coverage analysis and visualization tools.
"""

from balloon_sim.constants import (
    EARTH_RADIUS_KM,
    KM_PER_DEGREE_LAT,
    MS_TO_KMH,
    DEFAULT_COVERAGE_RADIUS_KM,
    DEFAULT_PRESSURE_LEVEL,
)
from balloon_sim.coordinates import (
    standard_to_grid,
    grid_to_standard,
    km_per_degree_lon,
)
from balloon_sim.wind import WindField, download_ncep_data
from balloon_sim.trajectory import TrajectoryComputer
from balloon_sim.balloon import Balloon
from balloon_sim.fleet import Fleet
from balloon_sim.coverage import CoverageAnalyzer

__all__ = [
    # Constants
    "EARTH_RADIUS_KM",
    "KM_PER_DEGREE_LAT",
    "MS_TO_KMH",
    "DEFAULT_COVERAGE_RADIUS_KM",
    "DEFAULT_PRESSURE_LEVEL",
    # Coordinates
    "standard_to_grid",
    "grid_to_standard",
    "km_per_degree_lon",
    # Core classes
    "WindField",
    "TrajectoryComputer",
    "Balloon",
    "Fleet",
    "CoverageAnalyzer",
    # Utilities
    "download_ncep_data",
]

__version__ = "0.1.0"
