#!/usr/bin/env python3
"""Balloon as a long-range Meshtastic repeater for GROUND users: the geometry/value
AND the saturation hazard. Models both from first principles.

VALUE: a balloon at float has line-of-sight to a huge ground radius, so it can bridge
two ground "buddies" hundreds of km apart (far beyond each other's ~tens-of-km ground
range). HAZARD: that same wide footprint means it HEARS every Meshtastic packet in
the radius; if it blindly rebroadcasts (flood/ROUTER role) it re-injects all of it
across the whole footprint -> channel saturation + power blowout. The footprint that
makes it valuable is the footprint that makes it dangerous. This script quantifies
where flood-repeat is safe (sparse) vs catastrophic (dense), and the implied design.

Run: analysis/.venv/bin/python analysis/network/90_meshtastic_relay.py
"""
from __future__ import annotations
import pathlib
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

HERE = pathlib.Path(__file__).resolve().parent
ANT = HERE.parent / "antenna"
sys.path.insert(0, str(ANT))
from _link import radio_horizon_km, time_on_air_s, sensitivity_dbm, fspl_db  # noqa: E402
import _style as S  # noqa: E402
FIGS = HERE / "figs"
S.use_light()

# LongFast (Meshtastic default): SF11/BW250/CR4-5, 16-sym preamble, ~40 B on air
TOA_LF = time_on_air_s(11, payload_b=40, bw_hz=250_000, cr_denom=5, n_preamble=16, lorawan_overhead_b=0)
SENS_LF = sensitivity_dbm(11, bw_hz=250_000)
GND_TX_DBM, GND_G, BAL_G = 22.0, 2.0, 2.0     # ground node 22 dBm + 2 dBi; balloon 2 dBi
E_TX_J = 0.044 * 3.3 / 0.85 * TOA_LF           # cap energy per LongFast rebroadcast


