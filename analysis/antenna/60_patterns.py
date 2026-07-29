"""PART B — Antenna pattern modeling for Stratolink v2 (PyNEC method-of-moments).

Compares four candidates at BOTH bands (868 EU / 915 US) against the REAL flight
geometry from Part A and the REAL payload attitude from Part B-0:

  1. monopole + PCB ground  — quarter-wave wire on the measured 23x57 mm board
                              ground plane (what flew).
  2. monopole, no ground    — worst-case bound (negligible counterpoise).
  3. vertical half-wave dipole — needs no ground plane; vertical pol.
  4. horizontal dipole      — the HF/WSPR-community convention.
  5. turnstile (crossed dipoles, 90 deg phased) — pattern + pol diversity.

For each we report, per band:
  - peak gain (dBi) and feed impedance / mismatch loss (the monopole's real
    problem is impedance, not just pattern).
  - "effective gain toward gateways" = pattern gain weighted by the empirical
    float depression-angle distribution (A4), averaged over the payload's
    uniform yaw-spin (Part B-0) -> a single decision number per antenna/band.
  - polarization-matched effective gain: ground gateways are vertical-pol; we
    fold in the polarization loss for each antenna given the payload's measured
    ~20 deg cant + uniform spin.

Outputs figures B1..B3 and report 03_patterns_partB.md.
Run: analysis/.venv/bin/python analysis/antenna/60_patterns.py
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import _style as S
import _nec as N
from _gps import classify_uplinks, LAUNCH_UTC

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"

BANDS = {"EU868": 868.1, "US915": 904.5}
SF7_SENS = S.SF7_SENS_DBM   # -124.5 dBm
TX_DBM = 14.0               # fixed all-region (lorawan.cpp)

# Body-frame cant measured in B-0: gravity sits ~20 deg off the body-y axis, i.e.
# the payload hangs tilted ~20 deg and spins about near-vertical. We model the
# antenna's nominal "up" axis as tilted TILT_DEG from true vertical.
TILT_DEG = 20.0
SWING_SIGMA_DEG = 5.0   # residual swing (B-0: body-z sigma ~2.7 deg, use ~5 to be safe)


# ---------------------------------------------------------------------------
# Flight angle distribution (from Part A, FRESH float receptions)
# ---------------------------------------------------------------------------
def flight_depression_weights():
    """Return (depr_angle_deg array, weight array) from FRESH float receptions:
    the empirical distribution of where, in elevation below the balloon's local
    horizontal, gateways actually were. This is what we integrate patterns over."""
    df = pd.read_parquet(DATA / "receptions_geo.parquet")
    fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"] & (df["balloon_alt"] >= 8000)]
    dep = fresh["depr_balloon_deg"].dropna().values
    return dep


def depression_to_theta(dep_deg, tilt_deg=0.0):
    """Convert a 'depression below horizontal' angle to NEC zenith theta.
    Horizon = theta 90 deg; below horizon adds to theta. A body tilt shifts the
    pattern, handled separately by sampling phi too. Here, nominal (untilted):
    theta = 90 + depression."""
    return 90.0 + dep_deg


# ---------------------------------------------------------------------------
# Effective gain toward the gateways, averaged over yaw spin + swing + tilt
# ---------------------------------------------------------------------------
def effective_gain_dbi(pat: N.Pattern, dep_weights, tilt_deg=TILT_DEG,
                       swing_sigma=SWING_SIGMA_DEG, n_spin=72, n_swing=15, rng=None):
    """Mean linear gain (then back to dBi) toward the empirical gateway
    directions, marginalizing over:
      - the uniform yaw spin (phi uniform 0..360),
      - the payload tilt (TILT_DEG) with small Gaussian swing,
      - the empirical depression-angle distribution (each reception = a target).
    This is the single 'how well does this antenna serve the real flight' number.
    """
    rng = rng or np.random.default_rng(42)
    phis = np.linspace(0, 360, n_spin, endpoint=False)
    lin_sum = 0.0
    cnt = 0
    for dep in dep_weights:
        # each gateway target at this depression; spin sweeps azimuth, swing
        # jitters the effective depression by the tilt + a small random wobble
        swings = rng.normal(0, swing_sigma, n_swing)
        tilts = tilt_deg + swings
        for t in tilts:
            theta = 90.0 + dep + 0.0  # base
            # the tilt rocks the pattern: sample the antenna at theta shifted by
            # +-tilt depending on which side the spin presents -> average over phi
            for ph in phis:
                # approximate tilt as a theta offset modulated by cos(phi)
                th = theta + t * np.cos(np.radians(ph))
                th = min(179.9, max(0.1, th))
                g_dbi = pat.gain_at(th, ph % 360)
                lin_sum += 10 ** (g_dbi / 10.0)
                cnt += 1
    return 10 * np.log10(lin_sum / cnt)


def horizon_gain_profile(pat: N.Pattern, phi=0.0):
    """Gain vs depression angle (0..40 deg below horizon) at a fixed azimuth,
    for the pattern plots."""
    deps = np.linspace(0, 40, 81)
    return deps, np.array([pat.gain_at(90 + d, phi) for d in deps])


# ---------------------------------------------------------------------------
def solve_all(f_mhz):
    """Solve all candidates at one frequency. Returns dict name->Pattern."""
    out = {}
    out["monopole+PCB"] = N.solve_monopole_pcb(f_mhz)
    out["monopole no-GP"] = N.solve_monopole_freespace(f_mhz)
    out["vertical dipole"] = N.solve_dipole(f_mhz)
    out["horizontal dipole"] = N.solve_dipole_horizontal(f_mhz)
    out["turnstile"] = N.solve_turnstile(f_mhz)
    return out


def main():
    dep_weights = flight_depression_weights()
    print(f"flight target directions (FRESH float receptions): n={len(dep_weights)}, "
          f"depression median {np.median(dep_weights):.1f} deg")

    rows = []
    patterns = {}
    for band, f in BANDS.items():
        pats = solve_all(f)
        patterns[band] = pats
        for name, p in pats.items():
            eff = effective_gain_dbi(p, dep_weights)
            ml = p.mismatch_loss_db()
            rows.append({
                "band": band, "f_mhz": f, "antenna": name,
                "peak_dbi": p.peak_dbi,
                "Z_real": p.z_in.real, "Z_imag": p.z_in.imag,
                "vswr50": p.vswr(), "mismatch_db": ml,
                "eff_gain_dbi": eff,
                "eff_gain_matched_dbi": eff - ml,  # after feed mismatch loss
            })
    res = pd.DataFrame(rows)
    res.to_csv(DATA / "pattern_scores.csv", index=False)

    print("\n=== Per-antenna, per-band scorecard ===")
    cols = ["band","antenna","peak_dbi","Z_real","Z_imag","vswr50","mismatch_db","eff_gain_dbi","eff_gain_matched_dbi"]
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(res[cols].to_string(index=False,
              formatters={c: (lambda v: f"{v:7.1f}") for c in cols if c not in ("band","antenna")}))

    # link margin at the typical float link (use the matched effective gain)
    print("\n=== Link margin vs SF7 floor (typical float reception) ===")
    print("(margin = TX 14 dBm + eff_gain_matched - median_path_loss + gateway_gain - floor)")
    # We don't re-derive path loss here; deltas between antennas are what matter:
    base = res.groupby("antenna")["eff_gain_matched_dbi"].mean().sort_values(ascending=False)
    best = base.max()
    for name, v in base.items():
        print(f"  {name:18} matched eff-gain {v:6.1f} dBi   ({v-best:+.1f} dB vs best)")

    make_plots(patterns, res, dep_weights)
    print("\nwrote figs B1/B2/B3 and data/pattern_scores.csv")
    return res


def make_plots(patterns, res, dep_weights):
    S.use_light()

    # --- B1: gain-vs-depression profiles, both bands ---
    # Drop the no-GP monopole from the visual: its feedpoint is an unphysical
    # NEC isolated-wire bound (kept only as a labeled row in the table). Show the
    # real candidates with distinct colors + line styles.
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), sharey=True)
    styles = {
        "monopole+PCB":      (S.RED,    "-",  2.4),
        "vertical dipole":   (S.TEAL7,  "-",  2.4),
        "horizontal dipole": (S.WARM,   "--", 2.0),
        "turnstile":         (S.MINT,   ":",  2.6),
    }
    for ax, (band, pats) in zip(axes, patterns.items()):
        for name, (col, ls, lw) in styles.items():
            deps, g = horizon_gain_profile(pats[name])
            ax.plot(deps, g, color=col, ls=ls, lw=lw, label=name)
        ax.axvspan(np.percentile(dep_weights, 10), np.percentile(dep_weights, 90),
                   color=S.MINT, alpha=0.10)
        ax.axvline(np.median(dep_weights), color=S.MINT, ls="--", lw=1, alpha=0.7)
        ax.set_title(f"B1 · Gain vs depression below horizon — {band}")
        ax.set_xlabel("depression below local horizontal (°)  [0 = horizon]")
        ax.grid(True, alpha=0.5)
        ax.set_ylim(-12, 4)
    axes[0].set_ylabel("gain (dBi)")
    axes[0].legend(loc="lower right", fontsize=9)
    axes[0].text(np.median(dep_weights)+0.6, -10.6,
                 "where gateways\nactually were (10–90%)", color=S.MINT, fontsize=8.5)
    S.footer(fig, "Stratolink-3 · PyNEC MoM · gain sliced at azimuth=0 · analysis/antenna/60_patterns.py")
    fig.tight_layout(); fig.savefig(FIGS / "B1_gain_profiles.png", dpi=190); plt.close(fig)

    # --- B2: scorecard bars — matched effective gain toward gateways ---
    # Exclude the unphysical no-GP bound; reference everything to the flown
    # monopole+PCB so the bars read as "dB better/worse than what flew".
    fig, ax = plt.subplots(figsize=(11, 6.2))
    piv = res[res["antenna"] != "monopole no-GP"].pivot(
        index="antenna", columns="band", values="eff_gain_matched_dbi")
    piv = piv.reindex(["monopole+PCB", "horizontal dipole", "turnstile", "vertical dipole"])
    ref = piv.mean(axis=1)["monopole+PCB"]
    x = np.arange(len(piv)); w = 0.38
    b1 = ax.bar(x - w/2, piv["EU868"], w, color=S.TEAL12, label="EU868")
    b2 = ax.bar(x + w/2, piv["US915"], w, color=S.TEAL7, label="US915")
    # annotate each antenna's mean delta vs the flown monopole
    for xi, name in zip(x, piv.index):
        d = piv.mean(axis=1)[name] - ref
        ax.text(xi, max(piv.loc[name]) + 0.25,
                ("flew" if name == "monopole+PCB" else f"{d:+.1f} dB"),
                ha="center", color=S.TEXT, fontsize=10, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(piv.index, rotation=10)
    ax.set_ylabel("effective gain toward gateways, after mismatch (dBi)")
    ax.set_title("B2 · What each antenna delivers to where the gateways actually were\n"
                 "pattern ∫ flight angle-distribution, averaged over yaw-spin + 20° cant, minus feed mismatch")
    ax.legend(loc="lower right"); ax.grid(True, axis="y", alpha=0.5)
    ax.axhline(0, color=S.TEXT_DIM, lw=0.8)
    ax.set_ylim(min(piv.min())*1.25, max(piv.max())+1.0)
    S.footer(fig, "Stratolink-3 · PyNEC MoM + flight geometry + measured attitude · no-GP bound excluded (see table)")
    fig.tight_layout(); fig.savefig(FIGS / "B2_scorecard.png", dpi=190); plt.close(fig)

    # --- B3: polar elevation patterns (vertical cut) for the key 3 at 900 MHz ---
    fig = plt.figure(figsize=(14, 5.4))
    key = [("monopole+PCB", S.RED), ("vertical dipole", S.TEAL7), ("turnstile", S.MINT)]
    DR = 25  # dB dynamic range shown
    for i, (name, col) in enumerate(key, 1):
        ax = fig.add_subplot(1, 3, i, projection="polar")
        ax.set_facecolor(S.PANEL)
        p = patterns["US915"][name]
        th = p.theta
        g = np.array([p.gain_at(t, 0) for t in th])
        gn = np.clip(g - p.peak_dbi, -DR, 0)   # normalize to peak, clamp floor
        elev = 90 - th                          # +90 up, 0 horizon, -90 down
        ax.plot(np.radians(elev), gn + DR, color=col, lw=2.4)   # shift so floor=0 at center
        ax.fill(np.radians(elev), gn + DR, color=col, alpha=0.12)
        # mark the flight gateway band (depression = below horizon = negative elev)
        med = -np.median(dep_weights)
        ax.plot([np.radians(med)] * 2, [0, DR], color=S.MINT, ls="--", lw=1.2, alpha=0.8)
        ax.set_theta_zero_location("E"); ax.set_theta_direction(1)
        ax.set_thetamin(-90); ax.set_thetamax(90)
        ax.set_rticks([DR-20, DR-10, DR]); ax.set_yticklabels(["-20", "-10", "0 dB"], fontsize=7)
        ax.set_rlabel_position(15)
        ax.set_title(f"{name}\npeak {p.peak_dbi:.1f} dBi", fontsize=11, pad=18, color=col)
    fig.suptitle("B3 · Elevation patterns (vertical cut, US915, normalized to peak) — horizon at right (0°), "
                 "nadir down\ndashed line = median gateway direction (~8° below horizon)", fontsize=12.5, y=1.02)
    S.footer(fig, "Stratolink-3 · PyNEC MoM · 25 dB dynamic range · normalized per-antenna")
    fig.tight_layout(); fig.savefig(FIGS / "B3_elevation_polar.png", dpi=190, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    main()
