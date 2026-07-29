#!/usr/bin/env python3
"""Physics of closing the ocean gap with balloon-to-balloon (B2B) LoRa relay.

Three questions, answered from first principles (reusing the vetted Semtech
link-budget in antenna/_link.py):
  1. How far can two balloons at float altitude see each other? (LOS horizon)
  2. Does a raw-LoRa P2P link close at that range, per SF? (link budget)
  3. How many balloons would a relay CHAIN need to span an ocean, and is a
     free-drifting fleet able to hold that chain? (the hard truth)

Raw LoRa P2P is not charged to TTN's 30 s/day fair-access allowance, but it
still consumes energy/shared spectrum and is subject to the applicable radio
rules. This script is a propagation/fleet model, not a regulatory authorization.

Run: analysis/.venv/bin/python analysis/network/40_ocean_relay_physics.py
"""
from __future__ import annotations
import pathlib
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ANT = HERE.parent / "antenna"
sys.path.insert(0, str(ANT))
from _link import sensitivity_dbm, fspl_db, radio_horizon_km  # noqa: E402
import _style as S  # noqa: E402

FIGS = HERE / "figs"
S.use_light()

ALT_M = 10000.0          # our observed float
F_MHZ = 915.0            # hypothetical link-budget case, not a global channel authorization
TX_DBM = 14.0            # our fixed TX power
G_DBI = 2.15             # each balloon, ~dipole toward horizon
POL_FADE_DB = 2.0        # tumble/pol mismatch budget (both ends move)
ATL_SPANS_KM = {"Newfoundland->Iberia (~3,500 km)": 3500,
                "US coast->Iberia (~5,500 km)": 5500}


def b2b_budget_range_km(sf, f_mhz=F_MHZ):
    """Link-budget-limited B2B range: distance where Prx == sensitivity."""
    s = sensitivity_dbm(sf)
    pl_max = TX_DBM + 2 * G_DBI - POL_FADE_DB - s
    return 10 ** ((pl_max - 20 * np.log10(f_mhz) - 32.45) / 20.0)


def los_b2b_km(h1=ALT_M, h2=ALT_M):
    """Balloon-to-balloon line-of-sight (4/3-earth), each to the shared tangent."""
    return radio_horizon_km(h1) + radio_horizon_km(h2)


def main():
    los = los_b2b_km()
    print(f"LOS: balloon@{ALT_M/1000:.0f}km -> sea horizon = {radio_horizon_km(ALT_M):.0f} km; "
          f"balloon-to-balloon (both @{ALT_M/1000:.0f}km) = {los:.0f} km")
    print(f"\n{'SF':>3} {'sens(dBm)':>10} {'B2B budget(km)':>15} {'hop=min(budget,LOS)':>20}")
    sfs = list(range(7, 13))
    hop = {}
    for sf in sfs:
        br = b2b_budget_range_km(sf)
        h = min(br, los)
        hop[sf] = h
        lim = "LOS-limited" if br > los else "link-limited"
        print(f"{sf:>3} {sensitivity_dbm(sf):>10.1f} {br:>15.0f} {h:>16.0f}  ({lim})")

    print("\n==== balloons needed to span an ocean as a PERFECTLY-SPACED chain ====")
    print(f"{'SF':>3} " + " ".join(f"{name.split('(')[0].strip():>26}" for name in ATL_SPANS_KM))
    for sf in sfs:
        cells = []
        for span in ATL_SPANS_KM.values():
            n = int(np.ceil(span / hop[sf])) + 1   # +1: endpoints
            cells.append(f"{n:>26d}")
        print(f"{sf:>3} " + " ".join(cells))
    print("\nNOTE: this is the BEST case (balloons exactly hop-spaced in a line). Free-")
    print("drifting balloons cannot hold that geometry, winds scatter them in 2-D, so a")
    print("deterministic chain is not maintainable. Realistic operation = store-and-forward")
    print("(delay-tolerant): a balloon buffers fixes and dumps them on any opportunistic")
    print("B2B contact or ground pass. Coverage is then statistical in the fleet size, not")
    print("guaranteed for one balloon crossing now.")

    # ---- figures ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))
    # (1) hop distance vs SF: budget vs LOS cap
    budget = [b2b_budget_range_km(sf) for sf in sfs]
    ax1.plot(sfs, budget, "o-", color=S.TEAL10, label="link-budget range (FSPL)")
    ax1.axhline(los, color=S.RED, ls="--", lw=1.6, label=f"LOS horizon (both @10 km) = {los:.0f} km")
    ax1.plot(sfs, [hop[s] for s in sfs], "s-", color=S.L_ACCENT, lw=2, label="usable hop = min(budget, LOS)")
    ax1.fill_between(sfs, [hop[s] for s in sfs], alpha=0.12, color=S.L_ACCENT)
    ax1.set_xlabel("spreading factor"); ax1.set_ylabel("balloon-to-balloon range (km)")
    ax1.set_title("B2B LoRa hop: link budget vs line-of-sight")
    ax1.legend(fontsize=8.5); ax1.grid(True, alpha=0.4)
    # (2) balloons needed vs SF
    for name, span in ATL_SPANS_KM.items():
        ax2.plot(sfs, [int(np.ceil(span / hop[s])) + 1 for s in sfs], "o-", label=name)
    ax2.set_xlabel("spreading factor"); ax2.set_ylabel("balloons to span ocean (best case)")
    ax2.set_title("Chain size to bridge the Atlantic")
    ax2.legend(fontsize=8.5); ax2.grid(True, alpha=0.4)
    fig.suptitle("Balloon-to-balloon relay physics, feasible per-hop, but a free-drifting "
                 "chain can't hold position", fontsize=12.5)
    S.footer(fig, "40_ocean_relay_physics.py · Semtech link budget, 4/3-earth LOS, 915 MHz, TX 14 dBm", light=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(FIGS / "O1_b2b_relay_physics.png", dpi=140); plt.close(fig)
    print("\nwrote O1_b2b_relay_physics.png")


if __name__ == "__main__":
    main()
