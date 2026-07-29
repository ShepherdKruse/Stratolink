#!/usr/bin/env python3
"""Historical screen for using the SF9/20-min idle time as an RX relay.

This intentionally retains the superseded nominal 1 F / 5.36 V / 3.32 V
accounting model for continuity with gps_start_power.py. It now distinguishes
the former busy-spin implementation (radio RX + estimated active MCU) from the
repaired shallow-WFI implementation. The repaired total remains unknown until
PPK2 measurement; radio-only is a lower engineering screen, not total current
or launch evidence.

Run: analysis/.venv/bin/python analysis/power/relay_power_budget.py
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
import _style as S
S.use_light()

# ---- hardware (identical to gps_start_power.py) ----
C_F, V_MAX, V_ACCOUNTING_FLOOR = 1.0, 5.36, 3.32
# Flight 3's fixed-VDDA conversion produced a false plateau near 3.32 V in
# buck dropout. Keep that value only as a deliberately conservative historical
# accounting endpoint; it is not measured VSTOR or a BOR threshold.
E_USABLE = 0.5 * C_F * (V_MAX**2 - V_ACCOUNTING_FLOOR**2)
V_RAIL, ETA = 3.3, 0.85

# ---- loads (datasheet typicals; GPS/MCU match gps_start_power.py) ----
I_GPS, I_MCU = 0.030, 0.005          # GPS acq 30 mA, MCU active 5 mA
I_RX, I_TX14 = 0.0055, 0.044         # SX1262/STM32WL: RX ~5.5 mA, TX@14dBm DCDC ~44 mA
I_SLEEP = 4e-6                        # STOP1 quiescent ~3-5 uA (DOCUMENTATION.md)
T_GPS_HOT, TOA_SF9 = 2.0, 0.308      # hot-start TTFF 2 s; SF9 35B ToA 308 ms
CADENCE = 1200.0                      # config.h TRANSMIT_INTERVAL_SEC (SF9, 20 min)
CYC_DAY = 86400 / CADENCE            # 72/day

def p(I):  # power drawn FROM the cap for a rail current I (incl. buck loss)
    return I * V_RAIL / ETA

def main():
    idle = CADENCE - T_GPS_HOT - TOA_SF9
    # per-cycle cap energy (J)
    e_gps  = p(I_GPS + I_MCU) * T_GPS_HOT
    e_tx   = p(I_TX14) * TOA_SF9
    e_slp  = p(I_SLEEP) * idle
    e_base = e_gps + e_tx + e_slp
    e_relay_radio = p(I_RX) * idle
    e_relay_former_mcu = p(I_MCU) * idle
    e_relay_former = e_relay_radio + e_relay_former_mcu
    print("=== per-cycle cap energy (1200 s cycle) ===")
    print(f"  GPS hot-start (2s,35mA): {e_gps:6.3f} J")
    print(f"  LoRaWAN uplink (SF9):    {e_tx:6.3f} J")
    print(f"  STOP1 sleep (idle 1198s):{e_slp:6.3f} J   <- today the idle time is ~free")
    print(f"  BASELINE per cycle:      {e_base:6.3f} J")
    print(f"  + relay radio RX only:   {e_relay_radio:6.2f} J   = lower screen, not total")
    print(f"  + former MCU busy-spin:  {e_relay_former_mcu:6.2f} J")
    print(f"  FORMER combined relay:   {e_relay_former:6.2f} J   = {e_relay_former/E_USABLE:4.1f}x the historical accounting window")
    print("  REPAIRED WFI relay:      exact total unknown; PPK2 required")

    # daily energy + average current
    base_day = e_base * CYC_DAY
    former_relay_day = (e_base + e_relay_former) * CYC_DAY
    iavg_base = (I_GPS*T_GPS_HOT + I_MCU*T_GPS_HOT + I_TX14*TOA_SF9 + I_SLEEP*idle)/CADENCE
    iavg_relay_radio_lower = iavg_base + I_RX*idle/CADENCE
    iavg_relay_former = iavg_relay_radio_lower + I_MCU*idle/CADENCE
    print("\n=== daily energy & average current ===")
    print(f"  baseline:                  {base_day:6.1f} J/day, avg {iavg_base*1e3:5.2f} mA")
    print(f"  radio-only lower screen:   {'unknown':>6} total, avg >= {iavg_relay_radio_lower*1e3:5.2f} mA")
    print(f"  former busy-spin relay:    {former_relay_day:6.0f} J/day, avg {iavg_relay_former*1e3:5.2f} mA")

    # cap drain into darkness (no solar), starting at a realistic dusk 4.5 V
    def t_to_accounting_floor(P, v0=4.5):
        E = 0.5*C_F*(v0**2 - V_ACCOUNTING_FLOOR**2)
        return E / P
    t_radio_lower = t_to_accounting_floor(p(I_RX))
    t_former = t_to_accounting_floor(p(I_RX + I_MCU))
    t_sleep = t_to_accounting_floor(p(I_SLEEP))
    print("\n=== survival into darkness (no sun, from 4.5 V) ===")
    print(f"  STOP1 baseline:             {t_sleep/3600:6.1f} h")
    print(f"  radio-only lower screen:    {t_radio_lower/60:6.1f} min")
    print(f"  former busy-spin combined:  {t_former/60:6.1f} min")
    print("  repaired shallow-WFI total: unknown until exact-image PPK2 capture")

    # ---- figure ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8))
    # A: average current by mode (log)
    labels = ["STOP1 sleep\n(baseline)", "GPS + MCU\n(2s/cyc)",
              "LoRaWAN TX\n(308ms/cyc)", "radio RX\n(lower screen)",
              "former MCU\nbusy-spin"]
    iavg = [I_SLEEP*idle/CADENCE*1e3, (I_GPS+I_MCU)*T_GPS_HOT/CADENCE*1e3,
            I_TX14*TOA_SF9/CADENCE*1e3, I_RX*idle/CADENCE*1e3,
            I_MCU*idle/CADENCE*1e3]
    cols = [S.MINT, S.TEAL10, S.TEAL7, S.WARM, S.RED]
    ax1.bar(labels, iavg, color=cols, alpha=0.9)
    ax1.set_yscale("log"); ax1.set_ylabel("contribution to average current (mA, log)")
    for i, v in enumerate(iavg):
        ax1.text(i, v*1.25, f"{v:.3f}" if v < 0.1 else f"{v:.2f}", ha="center", fontsize=9, fontweight="bold")
    ax1.set_title(
        "A · Old loop = radio RX + active MCU\n"
        "Repaired MCU term needs PPK2",
        fontsize=10.5,
    )
    ax1.tick_params(axis="x", labelsize=8)
    # B: cap drain into darkness
    for P, c, ls, lbl in [
        (p(I_SLEEP), S.MINT, "-", f"STOP1 baseline: {t_sleep/3600:.0f} h"),
        (p(I_RX), S.WARM, "--", f"radio-only lower screen: {t_radio_lower/60:.1f} min"),
        (p(I_RX + I_MCU), S.RED, "-", f"former busy-spin: {t_former/60:.1f} min"),
    ]:
        T = np.linspace(0, max(t_radio_lower*1.4, 1200), 400)
        E = 0.5*C_F*4.5**2 - P*T
        V = np.sqrt(np.clip(2*E/C_F, 0.01, None))
        V = np.where(2*E/C_F >= V_ACCOUNTING_FLOOR**2, np.sqrt(np.clip(2*E/C_F,0,None)), np.nan)
        ax2.plot(T/60, V, color=c, ls=ls, lw=2.6, label=lbl)
    ax2.axhline(V_ACCOUNTING_FLOOR, color=S.WARM, ls="--", lw=1.6)
    ax2.text(19, V_ACCOUNTING_FLOOR+0.04, "historical reported plateau 3.32 V",
             color=S.WARM, fontsize=9, ha="right")
    ax2.set_xlim(0, 20); ax2.set_ylim(3.2, 4.6)
    ax2.set_xlabel("minutes after the sun drops (no solar)"); ax2.set_ylabel("supercap voltage (V)")
    ax2.set_title(
        "B · Historical nominal-cap screen\nNot fitted endurance",
        fontsize=10.5,
    )
    ax2.legend(loc="upper right", fontsize=9)
    fig.suptitle("Relay RX energy correction: former busy-spin vs repaired shallow WFI",
                 fontsize=12.5)
    S.footer(fig, "HISTORICAL SCREEN, NOT LAUNCH EVIDENCE · nominal 1F / 5.36→3.32V · repaired WFI total unknown pending exact-image PPK2 · radio RX 5.5mA typical", light=True)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(HERE / "relay_power_budget.png", dpi=150)
    print("\nwrote", HERE / "relay_power_budget.png")

if __name__ == "__main__":
    main()
