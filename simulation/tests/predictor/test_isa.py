"""Tests for the USSA-1976 atmosphere implementation.

Reference values are from NASA TM-X-74335 "U.S. Standard Atmosphere, 1976".
Tolerance is 0.1 % as required by ``predictor-spec.md``.
"""

from __future__ import annotations

import math

import pytest

from predictor.atmosphere import isa


# (altitude_m, T_K, P_Pa, rho_kg_m3) from USSA-1976 reference table.
# Layer-boundary points (0, 11, 20 km) and three interior sample points.
REFERENCE_TABLE: list[tuple[float, float, float, float]] = [
    (    0.0, 288.150, 101325.0, 1.2250),
    ( 5000.0, 255.650,  54019.6, 0.73612),
    (11000.0, 216.650,  22632.06, 0.36391),
    (15000.0, 216.650,  12044.6, 0.19367),
    (20000.0, 216.650,   5474.89, 0.088035),
    (25000.0, 221.650,   2511.02, 0.039466),
    (32000.0, 228.650,    868.019, 0.013225),
]

TOL = 1e-3  # 0.1 %


def _rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b)


@pytest.mark.parametrize("h, T_ref, P_ref, rho_ref", REFERENCE_TABLE)
def test_temperature_matches_ussa_table(h, T_ref, P_ref, rho_ref):
    assert _rel(isa.temperature(h), T_ref) < TOL, (
        f"T({h} m) = {isa.temperature(h):.4f} K vs ref {T_ref:.4f} K"
    )


@pytest.mark.parametrize("h, T_ref, P_ref, rho_ref", REFERENCE_TABLE)
def test_pressure_matches_ussa_table(h, T_ref, P_ref, rho_ref):
    assert _rel(isa.pressure(h), P_ref) < TOL, (
        f"P({h} m) = {isa.pressure(h):.4f} Pa vs ref {P_ref:.4f} Pa"
    )


@pytest.mark.parametrize("h, T_ref, P_ref, rho_ref", REFERENCE_TABLE)
def test_density_matches_ussa_table(h, T_ref, P_ref, rho_ref):
    assert _rel(isa.density(h), rho_ref) < TOL, (
        f"ρ({h} m) = {isa.density(h):.6f} kg/m^3 vs ref {rho_ref:.6f} kg/m^3"
    )


def test_pressure_decreases_monotonically():
    altitudes = [0, 1000, 5000, 11000, 15000, 20000, 25000, 30000, 32000]
    pressures = [isa.pressure(h) for h in altitudes]
    for prev, curr in zip(pressures, pressures[1:]):
        assert curr < prev, f"Pressure not monotonic: {pressures}"


def test_density_decreases_monotonically():
    altitudes = [0, 1000, 5000, 11000, 15000, 20000, 25000, 30000, 32000]
    densities = [isa.density(h) for h in altitudes]
    for prev, curr in zip(densities, densities[1:]):
        assert curr < prev, f"Density not monotonic: {densities}"


def test_altitude_from_pressure_roundtrip():
    """altitude_from_pressure(pressure(h)) ≈ h across the supported range."""
    for h in [0.0, 1000.0, 5000.0, 10999.0, 11000.0, 11001.0,
              15000.0, 19999.0, 20000.0, 20001.0, 25000.0, 31999.0]:
        p = isa.pressure(h)
        h_back = isa.altitude_from_pressure(p)
        assert math.isclose(h, h_back, abs_tol=1e-3), (
            f"Roundtrip failed at h={h}: got {h_back:.4f} m"
        )


def test_below_sea_level_raises():
    with pytest.raises(ValueError, match="below sea level"):
        isa.temperature(-1.0)


def test_above_32km_raises():
    with pytest.raises(ValueError, match="32 km"):
        isa.pressure(32001.0)


def test_layer_seam_continuity():
    """Pressure and density must be continuous at 11 km and 20 km seams."""
    for h_seam in [11000.0, 20000.0]:
        p_below = isa.pressure(h_seam - 1e-6)
        p_above = isa.pressure(h_seam + 1e-6)
        assert math.isclose(p_below, p_above, rel_tol=1e-6)
        rho_below = isa.density(h_seam - 1e-6)
        rho_above = isa.density(h_seam + 1e-6)
        assert math.isclose(rho_below, rho_above, rel_tol=1e-6)
