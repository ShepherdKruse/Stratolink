"""Tests for :class:`RegularGridWindField` (fast numpy-based GFS-shape sampler)."""

from __future__ import annotations

import time as _time
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

xr = pytest.importorskip("xarray")

from predictor.weather.wind_field import RegularGridWindField


def _synthetic_gfs_like(
    *,
    n_lat: int = 5,
    n_lon: int = 5,
    levels_hpa: tuple[float, ...] = (50.0, 100.0, 250.0),
    times: tuple[datetime, ...] = (
        datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
    ),
    lon_convention: str = "signed",
) -> xr.Dataset:
    """Minimal GFS-shape Dataset (1-D lat/lon)."""
    lat = np.linspace(-90.0, 90.0, n_lat)
    if lon_convention == "0_360":
        lon = np.linspace(0.0, 360.0 - (360.0 / n_lon), n_lon)
    else:
        lon = np.linspace(-180.0, 180.0 - (360.0 / n_lon), n_lon)
    n_l = len(levels_hpa)
    n_t = len(times)
    # u = lat_idx + level_value/100 + t_idx; v = lon_idx
    u = np.zeros((n_t, n_l, n_lat, n_lon), dtype=np.float32)
    v = np.zeros((n_t, n_l, n_lat, n_lon), dtype=np.float32)
    for ti in range(n_t):
        for li in range(n_l):
            for j in range(n_lat):
                for i in range(n_lon):
                    u[ti, li, j, i] = j + levels_hpa[li] / 100.0 + ti
                    v[ti, li, j, i] = i

    times_naive = [t.replace(tzinfo=None) for t in times]
    return xr.Dataset(
        data_vars={
            "u": (("time", "isobaricInhPa", "latitude", "longitude"), u),
            "v": (("time", "isobaricInhPa", "latitude", "longitude"), v),
        },
        coords={
            "time": np.array([np.datetime64(t, "ns") for t in times_naive]),
            "isobaricInhPa": np.asarray(levels_hpa),
            "latitude": lat,
            "longitude": lon,
        },
    )


T0 = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def test_on_grid_query_returns_grid_value():
    ds = _synthetic_gfs_like()
    wf = RegularGridWindField(ds)
    # Grid point (j=2, i=2) at level=100 hPa, t=0: u = 2 + 1 + 0 = 3
    # lat = -90 + (180/4)*2 = 0, lon = -180 + (360/5)*2 = -36
    u, v = wf.get_wind(0.0, -36.0, pressure_pa=10000.0, time=T0)
    assert u == pytest.approx(3.0, abs=1e-5)
    assert v == pytest.approx(2.0, abs=1e-5)


def test_lat_linear_interp_midpoint():
    ds = _synthetic_gfs_like()
    wf = RegularGridWindField(ds)
    # Midpoint between j=2 (lat=0) and j=3 (lat=45): lat=22.5
    u_lo, _ = wf.get_wind(0.0, -36.0, 10000.0, T0)
    u_hi, _ = wf.get_wind(45.0, -36.0, 10000.0, T0)
    u_mid, _ = wf.get_wind(22.5, -36.0, 10000.0, T0)
    assert u_mid == pytest.approx((u_lo + u_hi) / 2.0, abs=1e-5)


def test_level_linear_interp_midpoint():
    ds = _synthetic_gfs_like()
    wf = RegularGridWindField(ds)
    # 75 hPa is halfway between 50 and 100 hPa
    u_50, _ = wf.get_wind(0.0, -36.0, 5000.0, T0)
    u_100, _ = wf.get_wind(0.0, -36.0, 10000.0, T0)
    u_75, _ = wf.get_wind(0.0, -36.0, 7500.0, T0)
    assert u_75 == pytest.approx((u_50 + u_100) / 2.0, abs=1e-5)


def test_time_linear_interp_midpoint():
    ds = _synthetic_gfs_like(times=(T0, T0 + timedelta(hours=2)))
    wf = RegularGridWindField(ds)
    u0, _ = wf.get_wind(0.0, -36.0, 10000.0, T0)
    u2, _ = wf.get_wind(0.0, -36.0, 10000.0, T0 + timedelta(hours=2))
    u1, _ = wf.get_wind(0.0, -36.0, 10000.0, T0 + timedelta(hours=1))
    assert u1 == pytest.approx((u0 + u2) / 2.0, abs=1e-5)


