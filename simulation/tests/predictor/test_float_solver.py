"""Tests for the superpressure float-altitude solver."""

from __future__ import annotations

import math

import pytest

from predictor.atmosphere import isa
from predictor.buoyancy.float_solver import (
    M_H2_KG_MOL,
    M_HE_KG_MOL,
    compute_float_altitude,
    molar_mass,
)


def test_satisfies_hydrostatic_equilibrium():
    """ρ_air(result.altitude_m) · V must equal m_total to machine precision."""
    V = 0.5
    m_sys = 0.012
    m_gas = 0.002
    result = compute_float_altitude(V, m_sys, "H2", m_gas)
    rho_check = isa.density(result.altitude_m)
    assert math.isclose(rho_check * V, m_sys + m_gas, rel_tol=1e-6)
    assert math.isclose(result.air_density_kg_m3, rho_check, rel_tol=1e-6)


def test_float_altitude_independent_of_gas_type():
    """Float altitude depends only on m_total / V, not on gas species."""
    V = 0.5
    m_sys = 0.012
    m_gas = 0.002
    h_h2 = compute_float_altitude(V, m_sys, "H2", m_gas).altitude_m
    h_he = compute_float_altitude(V, m_sys, "He", m_gas).altitude_m
    assert math.isclose(h_h2, h_he, abs_tol=1e-3)


def test_heavier_system_floats_lower():
    """Adding mass without changing volume lowers the equilibrium altitude."""
    V = 0.5
    light = compute_float_altitude(V, 0.012, "H2", 0.002)
    heavy = compute_float_altitude(V, 0.020, "H2", 0.002)
    assert heavy.altitude_m < light.altitude_m


def test_larger_envelope_floats_higher():
    """Holding mass constant, a larger envelope reaches a higher altitude."""
    m_sys = 0.012
    m_gas = 0.002
    small = compute_float_altitude(0.4, m_sys, "H2", m_gas)
    large = compute_float_altitude(0.6, m_sys, "H2", m_gas)
    assert large.altitude_m > small.altitude_m


def test_too_heavy_raises():
    with pytest.raises(ValueError, match="too heavy"):
        # 100 kg per m^3 is far above sea-level air density
        compute_float_altitude(0.5, 50.0, "H2", 0.002)


def test_too_light_raises():
    with pytest.raises(ValueError, match="too light"):
        # Below 32 km air density
        compute_float_altitude(1.0, 0.001, "H2", 0.0001)


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        compute_float_altitude(0.0, 0.012, "H2", 0.002)
    with pytest.raises(ValueError):
        compute_float_altitude(0.5, -0.001, "H2", 0.002)
    with pytest.raises(ValueError):
        compute_float_altitude(0.5, 0.012, "H2", -0.001)


def test_molar_mass_values():
    assert molar_mass("H2") == M_H2_KG_MOL
    assert molar_mass("He") == M_HE_KG_MOL


def test_unsupported_gas_raises():
    with pytest.raises(ValueError, match="Unsupported lift gas"):
        compute_float_altitude(0.5, 0.012, "Ar", 0.002)  # type: ignore[arg-type]


def test_default_picoballoon_floats_in_stratosphere():
    """The agreed defaults (0.5 m^3, 12 g, H2, 2 g) must reach the stratosphere.

    This catches the cardinal error of accidentally producing a sea-level
    result when units or signs are off.
    """
    result = compute_float_altitude(0.5, 0.012, "H2", 0.002)
    assert 20000.0 < result.altitude_m < 32000.0


def test_gas_pressure_diagnostic_reasonable():
    """For the default fill, the gas pressure at float should be on the order
    of the ambient pressure (it's nearly tautly inflated, not wildly off)."""
    result = compute_float_altitude(0.5, 0.012, "H2", 0.002)
    ratio = result.gas_pressure_pa / result.ambient_pressure_pa
    # Loose check — we mainly want to catch sign errors / unit confusion.
    assert 0.1 < ratio < 10.0
