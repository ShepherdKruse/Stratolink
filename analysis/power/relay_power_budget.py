#!/usr/bin/env python3
"""Can the SF9/20-min idle time double as a Meshtastic/LoRa relay? Power says no
(on the current supercap budget). Substantiated against the SAME 1F-cap model as
gps_start_power.py.

The idea: at SF9 the LoRaWAN uplink is ~308 ms every 1200 s, so the radio is idle
>99.9% of the time, "use it to relay." The catch: relaying random traffic means
LISTENING (RX), and continuous RX is a CONSTANT ~5.5 mA load, whereas the idle
time today is STOP1 SLEEP at ~4 uA. That 1000x+ difference is the whole ballgame.

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
C_F, V_MAX, V_BROWN = 1.0, 5.36, 3.32
E_USABLE = 0.5 * C_F * (V_MAX**2 - V_BROWN**2)     # 8.86 J to brownout
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
    e_relay_rx = p(I_RX) * idle            # if we LISTEN through the idle window
    print("=== per-cycle cap energy (1200 s cycle) ===")
    print(f"  GPS hot-start (2s,35mA): {e_gps:6.3f} J")
    print(f"  LoRaWAN uplink (SF9):    {e_tx:6.3f} J")
    print(f"  STOP1 sleep (idle 1198s):{e_slp:6.3f} J   <- today the idle time is ~free")
    print(f"  BASELINE per cycle:      {e_base:6.3f} J")
    print(f"  + continuous RX relay:   {e_relay_rx:6.2f} J   = {e_relay_rx/E_USABLE:4.1f}x the WHOLE 8.86 J cap, per cycle")

    # daily energy + average current
    base_day = e_base * CYC_DAY
    relay_day = (e_base + e_relay_rx) * CYC_DAY
    iavg_base = (I_GPS*T_GPS_HOT + I_MCU*T_GPS_HOT + I_TX14*TOA_SF9 + I_SLEEP*idle)/CADENCE
    iavg_relay = iavg_base + I_RX*idle/CADENCE
    print("\n=== daily energy & average current ===")
    print(f"  baseline:        {base_day:6.1f} J/day,  avg {iavg_base*1e3:5.2f} mA")
    print(f"  + relay listen:  {relay_day:6.0f} J/day,  avg {iavg_relay*1e3:5.2f} mA")
    print(f"  relay is {iavg_relay/iavg_base:4.0f}x the average load, and needs ~{I_RX*1e3:.1f} mA"
          f" of CONTINUOUS solar surplus")

    # cap drain into darkness (no solar), starting at a realistic dusk 4.5 V
    def t_to_brownout(P, v0=4.5):
        E = 0.5*C_F*(v0**2 - V_BROWN**2)
        return E / P
    t_relay = t_to_brownout(p(I_RX))
    t_sleep = t_to_brownout(p(I_SLEEP))
    print("\n=== survival into darkness (no sun, from 4.5 V) ===")
    print(f"  sleeping (today):     {t_sleep/3600:6.1f} h  -> survives to sunrise")
    print(f"  listening (relay):    {t_relay/60:6.1f} min -> browns out almost immediately")

    # ---- figure ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5))
    # A: average current by mode (log)
    labels = ["STOP1 sleep\n(idle today)", "GPS hot\n(2s/cyc)", "LoRaWAN TX\n(308ms/cyc)",
              "continuous RX\nrelay (idle)"]
    iavg = [I_SLEEP*idle/CADENCE*1e3, (I_GPS+I_MCU)*T_GPS_HOT/CADENCE*1e3,
            I_TX14*TOA_SF9/CADENCE*1e3, I_RX*idle/CADENCE*1e3]
    cols = [S.MINT, S.TEAL10, S.TEAL7, S.RED]
    ax1.bar(labels, iavg, color=cols, alpha=0.9)
    ax1.set_yscale("log"); ax1.set_ylabel("contribution to average current (mA, log)")
    for i, v in enumerate(iavg):
        ax1.text(i, v*1.25, f"{v:.3f}" if v < 0.1 else f"{v:.2f}", ha="center", fontsize=9, fontweight="bold")
    ax1.set_title(f"A · Listening to relay = {iavg[3]/sum(iavg[:3]):.0f}x the entire baseline load")
    ax1.tick_params(axis="x", labelsize=8)
    # B: cap drain into darkness
    for P, c, lbl in [(p(I_SLEEP), S.MINT, f"sleep (today): {t_sleep/3600:.0f} h to brownout"),
                      (p(I_RX), S.RED, f"relay RX: {t_relay/60:.0f} min to brownout")]:
        T = np.linspace(0, max(t_relay*1.4, 1200), 400)
        E = 0.5*C_F*4.5**2 - P*T
        V = np.sqrt(np.clip(2*E/C_F, V_BROWN**2*0.0+0.01, None))
        V = np.where(2*E/C_F >= V_BROWN**2, np.sqrt(np.clip(2*E/C_F,0,None)), np.nan)
        ax2.plot(T/60, V, color=c, lw=2.6, label=lbl)
    ax2.axhline(V_BROWN, color=S.WARM, ls="--", lw=1.6)
    ax2.text(19, V_BROWN+0.04, "brownout 3.32 V", color=S.WARM, fontsize=9, ha="right")
    ax2.set_xlim(0, 20); ax2.set_ylim(3.2, 4.6)
    ax2.set_xlabel("minutes after the sun drops (no solar)"); ax2.set_ylabel("supercap voltage (V)")
    ax2.set_title("B · Sleep survives to dawn; relay-listen dies in minutes")
    ax2.legend(loc="upper right", fontsize=9)
    fig.suptitle("Idle-time relay on the 1F supercap: airtime is fine, POWER is the wall",
                 fontsize=12.5)
    S.footer(fig, "relay_power_budget.py · 1F cap 8.86J · RX 5.5mA / TX@14 44mA / GPS 30mA / sleep 4uA · SF9 1200s", light=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(HERE / "relay_power_budget.png", dpi=150)
    print("\nwrote", HERE / "relay_power_budget.png")

if __name__ == "__main__":
    main()
