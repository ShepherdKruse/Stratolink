"""3D radiation-pattern rendering in the 4nec2 style (light mode).

Two views per antenna, matching the 4nec2 windows Teddy likes:
  - render_3d()    : the rainbow gain "doughnut" surface (like the 3D viewer),
                     radius = gain, colored by gain, with a ground plane + the
                     antenna wire drawn in, and a marker ring at the horizon.
  - render_polar() : the F4 vertical-plane polar cut (gain vs elevation).

Patterns come from _nec.Pattern (theta 0..180 from +z, phi 0..360).
We render in a world frame where +z is up; the caller can pass a tilt to show
the hung orientation.
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from mpl_toolkits.mplot3d.art3d import Line3DCollection

import _style as S


def _grid(pat, floor_db=-20):
    """Return theta,phi meshes (rad) and a gain grid clamped to a dB floor,
    normalized so 0 dB = peak."""
    th = np.radians(pat.theta)          # (nt,)
    ph = np.radians(pat.phi)            # (np,)
    g = pat.gain.copy()
    g = np.where(np.isfinite(g), g, floor_db)
    gn = np.clip(g - pat.peak_dbi, floor_db, 0)   # 0 = peak
    TH, PH = np.meshgrid(th, ph, indexing="ij")   # (nt, np)
    return TH, PH, gn


def render_3d(pat, title, out_path, wire="monopole_down", panels=False,
              floor_db=-20, color_span_db=12, elev=18, azim=-55):
    """4nec2-style 3D rainbow gain surface on a light background.

    wire: which antenna stick to draw ('monopole_down','dipole_v','dipole_h', None).
    color_span_db: dB below peak that the rainbow spans (smaller = more vivid,
    like the 4nec2 viewer where the torus cycles through the spectrum).
    """
    S.use_light()
    TH, PH, gn = _grid(pat, floor_db)
    r = gn - floor_db                  # radius >=0, 0 at the floor
    # spherical -> cartesian (theta from +z)
    x = r * np.sin(TH) * np.cos(PH)
    y = r * np.sin(TH) * np.sin(PH)
    z = r * np.cos(TH)

    # Color spans the top `color_span_db` below peak so the rainbow is vivid
    # across the visible torus (like the 4nec2 3D viewer). gn in [floor_db, 0].
    norm = np.clip((gn + color_span_db) / color_span_db, 0, 1)  # 0=span floor(blue) ->1=peak(red)
    colors = cm.get_cmap(S.PAT_CMAP)(norm)

    fig = plt.figure(figsize=(8.2, 7.2))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(S.L_BG)
    ax.plot_surface(x, y, z, facecolors=colors, rstride=1, cstride=1,
                    linewidth=0, antialiased=True, shade=False, alpha=0.97)

    R = r.max()
    # horizon ring (the elevation where gateways actually were ~ 0-10 deg below)
    ang = np.linspace(0, 2*np.pi, 200)
    ax.plot(R*1.02*np.cos(ang), R*1.02*np.sin(ang), np.zeros_like(ang),
            color=S.L_TEXT_DIM, lw=1.2, ls="--")
    ax.text(R*1.05, 0, 0, " horizon", color=S.L_TEXT_DIM, fontsize=9)

    # draw the antenna element + a faint ground/panel hint
    if wire == "monopole_down":
        ax.plot([0, 0], [0, 0], [0, -R*0.9], color="#222", lw=3)      # wire down
        ax.scatter([0], [0], [0], color="#222", s=20)
    elif wire == "dipole_v":
        ax.plot([0, 0], [0, 0], [-R*0.6, R*0.6], color="#222", lw=3)
    elif wire == "dipole_h":
        ax.plot([-R*0.6, R*0.6], [0, 0], [0, 0], color="#222", lw=3)
    if panels:
        for sx in (-1, 1):
            px = sx*np.array([0.18, 0.62, 0.62, 0.18])*R
            py = np.array([-0.35, -0.35, 0.35, 0.35])*R
            pz = np.zeros(4)
            ax.plot_trisurf(px, py, pz, color="#2b3a67", alpha=0.25, linewidth=0)

    from matplotlib.colors import Normalize
    m = cm.ScalarMappable(cmap=S.PAT_CMAP, norm=Normalize(vmin=-color_span_db, vmax=0))
    m.set_array([])
    cb = fig.colorbar(m, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("gain relative to peak (dB)")

    ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(f"{title}\npeak {pat.peak_dbi:.1f} dBi @ {pat.f_mhz:.0f} MHz",
                 fontsize=12, color=S.L_TEXT)
    fig.text(0.5, 0.02, "rainbow surface = gain in every direction · stick = antenna element · "
             "dashed ring = horizon (where gateways are)", ha="center",
             fontsize=8, color=S.L_TEXT_DIM)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def render_polar_cut(pats: dict, title, out_path, phi_deg=0.0,
                     gateway_dep_deg=8.0, floor_db=-25):
    """4nec2 F4-style vertical-plane polar cut, several antennas overlaid.

    pats: {name: Pattern}. Plotted as gain (dBi) vs elevation angle, with the
    horizon at 0 deg (right) and nadir down. Marks the median gateway direction."""
    S.use_light()
    fig = plt.figure(figsize=(8.6, 8))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(S.L_BG)
    ax.set_theta_zero_location("E")   # horizon to the right
    ax.set_theta_direction(1)
    ax.set_thetamin(-90); ax.set_thetamax(90)

    ip = int(round(phi_deg))
    for name, p in pats.items():
        col = S.L_SERIES.get(name, S.L_ACCENT)
        th = p.theta
        g = np.array([p.gain_at(t, phi_deg) for t in th])
        g = np.where(np.isfinite(g), g, floor_db)
        gg = np.clip(g, p.peak_dbi + floor_db, None)
        elev = 90 - th
        ax.plot(np.radians(elev), gg, color=col, lw=2.2, label=f"{name} ({p.peak_dbi:.1f} dBi pk)")

    # gateway band: 0..-15 deg elevation (below horizon)
    ax.fill_between(np.radians(np.linspace(0, -15, 30)),
                    floor_db*0 + ax.get_ylim()[0], 0,
                    color=S.L_ACCENT, alpha=0.07)
    ax.plot([np.radians(-gateway_dep_deg)]*2, [ax.get_ylim()[0], 5],
            color="#0a9396", ls="--", lw=1.5)
    ax.text(np.radians(-gateway_dep_deg), 6, f" median gateway\n {gateway_dep_deg:.0f}° below horizon",
            color="#0a7d6b", fontsize=9)

    ax.set_rlabel_position(95)
    ax.set_title(title, fontsize=12.5, pad=22, color=S.L_TEXT)
    ax.legend(loc="lower left", bbox_to_anchor=(-0.05, -0.08), fontsize=9)
    ax.text(np.radians(0), ax.get_ylim()[1], " horizon", fontsize=9, color=S.L_TEXT_DIM)
    ax.text(np.radians(89), ax.get_ylim()[1], "zenith ", fontsize=9, color=S.L_TEXT_DIM, ha="right")
    ax.text(np.radians(-89), ax.get_ylim()[1], "nadir ", fontsize=9, color=S.L_TEXT_DIM, ha="right")
    S.footer(fig, "Stratolink-3 · PyNEC MoM · vertical-plane cut · gain in dBi", light=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
