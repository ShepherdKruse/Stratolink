"""Tests for the WindField abstractions."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from predictor.weather.wind_field import (
    ConstantWindField,
    WindField,
    XarrayWindField,
)


def test_constant_wind_satisfies_protocol():
    cwf = ConstantWindField(u_m_s=10.0, v_m_s=-3.0)
    assert isinstance(cwf, WindField)


def test_constant_wind_returns_uv_regardless_of_query():
    cwf = ConstantWindField(u_m_s=10.0, v_m_s=-3.0)
    t = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    assert cwf.get_wind(0.0, 0.0, 50000.0, t) == (10.0, -3.0)
    assert cwf.get_wind(40.0, -105.0, 30000.0, t) == (10.0, -3.0)
    assert cwf.get_wind_at_altitude(40.0, -105.0, 18000.0, t) == (10.0, -3.0)


def _synthetic_dataset():
    """A minimal 4-D dataset with linear u/v fields for interpolation tests.

    Three levels and three timestamps so every query in the test suite
    is interior — xarray.interp returns NaN at axis boundaries and
    divides by zero on single-element axes, neither of which is a
    production-code concern (real HRRR has 39 levels and many cycles).
    """
    xr = pytest.importorskip("xarray")

    lat = np.array([30.0, 40.0, 50.0])
    lon = np.array([-110.0, -100.0, -90.0])
    level = np.array([300.0, 500.0, 700.0])  # hPa
    time = np.array(
        ["2026-05-17T12:00", "2026-05-17T15:00", "2026-05-17T18:00"],
        dtype="datetime64[ns]",
    )

    # u = lat + lon/10 + level/100 + (t in hours since start)
    # v = -lat + lon/10
    lat_g, lon_g, level_g, time_g = np.meshgrid(
        lat, lon, level, time, indexing="ij"
    )
    t_hours = ((time_g - time_g.min()).astype("timedelta64[h]")).astype(float)
    u = lat_g + lon_g / 10.0 + level_g / 100.0 + t_hours
    v = -lat_g + lon_g / 10.0

    return xr.Dataset(
        data_vars={
            "u": (("latitude", "longitude", "isobaricInhPa", "time"), u),
            "v": (("latitude", "longitude", "isobaricInhPa", "time"), v),
        },
        coords={
            "latitude": lat,
            "longitude": lon,
            "isobaricInhPa": level,
            "time": time,
        },
    )


def test_xarray_wind_field_exact_grid_point():
    ds = _synthetic_dataset()
    wf = XarrayWindField(ds)
    t = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    # At (lat=40, lon=-100, p=500hPa=50000Pa, t=start):
    # u = 40 + (-100)/10 + 500/100 + 0 = 40 - 10 + 5 = 35
    # v = -40 + (-100)/10 = -40 - 10 = -50
    u, v = wf.get_wind(40.0, -100.0, 50000.0, t)
    assert u == pytest.approx(35.0, abs=1e-6)
    assert v == pytest.approx(-50.0, abs=1e-6)


def test_xarray_wind_field_linear_interpolation():
    """Halfway between two grid points should give the arithmetic mean."""
    ds = _synthetic_dataset()
    wf = XarrayWindField(ds)
    t = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    # Halfway between (lat=30) and (lat=40), other coords on-grid
    u1, _ = wf.get_wind(30.0, -100.0, 50000.0, t)
    u2, _ = wf.get_wind(40.0, -100.0, 50000.0, t)
    u_mid, _ = wf.get_wind(35.0, -100.0, 50000.0, t)
    assert u_mid == pytest.approx((u1 + u2) / 2.0, abs=1e-6)


def test_xarray_wind_field_altitude_to_pressure():
    """get_wind_at_altitude must use ISA to convert altitude → pressure."""
    ds = _synthetic_dataset()
    wf = XarrayWindField(ds)
    t = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    # Pick an altitude whose ISA pressure is clearly interior to the
    # synthetic level grid [300, 500, 700] hPa — 5000 m maps to ~540 hPa.
    from predictor.atmosphere import isa
    h = 5000.0
    p_pa = isa.pressure(h)
    u_p, v_p = wf.get_wind(40.0, -100.0, p_pa, t)
    u_h, v_h = wf.get_wind_at_altitude(40.0, -100.0, h, t)
    assert u_h == pytest.approx(u_p, rel=1e-6)
    assert v_h == pytest.approx(v_p, rel=1e-6)


def test_xarray_wind_field_normalizes_0_360_longitude():
    """A dataset stored on [0, 360] must answer queries on [−180, 180]."""
    xr = pytest.importorskip("xarray")
    lat = np.array([30.0, 40.0, 50.0])
    lon_360 = np.array([250.0, 260.0, 270.0])  # equivalent to −110, −100, −90
    level = np.array([300.0, 500.0, 700.0])
    time = np.array(
        ["2026-05-17T12:00", "2026-05-17T15:00"], dtype="datetime64[ns]",
    )
    u = np.full((3, 3, 3, 2), 7.5)
    v = np.full((3, 3, 3, 2), -2.5)
    ds = xr.Dataset(
        data_vars={
            "u": (("latitude", "longitude", "isobaricInhPa", "time"), u),
            "v": (("latitude", "longitude", "isobaricInhPa", "time"), v),
        },
        coords={
            "latitude": lat,
            "longitude": lon_360,
            "isobaricInhPa": level,
            "time": time,
        },
    )
    wf = XarrayWindField(ds)
    t = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    u, v = wf.get_wind(40.0, -100.0, 50000.0, t)
    assert u == pytest.approx(7.5)
    assert v == pytest.approx(-2.5)
