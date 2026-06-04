#!/usr/bin/env python3
"""Coexistence model: our LoRaWAN (SF9/BW125) vs Meshtastic/MeshCore presets on
the SAME single SX1262 radio. Quantifies the airtime, sensitivity (range), and
radio time-budget tradeoffs so we can pick an architecture from numbers, not vibes.

Modem params (verified): our LoRaWAN uplink = SF9/BW125/CR4-5/8-sym preamble +13 B
MAC overhead. Meshtastic presets (firmware MeshRadio.h): LongFast SF11/BW250/CR4-5,
MediumFast SF9/BW250, ShortFast SF7/BW250, all 16-sym preamble, explicit header,
16 B plaintext header. Sensitivity = -174 + 10log10(BW) + NF + SNR_lim (BW-aware).

Run: analysis/.venv/bin/python analysis/network/80_meshtastic_coexist.py
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
from _link import time_on_air_s, sensitivity_dbm, fspl_db  # noqa: E402
import _style as S  # noqa: E402
FIGS = HERE / "figs"
S.use_light()

BW125, BW250 = 125_000, 250_000
# mode: (label, sf, bw, cr_denom, preamble, lorawan_overhead_b, header_b, color)
MODES = [
    ("Stratolink LoRaWAN  SF9/BW125", 9, BW125, 5, 8, 13, 0, S.TEAL7),
    ("Meshtastic LongFast  SF11/BW250", 11, BW250, 5, 16, 0, 16, S.RED),
    ("Meshtastic MediumFast SF9/BW250", 9, BW250, 5, 16, 0, 16, S.TEAL10),
    ("Meshtastic ShortFast  SF7/BW250", 7, BW250, 5, 16, 0, 16, S.WARM),
]

def toa(mode, app_bytes):
    _, sf, bw, cr, pre, ovh, hdr, _c = mode
    return time_on_air_s(sf, payload_b=app_bytes + hdr, bw_hz=bw, cr_denom=cr,
                         n_preamble=pre, lorawan_overhead_b=ovh)

def sens(mode):
    _, sf, bw, *_ = mode
    return sensitivity_dbm(sf, bw_hz=bw)

def rel_range(mode, ref_sens, f=915.0):
    # range ratio vs reference floor (FSPL): a LOWER (more negative) floor = more
    # link budget = longer range. budget gain = ref_sens - sens(mode).
    d = ref_sens - sens(mode)
    return 10 ** (d / 20.0)

def main():
    ref = sensitivity_dbm(9, bw_hz=BW125)  # our SF9 floor as the 1.0x reference
    print(f"{'mode':34} {'ToA@40B':>9} {'ToA@24B':>9} {'sens(dBm)':>10} {'rel range':>10}")
    for m in MODES:
        print(f"{m[0]:34} {toa(m,40)*1000:7.0f}ms {toa(m,24)*1000:7.0f}ms "
              f"{sens(m):10.1f} {rel_range(m, ref):9.2f}x")

    # radio time budget per 1200s cycle (one balloon)
    t_gps, t_tx = 2.0, toa(MODES[0], 22)   # GPS hot 2s; LoRaWAN uplink
    relay_avail = 1200 - t_gps - t_tx
    print(f"\nradio time per 1200s cycle: GPS {t_gps:.0f}s + LoRaWAN TX {t_tx*1000:.0f}ms "
          f"+ FREE for relay {relay_avail:.0f}s ({100*relay_avail/1200:.1f}%)")
    print(f"  -> relay packets that fit in the free radio time at LongFast "
          f"({toa(MODES[1],40)*1000:.0f}ms each): {int(relay_avail/toa(MODES[1],40))} "
          f"(airtime); POWER, not radio time, is the limit (see relay_power_budget.py)")

    # ---- figures ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    pl = np.arange(1, 200)
    for m in MODES:
        ax1.plot(pl, [toa(m, b)*1000 for b in pl], "-", color=m[7], lw=2, label=m[0])
    ax1.axvline(35, color=S.DIM, ls=":", lw=1); ax1.text(37, 50, "our 35 B\npayload", fontsize=8, color=S.TEXT_DIM)
    ax1.set_xlabel("application payload (bytes)"); ax1.set_ylabel("time-on-air (ms)")
    ax1.set_title("A · Airtime per packet, Meshtastic LongFast is ~4x our SF9")
    ax1.legend(fontsize=8); ax1.grid(True, alpha=0.4)

    # sensitivity vs ToA: the range/airtime plane
    for m in MODES:
        ax2.scatter(toa(m, 40)*1000, sens(m), s=90, color=m[7], zorder=5)
        ax2.annotate(m[0].split("  ")[0].split(" SF")[0] + f"\n{m[0].split('/')[0].split(' ')[-1]}/{m[0].split('/')[1]}",
                     (toa(m,40)*1000, sens(m)), fontsize=7.5, xytext=(6,6), textcoords="offset points")
    ax2.set_xlabel("time-on-air @40 B (ms, log)"); ax2.set_xscale("log")
    ax2.set_ylabel("receiver sensitivity floor (dBm)  ↓ = better range")
    ax2.invert_yaxis()
    ax2.set_title("B · Range vs airtime plane\n(down-left = more range AND less airtime = better)")
    ax2.grid(True, alpha=0.4, which="both")
    fig.suptitle("One SX1262, two protocols: LoRaWAN telemetry vs a Meshtastic-class relay mode",
                 fontsize=12.3)
    S.footer(fig, "80_meshtastic_coexist.py · Semtech ToA + sensitivity, BW-aware · presets from Meshtastic MeshRadio.h", light=True)
    fig.tight_layout(rect=(0,0.02,1,1))
    fig.savefig(FIGS / "N7_meshtastic_coexist.png", dpi=145); plt.close(fig)
    print("\nwrote N7_meshtastic_coexist.png")

if __name__ == "__main__":
    main()
