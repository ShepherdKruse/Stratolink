"""
Animation utilities for balloon simulation.

Creates animated visualizations of balloon trajectories and coverage.
"""

from typing import Optional, Union

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.patches import Polygon

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False

from balloon_sim.fleet import Fleet
from balloon_sim.balloon import Balloon
from balloon_sim.coverage import CoverageAnalyzer
from balloon_sim.constants import DEFAULT_COVERAGE_RADIUS_KM, KM_PER_DEGREE_LAT


def _compute_coverage_circle(lat: float, lon: float, radius_km: float, n_points: int = 48) -> np.ndarray:
    """
    Compute geodesic circle points around a location.

    Args:
        lat: Center latitude in degrees (-90 to 90)
        lon: Center longitude in degrees (-180 to 180 or 0 to 360)
        radius_km: Radius in kilometers
        n_points: Number of points to generate around the circle

    Returns:
        Array of shape (n_points, 2) with [lon, lat] coordinates
    """
    angles = np.linspace(0, 2 * np.pi, n_points, endpoint=False)

    # Radius in degrees
    lat_radius = radius_km / KM_PER_DEGREE_LAT

    # Longitude radius varies with latitude (smaller near poles)
    # Clamp latitude to avoid division issues at exact poles
    clamped_lat = np.clip(lat, -89.9, 89.9)
    lon_radius = radius_km / (KM_PER_DEGREE_LAT * np.cos(np.deg2rad(clamped_lat)))

    # Generate circle points
    circle_lats = lat + lat_radius * np.sin(angles)
    circle_lons = lon + lon_radius * np.cos(angles)

    # Clamp latitudes to valid range
    circle_lats = np.clip(circle_lats, -90, 90)

    return np.column_stack([circle_lons, circle_lats])


def _check_cartopy():
    """Raise error if cartopy is not installed."""
    if not HAS_CARTOPY:
        raise ImportError(
            "cartopy is required for visualization. "
            "Install with: pip install cartopy"
        )


