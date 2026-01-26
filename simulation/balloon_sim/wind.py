"""
Wind data loading and interpolation.

Loads NCEP Reanalysis 2 wind data and provides wind velocity lookups
with optional temporal interpolation.
"""

import os
import urllib.request
from typing import Literal, Optional

import numpy as np
import xarray as xr


NCEP_BASE_URL = "https://psl.noaa.gov/thredds/fileServer/Datasets/ncep.reanalysis2/pressure"


def _download_file(url: str, directory: str, filename: str) -> None:
    """Download a file using wget or curl."""
    import shutil
    import subprocess

    filepath = os.path.join(directory, filename)

    if shutil.which("wget"):
        # --tries=0 means infinite retries, -c continues partial downloads
        cmd = f'wget -q --tries=0 -c "{url}" -P "{directory}"'
    elif shutil.which("curl"):
        cmd = f'curl -L -s --retry 100 --retry-delay 1 -C - -o "{filepath}" "{url}"'
    else:
        raise RuntimeError(
            "Neither wget nor curl found. Please install one:\n"
            "  macOS: brew install wget\n"
            "  Ubuntu: apt install wget"
        )

    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise RuntimeError(f"Download failed with exit code {result.returncode}")


def download_ncep_data(
    data_path: str = "data",
    years: Optional[list[int]] = None,
    verbose: bool = True,
) -> str:
    """
    Download NCEP Reanalysis 2 wind data if not already present.

    Args:
        data_path: Directory to store downloaded files
        years: List of years to download (default: [2023, 2024])
        verbose: Print progress messages

    Returns:
        Path to the data directory
    """
    if years is None:
        years = [2023, 2024]

    os.makedirs(data_path, exist_ok=True)

    for year in years:
        for var in ["uwnd", "vwnd"]:
            filename = f"{var}.{year}.nc"
            filepath = os.path.join(data_path, filename)

            if os.path.exists(filepath):
                if verbose:
                    print(f"  {filename} already exists, skipping")
                continue

            url = f"{NCEP_BASE_URL}/{filename}"
            if verbose:
                print(f"  Downloading {filename}...", end=" ", flush=True)

            try:
                _download_file(url, data_path, filename)
                if verbose:
                    print("done")
            except Exception as e:
                if verbose:
                    print(f"failed: {e}")
                raise

    return data_path

from balloon_sim.constants import (
    DEFAULT_PRESSURE_LEVEL,
    MS_TO_KMH,
    WIND_UPDATE_HOURS,
)
from balloon_sim.coordinates import standard_to_internal, internal_to_grid


