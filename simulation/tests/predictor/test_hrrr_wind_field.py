"""Tests for :class:`HRRRWindField` using a synthetic Lambert-like grid.

We don't need a real Lambert projection — what we need is a 2-D
``latitude``/``longitude`` grid (the layout HRRR uses) plus the
``isobaricInhPa`` + ``time`` axes the field interpolates over. The
KDTree spatial sampling, the level interp, and the time interp all
exercise the same code paths regardless of which exact projection
generated the lat/lon arrays.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

xr = pytest.importorskip("xarray")

from predictor.weather.hrrr_wind_field import HRRRWindField


def _synthetic_lambert_like(
    *,
    n_y: int = 5,
    n_x: int = 5,
    levels_hpa: tuple[float, ...] = (50.0, 100.0, 250.0),
    times: tuple[datetime, ...] = (
        datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
    ),
) -> xr.Dataset:
    """Build a synthetic dataset that looks like an HRRR pressure-level subset.

    The lat/lon coords are 2-D (as in HRRR), the level/time coords are
    1-D. u and v are deterministic linear functions of the grid indices
    so test expectations are easy to compute.
    """
    # Lat from 30 → 40 along y; lon from -110 → -100 along x. Slight
    # row-by-row offset gives a non-uniform grid, mimicking Lambert.
    lat2d = np.zeros((n_y, n_x))
    lon2d = np.zeros((n_y, n_x))
    for j in range(n_y):
        for i in range(n_x):
            lat2d[j, i] = 30.0 + 10.0 * (j / (n_y - 1)) + 0.2 * (i / (n_x - 1))
            lon2d[j, i] = -110.0 + 10.0 * (i / (n_x - 1)) - 0.3 * (j / (n_y - 1))

    n_l = len(levels_hpa)
    n_t = len(times)
    # u = j (north index), v = i (east index), plus level and time offsets.
    # u[t, l, j, i] = j + 0.01*l + t (so equal-grid points across time differ)
    u = np.zeros((n_t, n_l, n_y, n_x), dtype=np.float32)
    v = np.zeros((n_t, n_l, n_y, n_x), dtype=np.float32)
    for ti in range(n_t):
        for li in range(n_l):
            for j in range(n_y):
                for i in range(n_x):
                    u[ti, li, j, i] = j + 0.01 * levels_hpa[li] + ti
                    v[ti, li, j, i] = i - 0.01 * levels_hpa[li] - ti

    times_naive = [t.replace(tzinfo=None) for t in times]
    return xr.Dataset(
        data_vars={
            "u": (("time", "isobaricInhPa", "y", "x"), u),
            "v": (("time", "isobaricInhPa", "y", "x"), v),
        },
        coords={
            "time": np.array([np.datetime64(t, "ns") for t in times_naive]),
            "valid_time": ("time", np.array([np.datetime64(t, "ns") for t in times_naive])),
            "isobaricInhPa": np.array(levels_hpa),
            "latitude": (("y", "x"), lat2d),
            "longitude": (("y", "x"), lon2d),
        },
    )


T0 = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def test_nearest_neighbor_at_exact_grid_point():
    ds = _synthetic_lambert_like()
    wf = HRRRWindField(ds)
    # Grid point (j=2, i=2) → lat = 30+5+0.1 = 35.1, lon = -110+5-0.15 = -105.15
    u, v = wf.get_wind(35.1, -105.15, pressure_pa=10000.0, time=T0)
    # u = j + 0.01*l + t = 2 + 1 + 0 = 3.0 at level=100 hPa, t_idx=0
    assert u == pytest.approx(3.0, abs=1e-5)
    # v = i - 0.01*l - t = 2 - 1 - 0 = 1.0
    assert v == pytest.approx(1.0, abs=1e-5)


def test_level_linear_interpolation():
    """Halfway between two pressure levels should give the arithmetic mean."""
    ds = _synthetic_lambert_like()
    wf = HRRRWindField(ds)
    # 75 hPa is halfway between 50 and 100 hPa
    u_50, _ = wf.get_wind(35.1, -105.15, pressure_pa=5000.0, time=T0)
    u_100, _ = wf.get_wind(35.1, -105.15, pressure_pa=10000.0, time=T0)
    u_75, _ = wf.get_wind(35.1, -105.15, pressure_pa=7500.0, time=T0)
    assert u_75 == pytest.approx((u_50 + u_100) / 2.0, abs=1e-5)


def test_time_linear_interpolation():
    """Halfway between two valid times should give the arithmetic mean."""
    times = (T0, T0 + timedelta(hours=2))
    ds = _synthetic_lambert_like(times=times)
    wf = HRRRWindField(ds)
    u_start, _ = wf.get_wind(35.1, -105.15, 10000.0, T0)
    u_end, _ = wf.get_wind(35.1, -105.15, 10000.0, T0 + timedelta(hours=2))
    u_mid, _ = wf.get_wind(35.1, -105.15, 10000.0, T0 + timedelta(hours=1))
    assert u_mid == pytest.approx((u_start + u_end) / 2.0, abs=1e-5)


def test_time_clamps_to_loaded_range():
    """Queries before/after the loaded time range clamp to the endpoints."""
    times = (T0, T0 + timedelta(hours=2))
    ds = _synthetic_lambert_like(times=times)
    wf = HRRRWindField(ds)
    u_before, _ = wf.get_wind(35.1, -105.15, 10000.0, T0 - timedelta(hours=5))
    u_at_start, _ = wf.get_wind(35.1, -105.15, 10000.0, T0)
    assert u_before == pytest.approx(u_at_start, abs=1e-5)

    u_after, _ = wf.get_wind(35.1, -105.15, 10000.0, T0 + timedelta(hours=10))
    u_at_end, _ = wf.get_wind(35.1, -105.15, 10000.0, T0 + timedelta(hours=2))
    assert u_after == pytest.approx(u_at_end, abs=1e-5)


def test_longitude_canonicalization_0_360_to_signed():
    """A dataset stored on [0, 360] must answer queries on [−180, 180]."""
    ds = _synthetic_lambert_like()
    # Re-encode lon to 0–360
    lon360 = (ds["longitude"].values + 360.0) % 360.0
    ds = ds.assign_coords(longitude=(("y", "x"), lon360))
    wf = HRRRWindField(ds)
    # Query in the [-180, 180] convention — should resolve to the same grid cell
    u, v = wf.get_wind(35.1, -105.15, 10000.0, T0)
    assert u == pytest.approx(3.0, abs=1e-5)
    assert v == pytest.approx(1.0, abs=1e-5)


def test_query_uses_nearest_grid_cell():
    """A query slightly off-grid should snap to the nearest cell."""
    ds = _synthetic_lambert_like()
    wf = HRRRWindField(ds)
    # 35.0999 ≈ 35.1, -105.149 ≈ -105.15 → same nearest cell as the exact point
    u_offset, _ = wf.get_wind(35.0999, -105.149, 10000.0, T0)
    u_exact, _ = wf.get_wind(35.1, -105.15, 10000.0, T0)
    assert u_offset == pytest.approx(u_exact, abs=1e-5)


def test_get_wind_at_altitude_uses_isa_pressure():
    from predictor.atmosphere import isa
    ds = _synthetic_lambert_like()
    wf = HRRRWindField(ds)
    h_m = 12000.0
    p_pa = isa.pressure(h_m)
    u_h, v_h = wf.get_wind_at_altitude(35.1, -105.15, h_m, T0)
    u_p, v_p = wf.get_wind(35.1, -105.15, p_pa, T0)
    assert u_h == pytest.approx(u_p, abs=1e-5)
    assert v_h == pytest.approx(v_p, abs=1e-5)


def test_grid_extent_exposed():
    ds = _synthetic_lambert_like()
    wf = HRRRWindField(ds)
    ext = wf.grid_extent
    assert ext["lat_min"] < ext["lat_max"]
    assert ext["lon_min"] < ext["lon_max"]
    assert 29.0 < ext["lat_min"] < 31.0
    assert 39.0 < ext["lat_max"] < 41.0


def test_level_clamping_outside_range():
    """Queries above the top level or below the bottom level clamp."""
    ds = _synthetic_lambert_like(levels_hpa=(100.0, 250.0))
    wf = HRRRWindField(ds)
    u_above_top, _ = wf.get_wind(35.1, -105.15, pressure_pa=5000.0, time=T0)  # 50 hPa
    u_at_top, _ = wf.get_wind(35.1, -105.15, pressure_pa=10000.0, time=T0)
    assert u_above_top == pytest.approx(u_at_top, abs=1e-5)
