"""Thin wrapper over PyNEC (NEC2 method-of-moments) for the antenna study.

Gives us: build a wire antenna, solve at a frequency, return the full
gain(theta, phi) pattern in dBi plus the feed-point impedance. Everything else
(scoring against the flight angle distribution, polarization, Monte-Carlo over
attitude) is built on top in 60_patterns.py.

Conventions (NEC standard spherical):
  theta = zenith angle from +z (0 = straight up, 90 = horizon, 180 = down)
  phi   = azimuth in the xy-plane
We model the antenna in its BODY frame with +z = "up out of the top of the
payload" when hung nominally; 50_attitude.py tells us the real tilt to apply.

Validation: build_dipole at 900 MHz must give ~2.15 dBi, Z~73+j42 (thin wire).
Run `python _nec.py` to self-test.
"""
from __future__ import annotations

import numpy as np

C_M = 299_792_458.0  # m/s


def wavelength_m(f_mhz: float) -> float:
    return C_M / (f_mhz * 1e6)


class Pattern:
    """A solved radiation pattern over a theta/phi grid."""
    def __init__(self, theta_deg, phi_deg, gain_dbi, z_in, f_mhz):
        self.theta = np.asarray(theta_deg)      # (nt,)
        self.phi = np.asarray(phi_deg)          # (np,)
        self.gain = np.asarray(gain_dbi)        # (nt, np) dBi (total, both pols)
        self.z_in = z_in                        # complex feed impedance
        self.f_mhz = f_mhz

    @property
    def peak_dbi(self):
        return float(np.nanmax(self.gain))

    def gain_at(self, theta_deg, phi_deg):
        """Bilinear-ish nearest lookup of gain (dBi) at a direction."""
        it = int(np.argmin(np.abs(self.theta - theta_deg)))
        ip = int(np.argmin(np.abs(self.phi - phi_deg)))
        return float(self.gain[it, ip])

    def vswr(self, z0=50.0):
        z = self.z_in
        gamma = abs((z - z0) / (z + z0))
        return (1 + gamma) / (1 - gamma) if gamma < 1 else np.inf

    def mismatch_loss_db(self, z0=50.0):
        z = self.z_in
        gamma = abs((z - z0) / (z + z0))
        # fraction of power accepted = 1 - |gamma|^2
        return -10 * np.log10(max(1e-6, 1 - gamma**2))


def _solve(build_fn, f_mhz, n_theta=181, n_phi=72, ground=None):
    """Run NEC for one geometry at one frequency, return a Pattern.

    build_fn(geo, wl) populates wires on the geometry object (meters).
    ground: None = free space; ('perfect',) = PEC ground at z=0;
            ('real', eps, sigma) = Sommerfeld real ground.
    """
    from PyNEC import nec_context
    ctx = nec_context()
    geo = ctx.get_geometry()
    wl = wavelength_m(f_mhz)
    feed_tag, feed_seg = build_fn(geo, wl)
    ctx.geometry_complete(1 if ground else 0)

    if ground is None:
        ctx.gn_card(-1, 0, 0, 0, 0, 0, 0, 0)         # free space
    elif ground[0] == "perfect":
        ctx.gn_card(1, 0, 0, 0, 0, 0, 0, 0)          # perfect ground
    else:
        _, eps, sigma = ground
        ctx.gn_card(0, 0, eps, sigma, 0, 0, 0, 0)    # finite ground

    ctx.ex_card(0, feed_tag, feed_seg, 0, 1.0, 0, 0, 0, 0, 0)
    ctx.fr_card(0, 1, f_mhz, 0)

    # theta sweep 0..180, phi sweep 0..360 (exclude duplicate 360)
    dt = 180.0 / (n_theta - 1)
    dp = 360.0 / n_phi
    ctx.rp_card(0, n_theta, n_phi, 0, 0, 0, 0, 0.0, 0.0, dt, dp, 0, 0)
    rp = ctx.get_radiation_pattern(0)
    gain = np.array(rp.get_gain())               # (n_theta, n_phi) dBi
    theta = np.linspace(0, 180, n_theta)
    phi = np.arange(n_phi) * dp

    ip = ctx.get_input_parameters(0)
    z = complex(ip.get_impedance()[0])
    return Pattern(theta, phi, gain, z, f_mhz)


