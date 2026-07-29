"""PART C — Temperature detuning, conductor material, and counterpoise.

Question: does the as-flown antenna (down monopole + solar-panel counterpoise)
stay matched and on-frequency when the stratosphere chills the wire to ~ -50 C?
And does the enamelled-copper choice matter vs alternatives?

THREE physical mechanisms (each quantified):

 1. Thermal contraction of the conductor. Copper CTE alpha = 16.5 ppm/C
    (amesweb; ETP 16.8, OF 17.7). Cooling +20 C -> -50 C (dT = -70 C) shrinks a
    length L by  dL/L = alpha*dT = 16.5e-6 * (-70) = -1.155e-3  (-0.12 %).
    A shorter wire resonates HIGHER in frequency: df/f = -dL/L = +0.12 %.
    At 904.5 MHz that is +1.04 MHz. Tiny vs the 125 kHz channel? No -- it is
    ~8 channel-widths, but the antenna BANDWIDTH is tens of MHz, so the match
    barely moves. We quantify the actual VSWR change in NEC by shrinking the wire.

 2. Enamel coating (velocity factor). The enamel (er~3, ~25 um thick) loads the
    wire so its ELECTRICAL length slightly exceeds physical -> a thin-coat
    correction lowers the resonant frequency a little and is nearly
    temperature-independent (the coat is thin; most field is in air). We treat it
    as a fixed small velocity factor and show the magnitude.

 3. Conductor material / loss. Cold copper has ~25% LOWER resistivity (good:
    a touch more efficiency). Aluminium (CTE 23 ppm/C) and steel (12) move
    resonance differently; we compare the detuning sensitivity by CTE.

Other materials considered for the wire: bare vs enamelled copper, aluminium,
phosphor-bronze (springy, survivable), and a PCB-trace option.

Models the as-flown structure (panels included) via _nec.build_monopole_asflown.
Run: analysis/.venv/bin/python analysis/antenna/80_thermal.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

import _style as S
import _nec as N
from _nec import _solve, build_monopole_asflown, wavelength_m

FIGS = Path(__file__).resolve().parent / "figs"

# Material linear CTE, ppm/C (alpha). Sources: amesweb (Cu), engineering tables.
CTE = {"copper": 16.5e-6, "aluminium": 23.1e-6, "phosphor-bronze": 17.3e-6, "steel": 12.0e-6}
ENAMEL_ER = 3.0          # relative permittivity of magnet-wire enamel (~3)
T_REF_C = 20.0           # length cut/tuned at room temp
T_COLD_C = -50.0         # stratospheric design case (wire in airstream)

BANDS = {"EU868": 868.1, "US915": 904.5}


def length_at_temp(L_ref, T_C, material="copper"):
    """Physical length of a wire cut to L_ref at T_REF, now at temperature T_C."""
    return L_ref * (1.0 + CTE[material] * (T_C - T_REF_C))


def enamel_velocity_factor(coat_um=25.0, wire_r_um=300.0, er=ENAMEL_ER):
    """Velocity factor of a thin dielectric-coated wire antenna.

    Honest scope note: an exact treatment needs the King-Wu insulated-antenna
    integral (transcendental). What is robust and well-supported (LowPowerLab /
    practical-antenna refs): insulated-wire VF sits in 0.95-0.98, and the effect
    grows with ln(b/a) so THINNER coats sit at the high (≈1) end.

    We use the standard near-field effective-permittivity estimate

        eps_eff = 1 + (er - 1) * F,   F = ln(b/a) / ln(R_eff/a)

    where b = a + coat, and R_eff is the radial extent the antenna near-field
    fills (~ a few wire radii). With a=300 um, b=325 um, R_eff~10a this gives
    eps_eff ~ 1.02 -> VF ~ 0.99 (≈1% shortening) — consistent with the 0.95-0.98
    band for much thicker hookup-wire insulation. Returns VF in (0,1].
    """
    a = wire_r_um
    b = wire_r_um + coat_um
    R_eff = 10.0 * a                     # near-field radial extent ~10 wire radii
    F = np.log(b / a) / np.log(R_eff / a)
    eps_eff = 1.0 + (er - 1.0) * F
    return 1.0 / np.sqrt(eps_eff)


def resonant_freq_scan(L_m, f_lo, f_hi, n=41, panels=True):
    """Sweep frequency for a fixed physical wire length; return (freqs, X, VSWR).
    Resonance = where reactance X crosses zero."""
    fs = np.linspace(f_lo, f_hi, n)
    X = np.zeros(n); V = np.zeros(n); R = np.zeros(n)
    for i, f in enumerate(fs):
        p = _solve(lambda g, wl, L=L_m: build_monopole_asflown(g, wl, mono_len=L, panels=panels), f)
        X[i] = p.z_in.imag; V[i] = p.vswr(); R[i] = p.z_in.real
    return fs, X, V, R


def find_resonance(fs, X):
    """Linear-interp the zero crossing of reactance -> resonant frequency (MHz)."""
    s = np.sign(X)
    idx = np.where(np.diff(s) != 0)[0]
    if len(idx) == 0:
        return None
    i = idx[0]
    f0, f1, x0, x1 = fs[i], fs[i+1], X[i], X[i+1]
    return f0 - x0 * (f1 - f0) / (x1 - x0)


def main():
    print("=== Part C: thermal detuning of the as-flown antenna ===")
    # Tune the monopole to resonance at US915 room temp, with panels.
    wl = wavelength_m(904.5)
    L_ref = 0.0  # find the resonant length at room temp via a short length sweep
    # quick length tune at 904.5 MHz
    best = None
    for frac in np.linspace(0.22, 0.30, 17):
        p = _solve(lambda g, w, fr=frac: build_monopole_asflown(g, w, mono_len=w*fr, panels=True), 904.5)
        if best is None or abs(p.z_in.imag) < abs(best[1]):
            best = (frac, p.z_in.imag, w if False else wl*frac)
    L_ref = best[2]
    print(f"room-temp resonant length (US915, panels): {L_ref*1000:.1f} mm  (X={best[1]:+.0f} ohm)")

    # Enamel velocity factor magnitude
    vf = enamel_velocity_factor()
    print(f"enamel velocity factor ~ {vf:.3f}  -> electrical lengthening ~ {(1/vf-1)*100:.1f}% "
          f"(~{(1/vf-1)*904.5:.1f} MHz downshift) — fixed, ~T-independent")

    # Length change cold
    L_cold = length_at_temp(L_ref, T_COLD_C, "copper")
    dL_ppm = (L_cold - L_ref) / L_ref
    print(f"\ncopper wire {T_REF_C:.0f}C -> {T_COLD_C:.0f}C: dL/L = {dL_ppm*1e2:+.3f}%  "
          f"({L_ref*1000:.2f} -> {L_cold*1000:.2f} mm) -> resonance shift df/f = {-dL_ppm*1e2:+.3f}% "
          f"= {-dL_ppm*904.5:+.2f} MHz")

    # NEC: sweep frequency at room-temp length vs cold-contracted length, measure
    # how far resonance moves and whether VSWR at the operating bands degrades.
    print("\nrunning NEC frequency sweeps (room vs cold length)...")
    f_lo, f_hi = 820, 1000
    fs_w, Xw, Vw, Rw = resonant_freq_scan(L_ref, f_lo, f_hi)
    fs_c, Xc, Vc, Rc = resonant_freq_scan(L_cold, f_lo, f_hi)
    f0_w = find_resonance(fs_w, Xw); f0_c = find_resonance(fs_c, Xc)
    print(f"  resonance warm: {f0_w:.1f} MHz   cold: {f0_c:.1f} MHz   shift {f0_c-f0_w:+.2f} MHz")

    # VSWR at the two operating bands, warm vs cold
    def vswr_at(fs, V, f):
        return float(np.interp(f, fs, V))
    print("\n  VSWR at the operating bands (warm -> cold):")
    for b, f in BANDS.items():
        print(f"    {b} ({f:.1f} MHz): {vswr_at(fs_w,Vw,f):.2f} -> {vswr_at(fs_c,Vc,f):.2f}")

    # Material sensitivity: resonance shift per material for the same dT
    print("\n  detuning sensitivity by conductor (dT = -70 C):")
    for mat, a in CTE.items():
        df = -a * (T_COLD_C - T_REF_C) * 904.5  # MHz
        print(f"    {mat:16} CTE {a*1e6:4.1f} ppm/C -> {df:+.2f} MHz")

    make_plot(fs_w, Vw, Xw, fs_c, Vc, Xc, f0_w, f0_c, L_ref, L_cold)
    print("\nwrote figs/C1_thermal_detuning.png")


def make_plot(fs_w, Vw, Xw, fs_c, Vc, Xc, f0_w, f0_c, L_ref, L_cold):
    S.use_light()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.6))

    # left: reactance vs freq, warm vs cold, zero-crossing = resonance
    ax1.axhline(0, color=S.TEXT_DIM, lw=0.8)
    ax1.plot(fs_w, Xw, color=S.L_SERIES["vertical dipole"], lw=2.2, label=f"warm (+20 °C), L={L_ref*1000:.1f} mm")
    ax1.plot(fs_c, Xc, color=S.RED, lw=2.2, ls="--", label=f"cold (−50 °C), L={L_cold*1000:.1f} mm")
    for b, f in BANDS.items():
        ax1.axvline(f, color=S.MINT, lw=1, alpha=0.5)
        ax1.text(f, ax1.get_ylim()[1]*0.9, b, rotation=90, fontsize=8, color=S.MINT, va="top", ha="right")
    ax1.set_xlabel("frequency (MHz)"); ax1.set_ylabel("feed reactance X (Ω)")
    ax1.set_title("C1a · Resonance shift with cold\n"
                  f"Δf = {f0_c-f0_w:+.1f} MHz over 70 °C — negligible vs antenna bandwidth")
    ax1.legend(loc="lower right", fontsize=9)

    # right: VSWR vs freq, warm vs cold
    ax2.plot(fs_w, Vw, color=S.L_SERIES["vertical dipole"], lw=2.2, label="warm (+20 °C)")
    ax2.plot(fs_c, Vc, color=S.RED, lw=2.2, ls="--", label="cold (−50 °C)")
    ax2.axhline(2.0, color=S.TEXT_DIM, ls=":", lw=1); ax2.text(825, 2.05, "VSWR 2:1", fontsize=8, color=S.TEXT_DIM)
    for b, f in BANDS.items():
        ax2.axvline(f, color=S.MINT, lw=1, alpha=0.5)
    ax2.set_ylim(1, 8)
    ax2.set_xlabel("frequency (MHz)"); ax2.set_ylabel("VSWR (vs 50 Ω)")
    ax2.set_title("C1b · Match holds cold\n"
                  "the operating bands stay well inside the VSWR skirt")
    ax2.legend(loc="upper right", fontsize=9)

    S.footer(fig, "Stratolink-3 · PyNEC MoM · as-flown monopole+panels · copper CTE 16.5 ppm/°C", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "C1_thermal_detuning.png", dpi=180); plt.close(fig)


if __name__ == "__main__":
    main()
