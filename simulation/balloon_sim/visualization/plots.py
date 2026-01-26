"""
Static plotting utilities for balloon simulation.

Uses cartopy for map projections and matplotlib for rendering.
"""

from typing import Optional, Union

import numpy as np
import matplotlib.pyplot as plt

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False

from balloon_sim.fleet import Fleet
from balloon_sim.balloon import Balloon
from balloon_sim.coverage import CoverageAnalyzer


def _check_cartopy():
    """Raise error if cartopy is not installed."""
    if not HAS_CARTOPY:
        raise ImportError(
            "cartopy is required for visualization. "
            "Install with: pip install cartopy"
        )


def plot_trajectories(
    fleet_or_balloon: Union[Fleet, Balloon],
    projection: str = "robinson",
    figsize: tuple[int, int] = (12, 8),
    title: Optional[str] = None,
    color: str = "gray",
    marker_size: float = 1.0,
    show_coastlines: bool = True,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """
    Plot balloon trajectories on a map.

    Args:
        fleet_or_balloon: Fleet or single Balloon to plot
        projection: Map projection ('robinson', 'platecarree', 'mollweide')
        figsize: Figure size in inches
        title: Optional title for the plot
        color: Trajectory color
        marker_size: Size of trajectory points
        show_coastlines: Whether to show coastlines
        ax: Optional existing axes to plot on

    Returns:
        matplotlib Figure object
    """
    _check_cartopy()

    # Get projection
    projections = {
        "robinson": ccrs.Robinson(),
        "platecarree": ccrs.PlateCarree(),
        "mollweide": ccrs.Mollweide(),
        "orthographic": ccrs.Orthographic(),
    }
    proj = projections.get(projection.lower(), ccrs.Robinson())

    # Create figure if needed
    if ax is None:
        fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": proj})
    else:
        fig = ax.get_figure()

    # Set up map
    ax.set_global()
    if show_coastlines:
        ax.coastlines(color="white", linewidth=0.5)
        ax.add_feature(cfeature.LAND, facecolor="lightgray")
        ax.add_feature(cfeature.OCEAN, facecolor="lightblue")

    # Plot trajectories
    if isinstance(fleet_or_balloon, Balloon):
        balloons = [fleet_or_balloon]
    else:
        balloons = fleet_or_balloon.balloons

    for balloon in balloons:
        ax.scatter(
            balloon.lons,
            balloon.lats,
            s=marker_size,
            c=color,
            transform=ccrs.PlateCarree(),
            zorder=10,
        )

    if title:
        ax.set_title(title)

    return fig


def plot_coverage(
    coverage_grid: np.ndarray,
    analyzer: Optional[CoverageAnalyzer] = None,
    projection: str = "robinson",
    figsize: tuple[int, int] = (12, 8),
    title: Optional[str] = None,
    cmap: str = "viridis",
    show_coastlines: bool = True,
    colorbar: bool = True,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """
    Plot coverage grid on a map.

    Args:
        coverage_grid: 2D numpy array of coverage values
        analyzer: Optional CoverageAnalyzer for computing statistics
        projection: Map projection
        figsize: Figure size in inches
        title: Optional title (if None and analyzer provided, shows coverage %)
        cmap: Colormap name
        show_coastlines: Whether to show coastlines
        colorbar: Whether to show colorbar
        ax: Optional existing axes to plot on

    Returns:
        matplotlib Figure object
    """
    _check_cartopy()

    # Get projection
    projections = {
        "robinson": ccrs.Robinson(),
        "platecarree": ccrs.PlateCarree(),
        "mollweide": ccrs.Mollweide(),
    }
    proj = projections.get(projection.lower(), ccrs.Robinson())

    # Create figure if needed
    if ax is None:
        fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": proj})
    else:
        fig = ax.get_figure()

    # Set up map
    ax.set_global()

    # Plot coverage
    # Transform grid to proper extent (-180 to 180, -90 to 90)
    img_extent = [-180, 180, -90, 90]
    im = ax.imshow(
        coverage_grid,
        transform=ccrs.PlateCarree(),
        extent=img_extent,
        origin="lower",
        cmap=cmap,
        zorder=2,
    )

    if show_coastlines:
        ax.coastlines(color="white", linewidth=0.5, zorder=3)

    if colorbar:
        plt.colorbar(im, ax=ax, orientation="horizontal", pad=0.05, shrink=0.8)

    # Set title
    if title:
        ax.set_title(title)
    elif analyzer is not None:
        coverage_pct = analyzer.compute_coverage_percentage(coverage_grid) * 100
        ax.set_title(f"Coverage: {coverage_pct:.1f}%")

    return fig


def plot_wind_field(
    u: np.ndarray,
    v: np.ndarray,
    time_index: int = 0,
    projection: str = "platecarree",
    figsize: tuple[int, int] = (14, 8),
    title: Optional[str] = None,
    stride: int = 3,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """
    Plot wind field as arrows/quiver plot.

    Args:
        u: U-component wind array (east-west, shape: time x lat x lon)
        v: V-component wind array (north-south)
        time_index: Time index to plot
        projection: Map projection
        figsize: Figure size in inches
        title: Optional title
        stride: Subsample factor for arrows (higher = fewer arrows)
        ax: Optional existing axes

    Returns:
        matplotlib Figure object
    """
    _check_cartopy()

    proj = ccrs.PlateCarree() if projection == "platecarree" else ccrs.Robinson()

    if ax is None:
        fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": proj})
    else:
        fig = ax.get_figure()

    ax.set_global()
    ax.coastlines()
    ax.add_feature(cfeature.LAND, facecolor="lightgray", alpha=0.5)

    # Create coordinate grids
    lat_count, lon_count = u.shape[1], u.shape[2]
    lons = np.linspace(-180, 180, lon_count)
    lats = np.linspace(-90, 90, lat_count)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    # Subsample for readability
    u_plot = u[time_index, ::stride, ::stride]
    v_plot = v[time_index, ::stride, ::stride]
    lon_plot = lon_grid[::stride, ::stride]
    lat_plot = lat_grid[::stride, ::stride]

    # Plot quiver
    speed = np.sqrt(u_plot**2 + v_plot**2)
    q = ax.quiver(
        lon_plot,
        lat_plot,
        u_plot,
        v_plot,
        speed,
        transform=ccrs.PlateCarree(),
        cmap="coolwarm",
        alpha=0.8,
    )
    plt.colorbar(q, ax=ax, label="Wind Speed (m/s)", shrink=0.6)

    if title:
        ax.set_title(title)
    else:
        ax.set_title(f"Wind Field at Time Index {time_index}")

    return fig


def plot_coverage_timeseries(
    coverage_values: list[float],
    time_hours: Optional[list[float]] = None,
    figsize: tuple[int, int] = (10, 6),
    title: str = "Coverage Over Time",
    xlabel: str = "Time (hours)",
    ylabel: str = "Coverage (%)",
) -> plt.Figure:
    """
    Plot coverage percentage over time.

    Args:
        coverage_values: List of coverage percentages
        time_hours: Optional time values (hours)
        figsize: Figure size
        title: Plot title
        xlabel: X-axis label
        ylabel: Y-axis label

    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    if time_hours is None:
        time_hours = list(range(len(coverage_values)))

    ax.plot(time_hours, coverage_values, linewidth=2)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    return fig
