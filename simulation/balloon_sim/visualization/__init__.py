"""
Visualization subpackage for balloon simulation.

Provides plotting and animation utilities using cartopy and matplotlib.
"""

from balloon_sim.visualization.plots import (
    plot_trajectories,
    plot_coverage,
    plot_wind_field,
    plot_coverage_timeseries,
)
from balloon_sim.visualization.animation import (
    create_trajectory_animation,
    create_trajectory_animation_parallel,
    create_coverage_animation,
)
from balloon_sim.visualization.kepler import (
    create_kepler_trajectory_map,
    export_kepler_html,
)

__all__ = [
    "plot_trajectories",
    "plot_coverage",
    "plot_wind_field",
    "plot_coverage_timeseries",
    "create_trajectory_animation",
    "create_trajectory_animation_parallel",
    "create_coverage_animation",
    "create_kepler_trajectory_map",
    "export_kepler_html",
]
