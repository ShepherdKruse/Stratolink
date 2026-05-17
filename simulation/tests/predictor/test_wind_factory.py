"""Tests for the HRRR/GFS wind-field orchestrator.

The factory does no network I/O directly — it calls the HRRR and GFS
clients. We exercise the orchestration logic (CONUS detection,
altitude gating, level subsetting, HRRR-to-GFS fallback) by
monkeypatching those clients with synthetic-dataset stubs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

xr = pytest.importorskip("xarray")

from predictor.weather import wind_factory
from predictor.weather.hrrr_client import HRRRCycle
from predictor.weather.gfs_client import GFSCycle


T_TARGET = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def _fake_hrrr_dataset(levels_mb, t0):
    """Synthetic HRRR-shaped Dataset for one fxx snapshot."""
    n_y, n_x = 4, 5
    lat2d = np.tile(np.linspace(30.0, 50.0, n_y), (n_x, 1)).T
    lon2d = np.tile(np.linspace(-110.0, -90.0, n_x), (n_y, 1))
    n_l = len(levels_mb)
    u = np.full((n_l, n_y, n_x), 7.0, dtype=np.float32)
    v = np.full((n_l, n_y, n_x), -3.0, dtype=np.float32)
    return xr.Dataset(
        data_vars={
            "u": (("isobaricInhPa", "y", "x"), u),
            "v": (("isobaricInhPa", "y", "x"), v),
        },
        coords={
            "isobaricInhPa": np.asarray(levels_mb, dtype=float),
            "latitude": (("y", "x"), lat2d),
            "longitude": (("y", "x"), lon2d),
            "time": np.datetime64(t0.replace(tzinfo=None), "ns"),
        },
    )


def _fake_gfs_dataset(levels_mb, t0):
    """Synthetic GFS-shaped Dataset (1-D lat/lon) for one fxx snapshot."""
    lat = np.linspace(-90.0, 90.0, 5)
    lon = np.linspace(0.0, 358.5, 5)  # 0-360 convention
    n_l = len(levels_mb)
    u = np.full((n_l, 5, 5), 11.0, dtype=np.float32)
    v = np.full((n_l, 5, 5), 4.0, dtype=np.float32)
    return xr.Dataset(
        data_vars={
            "u": (("isobaricInhPa", "latitude", "longitude"), u),
            "v": (("isobaricInhPa", "latitude", "longitude"), v),
        },
        coords={
            "isobaricInhPa": np.asarray(levels_mb, dtype=float),
            "latitude": lat,
            "longitude": lon,
            "time": np.datetime64(t0.replace(tzinfo=None), "ns"),
        },
    )


def _install_hrrr_stubs(monkeypatch, tmp_path):
    """Make the HRRR client return a known cycle and a synthetic open."""
    cycle = HRRRCycle(cycle_dt=T_TARGET.replace(minute=0))

    def fake_latest(target_time, lookback_hours=24):
        return SimpleNamespace(cycle=cycle, fxx=0, valid_time=target_time)

    def fake_download(c, fxx, cache_dir, levels_mb=None):
        path = Path(tmp_path) / f"hrrr_f{fxx:02d}.grib2"
        path.touch()
        return path

    def fake_open(path):
        # The factory will later sel(isobaricInhPa=...); return all the
        # levels the factory could plausibly ask for so that selection
        # always succeeds.
        levels = [
            1013, 1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750,
            725, 700, 675, 650, 625, 600, 575, 550, 525, 500, 475, 450,
            425, 400, 375, 350, 325, 300, 275, 250, 225, 200, 175, 150,
            125, 100, 75, 50,
        ]
        return _fake_hrrr_dataset(levels, T_TARGET)

    monkeypatch.setattr(wind_factory, "hrrr_latest", fake_latest)
    monkeypatch.setattr(wind_factory, "hrrr_download", fake_download)
    # The HRRRWindField.from_files path also calls hrrr_client.open_pressure_levels
    import predictor.weather.hrrr_wind_field as hwf
    monkeypatch.setattr("predictor.weather.hrrr_client.open_pressure_levels", fake_open)
    return cycle


def _install_gfs_stubs(monkeypatch, tmp_path):
    """Make the GFS client return a known cycle and synthetic data."""
    cycle = GFSCycle(cycle_dt=T_TARGET.replace(hour=6, minute=0))

    def fake_latest_before(now_utc, latency_padding_h=4.0):
        return cycle

    def fake_download(c, fxx, cache_dir, levels_mb=None, **kwargs):
        path = Path(tmp_path) / f"gfs_f{fxx:03d}.grib2"
        path.touch()
        return path

    def fake_open(grib_path, indexpath=""):
        levels = list(wind_factory.GFS_LEVELS_HPA)
        return _fake_gfs_dataset(levels, T_TARGET)

    monkeypatch.setattr(wind_factory.gfs_client, "latest_cycle_before", fake_latest_before)
    monkeypatch.setattr(wind_factory.gfs_client, "download_uv_pressure_levels", fake_download)
    monkeypatch.setattr(wind_factory.gfs_client, "open_pressure_levels", fake_open)
    return cycle


def test_conus_low_altitude_picks_hrrr(monkeypatch, tmp_path):
    _install_hrrr_stubs(monkeypatch, tmp_path)
    result = wind_factory.build_wind_field(
        target_time=T_TARGET,
        duration_hours=3.0,
        lat=40.0,
        lon=-105.0,
        altitude_m=10000.0,
        cache_dir=tmp_path,
    )
    assert result.metadata.source == "hrrr"
    assert result.metadata.region == "conus"
    # HRRR top is 75 hPa; the level subset should not include anything lower
    for lv in result.metadata.levels_hpa:
        assert lv >= wind_factory.HRRR_TOP_HPA


def test_outside_conus_picks_gfs(monkeypatch, tmp_path):
    _install_gfs_stubs(monkeypatch, tmp_path)
    result = wind_factory.build_wind_field(
        target_time=T_TARGET,
        duration_hours=3.0,
        lat=-25.0,
        lon=130.0,  # Australia
        altitude_m=10000.0,
        cache_dir=tmp_path,
    )
    assert result.metadata.source == "gfs"
    assert result.metadata.region == "global"


def test_high_altitude_picks_gfs_even_inside_conus(monkeypatch, tmp_path):
    """A 25 km float ≈ 25 hPa, below HRRR's 75 hPa gate — must use GFS."""
    _install_gfs_stubs(monkeypatch, tmp_path)
    result = wind_factory.build_wind_field(
        target_time=T_TARGET,
        duration_hours=3.0,
        lat=40.0,
        lon=-105.0,
        altitude_m=25000.0,
        cache_dir=tmp_path,
    )
    assert result.metadata.source == "gfs"


