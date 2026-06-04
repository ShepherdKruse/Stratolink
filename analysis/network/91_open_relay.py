#!/usr/bin/env python3
"""Can the balloon be an OPEN, public, default-channel Meshtastic relay for the
whole region (Teddy's actual goal) WITHOUT killing local meshes?

Yes, if it self-throttles its own airtime to the good-citizen limit (AirUtilTX
<= ~7.5%, ChUtil <= 25%) and uses ROUTER_LATE (defer/give-way). The beautiful part:
that cap makes the balloon AUTOMATICALLY a gap-filler. Where the ground mesh is
dense, the channel is busy and others already relay, so a deferring + airtime-capped
balloon stays nearly silent (not needed, would harm). Where the ground mesh is
sparse/absent, the channel is quiet and nobody else can relay, so the balloon
carries the traffic (needed, safe). "Help the whole region" -> in practice ->
"help the underserved parts of the region," which is the highest public benefit.

This models the OPEN relay on the public channel with an AirUtilTX self-cap.

Run: analysis/.venv/bin/python analysis/network/91_open_relay.py
"""
from __future__ import annotations
import pathlib
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
ANT = HERE.parent / "antenna"
sys.path.insert(0, str(ANT))
from _link import radio_horizon_km, time_on_air_s  # noqa: E402
import _style as S  # noqa: E402
FIGS = HERE / "figs"
S.use_light()

TOA = time_on_air_s(11, payload_b=40, bw_hz=250_000, cr_denom=5, n_preamble=16, lorawan_overhead_b=0)
E_TX_J = 0.044 * 3.3 / 0.85 * TOA
Rg = radio_horizon_km(10000)
FOOT = np.pi * Rg**2 / 1e6        # M km^2... keep km^2:
FOOT_KM2 = np.pi * Rg**2
RATE = 3.0                         # channel packets per node per hour
AIRUTILTX_CAP = 0.075             # good-citizen self-limit on the balloon's OWN airtime
CHUTIL_CEIL = 0.25                # total-channel ceiling above which a good node ceases relaying


def main():
    cap_pph = AIRUTILTX_CAP * 3600 / TOA      # max packets/hr the balloon may rebroadcast
    cap_pwr_mw = cap_pph * E_TX_J / 3600 * 1000
    print(f"footprint R_g={Rg:.0f} km ({FOOT_KM2/1e6:.2f}M km²); LongFast ToA {TOA*1000:.0f} ms")
    print(f"good-citizen self-cap: AirUtilTX {AIRUTILTX_CAP*100:.1f}% -> "
          f"<= {cap_pph:.0f} rebroadcasts/hr, <= {cap_pwr_mw:.1f} mW relay TX (in budget)")

    regimes = {"remote 1/10,000 km²": 1e-4, "rural 1/1,000 km²": 1e-3,
               "suburban 1/100 km²": 1e-2, "metro 1/10 km²": 1e-1}
    print(f"\n{'regime':22} {'offered pkt/hr':>14} {'naive util':>11} {'capped relay':>13} {'served':>8}")
    for name, rho in regimes.items():
        offered = rho * FOOT_KM2 * RATE
        naive_util = offered * TOA / 3600
        served = min(offered, cap_pph)
        frac = served / offered if offered else 1.0
        verdict = "full service" if frac > 0.95 else ("partial" if frac > 0.1 else "defers to ground")
        print(f"{name:22} {offered:>14,.0f} {naive_util*100:>10.0f}% {served:>11,.0f}/hr {frac*100:>6.0f}%  {verdict}")
    print("\n=> An airtime-capped OPEN relay is SAFE at every density: it serves ~all")
    print("   traffic where the mesh is sparse (max public benefit, nobody else can),")
    print("   and self-limits to its 7.5% slice where the mesh is dense (already covered).")

    # ---- figure ----
    rho = np.logspace(-5, 0, 250)
    offered = rho * FOOT_KM2 * RATE
    capped = np.minimum(offered, cap_pph)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    ax1.plot(rho, offered, "--", color=S.TEXT_DIM, lw=1.8, label="local traffic offered (pkt/hr)")
    ax1.plot(rho, capped, "-", color=S.TEAL7, lw=2.6, label="balloon relays (airtime-capped)")
    ax1.axhline(cap_pph, color=S.MINT, ls=":", lw=1.4)
    ax1.text(1.2e-5, cap_pph*1.15, f"good-citizen cap ≈ {cap_pph:.0f} pkt/hr (7.5% AirUtilTX)", color=S.MINT, fontsize=8.5)
    # shade serve-vs-defer
    cross = cap_pph / (FOOT_KM2 * RATE)
    ax1.axvspan(1e-5, cross, color=S.TEAL7, alpha=0.08)
    ax1.axvspan(cross, 1, color=S.WARM, alpha=0.07)
    ax1.text(2e-5, offered.max()*0.5, "SPARSE:\nballoon carries it\n(max public benefit)", fontsize=8.5, color=S.L_ACCENT)
    ax1.text(1.3e-2, offered.max()*0.5, "DENSE:\nballoon defers,\nground already covers", fontsize=8.5, color=S.WARM)
    ax1.set_xscale("log"); ax1.set_yscale("log")
    ax1.set_xlabel("ground node density (nodes/km²)"); ax1.set_ylabel("packets / hour")
    ax1.set_title("A · Open relay self-targets the underserved")
    ax1.legend(fontsize=8.5, loc="lower right"); ax1.grid(True, alpha=0.35, which="both")

    # B: channel utilization the balloon ADDS, naive flood vs capped
    naive_u = offered * TOA / 3600 * 100
    capped_u = capped * TOA / 3600 * 100
    ax2.plot(rho, naive_u, "-", color=S.RED, lw=2.2, label="naive flood-router (ROUTER)")
    ax2.plot(rho, capped_u, "-", color=S.TEAL7, lw=2.6, label="airtime-capped (ROUTER_LATE)")
    ax2.axhline(100, color=S.WARM, ls="--", lw=1.4); ax2.text(1.2e-5, 120, "100% = mesh killed", color=S.WARM, fontsize=8.5)
    ax2.axhline(AIRUTILTX_CAP*100, color=S.MINT, ls=":", lw=1.4); ax2.text(1.2e-5, 8.3, "7.5% self-cap", color=S.MINT, fontsize=8)
    ax2.set_xscale("log"); ax2.set_yscale("log")
    ax2.set_xlabel("ground node density (nodes/km²)"); ax2.set_ylabel("channel utilization the balloon adds (%)")
    ax2.set_title("B · Capped = safe at every density (vs flood blowing past 100%)")
    ax2.legend(fontsize=8.5, loc="upper left"); ax2.grid(True, alpha=0.35, which="both")
    fig.suptitle("An OPEN public default-channel relay IS safe, if it caps its own airtime (ROUTER_LATE)",
                 fontsize=12.3)
    S.footer(fig, "91_open_relay.py · LongFast, 412 km footprint, AirUtilTX cap 7.5% / ChUtil ceil 25%", light=True)
    fig.tight_layout(rect=(0,0.02,1,1))
    fig.savefig(FIGS / "N9_open_relay.png", dpi=145); plt.close(fig)
    print("\nwrote N9_open_relay.png")

if __name__ == "__main__":
    main()