# ---------------------------------------------------------------------------
# Antenna builders. All lengths in meters; +z is the nominal "up" body axis.
# Wire radius modeling the enameled Cu: AWG30 ~ 0.127 mm radius; use 0.0003 m.
# ---------------------------------------------------------------------------
WIRE_R = 0.0003  # 0.3 mm radius ~ enameled magnet wire
PCB_W = 0.0234   # 23.4 mm  measured board width  (Edge.Cuts)
PCB_H = 0.0573   # 57.3 mm  measured board height


def grid_rect(geo, tag0, p0, ux, uy, nu, nv, radius=0.0004):
    """Lay a node-connected wire-grid rectangle (NEC models a conductive sheet
    as a grid; wires must meet only at shared nodes, never cross mid-span).

    p0 = origin corner (x,y,z); ux,uy = the two edge VECTORS (m); nu,nv = cells.
    Returns the next free tag. Node (i,j) = p0 + i/nu*ux + j/nv*uy.
    """
    import numpy as _np
    p0 = _np.array(p0, float); ux = _np.array(ux, float); uy = _np.array(uy, float)
    tag = tag0
    def node(i, j):
        return p0 + (i / nu) * ux + (j / nv) * uy
    for j in range(nv + 1):              # edges along u
        for i in range(nu):
            a, b = node(i, j), node(i + 1, j)
            geo.wire(tag, 1, a[0], a[1], a[2], b[0], b[1], b[2], radius, 1, 1); tag += 1
    for i in range(nu + 1):              # edges along v
        for j in range(nv):
            a, b = node(i, j), node(i, j + 1)
            geo.wire(tag, 1, a[0], a[1], a[2], b[0], b[1], b[2], radius, 1, 1); tag += 1
    return tag


def build_dipole(geo, wl, total_len=None, seg=41):
    """Center-fed half-wave dipole along z (validation + candidate)."""
    L = (total_len or wl / 2) / 2
    geo.wire(1, seg, 0, 0, -L, 0, 0, +L, WIRE_R, 1, 1)
    return 1, seg // 2 + 1


def build_monopole_pcb(geo, wl, mono_len=None, seg=21):
    """Quarter-wave wire monopole fed against the actual PCB-sized ground plane,
    modeled with NEC surface patches (~23x57 mm). This is the 'what flew'
    candidate: a monopole whose counterpoise is far smaller than lambda/4, so it
    radiates poorly and asymmetrically. The wire rises in +z from board center.

    NEC requires a wire connecting to a surface patch to TOUCH the patch; we put
    the monopole base one tiny segment above z=0 and let the patches sit at z=0.
    Patches are built with the SM (multiple-patch) primitive via geo.sp/sm."""
    Lm = mono_len or wl / 4
    # Ground plane as a NODE-CONNECTED wire grid (NEC bonds wires that share an
    # endpoint; it rejects wires that cross mid-span). We draw each grid cell edge
    # as its own 1-seg wire so they meet only at nodes. Patches (SM card) do NOT
    # reliably bond to a feeding wire in NEC, which silently turns the model into
    # an isolated wire -> we use the grid instead. The monopole rises from the
    # center node so its base segment is galvanically tied to the counterpoise.
    nx, ny = 5, 9                      # grid nodes
    gr = 0.0004
    xs = np.linspace(-PCB_W/2, PCB_W/2, nx)
    ys = np.linspace(-PCB_H/2, PCB_H/2, ny)
    # snap center to a real node so the monopole connects
    cx_i, cy_i = nx // 2, ny // 2
    xs = xs - xs[cx_i]; ys = ys - ys[cy_i]
    tag = 2
    for j in range(ny):                # horizontal edges
        for i in range(nx - 1):
            geo.wire(tag, 1, xs[i], ys[j], 0, xs[i+1], ys[j], 0, gr, 1, 1); tag += 1
    for i in range(nx):                # vertical edges
        for j in range(ny - 1):
            geo.wire(tag, 1, xs[i], ys[j], 0, xs[i], ys[j+1], 0, gr, 1, 1); tag += 1
    # monopole from the (now-zero) center node upward; feed at base segment 1
    geo.wire(1, seg, 0, 0, 0, 0, 0, Lm, WIRE_R, 1, 1)
    return 1, 1


