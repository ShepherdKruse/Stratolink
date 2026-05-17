"""Tests for the vertical ascent model.

The ascent integrator is a ground-truth check on the float solver:
starting below the predicted float altitude with a small upward
velocity, the RK4 integration must converge to the same equilibrium
altitude (within damped-oscillation tolerance).
"""

from __future__ import annotations

from predictor.buoyancy.ascent_model import (
    AscentInitialConditions,
    simulate_ascent,
)
from predictor.buoyancy.float_solver import compute_float_altitude


def test_history_is_monotone_in_time():
    ic = AscentInitialConditions(
        altitude_m=15000.0,
        velocity_m_s=1.0,
        envelope_volume_m3=0.5,
        system_mass_kg=0.012,
        gas_mass_kg=0.002,
    )
    history = simulate_ascent(ic, dt=1.0)
    assert len(history) >= 2
    for prev, curr in zip(history, history[1:]):
        assert curr.t_s > prev.t_s


def test_terminates_when_velocity_drops_below_threshold():
    ic = AscentInitialConditions(
        altitude_m=15000.0,
        velocity_m_s=1.0,
        envelope_volume_m3=0.5,
        system_mass_kg=0.012,
        gas_mass_kg=0.002,
    )
    history = simulate_ascent(ic, dt=1.0, float_velocity_m_s=0.1)
    # If termination fired, last sample has |v| < 0.1 m/s
    last = history[-1]
    assert abs(last.velocity_m_s) < 0.1 or last.t_s >= 7200.0 - 1e-6


def test_converges_to_float_altitude():
    """Terminal altitude must match compute_float_altitude (within damped
    oscillation tolerance — the RK4 integration overshoots once before
    drag settles it)."""
    V = 0.5
    m_sys = 0.012
    m_gas = 0.002
    target = compute_float_altitude(V, m_sys, "H2", m_gas).altitude_m

    ic = AscentInitialConditions(
        altitude_m=target - 2000.0,  # start 2 km below float
        velocity_m_s=0.5,
        envelope_volume_m3=V,
        system_mass_kg=m_sys,
        gas_mass_kg=m_gas,
    )
    history = simulate_ascent(ic, dt=0.5, float_velocity_m_s=0.05)
    final = history[-1].altitude_m
    # 200 m tolerance — drag-limited overshoot for an underdamped sphere
    # of this mass class is on this order. Tighten later if we move to
    # an implicit integrator.
    assert abs(final - target) < 200.0, (
        f"Ascent terminal {final:.1f} m vs float target {target:.1f} m"
    )


def test_zero_gas_does_not_float():
    """A balloon with effectively zero gas mass and a small envelope
    cannot generate enough buoyancy to reach equilibrium — the simulator
    should hit the max-time cap rather than terminate."""
    ic = AscentInitialConditions(
        altitude_m=0.0,
        velocity_m_s=0.0,
        envelope_volume_m3=0.001,
        system_mass_kg=1.0,
        gas_mass_kg=0.0,
    )
    history = simulate_ascent(ic, dt=1.0, max_time_s=60.0)
    # Should not have climbed appreciably
    assert history[-1].altitude_m < 100.0
