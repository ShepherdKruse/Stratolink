#!/usr/bin/env python3
"""Does a FLEET of cheap pico-balloons close the ocean gap by store-and-forward
relay? Teddy's point: at <$80/launch we can fly enough balloons that we don't
need a held 1-D chain, we need enough spatial DENSITY that an opportunistic
relay mesh PERCOLATES across the Atlantic corridor to a coast.

Model: scatter N balloons uniformly over the N-Atlantic jet corridor (they fan
out in latitude and spread in longitude as they drift). A balloon over a "ground"
region (within reach of N-America or Iberia gateways) is an offload point. Build
the B2B connectivity graph (edge if two balloons are within the per-SF hop range)
and flood-fill from the ground regions. An OCEAN balloon is "covered" if a chain
of hops connects it to ground. Sweep N, average over random realizations.

This is a random-geometric-graph percolation problem; the output is the fleet
size at which ocean coverage switches on, per spreading factor.

Run: analysis/.venv/bin/python analysis/network/50_constellation_coverage.py
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
import _style as S  # noqa: E402
S.use_light()
FIGS = HERE / "figs"

# N-Atlantic jet corridor the balloons drift through (deg)
LAT0, LAT1 = 35.0, 55.0          # latitudinal fan-out
LON_W, LON_E = -80.0, -5.0       # US east coast to Iberia
GROUND_W, GROUND_E = -67.0, -11.0  # west of W / east of E = within coastal gateway reach
R_EARTH = 6371.0088

# per-SF usable B2B hop (from 40_ocean_relay_physics.py: min(link budget, 825 km LOS))
HOPS = {"SF9 (510 km)": 510.0, "SF10 (680 km)": 680.0, "SF12 (825 km LOS)": 825.0}


def _haversine_matrix(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    dlat = la[:, None] - la[None, :]
    dlon = lo[:, None] - lo[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin(dlon / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def covered_fraction(N, R, rng):
    lat = rng.uniform(LAT0, LAT1, N)
    lon = rng.uniform(LON_W, LON_E, N)
    ground = (lon <= GROUND_W) | (lon >= GROUND_E)
    ocean = ~ground
    if ocean.sum() == 0:
        return np.nan
    D = _haversine_matrix(lat, lon)
    adj = (D <= R) & ~np.eye(N, dtype=bool)
    reached = ground.copy()
    frontier = ground.copy()
    while frontier.any():
        nxt = adj[frontier].any(axis=0) & ~reached
        if not nxt.any():
            break
        reached |= nxt
        frontier = nxt
    return (reached & ocean).sum() / ocean.sum()


def main():
    rng = np.random.default_rng(12345)  # fixed seed (Math.random unavailable anyway)
    Ns = np.arange(5, 205, 5)
    TRIALS = 400
    curves = {}
    print("Atlantic-corridor relay coverage (fraction of OCEAN balloons that reach a coast):\n")
    print(f"{'N':>4} " + " ".join(f"{k:>18}" for k in HOPS))
    results = {k: [] for k in HOPS}
    for N in Ns:
        row = []
        for k, R in HOPS.items():
            fr = np.mean([covered_fraction(int(N), R, rng) for _ in range(TRIALS)])
            results[k].append(fr); row.append(fr)
        if N % 20 == 0 or N == 5:
            print(f"{N:>4} " + " ".join(f"{v:>18.2f}" for v in row))
    curves = {k: np.array(v) for k, v in results.items()}

    print("\nfleet size for target ocean coverage (balloons simultaneously in corridor):")
    print(f"{'hop':>20} {'50% cov':>9} {'90% cov':>9}")
    n50 = {}
    for k in HOPS:
        c = curves[k]
        def first_at(th):
            idx = np.where(c >= th)[0]
            return int(Ns[idx[0]]) if len(idx) else None
        n50[k] = first_at(0.5)
        print(f"{k:>20} {str(first_at(0.5)):>9} {str(first_at(0.9)):>9}")

    # ---- figures ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2),
                                   gridspec_kw={"width_ratios": [1.05, 1]})
    cols = [S.TEAL7, S.TEAL10, S.MINT]
    for (k, _), c in zip(HOPS.items(), cols):
        ax1.plot(Ns, curves[k] * 100, "o-", ms=3, color=c, label=k)
    ax1.axhline(90, color=S.DIM, ls=":", lw=1)
    ax1.set_xlabel("balloons simultaneously in the Atlantic corridor")
    ax1.set_ylabel("% of ocean balloons relay-connected to a coast")
    ax1.set_title("Store-and-forward coverage vs fleet size")
    ax1.legend(fontsize=9); ax1.grid(True, alpha=0.4); ax1.set_ylim(0, 101)

    # sample realization at the SF10 50%-coverage fleet size
    Nshow = n50["SF10 (680 km)"] or 60
    R = 680.0
    lat = rng.uniform(LAT0, LAT1, Nshow); lon = rng.uniform(LON_W, LON_E, Nshow)
    ground = (lon <= GROUND_W) | (lon >= GROUND_E)
    D = _haversine_matrix(lat, lon); adj = (D <= R) & ~np.eye(Nshow, dtype=bool)
    reached = ground.copy(); frontier = ground.copy()
    while frontier.any():
        nxt = adj[frontier].any(axis=0) & ~reached
        if not nxt.any():
            break
        reached |= nxt; frontier = nxt
    ax2.axvspan(LON_W, GROUND_W, color=S.L_ACCENT, alpha=0.10)
    ax2.axvspan(GROUND_E, LON_E, color=S.L_ACCENT, alpha=0.10)
    ax2.text(GROUND_W - 6.5, 54, "N. America\ngateways", fontsize=8, color=S.L_ACCENT, ha="center")
    ax2.text(GROUND_E + 3, 54, "Iberia\ngateways", fontsize=8, color=S.L_ACCENT, ha="center")
    for i in range(Nshow):
        for j in range(i + 1, Nshow):
            if adj[i, j]:
                ax2.plot([lon[i], lon[j]], [lat[i], lat[j]], "-", color=S.DIM, lw=0.4, alpha=0.5, zorder=1)
    ax2.scatter(lon[ground], lat[ground], s=30, color=S.L_ACCENT, zorder=3, label="over gateways")
    oc_cov = (~ground) & reached
    oc_unc = (~ground) & ~reached
    ax2.scatter(lon[oc_cov], lat[oc_cov], s=26, color=S.TEAL10, zorder=3, label="ocean: relayed to coast")
    ax2.scatter(lon[oc_unc], lat[oc_unc], s=26, color=S.RED, zorder=3, label="ocean: stranded")
    ax2.set_xlim(LON_W, LON_E); ax2.set_ylim(LAT0, LAT1 + 2)
    ax2.set_xlabel("longitude"); ax2.set_ylabel("latitude")
    ax2.set_title(f"One realization: {Nshow} balloons, SF10 hop (680 km)")
    ax2.legend(fontsize=8, loc="lower center", ncol=2)
    fig.suptitle("A cheap-balloon FLEET closes the ocean gap by percolation, not by holding a chain",
                 fontsize=12.5)
    S.footer(fig, "50_constellation_coverage.py · random-geometric-graph Monte Carlo, "
             "N-Atlantic corridor, store-and-forward to coasts", light=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(FIGS / "O2_constellation_coverage.png", dpi=140); plt.close(fig)
    print("\nwrote O2_constellation_coverage.png")


if __name__ == "__main__":
    main()