def build_monopole_asflown(geo, wl, mono_len=None, seg=21,
                            panels=True, panel_w=0.07, panel_h=0.10, panel_gap=0.012):
    """The REAL flight structure (from the launch photo):
      - monopole wire exits the BOTTOM edge of the board pointing DOWN (-z),
      - PCB is the 23x57 mm board (its own small ground plane),
      - two solar panels flank the board left/right like wings, in the antenna
        near field. They are conductive (cells + interconnect) and couple.

    The payload hangs from a top corner at ~20 deg; here we build it in the body
    frame (board in the x-z plane, long axis = z, monopole along -z) and let the
    caller apply the hang tilt when sampling. panel_w/h in meters (~7x10 cm from
    photo proportions vs the 57 mm board); panel_gap = board-edge to panel-inner-edge.

    Feed: base of the monopole at the board bottom edge, against the PCB+panel
    counterpoise. Returns (feed_tag, feed_seg)."""
    Lm = mono_len or wl / 4
    # PCB ground grid in the x-z plane (board long axis along z), centered x=0.
    # Board spans z in [0 .. PCB_H] (bottom edge at z=0). nbx EVEN so a node sits
    # exactly at x=0 on the bottom edge -> the monopole attaches at a node (NEC
    # rejects a wire that joins another wire mid-span).
    nbx, nbz = 4, 7
    tag = grid_rect(geo, 100, (-PCB_W/2, 0, 0), (PCB_W, 0, 0), (0, 0, PCB_H), nbx, nbz)
    if panels:
        # left wing: from board left edge outward in -x, same z-extent as board,
        # offset slightly in y so it doesn't intersect the board plane.
        x_in = -PCB_W/2 - panel_gap
        tag = grid_rect(geo, tag, (x_in - panel_w, (PCB_H/2 - panel_h/2)*0 + 0.0 + 0.0, 0.004),
                        (panel_w, 0, 0), (0, 0, panel_h), 4, 6)
        # right wing
        x_in = PCB_W/2 + panel_gap
        tag = grid_rect(geo, tag, (x_in, 0.0, -0.004),
                        (panel_w, 0, 0), (0, 0, panel_h), 4, 6)
    # monopole: from the board BOTTOM edge (z=0, x=0) pointing DOWN (-z)
    geo.wire(1, seg, 0, 0, 0.0, 0, 0, -Lm, WIRE_R, 1, 1)
    return 1, 1


def build_monopole_freespace(geo, wl, mono_len=None, seg=21):
    """Quarter-wave monopole with NO ground plane at all (worst-case bound):
    an asymmetric end-fed wire in free space. Bookend for 'negligible GP'."""
    Lm = mono_len or wl / 4
    geo.wire(1, seg, 0, 0, 0, 0, 0, Lm, WIRE_R, 1, 1)
    return 1, 1


def build_dipole_horizontal(geo, wl, total_len=None, seg=41):
    """Half-wave dipole lying horizontal (along x), at the payload. Tests the
    HF/WSPR-community 'horizontal dipole' convention against our vertical-pol
    ground gateways."""
    L = (total_len or wl / 2) / 2
    geo.wire(1, seg, -L, 0, 0, +L, 0, 0, WIRE_R, 1, 1)
    return 1, seg // 2 + 1


