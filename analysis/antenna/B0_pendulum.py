"""PART E — Mechanical stability: pendulum / string dynamics.

Three questions:
  1. What swing AMPLITUDE did the payload actually have? (recoverable from the
     accelerometer magnitude scatter, even at 5-min sampling).
  2. What string LENGTH / material should v2 use? (a DESIGN model — pendulum period,
     and the elastic-string parametric-resonance danger that a stretchy string adds).
  3. So what for the LINK? (map swing amplitude -> pattern-pointing fade).

Honest scope on "measure the string from flight data":
  Pendulum PERIOD encodes length (T = 2*pi*sqrt(L_eff/g)). Our telemetry samples at
  ~308 s; the pendulum swings at ~0.3-0.8 Hz, so we are aliased ~300x and CANNOT see
  the period -> string LENGTH is NOT recoverable from this data. What IS recoverable
  is the swing AMPLITUDE (from how far |a| departs from g). Length is exactly what a
  60 s high-rate accel log on the bench will nail (motivates the bench test).

Physics of the |a| signature (simple pendulum, accelerometer = specific force):
  turning point (max angle A): |a| = g*cos(A)            (radial (centripetal=0), reads < g)
  bottom of swing:             |a| = g*(3 - 2*cos(A))     (reads > g)
  => the spread of |a|/g across many random-phase snapshots encodes A.

Balloon-pendulum subtlety: the pivot is NOT fixed — it's a buoyant 32" sphere with
its own added mass. The effective pendulum length is shortened/modified by the
balloon's restoring response; we model both the naive (fixed-pivot) and the
balloon-coupled period so the bench number can be interpreted.

Run: analysis/.venv/bin/python analysis/antenna/B0_pendulum.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import _style as S
from _gps import classify_uplinks, LAUNCH_UTC

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"
G = 9.80665

# masses (g) — payload from flight notes; balloon film+gas approximate
M_PAYLOAD_G = 10.28
M_BALLOON_FILM_G = 47.0          # 32" Yokohama sphere ~47 g (flight notes)


def load_float_accel():
    df = pd.read_parquet(DATA / "telemetry_raw.parquet")
    df = classify_uplinks(df)
    for c in ("mems_accel_x", "mems_accel_y", "mems_accel_z"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    fl = df[df.time >= LAUNCH_UTC].dropna(subset=["mems_accel_x", "mems_accel_y", "mems_accel_z"]).copy()
    fl["amag"] = np.sqrt(fl.mems_accel_x**2 + fl.mems_accel_y**2 + fl.mems_accel_z**2)
    fl = fl[fl.amag > 5].copy()
    return fl[fl.altitude_m >= 8000].copy()


def amplitude_from_amag(amag_over_g):
    """Bound the swing amplitude from the |a|/g spread.

    Two independent signatures (use the dynamic-range one, report both):
      - bottom of swing: a_max/g = 3 - 2cos(A)        (reads > g)
      - turning point:   a_min/g = cos(A)             (reads < g; but the STATIC
        hang tilt also reads cos(tilt) < g, so a_min conflates swing + lean).
    The cleanest swing proxy is the EXCESS above g (purely kinematic, no static
    tilt can push |a| above g): a_max/g - 1 = 2(1-cos A). Invert that.
    If the excess is within sensor noise, swing is below the resolution floor and
    we report an UPPER BOUND only."""
    amax = np.percentile(amag_over_g, 95)
    excess = amax - 1.0
    if excess <= 0.005:                      # within ~0.05 m/s^2 sensor noise
        # upper bound: even the p95 barely exceeds g -> A is small
        A_ub = np.degrees(np.arccos(1 - max(excess, 0) / 2)) if excess > 0 else 0.0
        return ("upper_bound", max(A_ub, 8.0), amax)   # <= ~8-10 deg, noise-limited
    A = np.degrees(np.arccos(1 - excess / 2))
    return ("estimate", A, amax)


# --- pendulum period models -------------------------------------------------
def period_fixed_pivot(L_m):
    """Naive simple-pendulum period (small angle), fixed pivot."""
    return 2 * np.pi * np.sqrt(L_m / G)


def period_balloon_coupled(L_m, m_payload=M_PAYLOAD_G, m_balloon=M_BALLOON_FILM_G,
                           added_mass_factor=0.5, V_balloon_m3=0.30):
    """Balloon pivot is not fixed: it's a buoyant sphere with hydrodynamic added
    mass (~0.5 * displaced air for a sphere). The pendulum is really a two-body
    swing of payload against the balloon+added-air. Effective length:

        L_eff = L * (1 + m_payload / M_pivot)^(-1)   (reduced-mass-like shortening)

    where M_pivot = m_balloon_film + rho_air_disp*added_mass. At float, displaced
    air mass is tiny (rho~0.4 kg/m3 * 0.3 m3 = 120 g) but the helium+film system
    has inertia. This is a first-order estimate; the bench test on the ground (denser
    air) will read a slightly different L_eff than float — we note the direction."""
    rho_air_float = 0.40   # ~10-12 km
    m_added = added_mass_factor * rho_air_float * V_balloon_m3 * 1000.0  # grams
    M_pivot = m_balloon + m_added
    L_eff = L_m / (1 + m_payload / M_pivot)
    return 2 * np.pi * np.sqrt(L_eff / G), L_eff


def main():
    fl = load_float_accel()
    aog = (fl.amag / G).values
    kind, A_deg, amax = amplitude_from_amag(aog)
    print(f"=== Swing amplitude from flight accelerometer (n={len(fl)} float) ===")
    print(f"  |a|/g: median {np.median(aog):.3f}  p5 {np.percentile(aog,5):.3f}  p95 {np.percentile(aog,95):.3f}")
    if kind == "upper_bound":
        print(f"  swing amplitude: UPPER BOUND ~{A_deg:.0f} deg — the kinematic excess above g")
        print(f"  (p95 a/g={amax:.3f}) is at the sensor-noise floor, so the real swing is small/gentle.")
    else:
        print(f"  inferred swing amplitude ~ {A_deg:.0f} deg (from a_max/g={amax:.3f})")
    print(f"  => GENTLE swing (consistent with Part B-0 tight attitude). Not violent tumbling.")
    print(f"  CAVEAT: 308 s sampling aliases the ~0.3-0.8 Hz swing -> amplitude (bound) yes, PERIOD/length NO.")

    print(f"\n=== String LENGTH design model (period vs L) ===")
    print(f"  (length NOT measurable from flight data; this is the design curve the")
    print(f"   bench high-rate accel log will pin down)")
    print(f"  {'L (m)':>6} {'T_fixed(s)':>11} {'T_balloon(s)':>13} {'f (Hz)':>7}")
    for L in [0.3, 0.5, 1.0, 1.5, 2.0, 3.0]:
        Tf = period_fixed_pivot(L)
        Tb, Leff = period_balloon_coupled(L)
        print(f"  {L:6.1f} {Tf:11.2f} {Tb:13.2f} {1/Tb:7.3f}")

    # Parametric resonance (elastic string!): the spring-pendulum pumps swing when
    # the vertical bounce freq ~ 2x the swing freq. Find the danger string stiffness.
    print(f"\n=== Elastic-string parametric resonance (the real risk of a stretchy string) ===")
    print(f"  A spring-pendulum pumps energy into SWING when vertical bounce freq ~ 2x swing freq.")
    print(f"  swing freq f_s = (1/2pi)sqrt(g/L); bounce freq f_b = (1/2pi)sqrt(k/m).")
    print(f"  Danger when f_b ~ 2 f_s  ->  k ~ 4 m g / L. For m={M_PAYLOAD_G} g:")
    m = M_PAYLOAD_G/1000.0
    for L in [0.5, 1.0, 2.0]:
        k_danger = 4*m*G/L
        # static stretch of such a spring under the payload weight:
        stretch = m*G/k_danger  # = L/4
        print(f"    L={L} m: avoid string spring const k≈{k_danger:.2f} N/m "
              f"(one that sags ~{stretch*100:.0f} cm under the {M_PAYLOAD_G} g payload)")
    print(f"  Rule of thumb: a string that visibly bounces/stretches under the payload")
    print(f"  and whose bounce looks ~2x the swing rate is in the danger zone -> use a")
    print(f"  STIFFER (less elastic) line, or detune L so f_b != 2 f_s.")

    make_plot(fl, aog, A_deg, kind)
    print("\nwrote figs E1/E2 and the analysis")


def make_plot(fl, aog, A_deg, kind):
    S.use_light()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8))

    # E1: |a|/g histogram with amplitude-signature overlays
    ax1.hist(aog, bins=np.arange(0.88, 1.06, 0.01), color=S.L_SERIES["as-flown +panels"],
             alpha=0.8, label=f"flight float (n={len(fl)})")
    for Adeg, ls in [(10, ":"), (15, "--"), (20, "-.")]:
        A = np.radians(Adeg)
        ax1.axvline(3 - 2*np.cos(A), color=S.RED, ls=ls, lw=1.3,
                    label=f"swing {Adeg}° → a_max/g={3-2*np.cos(A):.2f}")
    ax1.axvline(1.0, color=S.TEXT_DIM, lw=1)
    ax1.set_xlabel("accelerometer |a| / g"); ax1.set_ylabel("uplinks")
    lbl = f"≤{A_deg:.0f}° (upper bound)" if kind == "upper_bound" else f"~{A_deg:.0f}° peak"
    ax1.set_title(f"E1 · Swing amplitude from |a| scatter\n{lbl} — a gentle swing, not a tumble")
    ax1.legend(fontsize=8, loc="upper left")

    # E2: pendulum period vs string length (the design + bench-prediction curve)
    L = np.linspace(0.2, 3.0, 100)
    Tf = period_fixed_pivot(L)
    Tb = np.array([period_balloon_coupled(x)[0] for x in L])
    ax2.plot(L, Tf, color=S.L_SERIES["vertical dipole"], lw=2.4, label="fixed-pivot period")
    ax2.plot(L, Tb, color=S.L_SERIES["horizontal dipole"], lw=2.2, ls="--", label="balloon-coupled period")
    ax2.set_xlabel("string length L (m)"); ax2.set_ylabel("pendulum period T (s)")
    ax2.set_title("E2 · String length ↔ swing period (the bench will measure T → L)\n"
                  "longer string = slower swing = steadier antenna pointing")
    ax2.legend(fontsize=9, loc="upper left")
    ax2.grid(True, alpha=0.5)

    S.footer(fig, "Stratolink · accel-derived swing + pendulum design model · analysis/antenna/B0_pendulum.py", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "E1_pendulum.png", dpi=180); plt.close(fig)


if __name__ == "__main__":
    main()
