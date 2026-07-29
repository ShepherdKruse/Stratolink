#!/usr/bin/env python3
"""Does it make sense to RESET / cold-start the GPS every cycle?

Substantiates, against the real 1F-supercap power budget, why "reset every cycle"
is the wrong lever and why "GPS on every high-tier packet" is instead achievable
near-free via retained-BBR HOT starts (the software-backup path we already use).

The crux is GPS start physics:
  * HOT start  (BBR retained on V_IO via UBX-RXM-PMREQ backup, ~15 uA): TTFF ~2 s.
  * COLD start (BBR wiped by a PA0 reset or a brownout): TTFF >= ~26-30 s, because
    a full ephemeris must be re-downloaded from the 50 bps satellite nav message
    (subframes 1-3, one full set per ~30 s frame). This floor is RF-bound, not
    compute-bound -- you cannot reset your way to a fast fix.

Hardware (firmware/include/stratolink_pins.h):
  C = 1 F, VSTOR 5.36 V max, conservative 3.32 V historical reported-plateau
  accounting endpoint -> 8.86 J; absolute min 2.51 V -> 11.2 J. The plateau is
  not measured VSTOR/BOR because the flown fixed-VDDA ADC lost observability in
  buck dropout. GPS is allowed at tier <= REDUCED (>=3.5 V).

Run: analysis/.venv/bin/python analysis/power/gps_start_power.py
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
try:
    import _style as S
    S.use_light()
    RED, MINT, WARM, DIM = S.RED, S.MINT, S.WARM, S.TEXT_DIM
    _footer = lambda fig, t: S.footer(fig, t, light=True)
except Exception:
    RED, MINT, WARM, DIM = "#e0594a", "#2a9d4e", "#f4a259", "#7e8aa3"
    plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white"})
    _footer = lambda fig, t: fig.text(0.99, 0.01, t, ha="right", va="bottom",
                                      fontsize=7.5, color=DIM)

# ---- hardware constants (firmware/include/stratolink_pins.h) ----
C_F        = 1.0
V_MAX      = 5.36
V_ACCOUNTING_FLOOR = 3.32  # conservative Flight-3 reported plateau, not BOR metrology
V_MIN      = 2.51
E_USABLE   = 0.5 * C_F * (V_MAX**2 - V_ACCOUNTING_FLOOR**2)
E_FULL     = 0.5 * C_F * (V_MAX**2 - V_MIN**2)     # 11.2 J absolute

# ---- loads (datasheet typicals) ----
I_GPS_ACQ  = 0.030    # MAX-M10S acquisition ~25-30 mA (use 30, conservative)
I_GPS_BKP  = 15e-6    # software-backup, BBR retained
I_MCU_ACT  = 0.005    # STM32WLE5 active during a fix poll
V_RAIL     = 3.3
ETA        = 0.85     # BQ25570 buck efficiency
P_ACQ      = (I_GPS_ACQ + I_MCU_ACT) * V_RAIL / ETA   # ~0.135 W drawn from cap

T_HOT, T_COLD, T_COLD_MARG = 2.0, 30.0, 90.0          # TTFF / window seconds
CADENCE_SEC = 1200.0                                   # flight config: SF9 / 20 min
CYC_PER_DAY = 86400.0 / CADENCE_SEC                    # 72/day

def e_acq(t):  # energy pulled from the cap for one acquisition of length t
    return P_ACQ * t

def main():
    hot, cold, marg = e_acq(T_HOT), e_acq(T_COLD), e_acq(T_COLD_MARG)
    print("=== energy per acquisition vs the 8.86 J conservative accounting window ===")
    for name, e, t in [("HOT (2s, BBR kept)", hot, T_HOT),
                       ("COLD (30s, reset)", cold, T_COLD),
                       ("COLD marginal (90s window)", marg, T_COLD_MARG)]:
        print(f"  {name:28} {e:6.2f} J  = {100*e/E_USABLE:5.1f}% of accounting window   (I*t={I_GPS_ACQ*1e3:.0f}mA*{t:.0f}s)")

    print(f"\n=== daily GPS energy at {CYC_PER_DAY:.0f} cycles/day (SF9/20-min) ===")
    backup_day = I_GPS_BKP * (V_MAX) * 86400  # ~ tiny
    strategies = {
        "HOT every cycle (retain BBR)":      CYC_PER_DAY*hot + backup_day,
        "reset every 10th cycle":            (CYC_PER_DAY*0.9*hot + CYC_PER_DAY*0.1*cold + backup_day),
        "reset every 5th cycle":             (CYC_PER_DAY*0.8*hot + CYC_PER_DAY*0.2*cold + backup_day),
        "RESET EVERY CYCLE (cold)":          CYC_PER_DAY*cold,
        "RESET EVERY CYCLE (90s marginal)":  CYC_PER_DAY*marg,
    }
    for k, v in strategies.items():
        print(f"  {k:34} {v:7.0f} J/day   ({v/(CYC_PER_DAY*hot+backup_day):4.1f}x the hot baseline)")

    # ---- cap-voltage trajectory during ONE acquisition, solar = 0 (spin-null) ----
    def v_traj(t_end, solar_w):
        t = np.linspace(0, t_end, 400)
        E0 = 0.5 * C_F * 4.5**2                  # start at 4.5 V (FULL/REDUCED boundary)
        E = E0 - (P_ACQ - solar_w) * t
        E = np.clip(E, 0.5*C_F*1.0**2, None)
        return t, np.sqrt(2*E/C_F)

    fig, ax = plt.subplots(1, 3, figsize=(16.5, 5.2))

    # Panel A: energy per acquisition vs cap
    bars = ["HOT\n2 s", "COLD\n30 s", "COLD\n90 s"]
    vals = [hot, cold, marg]
    cols = [MINT, WARM, RED]
    ax[0].bar(bars, vals, color=cols, alpha=0.9)
    ax[0].axhline(E_USABLE, color=DIM, ls="--", lw=1.6)
    ax[0].text(-0.35, E_USABLE+0.2,
               f"accounting window = {E_USABLE:.1f} J\n(5.36→3.32 V reported plateau)",
               color=DIM, fontsize=8.5, ha="left")
    ax[0].axhline(E_FULL, color=DIM, ls=":", lw=1.2)
    ax[0].text(-0.35, E_FULL+0.2, f"legacy 2.51 V window = {E_FULL:.1f} J",
               color=DIM, fontsize=8, ha="left")
    for i, v in enumerate(vals):
        ax[0].text(i, v+0.25,
                   f"{v:.1f} J\n{100*v/E_USABLE:.0f}% of acct. window",
                   ha="center", fontsize=9, fontweight="bold")
    ax[0].set_ylabel("energy per fix, from the cap (J)")
    ax[0].set_ylim(0, 13)
    ax[0].set_title("A · One cold start consumes ~46% of the accounting window\nhot start is ~3%")

    # Panel B: daily energy, log
    names = list(strategies.keys()); dvals = list(strategies.values())
    ax[1].barh(range(len(names)), dvals,
               color=[MINT, "#9bd6a8", WARM, RED, "#a81e10"])
    ax[1].set_yticks(range(len(names)))
    ax[1].set_yticklabels([n.replace(" (", "\n(") for n in names], fontsize=8)
    ax[1].invert_yaxis()
    ax[1].set_xscale("log")
    ax[1].set_xlabel("GPS energy per day (J/day, log)")
    for i, v in enumerate(dvals):
        ax[1].text(v*1.1, i, f"{v:.0f}", va="center", fontsize=8.5)
    cold_ratio = strategies["RESET EVERY CYCLE (cold)"] / strategies[
        "HOT every cycle (retain BBR)"
    ]
    marginal_ratio = strategies["RESET EVERY CYCLE (90s marginal)"] / strategies[
        "HOT every cycle (retain BBR)"
    ]
    ax[1].set_title(
        f"B · Reset-every-cycle costs {cold_ratio:.0f}-{marginal_ratio:.0f}×\n"
        f"the hot-start budget ({CYC_PER_DAY:.0f} fixes/day)"
    )

    # Panel C: cap voltage during one acquisition, no solar (a spin null)
    for t_end, c, lbl in [(T_HOT, MINT, "HOT 2 s"),
                          (T_COLD, WARM, "COLD 30 s"),
                          (T_COLD_MARG, RED, "COLD 90 s")]:
        t, v = v_traj(t_end, 0.0)
        ax[2].plot(t, v, color=c, lw=2.6, label=lbl)
        ax[2].scatter([t[-1]], [v[-1]], color=c, s=40, zorder=5)
    ax[2].axhline(V_ACCOUNTING_FLOOR, color=RED, ls="--", lw=1.6)
    ax[2].text(91, V_ACCOUNTING_FLOOR+0.05, "historical reported plateau 3.32 V",
               color=RED, fontsize=8.5, ha="right")
    ax[2].set_xlabel("time into acquisition (s)")
    ax[2].set_ylabel("supercap voltage (V)")
    ax[2].set_title("C · Cap during ONE fix at a solar null\n(spinning payload; illustrative endpoint)")
    ax[2].legend(loc="lower left", fontsize=9)
    ax[2].set_ylim(2.4, 4.7)

    _footer(
        fig,
        "Stratolink · nominal 1F / historical 5.36→3.32V accounting window=8.86J · MAX-M10S 30mA acq · "
        "cold TTFF≈30s ephemeris-bound · 72 cyc/day",
    )
    fig.tight_layout()
    out = HERE / "gps_start_power.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"\nwrote {out}")

if __name__ == "__main__":
    main()