def create_trajectory_animation(
    fleet_or_balloon: Union[Fleet, Balloon],
    wind_field=None,
    projection: str = "platecarree",
    figsize: tuple[int, int] = (14, 8),
    interval: int = 50,
    trail_length: int = 20,
    save_path: Optional[str] = None,
    dpi: int = 150,
    fps: int = 30,
    show_wind: bool = False,
    wind_style: str = "quiver",
    wind_density: float = 1.0,
    wind_stride: int = 4,
    arrow_scale: float = 0.3,
    title_template: str = "Hour: {hour}",
    frame_step: int = 1,
    show_coverage: bool = False,
    coverage_radius_km: Optional[float] = None,
    coverage_alpha: float = 0.15,
) -> animation.FuncAnimation:
    """
    Create animated trajectory visualization with optional wind vectors.

    Args:
        fleet_or_balloon: Fleet or single Balloon to animate
        wind_field: Optional WindField instance for displaying wind vectors
        projection: Map projection ('platecarree', 'robinson', 'mollweide')
        figsize: Figure size in inches
        interval: Milliseconds between frames
        trail_length: Number of previous positions to show as trail
        save_path: Optional path to save animation (e.g., 'output.mp4')
        dpi: Resolution for saved animation
        fps: Frames per second for saved video
        show_wind: Whether to display wind (requires wind_field)
        wind_style: 'quiver' (arrows, default) or 'streamlines'
        wind_density: Density of streamlines (default 1.0)
        wind_stride: Subsample factor for wind display (higher = fewer arrows/lines)
        arrow_scale: Scale for quiver arrow size (default 0.3, larger = bigger arrows)
        title_template: Title format string (use {hour} for current hour)
        frame_step: Only render every Nth frame (e.g., 6 = one frame per 6 hours)
        show_coverage: Whether to display coverage circles around balloons
        coverage_radius_km: Coverage radius in km (default: DEFAULT_COVERAGE_RADIUS_KM = 370)
        coverage_alpha: Transparency of coverage circles (default 0.15)

    Returns:
        matplotlib FuncAnimation object
    """
    _check_cartopy()

    if show_wind and wind_field is None:
        raise ValueError("wind_field must be provided when show_wind=True")

    # Get projection
    projections = {
        "robinson": ccrs.Robinson(),
        "platecarree": ccrs.PlateCarree(),
        "mollweide": ccrs.Mollweide(),
    }
    proj = projections.get(projection.lower(), ccrs.PlateCarree())

    # Create figure with minimal margins
    fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": proj})
    fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.02)
    ax.set_global()
    ax.coastlines(color="gray", linewidth=0.5)
    ax.add_feature(cfeature.LAND, facecolor="lightgray", alpha=0.5)
    ax.add_feature(cfeature.OCEAN, facecolor="lightblue", alpha=0.3)

    # Get balloons
    if isinstance(fleet_or_balloon, Balloon):
        balloons = [fleet_or_balloon]
    else:
        balloons = fleet_or_balloon.balloons

    # Determine number of frames (with step)
    total_steps = min(len(b.lats) for b in balloons)
    num_frames = total_steps // frame_step

    # Set up wind coordinate grids
    quiver_obj = None
    wind_lons = None
    wind_lats = None
    lon_plot = None
    lat_plot = None

    if show_wind and wind_field is not None:
        lat_count, lon_count = wind_field.grid_height, wind_field.grid_width
        # NCEP lon: 0, 2.5, 5, ..., 357.5 (144 points, NOT including 360)
        # Keep 0-360 range to match data indexing (cartopy handles this fine)
        wind_lons = np.linspace(0, 360, lon_count, endpoint=False)
        # Data is flipped at load time, so index 0 = south pole, index max = north pole
        wind_lats = np.linspace(-90, 90, lat_count)

        if wind_style == "quiver":
            lon_grid, lat_grid = np.meshgrid(wind_lons, wind_lats)
            lon_plot = lon_grid[::wind_stride, ::wind_stride]
            lat_plot = lat_grid[::wind_stride, ::wind_stride]

            # Initialize quiver with zeros
            # scale_units='inches' + scale controls arrow size consistently
            # Higher scale = smaller arrows. We invert arrow_scale for intuitive control.
            quiver_scale = 100 / max(arrow_scale, 0.01)  # arrow_scale=1 -> scale=100
            quiver_obj = ax.quiver(
                lon_plot, lat_plot,
                np.zeros_like(lon_plot), np.zeros_like(lat_plot),
                transform=ccrs.PlateCarree(),
                alpha=0.7,
                color='steelblue',
                zorder=3,
                scale=quiver_scale,
                scale_units='inches',
            )

    # Set up coverage circles if requested
    if coverage_radius_km is None:
        coverage_radius_km = DEFAULT_COVERAGE_RADIUS_KM

    coverage_patches = []
    if show_coverage:
        for i, balloon in enumerate(balloons):
            # Create initial polygon (will be updated each frame)
            initial_coords = _compute_coverage_circle(
                balloon.lats[0], balloon.lons[0], coverage_radius_km
            )
            patch = Polygon(
                initial_coords,
                closed=True,
                facecolor=f"C{i % 10}",
                edgecolor=f"C{i % 10}",
                alpha=coverage_alpha,
                linewidth=0.5,
                transform=ccrs.PlateCarree(),
                zorder=4,
            )
            ax.add_patch(patch)
            coverage_patches.append(patch)

    # Create scatter plots for each balloon
    scatters = []
    trails = []
    for i, balloon in enumerate(balloons):
        scatter = ax.scatter(
            [], [],
            s=50,
            c=f"C{i % 10}",
            transform=ccrs.PlateCarree(),
            zorder=10,
            edgecolors="white",
            linewidths=.5,
            alpha=0.75,
        )
        scatters.append(scatter)

        trail = ax.scatter(
            [], [],
            s=8,
            c=f"C{i % 10}",
            alpha=0.5,
            transform=ccrs.PlateCarree(),
            zorder=5,
        )
        trails.append(trail)

    title = ax.set_title(title_template.format(day=1))

    # For streamlines: track baseline counts to know what to remove
    base_n_collections = len(ax.collections)
    base_n_patches = len(ax.patches)

    def init():
        for scatter, trail in zip(scatters, trails):
            scatter.set_offsets(np.empty((0, 2)))
            trail.set_offsets(np.empty((0, 2)))
        return scatters + trails + coverage_patches + [title]

    def update(frame_idx):
        hour = frame_idx * frame_step

        # Update balloon positions and coverage circles
        for i, (balloon, scatter, trail) in enumerate(zip(balloons, scatters, trails)):
            lat = balloon.lats[hour]
            lon = balloon.lons[hour]
            scatter.set_offsets([[lon, lat]])

            start = max(0, hour - trail_length * frame_step)
            trail_lons = balloon.lons[start : hour + 1]
            trail_lats = balloon.lats[start : hour + 1]
            trail.set_offsets(np.column_stack([trail_lons, trail_lats]))

            # Update coverage circle
            if show_coverage and i < len(coverage_patches):
                circle_coords = _compute_coverage_circle(lat, lon, coverage_radius_km)
                coverage_patches[i].set_xy(circle_coords)

        # Update wind (use interpolation to match balloon trajectories)
        if show_wind and wind_field is not None:
            if wind_field.interpolation == "linear":
                # Interpolate between time steps (same as balloon physics)
                t_frac = hour / 6.0  # 6-hour intervals
                t0 = int(t_frac)
                t1 = t0 + 1
                t0 = min(t0, wind_field.num_times - 1)
                t1 = min(t1, wind_field.num_times - 1)
                alpha = t_frac - int(t_frac)
                u = (1 - alpha) * wind_field._u[t0] + alpha * wind_field._u[t1]
                v = (1 - alpha) * wind_field._v[t0] + alpha * wind_field._v[t1]
            else:
                # Step function (original behavior)
                time_idx = min(hour // 6, wind_field.num_times - 1)
                u = wind_field._u[time_idx]
                v = wind_field._v[time_idx]

            if wind_style == "quiver" and quiver_obj is not None:
                # Pass raw wind values - scaling is handled by quiver's scale parameter
                u_plot = u[::wind_stride, ::wind_stride]
                v_plot = v[::wind_stride, ::wind_stride]
                quiver_obj.set_UVC(u_plot, v_plot)

            elif wind_style == "streamlines":
                # Remove all collections added after baseline (streamlines add LineCollection)
                while len(ax.collections) > base_n_collections:
                    ax.collections[-1].remove()

                # Remove all patches added after baseline (streamlines add arrow patches)
                while len(ax.patches) > base_n_patches:
                    ax.patches[-1].remove()

                # Draw new streamlines
                speed = np.sqrt(u**2 + v**2)
                ax.streamplot(
                    wind_lons, wind_lats, u, v,
                    transform=ccrs.PlateCarree(),
                    density=wind_density,
                    color=speed,
                    cmap='Blues',
                    linewidth=0.8,
                    arrowsize=0.8,
                    zorder=3,
                )

        title.set_text(title_template.format(day=hour // 24 + 1))
        return scatters + trails + coverage_patches + [title]

    # Streamlines and coverage circles can't use blit reliably with cartopy
    use_blit = (wind_style != "streamlines" or not show_wind) and not show_coverage

    anim = animation.FuncAnimation(
        fig,
        update,
        init_func=init,
        frames=num_frames,
        interval=interval,
        blit=use_blit,
    )

    if save_path:
        print(f"Saving animation to {save_path}...")
        # Use CRF for quality-based encoding (lower = better, 18 is visually lossless)
        # -preset slow improves quality at cost of encoding time
        writer = animation.FFMpegWriter(
            fps=fps,
            codec='libx264',
            extra_args=['-crf', '32', '-preset', 'fast', '-pix_fmt', 'yuv420p'],
        )
        anim.save(save_path, writer=writer, dpi=dpi,
                  progress_callback=lambda i, n: print(f"\r  Frame {i+1}/{n}", end="", flush=True))
        print("\n  Done!")

    return anim


def create_coverage_animation(
    fleet: Fleet,
    analyzer: CoverageAnalyzer,
    projection: str = "robinson",
    figsize: tuple[int, int] = (12, 8),
    interval: int = 100,
    save_path: Optional[str] = None,
    dpi: int = 150,
    step_size: int = 1,
) -> animation.FuncAnimation:
    """
    Create animated coverage visualization.

    Shows coverage building up over time as balloons move.

    Args:
        fleet: Fleet of balloons to animate
        analyzer: CoverageAnalyzer instance
        projection: Map projection
        figsize: Figure size in inches
        interval: Milliseconds between frames
        save_path: Optional path to save animation
        dpi: Resolution for saved animation
        step_size: Compute coverage every N steps (for performance)

    Returns:
        matplotlib FuncAnimation object
    """
    _check_cartopy()

    # Get projection
    projections = {
        "robinson": ccrs.Robinson(),
        "platecarree": ccrs.PlateCarree(),
        "mollweide": ccrs.Mollweide(),
    }
    proj = projections.get(projection.lower(), ccrs.Robinson())

    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": proj})
    ax.set_global()

    # Initial empty coverage
    img_extent = [-180, 180, -90, 90]
    grid = analyzer.create_grid()
    im = ax.imshow(
        grid,
        transform=ccrs.PlateCarree(),
        extent=img_extent,
        origin="lower",
        cmap="viridis",
        vmin=0,
        vmax=1,
        zorder=2,
    )

    ax.coastlines(color="white", linewidth=0.5, zorder=3)

    # Balloon position markers
    balloons = fleet.balloons
    scatters = []
    for i, balloon in enumerate(balloons):
        scatter = ax.scatter(
            [],
            [],
            s=30,
            c="red",
            transform=ccrs.PlateCarree(),
            zorder=10,
            marker="o",
            alpha=0.5,
        )
        scatters.append(scatter)

    title = ax.set_title("Coverage: 0.0%")

    # Determine number of frames
    num_frames = min(len(b.lats) for b in balloons) // step_size

    def init():
        for scatter in scatters:
            scatter.set_offsets(np.empty((0, 2)))
        return [im] + scatters + [title]

    def update(frame_idx):
        frame = frame_idx * step_size
        grid = analyzer.create_grid()

        # Update coverage for all balloons up to current frame
        for balloon in balloons:
            for i in range(0, min(frame + 1, len(balloon.lats)), max(1, step_size)):
                analyzer.update_coverage(
                    balloon.lats[i], balloon.lons[i], grid, frame - i + 1
                )

        # Normalize for display
        display_grid = grid / (np.max(grid) + 1e-10)
        im.set_array(display_grid)

        # Update balloon positions
        for balloon, scatter in zip(balloons, scatters):
            if frame < len(balloon.lats):
                scatter.set_offsets([[balloon.lons[frame], balloon.lats[frame]]])

        # Update title with coverage percentage
        coverage_pct = analyzer.compute_coverage_percentage(grid) * 100
        title.set_text(f"Coverage: {coverage_pct:.1f}%")

        return [im] + scatters + [title]

    anim = animation.FuncAnimation(
        fig,
        update,
        init_func=init,
        frames=num_frames,
        interval=interval,
        blit=True,
    )

    if save_path:
        writer = animation.FFMpegWriter(fps=30, bitrate=8192)
        anim.save(save_path, writer=writer, dpi=dpi)

    return anim


# ============================================================================
# Parallel rendering implementation
# ============================================================================

def _render_frames_worker(args):
    """
    Worker function to render a range of frames to PNG files.

    This runs in a separate process with its own matplotlib instance.
    Wind data is accessed via shared memory to minimize memory usage.
    """
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend for worker processes
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from multiprocessing import shared_memory

    (
        frame_indices,
        output_dir,
        # Shared memory info for wind data
        shm_u_name,
        shm_v_name,
        wind_shape,
        wind_dtype,
        wind_interpolation,
        wind_num_times,
        # Balloon data (small, just copy it)
        balloon_data,  # List of (lats, lons, balloon_id) tuples
        # Rendering parameters
        projection,
        figsize,
        frame_step,
        trail_length,
        show_wind,
        wind_style,
        wind_stride,
        arrow_scale,
        wind_density,
        show_coverage,
        coverage_radius_km,
        coverage_alpha,
        title_template,
        dpi,
    ) = args

    # Reconstruct wind arrays from shared memory
    shm_u = shared_memory.SharedMemory(name=shm_u_name)
    shm_v = shared_memory.SharedMemory(name=shm_v_name)
    wind_u = np.ndarray(wind_shape, dtype=wind_dtype, buffer=shm_u.buf)
    wind_v = np.ndarray(wind_shape, dtype=wind_dtype, buffer=shm_v.buf)

    # Set up projection
    projections = {
        "robinson": ccrs.Robinson(),
        "platecarree": ccrs.PlateCarree(),
        "mollweide": ccrs.Mollweide(),
    }
    proj = projections.get(projection.lower(), ccrs.PlateCarree())

    # Set up wind coordinate grids
    lat_count, lon_count = wind_shape[1], wind_shape[2]
    wind_lons = np.linspace(0, 360, lon_count, endpoint=False)
    wind_lats = np.linspace(-90, 90, lat_count)

    # Create figure once, reuse for all frames
    fig, ax = plt.subplots(1, 1, figsize=figsize, subplot_kw={"projection": proj})
    fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.02)

    rendered_count = 0

    for frame_idx in frame_indices:
        ax.clear()
        ax.set_global()
        ax.coastlines(color="gray", linewidth=0.5)
        ax.add_feature(cfeature.LAND, facecolor="lightgray", alpha=0.5)
        ax.add_feature(cfeature.OCEAN, facecolor="lightblue", alpha=0.3)

        hour = frame_idx * frame_step

        # Get wind data for this frame
        if show_wind:
            if wind_interpolation == "linear":
                t_frac = hour / 6.0
                t0 = int(t_frac)
                t1 = t0 + 1
                t0 = min(t0, wind_num_times - 1)
                t1 = min(t1, wind_num_times - 1)
                alpha = t_frac - int(t_frac)
                u = (1 - alpha) * wind_u[t0] + alpha * wind_u[t1]
                v = (1 - alpha) * wind_v[t0] + alpha * wind_v[t1]
            else:
                time_idx = min(hour // 6, wind_num_times - 1)
                u = wind_u[time_idx]
                v = wind_v[time_idx]

            if wind_style == "quiver":
                lon_grid, lat_grid = np.meshgrid(wind_lons, wind_lats)
                lon_plot = lon_grid[::wind_stride, ::wind_stride]
                lat_plot = lat_grid[::wind_stride, ::wind_stride]
                u_plot = u[::wind_stride, ::wind_stride]
                v_plot = v[::wind_stride, ::wind_stride]

                quiver_scale = 100 / max(arrow_scale, 0.01)
                ax.quiver(
                    lon_plot, lat_plot, u_plot, v_plot,
                    transform=ccrs.PlateCarree(),
                    alpha=0.7,
                    color='steelblue',
                    zorder=3,
                    scale=quiver_scale,
                    scale_units='inches',
                )
            elif wind_style == "streamlines":
                speed = np.sqrt(u**2 + v**2)
                ax.streamplot(
                    wind_lons, wind_lats, u, v,
                    transform=ccrs.PlateCarree(),
                    density=wind_density,
                    color=speed,
                    cmap='Blues',
                    linewidth=0.8,
                    arrowsize=0.8,
                    zorder=3,
                )

        # Draw balloons
        for i, (lats, lons, balloon_id) in enumerate(balloon_data):
            lat = lats[hour]
            lon = lons[hour]
            color = f"C{i % 10}"

            # Coverage circle
            if show_coverage:
                circle_coords = _compute_coverage_circle(lat, lon, coverage_radius_km)
                patch = Polygon(
                    circle_coords,
                    closed=True,
                    facecolor=color,
                    edgecolor=color,
                    alpha=coverage_alpha,
                    linewidth=0.5,
                    transform=ccrs.PlateCarree(),
                    zorder=4,
                )
                ax.add_patch(patch)

            # Trail
            start = max(0, hour - trail_length * frame_step)
            trail_lons = lons[start:hour + 1]
            trail_lats = lats[start:hour + 1]
            ax.scatter(
                trail_lons, trail_lats,
                s=8,
                c=color,
                alpha=0.5,
                transform=ccrs.PlateCarree(),
                zorder=5,
            )

            # Current position
            ax.scatter(
                [lon], [lat],
                s=50,
                c=color,
                transform=ccrs.PlateCarree(),
                zorder=10,
                edgecolors="white",
                linewidths=0.5,
                alpha=0.75,
            )

        ax.set_title(title_template.format(hour=hour, day=hour // 24 + 1))

        # Save frame
        frame_path = f"{output_dir}/frame_{frame_idx:06d}.png"
        fig.savefig(frame_path, dpi=dpi, facecolor='white', edgecolor='none')
        rendered_count += 1

    plt.close(fig)

    # Close shared memory (don't unlink - main process does that)
    shm_u.close()
    shm_v.close()

    return rendered_count


def create_trajectory_animation_parallel(
    fleet_or_balloon: Union[Fleet, Balloon],
    wind_field,
    save_path: str,
    projection: str = "platecarree",
    figsize: tuple[int, int] = (14, 8),
    dpi: int = 150,
    fps: int = 30,
    trail_length: int = 20,
    show_wind: bool = False,
    wind_style: str = "quiver",
    wind_density: float = 1.0,
    wind_stride: int = 4,
    arrow_scale: float = 0.3,
    title_template: str = "Day: {day}",
    frame_step: int = 1,
    show_coverage: bool = False,
    coverage_radius_km: Optional[float] = None,
    coverage_alpha: float = 0.15,
    n_workers: Optional[int] = None,
    crf: int = 23,
) -> str:
    """
    Create trajectory animation using parallel rendering for faster generation.

    Uses multiprocessing with shared memory for wind data to minimize memory usage.
    Renders frames in parallel to PNG files, then combines with FFmpeg.

    Args:
        fleet_or_balloon: Fleet or single Balloon to animate
        wind_field: WindField instance (required for parallel rendering)
        save_path: Path to save the output video (e.g., 'output.mp4')
        projection: Map projection ('platecarree', 'robinson', 'mollweide')
        figsize: Figure size in inches
        dpi: Resolution for rendered frames
        fps: Frames per second in output video
        trail_length: Number of previous positions to show as trail
        show_wind: Whether to display wind vectors
        wind_style: 'quiver' or 'streamlines'
        wind_density: Density of streamlines
        wind_stride: Subsample factor for wind display
        arrow_scale: Scale for quiver arrows
        title_template: Title format string ({hour} and {day} available)
        frame_step: Only render every Nth frame
        show_coverage: Whether to display coverage circles
        coverage_radius_km: Coverage radius (default: DEFAULT_COVERAGE_RADIUS_KM)
        coverage_alpha: Transparency of coverage circles
        n_workers: Number of parallel workers (default: CPU count - 1)
        crf: FFmpeg CRF quality (lower = better, 18-28 typical)

    Returns:
        Path to the saved video file
    """
    import tempfile
    import shutil
    import subprocess
    import os
    from multiprocessing import Pool, cpu_count, shared_memory

    _check_cartopy()

    if coverage_radius_km is None:
        coverage_radius_km = DEFAULT_COVERAGE_RADIUS_KM

    if n_workers is None:
        n_workers = max(1, cpu_count() - 1)

    # Get balloons
    if isinstance(fleet_or_balloon, Balloon):
        balloons = [fleet_or_balloon]
    else:
        balloons = fleet_or_balloon.balloons

    # Extract balloon data (small, can be pickled)
    balloon_data = [(b.lats.copy(), b.lons.copy(), b.balloon_id) for b in balloons]

    # Determine frame count
    total_steps = min(len(b.lats) for b in balloons)
    num_frames = total_steps // frame_step

    print(f"Parallel rendering: {num_frames} frames using {n_workers} workers")

    # Create shared memory for wind data
    wind_u = wind_field._u
    wind_v = wind_field._v

    shm_u = shared_memory.SharedMemory(create=True, size=wind_u.nbytes)
    shm_v = shared_memory.SharedMemory(create=True, size=wind_v.nbytes)

    # Copy wind data to shared memory
    shm_u_array = np.ndarray(wind_u.shape, dtype=wind_u.dtype, buffer=shm_u.buf)
    shm_v_array = np.ndarray(wind_v.shape, dtype=wind_v.dtype, buffer=shm_v.buf)
    shm_u_array[:] = wind_u[:]
    shm_v_array[:] = wind_v[:]

    # Create temporary directory for frames
    temp_dir = tempfile.mkdtemp(prefix="balloon_anim_")

    try:
        # Split frames among workers
        frame_indices = list(range(num_frames))
        chunks = np.array_split(frame_indices, n_workers)

        # Prepare arguments for each worker
        worker_args = []
        for chunk in chunks:
            if len(chunk) == 0:
                continue
            args = (
                chunk.tolist(),
                temp_dir,
                shm_u.name,
                shm_v.name,
                wind_u.shape,
                str(wind_u.dtype),
                wind_field.interpolation,
                wind_field.num_times,
                balloon_data,
                projection,
                figsize,
                frame_step,
                trail_length,
                show_wind,
                wind_style,
                wind_stride,
                arrow_scale,
                wind_density,
                show_coverage,
                coverage_radius_km,
                coverage_alpha,
                title_template,
                dpi,
            )
            worker_args.append(args)

        # Render frames in parallel
        print("Rendering frames...")
        with Pool(n_workers) as pool:
            results = pool.map(_render_frames_worker, worker_args)

        total_rendered = sum(results)
        print(f"Rendered {total_rendered} frames")

        # Combine frames with FFmpeg
        print("Encoding video...")
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-framerate', str(fps),
            '-i', f'{temp_dir}/frame_%06d.png',
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-preset', 'medium',
            '-pix_fmt', 'yuv420p',
            save_path,
        ]

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg failed with code {result.returncode}")

        print(f"Saved video to {save_path}")

    finally:
        # Clean up
        shm_u.close()
        shm_u.unlink()
        shm_v.close()
        shm_v.unlink()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return save_path