def test_hrrr_fallback_to_gfs_on_fetch_failure(monkeypatch, tmp_path):
    """If HRRR download raises, the factory must fall back to GFS, not crash."""
    cycle = HRRRCycle(cycle_dt=T_TARGET.replace(minute=0))

    def fake_latest(target_time, lookback_hours=24):
        return SimpleNamespace(cycle=cycle, fxx=0, valid_time=target_time)

    def failing_download(*a, **kw):
        raise FileNotFoundError("Simulated HRRR upload latency")

    monkeypatch.setattr(wind_factory, "hrrr_latest", fake_latest)
    monkeypatch.setattr(wind_factory, "hrrr_download", failing_download)
    _install_gfs_stubs(monkeypatch, tmp_path)

    result = wind_factory.build_wind_field(
        target_time=T_TARGET,
        duration_hours=3.0,
        lat=40.0,
        lon=-105.0,
        altitude_m=10000.0,
        cache_dir=tmp_path,
    )
    assert result.metadata.source == "gfs"


def test_prefer_hrrr_false_skips_hrrr(monkeypatch, tmp_path):
    """``prefer_hrrr=False`` must skip HRRR even when it would have been viable."""
    _install_gfs_stubs(monkeypatch, tmp_path)
    # Don't install HRRR stubs — if HRRR is attempted the test crashes
    result = wind_factory.build_wind_field(
        target_time=T_TARGET,
        duration_hours=3.0,
        lat=40.0,
        lon=-105.0,
        altitude_m=10000.0,
        cache_dir=tmp_path,
        prefer_hrrr=False,
    )
    assert result.metadata.source == "gfs"


def test_levels_subsetted_around_flight_altitude(monkeypatch, tmp_path):
    """The factory should request a small level window straddling the float."""
    _install_gfs_stubs(monkeypatch, tmp_path)
    # 20 km float → ~55 hPa target
    result = wind_factory.build_wind_field(
        target_time=T_TARGET,
        duration_hours=3.0,
        lat=-25.0,
        lon=130.0,
        altitude_m=20000.0,
        cache_dir=tmp_path,
    )
    lv = result.metadata.levels_hpa
    # 2 * HRRR_LEVEL_HALF_WINDOW + 1 = 7 levels
    assert len(lv) == 2 * wind_factory.HRRR_LEVEL_HALF_WINDOW + 1
    # All should be within an order of magnitude of the target
    target_hpa = 55.0
    for level in lv:
        assert 0.1 * target_hpa < level < 10.0 * target_hpa


def test_naive_target_time_raises(tmp_path):
    with pytest.raises(ValueError, match="UTC"):
        wind_factory.build_wind_field(
            target_time=datetime(2026, 5, 17, 12, 0),  # naive
            duration_hours=3.0,
            lat=40.0,
            lon=-105.0,
            altitude_m=10000.0,
            cache_dir=tmp_path,
        )


def test_conus_detection_boundary():
    """Bounding box should include typical CONUS launch sites and exclude obvious non-CONUS."""
    assert wind_factory._inside_conus(40.0, -105.0)   # Boulder, CO
    assert wind_factory._inside_conus(38.5, -77.0)    # DC
    assert wind_factory._inside_conus(34.0, -118.0)   # LA
    assert not wind_factory._inside_conus(60.0, -150.0)   # Alaska
    assert not wind_factory._inside_conus(-25.0, 130.0)   # Australia
    assert not wind_factory._inside_conus(0.0, 0.0)       # Atlantic
