"""Render antenna radiation patterns in the 4nec2 style (light mode) — the
visualizations Teddy asked for: rainbow 3D 'doughnut' surfaces + polar cuts.

Run: analysis/.venv/bin/python analysis/antenna/70_visualize.py
Outputs to figs/ (light-mode PNGs prefixed V*).
"""
from __future__ import annotations
from pathlib import Path

import _nec as N
from _nec import _solve, build_monopole_asflown
import _pattern3d as P3

FIGS = Path(__file__).resolve().parent / "figs"
F = 904.5  # US915 band centre for the renders

def main():
    # Solve the candidates (US915).
    asflown = _solve(lambda g, wl: build_monopole_asflown(g, wl, panels=True), F)
    asflown_nopanel = _solve(lambda g, wl: build_monopole_asflown(g, wl, panels=False), F)
    vdip = N.solve_dipole(F)
    hdip = N.solve_dipole_horizontal(F)
    turn = N.solve_turnstile(F)

    # --- 3D doughnuts ---
    P3.render_3d(asflown, "As-flown: down monopole + solar-panel counterpoise",
                 FIGS / "V_3d_asflown.png", wire="monopole_down", panels=True)
    P3.render_3d(vdip, "Vertical λ/2 dipole",
                 FIGS / "V_3d_vdipole.png", wire="dipole_v")
    P3.render_3d(hdip, "Horizontal λ/2 dipole",
                 FIGS / "V_3d_hdipole.png", wire="dipole_h")

    # --- polar vertical-cut comparison (the F4-style plot) ---
    P3.render_polar_cut(
        {"as-flown +panels": asflown, "vertical dipole": vdip,
         "horizontal dipole": hdip, "turnstile": turn},
        "Vertical-plane gain cut — candidates vs where the gateways were",
        FIGS / "V_polar_compare.png")

    # --- the panel effect, side by side as polar ---
    P3.render_polar_cut(
        {"as-flown +panels": asflown, "monopole, no panels": asflown_nopanel},
        "Solar panels as counterpoise — with vs without",
        FIGS / "V_polar_panels.png")

    print("wrote V_3d_asflown / V_3d_vdipole / V_3d_hdipole / V_polar_compare / V_polar_panels")
    # quick numeric recap
    for name, p in [("as-flown+panels", asflown), ("no-panels", asflown_nopanel),
                    ("vert dipole", vdip), ("horiz dipole", hdip), ("turnstile", turn)]:
        print(f"  {name:16} peak {p.peak_dbi:5.2f} dBi  Z {p.z_in.real:4.0f}{p.z_in.imag:+.0f}j  "
              f"mismatch {p.mismatch_loss_db():.1f} dB")


if __name__ == "__main__":
    main()