def main():
    print(f"LongFast: ToA@40B = {TOA_LF*1000:.0f} ms, sensitivity {SENS_LF:.1f} dBm, "
          f"energy/rebroadcast {E_TX_J*1000:.0f} mJ")

    # --- ground<->balloon range: LOS vs link budget ---
    print("\n=== ground<->balloon range (is it LOS-limited or link-limited?) ===")
    for h in (8000, 10000, 12000):
        los = radio_horizon_km(h) + radio_horizon_km(2)   # balloon horizon + ground 2 m
        budget = GND_TX_DBM + GND_G + BAL_G - SENS_LF
        link_km = 10 ** ((budget - 20*np.log10(915) - 32.45) / 20)
        rg = min(los, link_km)
        print(f"  {h/1000:.0f} km alt: LOS {los:.0f} km, link-budget {link_km:.0f} km "
              f"-> usable R_g = {rg:.0f} km ({'LOS' if los<link_km else 'link'}-limited); "
              f"buddy-bridge reach ~{2*rg:.0f} km; footprint {np.pi*rg**2/1e6:.2f}M km^2")

    Rg = radio_horizon_km(10000)   # use 10 km
    foot = np.pi * Rg**2

    # --- saturation: if the balloon FLOOD-rebroadcasts everything it hears ---
    # node density rho (nodes/km^2) x packets/node/hour -> channel airtime + power
    rate = 3.0    # channel packets per node per hour (nodeinfo+position+telemetry+texts; typical)
    regimes = {"remote (1 / 10,000 km²)": 1e-4, "rural (1 / 1,000 km²)": 1e-3,
               "suburban (1 / 100 km²)": 1e-2, "dense metro (1 / 10 km²)": 1e-1}
    print(f"\n=== flood-rebroadcast load over a {Rg:.0f} km footprint "
          f"({foot/1e6:.2f}M km², {rate:.0f} pkt/node/hr) ===")
    print(f"{'regime':30} {'nodes seen':>11} {'pkts/hr':>9} {'channel util':>13} {'relay power':>12}")
    for name, rho in regimes.items():
        nodes = rho * foot
        pph = nodes * rate
        util = pph * TOA_LF / 3600.0
        pwr_mw = pph * E_TX_J / 3600.0 * 1000  # avg mW for rebroadcast TX alone
        print(f"{name:30} {nodes:>11,.0f} {pph:>9,.0f} {util*100:>11.0f}% {pwr_mw:>10.1f} mW")
    print("  (channel util >100% = impossible/total saturation; +the ~5.5 mA RX listen on top.)")
    print("  => flood-repeat is only safe over SPARSE land; dense areas saturate AND blow power.")

    # ---- figures ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.4))
    # A: top-down footprint + buddy bridge
    ax1.set_aspect("equal")
    ax1.add_patch(Circle((0, 0), Rg, fc=S.TEAL7, ec=S.L_ACCENT, alpha=0.13, lw=1.5))
    ax1.plot(0, 0, "^", color=S.RED, ms=13, zorder=5)
    ax1.text(0, Rg*0.10, "balloon\n10 km", ha="center", fontsize=9, color=S.RED)
    bx = Rg*0.78
    for sx, lbl in ((-bx, "Buddy A"), (bx, "Buddy B")):
        ax1.plot(sx, 0, "o", color=S.MINT, ms=9, zorder=5)
        ax1.add_patch(Circle((sx, 0), 30, fc="none", ec=S.DIM, ls=":", lw=1))  # ~30 km ground range
        ax1.text(sx, -Rg*0.14, lbl, ha="center", fontsize=9, color=S.MINT)
    ax1.annotate("", (bx, Rg*0.0), (-bx, Rg*0.0),
                 arrowprops=dict(arrowstyle="<->", color=S.TEXT_DIM, lw=1.2))
    ax1.text(0, Rg*0.22, f"~{2*bx:.0f} km apart, bridged by 1 balloon hop\n"
             f"(ground direct range ~30 km, dotted)", ha="center", fontsize=8.5, color=S.TEXT_DIM)
    ax1.set_xlim(-Rg*1.1, Rg*1.1); ax1.set_ylim(-Rg*1.1, Rg*1.1)
    ax1.set_xlabel("km"); ax1.set_title(f"A · Value: a {Rg:.0f} km footprint bridges distant buddies")

    # B: saturation vs node density
    rho = np.logspace(-5, 0, 200)
    nodes = rho * foot
    util = nodes * rate * TOA_LF / 3600.0 * 100
    pwr = nodes * rate * E_TX_J / 3600.0 * 1000
    ax2.plot(rho, util, "-", color=S.RED, lw=2.4, label="channel utilization (%)")
    ax2.axhline(100, color=S.WARM, ls="--", lw=1.5); ax2.text(2e-5, 130, "100% = saturated", color=S.WARM, fontsize=8.5)
    ax2.axhline(10, color=S.DIM, ls=":", lw=1.2); ax2.text(2e-5, 6, "10% (EU duty / good-citizen)", color=S.TEXT_DIM, fontsize=8)
    for name, r in regimes.items():
        u = (r*foot)*rate*TOA_LF/3600*100
        ax2.scatter([r], [u], s=55, color=S.TEAL10, zorder=5)
        ax2.annotate(name.split(" (")[0], (r, u), fontsize=8, xytext=(4,4), textcoords="offset points")
    ax2.set_xscale("log"); ax2.set_yscale("log")
    ax2.set_xlabel("ground Meshtastic node density (nodes / km²)")
    ax2.set_ylabel("balloon flood-rebroadcast channel utilization (%)")
    ax2.set_title("B · Hazard: blind flood-repeat saturates over dense areas\n(value is highest where it's safest: sparse/rural)")
    ax2.grid(True, alpha=0.4, which="both")
    fig.suptitle("Balloon as a Meshtastic repeater: huge reach, but must be SELECTIVE not a flood-router",
                 fontsize=12.3)
    S.footer(fig, "90_meshtastic_relay.py · LongFast SF11/BW250, 4/3-earth LOS, 22dBm ground node, 3 pkt/node/hr", light=True)
    fig.tight_layout(rect=(0,0.02,1,1))
    fig.savefig(FIGS / "N8_meshtastic_relay.png", dpi=145); plt.close(fig)
    print("\nwrote N8_meshtastic_relay.png")

if __name__ == "__main__":
    main()
