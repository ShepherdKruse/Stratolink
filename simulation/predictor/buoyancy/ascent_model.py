"""
Vertical ascent model: integrate buoyancy − weight − drag with RK4.

Used as a ground-truth check on ``float_solver`` — given an initial
state below the predicted float altitude, simulate vertical motion
until ascent velocity drops below 0.1 m/s. The terminal altitude must
match :func:`predictor.buoyancy.float_solver.compute_float_altitude`
to within damped-oscillation tolerance.

Constant envelope volume is assumed (superpressure / fully taut).
Cross-sectional area is derived from the equivalent-volume sphere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from predictor.atmosphere import isa


# Standard sphere drag coefficient
CD_SPHERE = 0.47


@dataclass(frozen=True)
class AscentState:
    """One sample on the vertical trajectory.

    Attributes
    ----------
    t_s : float
        Time since launch [s].
    altitude_m : float
        Altitude above sea level [m].
    velocity_m_s : float
        Vertical velocity, positive = up [m/s].
    """

    t_s: float
    altitude_m: float
    velocity_m_s: float


@dataclass(frozen=True)
class AscentInitialConditions:
    """Initial state for :func:`simulate_ascent`.

    Attributes
    ----------
    altitude_m : float
        Starting altitude [m]. Must be in the USSA-1976 valid range.
    velocity_m_s : float
        Starting vertical velocity [m/s]. Positive = up.
    envelope_volume_m3 : float
        Constant (rigid) envelope volume [m^3].
    system_mass_kg : float
        Non-gas system mass [kg].
    gas_mass_kg : float
        Lift-gas mass [kg].
    """

    altitude_m: float
    velocity_m_s: float
    envelope_volume_m3: float
    system_mass_kg: float
    gas_mass_kg: float


def _sphere_cross_section_m2(volume_m3: float) -> float:
    """Cross-sectional area of a sphere of given volume [m^2]."""
    r = (3.0 * volume_m3 / (4.0 * math.pi)) ** (1.0 / 3.0)
    return math.pi * r * r


def _vertical_accel(
    altitude_m: float,
    velocity_m_s: float,
    volume_m3: float,
    total_mass_kg: float,
    area_m2: float,
) -> float:
    """Net vertical acceleration [m/s^2], positive = up.

    Forces: buoyancy ρ·V·g, weight m·g, quadratic drag opposing motion.
    """
    # Clamp to atmosphere validity so the integrator can briefly excurse
    # past the top of the model without raising — physically the balloon
    # is decelerating hard there anyway.
    h_eval = min(max(altitude_m, isa.H_MIN_M), isa.H_MAX_M)
    rho = isa.density(h_eval)
    f_buoy = rho * volume_m3 * isa.G0_M_S2
    f_grav = total_mass_kg * isa.G0_M_S2
    f_drag = 0.5 * rho * velocity_m_s * abs(velocity_m_s) * CD_SPHERE * area_m2
    return (f_buoy - f_grav - f_drag) / total_mass_kg


def simulate_ascent(
    initial_conditions: AscentInitialConditions,
    dt: float = 1.0,
    max_time_s: float = 7200.0,
    float_velocity_m_s: float = 0.1,
    min_climb_m: float = 100.0,
) -> list[AscentState]:
    """Integrate the vertical equation of motion with RK4.

    Parameters
    ----------
    initial_conditions : AscentInitialConditions
        Starting state and balloon parameters.
    dt : float
        Time step for the RK4 integrator [s]. 1 s is well below the
        natural buoyancy time scale for pico-balloons.
    max_time_s : float
        Safety cap on integration time [s].
    float_velocity_m_s : float
        Termination threshold — once ``|v| < float_velocity_m_s`` and
        the balloon has climbed at least ``min_climb_m`` above its
        starting altitude, the integration stops.
    min_climb_m : float
        Minimum climb above the launch altitude before the velocity
        termination check fires. Prevents early termination during the
        first integration step when v starts at 0.

    Returns
    -------
    list[AscentState]
        Samples at ``dt``-second intervals, including the initial and
        terminal states.
    """
    total_mass = initial_conditions.system_mass_kg + initial_conditions.gas_mass_kg
    if total_mass <= 0.0:
        raise ValueError("Total mass (system + gas) must be positive.")
    area = _sphere_cross_section_m2(initial_conditions.envelope_volume_m3)

    h = initial_conditions.altitude_m
    v = initial_conditions.velocity_m_s
    t = 0.0
    h0 = h
    history: list[AscentState] = [AscentState(t, h, v)]

    def accel(h_: float, v_: float) -> float:
        return _vertical_accel(
            h_, v_,
            initial_conditions.envelope_volume_m3,
            total_mass,
            area,
        )

    while t < max_time_s:
        # RK4 on state (h, v) with derivatives (v, a(h, v))
        k1h, k1v = v, accel(h, v)
        k2h, k2v = v + 0.5 * dt * k1v, accel(h + 0.5 * dt * k1h, v + 0.5 * dt * k1v)
        k3h, k3v = v + 0.5 * dt * k2v, accel(h + 0.5 * dt * k2h, v + 0.5 * dt * k2v)
        k4h, k4v = v + dt * k3v, accel(h + dt * k3h, v + dt * k3v)

        h += dt * (k1h + 2.0 * k2h + 2.0 * k3h + k4h) / 6.0
        v += dt * (k1v + 2.0 * k2v + 2.0 * k3v + k4v) / 6.0
        t += dt

        # Hard floors so the integrator doesn't excurse past USSA validity
        if h > isa.H_MAX_M:
            h = isa.H_MAX_M
            v = min(v, 0.0)
        elif h < isa.H_MIN_M:
            h = isa.H_MIN_M
            v = max(v, 0.0)

        history.append(AscentState(t, h, v))

        if abs(v) < float_velocity_m_s and (h - h0) > min_climb_m:
            break

    return history
