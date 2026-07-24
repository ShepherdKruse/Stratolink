"""PART F: Solar-panel counterpoise bonding / terminal orientation.

Teddy's question (2026-06-02): the two solar panels are the monopole's counterpoise.
Each panel has a (+) and (-) terminal at opposite ends (silver strip tabs); one ends up
near the board, one far. Flight-3 flew (+) hot near the board and (-) GROUND at the FAR
edge, with the two panel grounds joined by a copper cross-strap perpendicular to the
antenna (confirmed from the launch photo). Proposed swap: (-) ground NEAR the board
(~5 mm short bond), (+) hot on the outer edges. Does the shorter ground path help, by how
much, and what mounting/wiring is actually best?

Two layers here:
  fig F1  THEORY: the panel->board ground bond is a series inductor; its reactance vs
            length, next to the Part B feed impedance. Pure auditable physics.
  figs F2/F3  NEC A/B: model the ground bond EXPLICITLY and compare four wirings of the
            SAME panels (flown / swap / ideal / floating) for feed Z, match, spin- &
            gateway-weighted effective gain, and azimuth ripple. The substantiation.

Bench A/B on a spare board is the final decider (08_bench_test_plan.md).
Run:  analysis/.venv/bin/python analysis/antenna/C0_solar.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import _style as S
import _nec as N
import _tilt as T

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"

MU0 = 4e-7 * np.pi            # H/m
WIRE_A = 0.0003              # 0.3 mm wire radius (matches _nec.WIRE_R, ~22 AWG enameled)
BANDS = {"US915 (~905 MHz)": 904.5e6, "EU868 (~868 MHz)": 868.1e6}
FEED_R = 21.0                # Ohm  Part B measured as-flown monopole feed R
FEED_X = 68.0                # Ohm  |reactance| the small ground plane detunes it to
FLOWN_TAU = 20.0             # measured corner-hang (Part B-0)

# config display order + colors
CFG_ORDER = ["floating", "flown", "swap", "ideal"]
CFG_LABEL = {"floating": "floating\n(no GND bond)",
             "flown": "flown\n(GND→far edge)",
             "swap": "swap\n(GND→near edge)",
             "ideal": "ideal\n(fully bonded)"}


# ===========================================================================
# THEORY (F1)
# ===========================================================================
def wire_L_nH(length_m, a=WIRE_A):
    """External self-inductance of a straight round wire (length>>a), at RF where
    skin effect drives internal inductance ~0:  L = (mu0*l/2pi)[ln(2l/a) - 1].
    Standard result (Rosa 1908; Terman). Returns nH."""
    l = np.asarray(length_m, float)
    return 1e9 * (MU0 * l / (2 * np.pi)) * (np.log(2 * l / a) - 1.0)


def fig_F1_theory():
    S.use_light()
    ell_mm = np.linspace(1, 40, 200)
    L_nH = wire_L_nH(ell_mm / 1000.0)
    fig, ax = plt.subplots(figsize=(10.5, 6.4))
    band_cols = {"US915 (~905 MHz)": S.L_SERIES["vertical dipole"],
                 "EU868 (~868 MHz)": S.L_SERIES["as-flown +panels"]}
    for name, f in BANDS.items():
        X = 2 * np.pi * f * (L_nH * 1e-9)
        ax.plot(ell_mm, X, lw=2.6, color=band_cols[name], label=f"$X_{{bond}}=\\omega L$, {name}")
    ax.axhline(FEED_R, color=S.DIM, ls=":", lw=1.6)
    ax.text(40, FEED_R + 1.5, "monopole feed R ≈ 21 Ω (Part B)", ha="right", va="bottom",
            color=S.TEXT_DIM, fontsize=9)
    ax.axhline(FEED_X, color=S.WARM, ls="--", lw=1.6)
    ax.text(40, FEED_X + 1.5, "|feed reactance| ≈ 68 Ω  (small ground-plane detuning, Part B)",
            ha="right", va="bottom", color=S.WARM, fontsize=9)
    f0 = 904.5e6
    x5 = 2 * np.pi * f0 * (wire_L_nH(0.005) * 1e-9)
    ax.scatter([5], [x5], s=90, zorder=6, color=S.MINT, edgecolor="white", lw=1.2)
    ax.annotate(f"SWAP: 5 mm ground bond\nX ≈ {x5:.0f} Ω  (stays << antenna Z)",
                xy=(5, x5), xytext=(8.5, x5 + 24), fontsize=10, color=S.MINT,
                arrowprops=dict(arrowstyle="->", color=S.MINT, lw=1.5))
    ax.axvspan(15, 30, color=S.RED, alpha=0.10)
    xf_lo = 2 * np.pi * f0 * (wire_L_nH(0.015) * 1e-9)
    xf_hi = 2 * np.pi * f0 * (wire_L_nH(0.030) * 1e-9)
    ax.text(22.5, xf_hi + 6, f"FLOWN: ground at far edge\n+ cross-strap, RF path ~15-30 mm\n"
            f"X ≈ {xf_lo:.0f}-{xf_hi:.0f} Ω  (≳ antenna Z, chokes the panel)",
            ha="center", va="bottom", color=S.RED, fontsize=10)
    ax.set_xlabel("panel-ground → board-ground bond length  (mm)")
    ax.set_ylabel("series RF reactance of the bond,  $X = \\omega L$   (Ω)")
    ax.set_title("F1 · Why solar-ground routing is an RF lever, not just a wiring choice\n"
                 "the bond between the panel counterpoise and the board RF ground is an "
                 "inductor; its reactance grows ~linearly with length")
    ax.set_xlim(0, 40); ax.set_ylim(0, 170)
    ax.legend(loc="upper left", fontsize=10)
    S.footer(fig, "Stratolink · straight-wire inductance L=(μ0·l/2π)[ln(2l/a)−1], a=0.3 mm · "
                  "feed Z from Part B PyNEC · THEORY layer (verify with NEC + bench)", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "F1_bond_reactance.png", dpi=180); plt.close(fig)
    print("wrote F1_bond_reactance.png")


# ===========================================================================
# NEC A/B (F2/F3): the flown monopole + two flanking panels, GND bond modeled
# ===========================================================================
def build_solar(geo, wl, config="flown", mono_len=None, seg=21,
                gap=0.010, panel_w=0.07, bond_y=0.006):
    """Monopole (down -z, fed at board bottom-center) + two flanking solar panels,
    with the panel->board GROUND BOND modeled EXPLICITLY. Panel geometry is held
    FIXED across configs; only the ground wiring changes (the variable Teddy asks
    about):
      'floating' no galvanic bond (capacitive coupling only), worst-case bound.
      'flown'    single strap from the board edge, routed behind the plane, to the
                 panel's FAR (outer) edge, flight-3 (GND tabs at far edge + strap).
      'swap'     short strap from the board edge to the panel's NEAR (inner) edge.
      'ideal'    panel inner edge stitched to the board edge at every node, best case.
    Board in x-z plane (y=0), long axis z, monopole along -z. Panels coplanar (a
    dihedral refinement is a TODO). Shared z-lattice so bond endpoints land on real
    nodes (NEC bonds only at coincident nodes)."""
    W, H = N.PCB_W, N.PCB_H
    Lm = mono_len or wl / 4
    nbx, nbz = 4, 6
    dz = H / nbz
    # board ground grid
    tag = N.grid_rect(geo, 100, (-W/2, 0, 0), (W, 0, 0), (0, 0, H), nbx, nbz)
    # panels on the shared dz lattice, centered vertically on the board
    nu_p, nv_p = 5, 10
    panel_h = nv_p * dz
    zp0 = H/2 - (nv_p/2)*dz
    xL_in = -(W/2 + gap); xL_out = xL_in - panel_w
    xR_in = (W/2 + gap);  xR_out = xR_in + panel_w
    tag = N.grid_rect(geo, tag, (xL_out, 0, zp0), (panel_w, 0, 0), (0, 0, panel_h), nu_p, nv_p)
    tag = N.grid_rect(geo, tag, (xR_in,  0, zp0), (panel_w, 0, 0), (0, 0, panel_h), nu_p, nv_p)

    zb = 3 * dz                                  # bond height = a node on both grids
    bt = [900]
    def bond(x1, y1, z1, x2, y2, z2):
        geo.wire(bt[0], 1, x1, y1, z1, x2, y2, z2, N.WIRE_R, 1, 1); bt[0] += 1

    if config == "swap":
        bond(-W/2, 0, zb, xL_in, 0, zb)
        bond(W/2, 0, zb, xR_in, 0, zb)
    elif config == "flown":
        # strap routed at y=bond_y (behind the plane) out to the FAR edge
        bond(-W/2, 0, zb, -W/2, bond_y, zb); bond(-W/2, bond_y, zb, xL_out, bond_y, zb); bond(xL_out, bond_y, zb, xL_out, 0, zb)
        bond(W/2, 0, zb,  W/2, bond_y, zb);  bond(W/2, bond_y, zb,  xR_out, bond_y, zb); bond(xR_out, bond_y, zb, xR_out, 0, zb)
    elif config == "ideal":
        for j in range(nbz + 1):
            z = j * dz
            bond(-W/2, 0, z, xL_in, 0, z)
            bond(W/2, 0, z, xR_in, 0, z)
    elif config == "floating":
        pass
    else:
        raise ValueError(config)

    geo.wire(1, seg, 0, 0, 0.0, 0, 0, -Lm, N.WIRE_R, 1, 1)   # monopole, feed at base
    return 1, 1


def gateway_depressions():
    df = pd.read_parquet(DATA / "receptions_geo.parquet")
    fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"] & (df["balloon_alt"] >= 8000)]
    return fresh["depr_balloon_deg"].dropna().values


def azimuth_ripple_db(pat, dep_deg=8.0):
    """Peak-to-trough body-frame azimuth variation at the gateway elevation (how
    non-omni the raw pattern is where gateways actually sit)."""
    it = int(np.argmin(np.abs(pat.theta - (90 + dep_deg))))
    row = pat.gain[it, :]
    return float(np.nanmax(row) - np.nanmin(row))


def sweep_length(cfg, f_mhz, lens):
    """Solve the config across a monopole-length sweep; return list of (Lm, Pattern)."""
    return [(Lm, N._solve(lambda g, wl: build_solar(g, wl, config=cfg, mono_len=Lm), f_mhz))
            for Lm in lens]


def run_nec_ab(f_mhz=904.5):
    deps = gateway_depressions()
    wl = N.C_M / (f_mhz * 1e6); q = wl / 4
    # length grid: 0.55..1.30 of a free-space quarter wave, plus exactly wl/4
    lens = np.unique(np.round(np.concatenate([np.linspace(0.55, 1.30, 16) * q, [q]]), 5))
    print(f"\n=== NEC A/B @ {f_mhz} MHz, gateway deps n={len(deps)}, median {np.median(deps):.1f}° ===")
    print(f"    monopole-length sweep {lens[0]*1000:.0f}..{lens[-1]*1000:.0f} mm (λ/4={q*1000:.1f} mm)\n")

    sweeps, picks, rows = {}, {}, []
    for cfg in CFG_ORDER:
        sw = sweep_length(cfg, f_mhz, lens)
        sweeps[cfg] = sw
        vswrs = np.array([p.vswr() for _, p in sw])
        i_q = int(np.argmin(np.abs(lens - q)))          # untuned reference (λ/4)
        i_best = int(np.argmin(vswrs))                  # tuned (best match)
        picks[cfg] = dict(untuned=sw[i_q], tuned=sw[i_best])
        for mode, (Lm, p) in picks[cfg].items():
            effm = T.effective_gain_over_flight(p, deps, FLOWN_TAU)
            tot = effm - p.mismatch_loss_db()
            rows.append(dict(config=cfg, mode=mode, Lm_mm=Lm * 1000, R=p.z_in.real, X=p.z_in.imag,
                             vswr=p.vswr(), mm=p.mismatch_loss_db(), effm=effm,
                             eff_total=tot, azrip=azimuth_ripple_db(p)))
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "solar_bond_scorecard.csv", index=False)
    print(df.to_string(index=False,
          formatters={"Lm_mm": "{:.0f}".format, "R": "{:.1f}".format, "X": "{:+.1f}".format,
                      "vswr": "{:.1f}".format, "mm": "{:.1f}".format, "effm": "{:+.2f}".format,
                      "eff_total": "{:+.2f}".format, "azrip": "{:.1f}".format}))

    piv = df.pivot(index="config", columns="mode", values="eff_total")
    print("\n  delivered effective gain (dBi):")
    for cfg in CFG_ORDER:
        print(f"    {cfg:9s} untuned(λ/4) {piv.loc[cfg,'untuned']:+.2f}   tuned {piv.loc[cfg,'tuned']:+.2f}")
    print(f"\n  >>> TUNED swap vs flown: {piv.loc['swap','tuned']-piv.loc['flown','tuned']:+.2f} dB"
          f"   |  UNTUNED swap vs flown: {piv.loc['swap','untuned']-piv.loc['flown','untuned']:+.2f} dB")

    make_F2(df)
    make_F4(sweeps, lens, q)
    make_F3({c: picks[c]["tuned"][1] for c in CFG_ORDER}, deps, tag="tuned")
    return df


def make_F2(df):
    """Untuned (λ/4) vs tuned delivered effective gain, per config."""
    S.use_light()
    fig, ax = plt.subplots(figsize=(11, 6.2))
    x = np.arange(len(CFG_ORDER)); w = 0.38
    piv = df.pivot(index="config", columns="mode", values="eff_total").loc[CFG_ORDER]
    ax.bar(x - w/2, piv["untuned"], w, color=S.DIM, edgecolor="white", lw=1.0, label="untuned (λ/4 wire)")
    ax.bar(x + w/2, piv["tuned"], w, color=S.MINT, edgecolor="white", lw=1.0, label="tuned (wire re-cut for best match)")
    for i, c in enumerate(CFG_ORDER):
        for off, m in ((-w/2, "untuned"), (w/2, "tuned")):
            v = piv.loc[c, m]
            ax.text(i + off, v + (0.08 if v >= 0 else -0.08), f"{v:+.2f}",
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5)
    ax.axhline(0, color=S.TEXT_DIM, lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels([CFG_LABEL[c] for c in CFG_ORDER])
    ax.set_ylabel("delivered effective gain toward gateways (dBi)\n[spin- & gateway-weighted − mismatch loss]")
    ax.set_title("F2 · Solar ground-bond A/B: does the wiring matter once you tune the wire?\n"
                 "same panels, four ground wirings; gray = fixed λ/4 wire, mint = wire re-cut to best match")
    ax.legend(loc="lower right", fontsize=10)
    S.footer(fig, "Stratolink · PyNEC NEC2 · monopole+2 panels, GND bond modeled · US915 904.5 MHz · "
                  "eff. gain over FRESH-float gateway depressions, τ=20°", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "F2_solar_scorecard.png", dpi=180); plt.close(fig)
    print("wrote F2_solar_scorecard.png")


def make_F4(sweeps, lens, q):
    """VSWR vs monopole length per config: the tunability / detuning story."""
    S.use_light()
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    cols = {"floating": S.DIM, "flown": S.RED, "swap": S.MINT, "ideal": S.L_SERIES["vertical dipole"]}
    for cfg in CFG_ORDER:
        v = [p.vswr() for _, p in sweeps[cfg]]
        ax.plot(lens * 1000, v, lw=2.3, color=cols[cfg], marker="o", ms=3,
                label=CFG_LABEL[cfg].replace("\n", " "))
        ib = int(np.argmin(v))
        ax.scatter([lens[ib]*1000], [v[ib]], s=70, color=cols[cfg], edgecolor="white", zorder=6)
    ax.axvline(q*1000, color=S.L_TEXT, ls=":", lw=1.3)
    ax.text(q*1000+1, ax.get_ylim()[1]*0.9, "free-space λ/4", fontsize=9)
    ax.axhline(2.0, color=S.WARM, ls="--", lw=1.2); ax.text(lens[0]*1000, 2.1, "VSWR 2 (≈0.5 dB)", fontsize=8.5, color=S.WARM)
    ax.set_ylim(1, 12)
    ax.set_xlabel("monopole wire length (mm)")
    ax.set_ylabel("feed VSWR vs 50 Ω")
    ax.set_title("F4 · Each wiring detunes the λ/4 wire differently, but all are tunable\n"
                 "dots = best match; grounding the big panel near the feed (swap) shifts resonance most")
    ax.legend(loc="upper right", fontsize=9.5)
    S.footer(fig, "Stratolink · PyNEC · feed Z vs monopole length, 4 ground wirings · US915 904.5 MHz", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "F4_vswr_vs_length.png", dpi=180); plt.close(fig)
    print("wrote F4_vswr_vs_length.png")


def make_F3(pats, deps, tag="tuned"):
    """Spin-averaged delivered gain vs gateway depression for the four configs."""
    S.use_light()
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    cols = {"floating": S.DIM, "flown": S.RED, "swap": S.MINT, "ideal": S.L_SERIES["vertical dipole"]}
    dep_grid = np.linspace(-10, 50, 121)
    for cfg in CFG_ORDER:
        p = pats[cfg]
        g = [T.spin_avg_gain_dbi(p, d, FLOWN_TAU, n_spin=36) - p.mismatch_loss_db() for d in dep_grid]
        ax.plot(dep_grid, g, lw=2.4, color=cols[cfg], label=CFG_LABEL[cfg].replace("\n", " "))
    ax2 = ax.twinx()
    ax2.hist(deps, bins=np.arange(0, 45, 3), color=S.DIM, alpha=0.30)
    ax2.set_yticks([]); ax2.set_ylabel("gateway count (flight)", color=S.TEXT_DIM)
    ax.axvline(np.median(deps), color=S.L_TEXT, ls=":", lw=1.2)
    ax.text(np.median(deps)+1, ax.get_ylim()[0]+0.4, f"median gateway {np.median(deps):.0f}°", fontsize=9)
    ax.set_zorder(ax2.get_zorder()+1); ax.patch.set_visible(False)
    ax.set_xlabel("gateway depression below horizontal (°)   [0 = horizon, →down]")
    ax.set_ylabel("delivered spin-averaged gain (dBi)  [incl. mismatch]")
    ax.set_title(f"F3 · Delivered gain vs gateway angle, solar ground-bond A/B ({tag} wire)\n"
                 "gateways cluster near the horizon (shaded); once tuned the four wirings nearly coincide")
    ax.legend(loc="lower left", fontsize=9.5)
    S.footer(fig, f"Stratolink · PyNEC · spin-averaged, τ=20° · {tag} monopole length · US915 904.5 MHz", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "F3_solar_gain_vs_depression.png", dpi=180); plt.close(fig)
    print("wrote F3_solar_gain_vs_depression.png")


def panel_size_sweep(f_mhz=904.5, widths=None):
    """Is the flown-vs-swap sign robust to panel size, or a resonance knife-edge?
    For each panel width, TUNE each wiring to best match and record delivered gain."""
    deps = gateway_depressions()
    wl = N.C_M / (f_mhz * 1e6); q = wl / 4
    lens = np.linspace(0.55, 1.30, 12) * q
    widths = np.arange(0.04, 0.115, 0.01) if widths is None else np.asarray(widths)
    out = {c: [] for c in ("floating", "flown", "swap")}
    print("\n=== Panel-size sensitivity (each wiring tuned) ===")
    for pw in widths:
        line = f"  panel_w={pw*1000:3.0f}mm ({pw/wl:.2f}λ): "
        for cfg in out:
            best = None
            for Lm in lens:
                p = N._solve(lambda g, w: build_solar(g, w, config=cfg, mono_len=Lm, panel_w=pw), f_mhz)
                if best is None or p.vswr() < best.vswr():
                    best = p
            tot = T.effective_gain_over_flight(best, deps, FLOWN_TAU) - best.mismatch_loss_db()
            out[cfg].append(tot)
            line += f"{cfg} {tot:+.2f}  "
        print(line)
    make_F5(widths, out, wl)
    return widths, out


def make_F5(widths, out, wl):
    S.use_light()
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    cols = {"floating": S.DIM, "flown": S.RED, "swap": S.MINT}
    for cfg, ys in out.items():
        ax.plot(widths * 1000, ys, lw=2.5, marker="o", ms=4, color=cols[cfg],
                label={"floating": "floating (no GND bond)", "flown": "flown (GND→far edge)",
                       "swap": "swap (GND→near edge)"}[cfg])
    ax.axvline(wl/4*1000, color=S.L_TEXT, ls=":", lw=1.3)
    ax.text(wl/4*1000+1.5, ax.get_ylim()[0]+0.15, "panel ≈ λ/4\n(resonant)", fontsize=9)
    ax.axvline(70, color=S.WARM, ls="--", lw=1.2); ax.text(70-2, ax.get_ylim()[1]-0.4, "photo est. ~70 mm", fontsize=8.5, color=S.WARM, ha="right")
    ax.set_xlabel("solar panel radial width, inner edge to outer edge (mm)")
    ax.set_ylabel("delivered effective gain toward gateways (dBi)\n[each wiring tuned to best match]")
    ax.set_title("F5 · Is the result robust to panel size? Each wiring re-tuned at every size\n"
                 "near the panel≈λ/4 resonance, grounding it at the near edge (swap) costs the most")
    ax.legend(loc="lower left", fontsize=10)
    S.footer(fig, "Stratolink · PyNEC · tuned delivered gain vs panel size · US915 904.5 MHz · "
                  "free-space, coplanar panels (model bounds, verify on bench)", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "F5_panel_size_sweep.png", dpi=180); plt.close(fig)
    print("wrote F5_panel_size_sweep.png")


def main():
    fig_F1_theory()
    run_nec_ab(904.5)
    panel_size_sweep(904.5)


if __name__ == "__main__":
    main()
