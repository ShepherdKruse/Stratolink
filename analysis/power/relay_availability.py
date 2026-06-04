#!/usr/bin/env python3
"""Power-tier-gated relay: how often could a SUPERCAP-only balloon afford to relay,
and what does that buy the global Meshtastic network at N balloons?

Gate (mission-safe): relay ONLY when the cap is topped (tier FULL, VSTOR >= 4.5 V)
AND the sun is actively charging (solar > 3 V), i.e. spend the harvester SURPLUS
that the BQ25570 would otherwise clip, never the reserve the telemetry mission needs.

Part 1, measure the relay-affordable duty `f` from flight-3 telemetry, binned by
LOCAL SOLAR HOUR (corrects for the fact that rows only exist when the balloon both
had power AND was heard by a gateway, so nights/ocean are under-sampled, but the
power state is sun-driven, so per-local-hour it generalizes).

Part 2, model the global benefit vs fleet size N, using the measured f.

Run: analysis/.venv/bin/python analysis/power/relay_availability.py
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
import _style as S
S.use_light()

FULL_V = 4.5           # POWER_TIER_FULL threshold (power_adc.h)
SOLAR_UP_V = 3.0       # solar panel clearly producing (daylight + charging)

# ground-coverage radius of a relay-on balloon at ~10 km (LoRa to ground)
R_COV_KM = {"R=300 km": 300.0, "R=400 km": 400.0}
A_EARTH = 510e6        # km^2
A_LAND = 149e6         # km^2
LAND_FRAC = A_LAND / A_EARTH


def main():
    df = pd.read_csv(HERE / "flight_power.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601", errors="coerce")
    df = df.dropna(subset=["time"])
    for c in ("battery_voltage", "solar_voltage", "lon", "ambient_lux", "uv_index"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["battery_voltage", "time"])

    # local solar hour = UTC hour + lon/15 (deg->hours), wrapped 0..24
    utc_h = df["time"].dt.hour + df["time"].dt.minute / 60.0
    df["solar_hour"] = (utc_h + df["lon"].fillna(0) / 15.0) % 24.0
    df["relay_ok"] = (df["battery_voltage"] >= FULL_V) & (df["solar_voltage"].fillna(0) >= SOLAR_UP_V)

    # tier distribution of TRANSMITTED moments
    tiers = pd.cut(df["battery_voltage"], [0, 2.8, 3.0, 3.5, 4.5, 99],
                   labels=["CRITICAL", "EMERGENCY", "NO_GPS", "REDUCED", "FULL"])
    print("=== tier of transmitted moments (battery_voltage) ===")
    print((tiers.value_counts(normalize=True).reindex(
        ["FULL", "REDUCED", "NO_GPS", "EMERGENCY", "CRITICAL"]) * 100).round(1).to_string())
    print(f"\nrelay_ok (FULL & solar up) among transmitted moments: "
          f"{100*df['relay_ok'].mean():.1f}%")

    # diurnal: relay_ok probability per local-hour bin, + row counts
    df["hbin"] = df["solar_hour"].astype(int)
    g = df.groupby("hbin").agg(p_relay=("relay_ok", "mean"), n=("relay_ok", "size"))
    g = g.reindex(range(24))
    # empty local-hour bins => no telemetry there at all => treat as unavailable
    # (deep night brownout / no uplink); p_relay = 0 for the daily integral.
    p_hour = g["p_relay"].fillna(0.0).values
    hours_avail = p_hour.sum()              # expected relay-affordable hours/day
    f_duty = hours_avail / 24.0
    print(f"\n=== relay-affordable duty (corrected by local solar hour) ===")
    print(f"  expected hours/day a balloon can relay: {hours_avail:.1f} h  -> duty f = {f_duty:.2f}")
    print(f"  (rows per local hour ranged {int(np.nanmin(g['n']))}..{int(np.nanmax(g['n']))}; "
          f"{int(g['n'].isna().sum())} hours had no telemetry at all)")

    # ---- Part 2: global benefit vs fleet size N ----
    Ns = np.arange(0, 1001, 10)
    print("\n=== global benefit vs fleet size (using measured f) ===")
    print(f"{'N':>5} {'relays on':>10} " + " ".join(f"{k+' daylit-land':>20}" for k in R_COV_KM))
    cover = {k: [] for k in R_COV_KM}
    simulrelay = []
    A_daylit_land = A_LAND / 2.0           # only the sunlit half can be served
    for N in Ns:
        n_on = N * f_duty                  # relay-on at a random instant
        simulrelay.append(n_on)
        n_on_land = n_on * LAND_FRAC       # of those, fraction over land
        for k, R in R_COV_KM.items():
            a = np.pi * R * R
            cov = 1 - (1 - min(a / A_daylit_land, 1.0)) ** n_on_land
            cover[k].append(cov)
    for N in (50, 100, 250, 500, 1000):
        i = list(Ns).index(N)
        print(f"{N:>5} {simulrelay[i]:>10.1f} " +
              " ".join(f"{cover[k][i]*100:>19.1f}%" for k in R_COV_KM))

    # ---- figures ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    # A: diurnal availability
    hrs = np.arange(24)
    ax1.bar(hrs, p_hour * 100, color=S.TEAL7, alpha=0.9, width=0.9)
    ax1.set_xlabel("local solar hour"); ax1.set_ylabel("% of time relay-affordable (FULL + sun)")
    ax1.set_title(f"A · Flight-3 relay-affordable window\n≈ {hours_avail:.0f} h/day (duty f = {f_duty:.2f})")
    ax1.set_xticks(range(0, 24, 3)); ax1.set_ylim(0, 105)
    ax1.axvspan(0, 6, color=S.DIM, alpha=0.12); ax1.axvspan(19, 24, color=S.DIM, alpha=0.12)
    ax1.text(3, 50, "night\nbrownout", ha="center", color=S.TEXT_DIM, fontsize=9)
    # B: global benefit vs N
    for (k, _), c in zip(R_COV_KM.items(), [S.TEAL10, S.MINT]):
        ax2.plot(Ns, np.array(cover[k]) * 100, "-", color=c, lw=2.2, label=f"daylit-land coverage ({k})")
    ax2b = ax2.twinx()
    ax2b.plot(Ns, simulrelay, ":", color=S.WARM, lw=1.8, label="relays on at once (N·f)")
    ax2b.set_ylabel("balloons relaying simultaneously", color=S.WARM)
    ax2.set_xlabel("fleet size N (balloons aloft globally)")
    ax2.set_ylabel("% of sunlit land within range of a relay")
    ax2.set_title("B · Global ground-Meshtastic benefit vs fleet size\n(supercap-only, day-gated)")
    ax2.legend(loc="upper left", fontsize=8.5); ax2.set_ylim(0, 100)
    fig.suptitle("Power-tier-gated relay: free midday surplus, but a day-following / fleet-scale network",
                 fontsize=12.3)
    S.footer(fig, "relay_availability.py · gate: VSTOR>=4.5V & solar>3V · f from flight-3 telemetry by local solar hour", light=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(HERE / "relay_availability.png", dpi=150)
    print("\nwrote", HERE / "relay_availability.png")


if __name__ == "__main__":
    main()
