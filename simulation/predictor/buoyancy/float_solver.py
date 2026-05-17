"""
Float-altitude solver for a superpressure pico-balloon.

Given a rigid (fully expanded) envelope volume, the total system mass,
and a USSA-1976 atmosphere, find the altitude where buoyancy equals
weight. Equilibrium condition:

    ρ_air(h) · V_env = m_system + m_gas

The lift gas type does not enter the equilibrium equation directly —
it only affects how much gas mass is required to inflate the envelope
to its rigid volume and what the internal gas pressure is at float.
We return both as diagnostics so callers can sanity-check that the
balloon is actually superpressure (``gas_pressure_pa > ambient_pressure_pa``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scipy.optimize import brentq

from predictor.atmosphere import isa


# Molar masses [kg/mol]
M_H2_KG_MOL = 0.002016
M_HE_KG_MOL = 0.004003

# Universal gas constant [J/(mol·K)]
R_UNIVERSAL_J_MOL_K = 8.31446

LiftGas = Literal["H2", "He"]


@dataclass(frozen=True)
class FloatResult:
    """Solution of the float-altitude equation.

    Attributes
    ----------
    altitude_m : float
        Equilibrium altitude in metres above sea level.
    air_density_kg_m3 : float
        Ambient air density at the float altitude (equals
        ``m_total / envelope_volume`` by construction).
    gas_pressure_pa : float
        Internal lift-gas pressure at the float altitude, from the
        ideal-gas law with the supplied gas mass and envelope volume.
    ambient_pressure_pa : float
        Atmospheric pressure at the float altitude.
    """

    altitude_m: float
    air_density_kg_m3: float
    gas_pressure_pa: float
    ambient_pressure_pa: float


def molar_mass(gas: LiftGas) -> float:
    """Molar mass of the lift gas in kg/mol.

    Parameters
    ----------
    gas : {'H2', 'He'}

    Returns
    -------
    float
        Molar mass in kg/mol.
    """
    if gas == "H2":
        return M_H2_KG_MOL
    if gas == "He":
        return M_HE_KG_MOL
    raise ValueError(f"Unsupported lift gas: {gas!r}; expected 'H2' or 'He'.")


def compute_float_altitude(
    envelope_volume_m3: float,
    system_mass_kg: float,
    lift_gas: LiftGas,
    gas_mass_kg: float,
) -> FloatResult:
    """Compute the equilibrium altitude of a superpressure balloon.

    Parameters
    ----------
    envelope_volume_m3 : float
        Rigid (fully expanded) envelope volume [m^3]. Assumed constant
        with altitude — appropriate for superpressure balloons whose
        envelope is taut at all altitudes of interest.
    system_mass_kg : float
        Total non-gas system mass [kg]: payload, electronics, battery,
        envelope material, antenna, ballast. Excludes the lift gas itself.
    lift_gas : {'H2', 'He'}
        Lift gas. Affects only the reported gas pressure; the float
        altitude depends solely on ``m_total / V_env``.
    gas_mass_kg : float
        Mass of lift gas inside the envelope [kg].

    Returns
    -------
    FloatResult
        Equilibrium altitude and supporting diagnostics.

    Raises
    ------
    ValueError
        If ``m_total / V_env`` is outside the air density range
        ``[ρ(32 km), ρ(0)]`` — i.e. the balloon is too heavy to leave
        the ground or too light to reach equilibrium below 32 km.
    """
    if envelope_volume_m3 <= 0.0:
        raise ValueError("envelope_volume_m3 must be positive.")
    if system_mass_kg < 0.0:
        raise ValueError("system_mass_kg must be non-negative.")
    if gas_mass_kg < 0.0:
        raise ValueError("gas_mass_kg must be non-negative.")

    m_total = system_mass_kg + gas_mass_kg
    target_rho = m_total / envelope_volume_m3

    rho_floor = isa.density(isa.H_MAX_M)
    rho_ceil = isa.density(isa.H_MIN_M)
    if target_rho > rho_ceil:
        raise ValueError(
            f"System is too heavy to leave sea level: required ρ = "
            f"{target_rho:.4f} kg/m^3 exceeds sea-level air density "
            f"{rho_ceil:.4f} kg/m^3."
        )
    if target_rho < rho_floor:
        raise ValueError(
            f"System is too light to settle below 32 km: required ρ = "
            f"{target_rho:.6f} kg/m^3 is below the 32 km air density "
            f"{rho_floor:.6f} kg/m^3."
        )

    altitude_m = brentq(
        lambda h: isa.density(h) - target_rho,
        isa.H_MIN_M,
        isa.H_MAX_M,
        xtol=1e-3,  # 1 mm — well below any relevant scale
    )

    p_ambient = isa.pressure(altitude_m)
    T = isa.temperature(altitude_m)
    n_gas_mol = gas_mass_kg / molar_mass(lift_gas)
    p_gas = n_gas_mol * R_UNIVERSAL_J_MOL_K * T / envelope_volume_m3

    return FloatResult(
        altitude_m=altitude_m,
        air_density_kg_m3=target_rho,
        gas_pressure_pa=p_gas,
        ambient_pressure_pa=p_ambient,
    )
