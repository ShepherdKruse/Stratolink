"""PART D — Mounting / hang-tilt optimization.

Teddy's hypothesis: hanging the payload so the monopole points STRAIGHT DOWN
(antenna axis vertical -> doughnut peak exactly at the horizon, tilt tau=0) should
beat the flown ~20deg corner-hang. Substantiate it.

Method: the as-flown antenna pattern (down monopole + solar-panel counterpoise,
from _nec) is fixed to the body. The hang tilt `tau` leans the body from vertical;
the payload spins freely (Part B-0). For each tau we rotate the pattern, average
over the uniform spin, and weight by the EMPIRICAL gateway depression distribution
from Part A (median ~8deg below horizon). Sweep tau 0..45deg -> find the optimum.

Also: translate tau into a string-attachment geometry, and note the solar tradeoff.

Run: analysis/.venv/bin/python analysis/antenna/A0_mounting.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import _style as S
import _nec as N
import _tilt as T

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"

TAUS = np.arange(0, 46, 2.5)          # hang tilt sweep, deg
FLOWN_TAU = 20.0                      # measured corner-hang (Part B-0)


def gateway_depressions():
    df = pd.read_parquet(DATA / "receptions_geo.parquet")
    fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"] & (df["balloon_alt"] >= 8000)]
    return fresh["depr_balloon_deg"].dropna().values


def main():
    deps = gateway_depressions()
    print(f"gateway depression sample (FRESH float): n={len(deps)}, "
          f"median {np.median(deps):.1f}deg, p10 {np.percentile(deps,10):.1f}, p90 {np.percentile(deps,90):.1f}")

    # As-flown antenna at both bands; the pattern shape is what matters here.
    pats = {
        "as-flown (US915)": N._solve(lambda g, wl: N.build_monopole_asflown(g, wl, panels=True), 904.5),
        "vertical dipole":  N.solve_dipole(904.5),
    }

    print("\n=== Effective gain vs hang-tilt (spin- & gateway-weighted) ===")
    results = {}
    for name, p in pats.items():
        eff = np.array([T.effective_gain_over_flight(p, deps, tau) for tau in TAUS])
        results[name] = eff
        i_best = int(np.argmax(eff))
        tau0 = eff[np.argmin(np.abs(TAUS - 0))]
        tau20 = eff[np.argmin(np.abs(TAUS - FLOWN_TAU))]
        print(f"\n  {name}:")
        print(f"    optimum tilt   : {TAUS[i_best]:.1f}deg  -> {eff[i_best]:.2f} dBi")
        print(f"    nadir-down (0deg): {tau0:.2f} dBi")
        print(f"    flown (~20deg)   : {tau20:.2f} dBi")
        print(f"    nadir-down vs flown: {tau0 - tau20:+.2f} dB")
        print(f"    optimum vs flown   : {eff[i_best] - tau20:+.2f} dB")

    make_plot(results, deps, pats)
    # also save curve data
    out = pd.DataFrame({"tau_deg": TAUS, **{k: v for k, v in results.items()}})
    out.to_csv(DATA / "mounting_tilt_sweep.csv", index=False)
    print("\nwrote figs D4/D5 and data/mounting_tilt_sweep.csv")


def make_plot(results, deps, pats):
    S.use_light()

    # --- D4: effective gain vs hang tilt ---
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    colors = {"as-flown (US915)": S.L_SERIES["as-flown +panels"],
              "vertical dipole": S.L_SERIES["vertical dipole"]}
    for name, eff in results.items():
        ax.plot(TAUS, eff - eff[0], color=colors[name], lw=2.4, marker="o", ms=4,
                label=name)
    ax.axvline(0, color=S.MINT, lw=1.5, ls="-", alpha=0.6)
    ax.text(0.4, ax.get_ylim()[0]+0.05, "nadir-down\n(proposed)", color=S.MINT, fontsize=9, va="bottom")
    ax.axvline(FLOWN_TAU, color=S.RED, lw=1.5, ls="--")
    ax.text(FLOWN_TAU+0.6, ax.get_ylim()[0]+0.05, "flown\n(~20° corner)", color=S.RED, fontsize=9, va="bottom")
    ax.set_xlabel("hang tilt τ — antenna axis lean from vertical (°)")
    ax.set_ylabel("effective gain toward gateways, Δ vs nadir-down (dB)")
    ax.set_title("D4 · Mounting angle: does pointing the monopole straight down help?\n"
                 "spin-averaged, weighted by the real flight gateway-angle distribution")
    ax.legend(loc="lower left", fontsize=10)
    S.footer(fig, "Stratolink · as-flown pattern (PyNEC) rotated by hang tilt · FRESH float gateways", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "D4_mounting_tilt.png", dpi=180); plt.close(fig)

    # --- D5: the intuition — gain vs depression at tau=0 vs tau=20, w/ gateway hist ---
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    p = pats["as-flown (US915)"]
    dep_grid = np.linspace(-20, 60, 161)
    for tau, col, lab in [(0, S.MINT, "nadir-down (τ=0°)"), (FLOWN_TAU, S.RED, "flown (τ=20°)")]:
        g = [T.spin_avg_gain_dbi(p, d, tau) for d in dep_grid]
        ax.plot(dep_grid, g, color=col, lw=2.4, label=lab)
    ax.set_xlabel("gateway depression below horizontal (°)   [0 = horizon, →down]")
    ax.set_ylabel("spin-averaged gain (dBi)")
    # overlay the gateway distribution
    ax2 = ax.twinx()
    ax2.hist(deps, bins=np.arange(0, 45, 3), color=S.DIM, alpha=0.35)
    ax2.set_ylabel("gateway count (flight)", color=S.TEXT_DIM)
    ax2.set_yticks([])
    ax.axvline(np.median(deps), color=S.L_TEXT, ls=":", lw=1.2)
    ax.text(np.median(deps)+1, ax.get_ylim()[0]+0.5, f"median gateway {np.median(deps):.0f}°", fontsize=9)
    ax.set_zorder(ax2.get_zorder()+1); ax.patch.set_visible(False)
    ax.set_title("D5 · Why: the gateways sit near the horizon, where the untilted doughnut peaks\n"
                 "tilting 20° drags the peak off the gateways (and into the sky on the far side)")
    ax.legend(loc="upper right", fontsize=10)
    S.footer(fig, "Stratolink · as-flown pattern · spin-averaged gain vs gateway depression", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "D5_gain_vs_depression.png", dpi=180); plt.close(fig)


if __name__ == "__main__":
    main()