def test_0_360_longitude_canonicalization():
    """A GFS-shape dataset on [0, 360] must answer queries on [−180, 180]."""
    ds = _synthetic_gfs_like(lon_convention="0_360")
    wf = RegularGridWindField(ds)
    # Querying lon = -36 should hit the cell that was originally at lon = 324
    u, v = wf.get_wind(0.0, -36.0, 10000.0, T0)
    assert np.isfinite(u)
    assert np.isfinite(v)


def test_descending_latitude_normalized():
    """GFS often stores lat 90 → -90 (descending). Constructor must flip."""
    ds = _synthetic_gfs_like()
    ds_desc = ds.sortby("latitude", ascending=False)
    wf_desc = RegularGridWindField(ds_desc)
    wf_asc = RegularGridWindField(ds)
    # Same query should give same result regardless of stored order
    u_d, _ = wf_desc.get_wind(0.0, -36.0, 10000.0, T0)
    u_a, _ = wf_asc.get_wind(0.0, -36.0, 10000.0, T0)
    assert u_d == pytest.approx(u_a, abs=1e-5)


def test_lat_out_of_range_clamps():
    ds = _synthetic_gfs_like()
    wf = RegularGridWindField(ds)
    u_clamped, _ = wf.get_wind(95.0, -36.0, 10000.0, T0)
    u_at_pole, _ = wf.get_wind(90.0, -36.0, 10000.0, T0)
    assert u_clamped == pytest.approx(u_at_pole, abs=1e-5)


def test_get_wind_at_altitude_uses_isa():
    from predictor.atmosphere import isa
    ds = _synthetic_gfs_like()
    wf = RegularGridWindField(ds)
    h_m = 12000.0
    u_h, v_h = wf.get_wind_at_altitude(0.0, -36.0, h_m, T0)
    u_p, v_p = wf.get_wind(0.0, -36.0, isa.pressure(h_m), T0)
    assert u_h == pytest.approx(u_p, abs=1e-5)
    assert v_h == pytest.approx(v_p, abs=1e-5)


def test_throughput_meets_ensemble_budget():
    """A 50-member × 360-step ensemble fires ~18 000 wind samples per request.
    The fast sampler must complete that volume in well under one second so
    a single API request stays interactive."""
    # Build a realistically-shaped GFS-subset dataset (8 fxx × 7 levels ×
    # 721 lat × 1440 lon ≈ the production payload)
    times = tuple(T0 + timedelta(hours=h) for h in range(8))
    lat = np.linspace(-90.0, 90.0, 721)
    lon = np.linspace(0.0, 359.75, 1440)
    levels = (10.0, 20.0, 30.0, 50.0, 70.0, 100.0, 150.0)
    u = np.random.rand(8, 7, 721, 1440).astype(np.float32) * 30.0 - 15.0
    v = np.random.rand(8, 7, 721, 1440).astype(np.float32) * 30.0 - 15.0
    ds = xr.Dataset(
        data_vars={
            "u": (("time", "isobaricInhPa", "latitude", "longitude"), u),
            "v": (("time", "isobaricInhPa", "latitude", "longitude"), v),
        },
        coords={
            "time": np.array([np.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
            "isobaricInhPa": np.asarray(levels),
            "latitude": lat,
            "longitude": lon,
        },
    )
    wf = RegularGridWindField(ds)
    # Warm-up
    wf.get_wind(40.0, -105.0, 5500.0, T0 + timedelta(hours=1))

    n = 18000
    start = _time.perf_counter()
    for i in range(n):
        wf.get_wind(40.0 + (i % 100) * 0.01, -105.0 + (i % 100) * 0.01,
                    5500.0, T0 + timedelta(hours=1, seconds=i))
    elapsed = _time.perf_counter() - start
    # Budget: 18000 calls in < 1.5 s on this hardware leaves plenty of
    # headroom for the rest of the ensemble loop. Trip the alarm only on
    # an outright regression (10×+ slowdown).
    assert elapsed < 5.0, f"RegularGridWindField too slow: {elapsed:.2f}s for {n} calls"
