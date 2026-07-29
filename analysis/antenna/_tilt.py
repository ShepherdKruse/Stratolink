"""Pattern rotation + spin-averaging for the mounting-angle study (Part D).

The antenna pattern is fixed to the payload BODY. How the payload hangs sets the
body's tilt from vertical; the payload then spins freely about the vertical
(Part B-0: stable hang + yaw spin). So the gain seen toward a gateway at a given
world-frame depression angle is the body-frame gain at the direction you get by:

  1. taking the world direction (depression delta below horizontal, azimuth A),
  2. rotating it into the body frame by the hang-tilt tau about a horizontal axis,
  3. looking up the NEC pattern gain there,
  4. averaging over the uniform spin (A uniform 0..360) and over the empirical
     distribution of gateway depressions.

We do the rotation with real 3-D direction vectors (no small-angle/cos approx).

Frame: world +Z = up. A gateway at depression `dep` below the local horizontal,
at world-azimuth `A`, is the unit vector:
    d_world = (cos(-dep)cosA, cos(-dep)sinA, sin(-dep))      # points down-and-out
The body is tilted by `tau` about the world +Y axis (a fixed lean); spin is a
rotation `psi` about world +Z applied to the body. Equivalent: rotate the world
direction by -psi about Z then by -tau about Y to express it in the body frame,
then convert to (theta,phi) for the NEC lookup.
"""
from __future__ import annotations
import numpy as np


def _Rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _Ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1.0, 0], [-s, 0, c]])


def world_dir(dep_deg, az_deg):
    """Unit vector toward a gateway at `dep` below horizontal, azimuth `az`."""
    dep = np.radians(dep_deg); az = np.radians(az_deg)
    return np.array([np.cos(dep) * np.cos(az),
                     np.cos(dep) * np.sin(az),
                     -np.sin(dep)])


def body_theta_phi(dep_deg, az_deg, tau_deg, psi_deg):
    """Express a world gateway direction in the body frame and return NEC
    (theta, phi) degrees. tau = hang tilt (lean from vertical), psi = spin."""
    d = world_dir(dep_deg, az_deg)
    # body obtained from world by Rz(psi) then Ry(tau); to bring a world vector
    # into the body frame we apply the inverse: Ry(-tau) @ Rz(-psi).
    db = _Ry(np.radians(-tau_deg)) @ (_Rz(np.radians(-psi_deg)) @ d)
    x, y, z = db
    theta = np.degrees(np.arccos(np.clip(z, -1, 1)))     # from +z (body up)
    phi = np.degrees(np.arctan2(y, x)) % 360.0
    return theta, phi


def spin_avg_gain_dbi(pat, dep_deg, tau_deg, n_spin=72):
    """Mean LINEAR gain (returned in dBi) toward a gateway at depression `dep`,
    for hang-tilt `tau`, averaged over a full uniform spin."""
    lin = 0.0
    for psi in np.linspace(0, 360, n_spin, endpoint=False):
        th, ph = body_theta_phi(dep_deg, az_deg=0.0, tau_deg=tau_deg, psi_deg=psi)
        lin += 10 ** (pat.gain_at(th, ph) / 10.0)
    return 10 * np.log10(lin / n_spin)


def effective_gain_over_flight(pat, dep_weights, tau_deg, n_spin=72):
    """Spin- AND gateway-distribution-averaged effective gain (dBi) for a given
    hang tilt. dep_weights = array of empirical gateway depressions (deg)."""
    lin = 0.0
    cnt = 0
    for dep in dep_weights:
        for psi in np.linspace(0, 360, n_spin, endpoint=False):
            th, ph = body_theta_phi(dep, 0.0, tau_deg, psi)
            lin += 10 ** (pat.gain_at(th, ph) / 10.0)
            cnt += 1
    return 10 * np.log10(lin / cnt)
