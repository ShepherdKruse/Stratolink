"""
U.S. Standard Atmosphere 1976 (USSA-1976), valid 0–32 km.

Three-layer model covering the troposphere, tropopause, and lower
stratosphere. All inputs are altitude in metres above mean sea level
(treated here as geopotential altitude — the standard reports values
to within 140 m of geometric altitude across the supported range,
inside the 0.1 % tolerance required by the test suite). All outputs
are in SI base units.

References
----------
NASA TM-X-74335, "U.S. Standard Atmosphere, 1976" (NOAA/NASA/USAF, 1976).
Reference values used in ``tests/predictor/test_isa.py`` come from the
same document.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Sea-level reference conditions
T0_K = 288.15        # base temperature [K]
P0_PA = 101325.0     # base pressure [Pa]

# Physical constants
G0_M_S2 = 9.80665           # standard gravity [m/s^2]
R_AIR_J_KG_K = 287.0528     # specific gas constant for dry air [J/(kg·K)]

# USSA-1976 supported range
H_MIN_M = 0.0
H_MAX_M = 32000.0


@dataclass(frozen=True)
class _Layer:
    """One USSA-1976 atmospheric layer."""

    h_base_m: float       # altitude at base of layer [m]
    T_base_K: float       # temperature at base of layer [K]
    P_base_Pa: float      # pressure at base of layer [Pa]
    lapse_K_per_m: float  # dT/dh in this layer [K/m]; 0 for isothermal


def _build_layers() -> tuple[_Layer, ...]:
    """Build the three-layer USSA-1976 table for 0–32 km.

    Each layer's base pressure is integrated from the previous layer
    using the same formula ``pressure()`` uses, so the table is
    self-consistent — no risk of seam discontinuity at 11 km or 20 km.
    """
    layers = [
        _Layer(
            h_base_m=0.0,
            T_base_K=T0_K,
            P_base_Pa=P0_PA,
            lapse_K_per_m=-0.0065,
        )
    ]

    # (h_top of layer, lapse rate of the next layer up [K/m])
    transitions = (
        (11000.0, 0.0),     # tropopause: isothermal at 216.65 K
        (20000.0, 0.001),   # lower stratosphere: +1 K/km
    )

    for h_top, next_lapse in transitions:
        prev = layers[-1]
        T_top = prev.T_base_K + prev.lapse_K_per_m * (h_top - prev.h_base_m)
        if prev.lapse_K_per_m == 0.0:
            P_top = prev.P_base_Pa * math.exp(
                -G0_M_S2 * (h_top - prev.h_base_m)
                / (R_AIR_J_KG_K * prev.T_base_K)
            )
        else:
            P_top = prev.P_base_Pa * (T_top / prev.T_base_K) ** (
                -G0_M_S2 / (R_AIR_J_KG_K * prev.lapse_K_per_m)
            )
        layers.append(
            _Layer(
                h_base_m=h_top,
                T_base_K=T_top,
                P_base_Pa=P_top,
                lapse_K_per_m=next_lapse,
            )
        )
    return tuple(layers)


_LAYERS: tuple[_Layer, ...] = _build_layers()


def _find_layer(h_m: float) -> _Layer:
    """Return the layer containing ``h_m``. Raises if outside 0–32 km."""
    if h_m < H_MIN_M:
        raise ValueError(
            f"Altitude {h_m} m is below sea level; USSA-1976 unsupported."
        )
    if h_m > H_MAX_M:
        raise ValueError(
            f"Altitude {h_m} m exceeds the USSA-1976 32 km upper bound."
        )
    # Walk down so the lowest layer with h_base <= h_m wins
    for i in range(len(_LAYERS) - 1, -1, -1):
        if h_m >= _LAYERS[i].h_base_m:
            return _LAYERS[i]
    return _LAYERS[0]  # unreachable for h_m >= 0


def temperature(altitude_m: float) -> float:
    """Air temperature at the given altitude.

    Parameters
    ----------
    altitude_m : float
        Altitude above sea level in metres. Valid range ``[0, 32000]``.

    Returns
    -------
    float
        Air temperature in Kelvin.
    """
    layer = _find_layer(altitude_m)
    return layer.T_base_K + layer.lapse_K_per_m * (altitude_m - layer.h_base_m)


def pressure(altitude_m: float) -> float:
    """Air pressure at the given altitude.

    Parameters
    ----------
    altitude_m : float
        Altitude above sea level in metres. Valid range ``[0, 32000]``.

    Returns
    -------
    float
        Air pressure in Pascals.
    """
    layer = _find_layer(altitude_m)
    if layer.lapse_K_per_m == 0.0:
        return layer.P_base_Pa * math.exp(
            -G0_M_S2 * (altitude_m - layer.h_base_m)
            / (R_AIR_J_KG_K * layer.T_base_K)
        )
    T = layer.T_base_K + layer.lapse_K_per_m * (altitude_m - layer.h_base_m)
    return layer.P_base_Pa * (T / layer.T_base_K) ** (
        -G0_M_S2 / (R_AIR_J_KG_K * layer.lapse_K_per_m)
    )


def density(altitude_m: float) -> float:
    """Air mass density at the given altitude.

    Parameters
    ----------
    altitude_m : float
        Altitude above sea level in metres. Valid range ``[0, 32000]``.

    Returns
    -------
    float
        Air density in kg/m^3, computed as ``P / (R_air · T)``.
    """
    return pressure(altitude_m) / (R_AIR_J_KG_K * temperature(altitude_m))


def altitude_from_pressure(p_pa: float) -> float:
    """Inverse mapping: altitude corresponding to a given air pressure.

    Useful for converting NWP pressure levels to altitudes when
    sampling a ``WindField``.

    Parameters
    ----------
    p_pa : float
        Pressure in Pascals. Must lie within the pressure range of the
        0–32 km USSA-1976 model.

    Returns
    -------
    float
        Altitude in metres above sea level.
    """
    p_top = pressure(H_MAX_M)
    if p_pa > P0_PA:
        raise ValueError(
            f"Pressure {p_pa} Pa exceeds sea-level pressure "
            f"{P0_PA} Pa; outside USSA-1976 range."
        )
    if p_pa < p_top:
        raise ValueError(
            f"Pressure {p_pa} Pa is below 32 km pressure "
            f"{p_top:.4f} Pa; outside USSA-1976 range."
        )

    # Pressure decreases monotonically with altitude, so walk layers
    # bottom-up and pick the one whose [P_top, P_base] bracket contains p_pa.
    for i, layer in enumerate(_LAYERS):
        if i + 1 < len(_LAYERS):
            upper_P = _LAYERS[i + 1].P_base_Pa
        else:
            upper_P = p_top
        if upper_P <= p_pa <= layer.P_base_Pa:
            if layer.lapse_K_per_m == 0.0:
                return layer.h_base_m + (
                    -R_AIR_J_KG_K * layer.T_base_K / G0_M_S2
                    * math.log(p_pa / layer.P_base_Pa)
                )
            ratio = (p_pa / layer.P_base_Pa) ** (
                -R_AIR_J_KG_K * layer.lapse_K_per_m / G0_M_S2
            )
            return layer.h_base_m + layer.T_base_K / layer.lapse_K_per_m * (
                ratio - 1.0
            )
    raise AssertionError("Unreachable: pressure layer search fell through.")