def build_turnstile(geo, wl, total_len=None, seg=21):
    """Turnstile: two horizontal half-wave dipoles crossed at 90 deg, fed 90 deg
    out of phase -> near-omni azimuth with a horizon-favoring pattern and mixed
    polarization (robust to a spinning payload). We approximate the quadrature
    feed by exciting both with a phase offset via two EX sources.
    NOTE: returns the primary feed; the phasing is applied in the solver variant."""
    L = (total_len or wl / 2) / 2
    geo.wire(1, seg, -L, 0, 0, +L, 0, 0, WIRE_R, 1, 1)   # dipole along x
    geo.wire(2, seg, 0, -L, 0, 0, +L, 0, WIRE_R, 1, 1)   # dipole along y
    return 1, seg // 2 + 1  # (turnstile phasing handled specially)


def solve_dipole(f_mhz, **kw):
    return _solve(lambda g, wl: build_dipole(g, wl, **kw), f_mhz)

def solve_monopole_pcb(f_mhz, **kw):
    return _solve(lambda g, wl: build_monopole_pcb(g, wl, **kw), f_mhz)

def solve_monopole_freespace(f_mhz, **kw):
    return _solve(lambda g, wl: build_monopole_freespace(g, wl, **kw), f_mhz)

def solve_dipole_horizontal(f_mhz, **kw):
    return _solve(lambda g, wl: build_dipole_horizontal(g, wl, **kw), f_mhz)


def solve_turnstile(f_mhz, total_len=None, seg=41):
    """Turnstile = two horizontal half-wave dipoles crossed 90 deg, fed in phase
    quadrature. Its defining property is a near-omnidirectional azimuth pattern.

    A single NEC solve with two voltage sources does NOT give equal arm CURRENTS
    (mutual coupling differs), so the azimuth ripple comes out wrong. The faithful
    construction is field superposition: solve each dipole ALONE (so its current
    distribution is the natural half-wave one), then add the complex far-fields
    with a 90 deg phase. We approximate the complex sum on the (already-dB) gain
    grids by combining linear powers with the quadrature cross-term integrated
    out over the fast-spinning payload -> for an incoherent-average observer the
    turnstile power pattern is the mean of the two orthogonal dipole power
    patterns. That is exactly what our spin-averaged effective-gain metric wants,
    so we return the power-averaged pattern of the two orthogonal dipoles."""
    px = _solve(lambda g, wl: build_dipole_horizontal(g, wl, total_len=total_len, seg=seg), f_mhz)
    # second dipole along y = the x-dipole pattern rotated 90 deg in azimuth.
    py_gain = np.roll(px.gain, px.gain.shape[1] // 4, axis=1)  # +90 deg phi shift
    lin = (10 ** (px.gain / 10.0) + 10 ** (py_gain / 10.0)) / 2.0
    gain = 10 * np.log10(lin)
    # feed impedance: each dipole sees ~its own Z; report the single-dipole Z
    return Pattern(px.theta, px.phi, gain, px.z_in, f_mhz)


if __name__ == "__main__":
    print("PyNEC self-test (900 MHz):")
    d = solve_dipole(900.0)
    print(f"  half-wave dipole: peak {d.peak_dbi:.2f} dBi (expect ~2.15), "
          f"Z {d.z_in.real:.0f}{d.z_in.imag:+.0f}j (expect ~73+42j), VSWR50 {d.vswr():.1f}")
    mp = solve_monopole_pcb(900.0)
    print(f"  monopole+PCB-GP: peak {mp.peak_dbi:.2f} dBi, Z {mp.z_in.real:.0f}{mp.z_in.imag:+.0f}j")
    mf = solve_monopole_freespace(900.0)
    print(f"  monopole no-GP : peak {mf.peak_dbi:.2f} dBi, Z {mf.z_in.real:.0f}{mf.z_in.imag:+.0f}j")
    print("  (theta=90 is horizon; gateways sit at theta~95-100 deg from a hung payload)")