class WindField:
    """
    Manages wind data from NCEP Reanalysis files.

    The wind field provides U (east-west) and V (north-south) wind components
    at a specified pressure level, with optional temporal interpolation.

    Attributes:
        pressure_level: Pressure level in hPa (default 300)
        interpolation: Interpolation mode ('none' or 'linear')
        grid_height: Number of latitude points in the grid
        grid_width: Number of longitude points in the grid
        num_times: Number of time steps in the data
    """

    def __init__(
        self,
        data_path: str,
        pressure_level: int = DEFAULT_PRESSURE_LEVEL,
        interpolation: Literal["none", "linear"] = "none",
    ):
        """
        Load wind data from NCEP Reanalysis files.

        Args:
            data_path: Path to directory containing uwnd*.nc and vwnd*.nc files
            pressure_level: Pressure level to extract (hPa), default 300
            interpolation: 'none' for step function (original behavior),
                          'linear' for linear interpolation between time steps
        """
        self.pressure_level = pressure_level
        self.interpolation = interpolation
        self._load_data(data_path)

    def _load_data(self, data_path: str) -> None:
        """Load and concatenate wind data files."""
        u_files = sorted(
            [f for f in os.listdir(data_path) if "uwnd" in f and f.endswith(".nc")]
        )
        v_files = sorted(
            [f for f in os.listdir(data_path) if "vwnd" in f and f.endswith(".nc")]
        )

        if not u_files or not v_files:
            raise FileNotFoundError(
                f"No wind data files found in {data_path}. "
                "Expected files matching 'uwnd*.nc' and 'vwnd*.nc'"
            )

        # Load first file
        uwind = xr.open_dataset(
            os.path.join(data_path, u_files[0]), engine="netcdf4"
        ).sel(level=self.pressure_level)["uwnd"]
        vwind = xr.open_dataset(
            os.path.join(data_path, v_files[0]), engine="netcdf4"
        ).sel(level=self.pressure_level)["vwnd"]

        # Concatenate additional files
        for u_file in u_files[1:]:
            new_u = xr.open_dataset(
                os.path.join(data_path, u_file), engine="netcdf4"
            ).sel(level=self.pressure_level)["uwnd"]
            uwind = xr.concat([uwind, new_u], "time")

        for v_file in v_files[1:]:
            new_v = xr.open_dataset(
                os.path.join(data_path, v_file), engine="netcdf4"
            ).sel(level=self.pressure_level)["vwnd"]
            vwind = xr.concat([vwind, new_v], "time")

        # Store as numpy arrays for fast access
        # NCEP data has latitude from 90 to -90 (north to south)
        # Our coordinate system expects 0=south, max=north, so flip latitude axis
        self._u = np.flip(uwind.values, axis=1)  # Shape: (time, lat, lon)
        self._v = np.flip(vwind.values, axis=1)
        self._times = uwind.time.values

        self.grid_height = self._u.shape[1]
        self.grid_width = self._u.shape[2]
        self.num_times = self._u.shape[0]

    @property
    def times(self) -> np.ndarray:
        """Return the time coordinates of the wind data."""
        return self._times

    def get_wind(
        self, lat: float, lon: float, hour_index: int
    ) -> tuple[float, float]:
        """
        Get wind velocity at a location and time.

        Args:
            lat: Latitude in standard format (-90 to 90)
            lon: Longitude in standard format (-180 to 180)
            hour_index: Simulation hour (0-indexed, advances every hour)

        Returns:
            Tuple of (u, v) wind components in km/h where:
            - u is east-west velocity (positive = eastward)
            - v is north-south velocity (positive = northward)
        """
        # Convert to internal coordinates and grid indices
        internal_lat, internal_lon = standard_to_internal(lat, lon)
        y, x = internal_to_grid(
            internal_lat, internal_lon, self.grid_height, self.grid_width
        )

        if self.interpolation == "none":
            # Original behavior: step function, update every 6 hours
            time_idx = hour_index // WIND_UPDATE_HOURS
            time_idx = min(time_idx, self.num_times - 1)

            u_ms = self._u[time_idx, y, x]
            v_ms = self._v[time_idx, y, x]
        else:
            # Linear interpolation between time steps
            u_ms, v_ms = self._interpolate_wind(hour_index, y, x)

        # Convert from m/s to km/h
        return float(u_ms * MS_TO_KMH), float(v_ms * MS_TO_KMH)

    def _interpolate_wind(
        self, hour_index: int, y: int, x: int
    ) -> tuple[float, float]:
        """
        Linearly interpolate wind between time steps.

        Bug #3 fix: Instead of using stale wind for 5/6 of steps,
        interpolate between adjacent time steps.
        """
        # Fractional position between time steps
        t_frac = hour_index / WIND_UPDATE_HOURS

        t0 = int(t_frac)
        t1 = t0 + 1

        # Clamp to valid range
        t0 = min(t0, self.num_times - 1)
        t1 = min(t1, self.num_times - 1)

        # Interpolation weight
        alpha = t_frac - int(t_frac)

        # Interpolate
        u_ms = (1 - alpha) * self._u[t0, y, x] + alpha * self._u[t1, y, x]
        v_ms = (1 - alpha) * self._v[t0, y, x] + alpha * self._v[t1, y, x]

        return u_ms, v_ms

    def get_wind_internal(
        self, lat: float, lon: float, hour_index: int
    ) -> tuple[float, float]:
        """
        Get wind velocity using internal coordinates.

        Args:
            lat: Latitude in internal format (0 to 180)
            lon: Longitude in internal format (0 to 360)
            hour_index: Simulation hour (0-indexed)

        Returns:
            Tuple of (u, v) wind components in km/h
        """
        y, x = internal_to_grid(lat, lon, self.grid_height, self.grid_width)

        if self.interpolation == "none":
            time_idx = hour_index // WIND_UPDATE_HOURS
            time_idx = min(time_idx, self.num_times - 1)
            u_ms = self._u[time_idx, y, x]
            v_ms = self._v[time_idx, y, x]
        else:
            u_ms, v_ms = self._interpolate_wind(hour_index, y, x)

        return float(u_ms * MS_TO_KMH), float(v_ms * MS_TO_KMH)
