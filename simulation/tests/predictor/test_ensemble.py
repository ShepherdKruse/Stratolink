"""Tests for the ensemble propagator.

Primary verification gate (per ``predictor-spec.md`` §Verification):
ensemble position spread must grow roughly as √t in a constant-wind
environment (so that the underlying deterministic motion contributes
no spread, isolating the noise-driven √t signature).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from predictor.trajectory.ensemble import (
    DEFAULT_N_MEMBERS,
    EnsembleResult,
    cep_radius_km,
    run_ensemble,
)
from predictor.trajectory.integrator import GeodeticPosition
from predictor.weather.wind_field import ConstantWindField


T0 = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def _baseline_args(**overrides):
    args = dict(
        initial_position=GeodeticPosition(40.0, -105.0, 20000.0),
        wind_field=ConstantWindField(u_m_s=10.0, v_m_s=0.0),
        duration_hours=6.0,
        start_time=T0,
        n_members=50,
        seed=42,
    )
    args.update(overrides)
    return args


def test_spread_grows_as_sqrt_t():
    """Phase 4 verification gate.

    Log-log slope of σ1(t) vs t must be ≈ 0.5 (allow 0.4–0.65). At very
    short t the constant initial-position σ dominates and shallows the
    slope; we restrict the fit to t ≥ 1 h where the Brownian wind term
    has overtaken it.
    """
    result = run_ensemble(**_baseline_args(n_members=200, duration_hours=10.0))
    sample_hours = [1.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    sigmas = []
    for h in sample_hours:
        idx = int(round(h * 3600.0 / 300.0))
        sigmas.append(result.summary[idx].sigma1_radius_km)
    log_t = np.log(sample_hours)
    log_s = np.log(sigmas)
    slope = float(np.polyfit(log_t, log_s, 1)[0])
    assert 0.4 < slope < 0.65, (
        f"log-log slope {slope:.3f} not √t-like (expect ~0.5). "
        f"sigmas={['%.2f' % s for s in sigmas]}"
    )


def test_default_member_count():
    result = run_ensemble(**_baseline_args(n_members=DEFAULT_N_MEMBERS))
    assert len(result.members) == DEFAULT_N_MEMBERS
    assert result.n_members == DEFAULT_N_MEMBERS


def test_summary_length_matches_members():
    result = run_ensemble(**_baseline_args())
    n_points = len(result.members[0].points)
    assert len(result.summary) == n_points


def test_sigma2_at_least_sigma1():
    result = run_ensemble(**_baseline_args())
    for p in result.summary:
        assert p.sigma2_radius_km >= p.sigma1_radius_km - 1e-9


def test_spread_at_t0_dominated_by_initial_position_sigma():
    """At t=0 only initial-position perturbations contribute. The 1σ
    radius should be near the configured ``initial_position_sigma_m``."""
    result = run_ensemble(**_baseline_args(initial_position_sigma_m=500.0))
    s0 = result.summary[0].sigma1_radius_km
    # 1σ of a 2D isotropic Gaussian projected to radius: σ_r ≈ σ · √(2 ln 2) at
    # the median; the empirical 68th percentile of |r| for N(0, σ²) in 2D ≈ 1.51σ
    # → 1.51·0.5 km ≈ 0.75 km. Loose check: should be within a factor of 2 of σ.
    assert 0.25 < s0 < 1.5, f"sigma1@t=0 = {s0:.3f} km outside expected range"


def test_zero_wind_perturbation_gives_zero_spread_from_wind():
    """With wind_sigma_m_s=0 and initial_position_sigma_m=0, all members
    follow the same deterministic trajectory → sigma1 == 0 at every t."""
    result = run_ensemble(**_baseline_args(
        wind_sigma_m_s=0.0,
        initial_position_sigma_m=0.0,
        altitude_sigma_m=0.0,
    ))
    for p in result.summary:
        assert p.sigma1_radius_km < 1e-6


def test_seed_makes_results_reproducible():
    a = run_ensemble(**_baseline_args(seed=123))
    b = run_ensemble(**_baseline_args(seed=123))
    for pa, pb in zip(a.summary, b.summary):
        assert pa.sigma1_radius_km == pytest.approx(pb.sigma1_radius_km, rel=1e-12)
        assert pa.lat_deg == pytest.approx(pb.lat_deg, abs=1e-12)
        assert pa.lon_deg == pytest.approx(pb.lon_deg, abs=1e-12)


def test_different_seeds_give_different_results():
    a = run_ensemble(**_baseline_args(seed=1))
    b = run_ensemble(**_baseline_args(seed=2))
    diffs = [abs(pa.sigma1_radius_km - pb.sigma1_radius_km)
             for pa, pb in zip(a.summary, b.summary)]
    assert max(diffs) > 1e-3


def test_median_tracks_unperturbed_trajectory():
    """The median of a symmetric-noise ensemble should track the
    deterministic constant-wind path closely."""
    result = run_ensemble(**_baseline_args(n_members=200))
    # After 1 h with 10 m/s east wind, deterministic displacement is 36 km east
    final_t_idx = int(round(3600.0 / 300.0))
    median_p = result.summary[final_t_idx]
    start = GeodeticPosition(40.0, -105.0, 20000.0)
    # Deterministic east drift in degrees
    expected_dlon = 36000.0 / (
        6371008.8 * math.cos(math.radians(start.lat_deg))
    ) * 180.0 / math.pi
    expected_lon = start.lon_deg + expected_dlon
    assert median_p.lon_deg == pytest.approx(expected_lon, abs=0.05)
    assert median_p.lat_deg == pytest.approx(start.lat_deg, abs=0.05)


def test_cep_radius_lookup_picks_nearest_horizon():
    spread = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]  # 5 minutes apart by default
    horizons = cep_radius_km(spread, [0.0, 0.25 / 60 * 1.0, 5 * 5 / 60.0])
    assert horizons[0.0] == 0.0


def test_invalid_n_members_raises():
    with pytest.raises(ValueError, match="n_members"):
        run_ensemble(**_baseline_args(n_members=1))
