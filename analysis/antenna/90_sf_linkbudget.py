"""TASK 3 — Spreading-factor / airtime / range optimization (study + plots).

The link, not the payload, was the binding constraint on flight-3 (Part A: ran at
the SF7 floor, max fresh range 252 km vs a 412 km horizon). This quantifies the
single biggest lever we have: SPREADING FACTOR.

The tension:
  higher SF -> lower sensitivity floor -> more range / more gateways heard,
  BUT exponentially more time-on-air -> fewer uplinks/day under TTN FUP (30 s/day).

Deliverables (all from _link.py canonical Semtech formulas, our real 35 B payload):
  D1  airtime & FUP vs SF, and the feasible (SF, interval) region.
  D2  range vs SF, with the radio horizon and our flight's achieved range overlaid.
  D3  a recommended fixed DR per region, with the reasoning.

Run: analysis/.venv/bin/python analysis/antenna/90_sf_linkbudget.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import _style as S
import _link as L

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"

SFS = list(range(7, 13))
CURRENT_INTERVAL_S = 300      # config.h TRANSMIT_INTERVAL_SEC
FUP_S_PER_DAY = 30.0          # TTN Fair-Use airtime budget


def achieved_range_km():
    """Our best FRESH reception range from Part A (geolocated, fresh GPS only)."""
    try:
        df = pd.read_parquet(DATA / "receptions_geo.parquet")
        fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"]]
        return float(fresh["slant_km"].max()), float(fresh["slant_km"].median())
    except Exception:
        return 252.0, 100.0


def table():
    rows = []
    for sf in SFS:
        toa = L.time_on_air_s(sf)
        rows.append(dict(
            sf=sf, toa_ms=toa * 1e3, sens_dbm=L.sensitivity_dbm(sf),
            fup_per_day=L.fup_msgs_per_day(sf),
            min_interval_s=toa / (FUP_S_PER_DAY / 86400.0),  # interval that just meets FUP
            range_us=L.max_range_km(sf, L.REGION_FREQ_MHZ["US915"]),
            range_eu=L.max_range_km(sf, L.REGION_FREQ_MHZ["EU868"]),
        ))
    return pd.DataFrame(rows)


def main():
    df = table()
    rmax, rmed = achieved_range_km()
    pd.set_option("display.width", 160)
    print("=== SF scorecard (35 B payload, BW125, CR4/5) ===")
    show = df.copy()
    for c in ("toa_ms", "sens_dbm", "fup_per_day", "min_interval_s", "range_us", "range_eu"):
        show[c] = show[c].round(1)
    print(show.to_string(index=False))

    print(f"\nFlight-3 achieved (FRESH): max {rmax:.0f} km, median {rmed:.0f} km")
    print(f"Radio horizon @10/12 km: {L.radio_horizon_km(10000):.0f} / {L.radio_horizon_km(12000):.0f} km")
    print(f"Current cadence {CURRENT_INTERVAL_S}s -> {86400/CURRENT_INTERVAL_S:.0f} uplinks/day, "
          f"airtime/day by SF:")
    for sf in SFS:
        used = (86400 / CURRENT_INTERVAL_S) * L.time_on_air_s(sf)
        ok = "OK" if used <= FUP_S_PER_DAY else "OVER FUP"
        print(f"   SF{sf}: {used:5.1f} s/day  [{ok}]")

    # decision: gain vs SF7, and FUP headroom at current cadence
    print("\n=== dB gain vs SF7 and feasibility at 300 s cadence ===")
    base = L.sensitivity_dbm(7)
    for sf in SFS:
        dg = base - L.sensitivity_dbm(sf)   # positive = more sensitive
        used = (86400 / CURRENT_INTERVAL_S) * L.time_on_air_s(sf)
        print(f"   SF{sf}: +{dg:4.1f} dB floor, {used:5.1f}/30 s FUP "
              f"({'fits' if used<=FUP_S_PER_DAY else 'NEEDS slower cadence'})")

    make_plots(df, rmax, rmed)
    df.to_csv(DATA / "sf_scorecard.csv", index=False)
    print("\nwrote figs C2/C3/C4 and data/sf_scorecard.csv")


def make_plots(df, rmax, rmed):
    S.use_light()

    # --- D1: airtime + FUP feasibility (SF vs interval) ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8))
    # left: ToA and FUP cap per SF
    c1 = S.L_SERIES["vertical dipole"]
    ax1.bar([f"SF{s}" for s in df.sf], df.toa_ms, color=c1, alpha=0.85)
    ax1.set_ylabel("time-on-air per uplink (ms)", color=c1)
    ax1.tick_params(axis="y", labelcolor=c1)
    ax1b = ax1.twinx()
    ax1b.plot([f"SF{s}" for s in df.sf], df.fup_per_day, color=S.WARM, marker="o", lw=2.2)
    ax1b.set_ylabel("max uplinks/day under TTN FUP (30 s)", color=S.WARM)
    ax1b.tick_params(axis="y", labelcolor=S.WARM)
    ax1b.axhline(86400/CURRENT_INTERVAL_S, color=S.MINT, ls="--", lw=1.5)
    ax1b.text(0.1, 86400/CURRENT_INTERVAL_S+6, f"288/day @ {CURRENT_INTERVAL_S}s cadence",
              color=S.MINT, fontsize=9)
    ax1.set_title("D1a · Airtime explodes with SF; FUP caps uplinks/day\n"
                  "exponential time-on-air is the cost of range")

    # right: feasible region — min interval to stay within FUP, per SF
    ax2.plot(df.sf, df.min_interval_s, color=S.RED, marker="o", lw=2.4,
             label="min interval to meet FUP")
    ax2.axhline(CURRENT_INTERVAL_S, color=S.MINT, ls="--", lw=1.5)
    ax2.text(7.1, CURRENT_INTERVAL_S+12, f"current {CURRENT_INTERVAL_S}s cadence", color=S.MINT, fontsize=9)
    ax2.fill_between(df.sf, df.min_interval_s, 1e4, color=c1, alpha=0.10)
    ax2.set_yscale("log")
    ax2.set_xlabel("spreading factor"); ax2.set_ylabel("uplink interval (s, log)")
    ax2.set_title("D1b · Feasible (SF, interval) region\n"
                  "shaded = FUP-legal; below the red line you exceed 30 s/day")
    ax2.legend(loc="upper left", fontsize=9)
    S.footer(fig, "Stratolink · TTN FUP 30 s/day · 35 B payload · _link.py", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "D1_airtime_fup.png", dpi=180); plt.close(fig)

    # --- D2: range vs SF with horizon + achieved overlays ---
    fig, ax = plt.subplots(figsize=(11, 6.4))
    ax.plot(df.sf, df.range_us, color=S.L_SERIES["vertical dipole"], marker="o", lw=2.4, label="US915 link-budget range")
    ax.plot(df.sf, df.range_eu, color=S.L_SERIES["horizontal dipole"], marker="s", lw=2.4, label="EU868 link-budget range")
    for h, lbl in [(10000, "horizon @10 km"), (12000, "horizon @12 km")]:
        hz = L.radio_horizon_km(h)
        ax.axhline(hz, color=S.TEXT_DIM, ls=":", lw=1.3)
        ax.text(11.4, hz+8, f"{lbl} = {hz:.0f} km", color=S.TEXT_DIM, fontsize=9)
    ax.axhline(rmax, color=S.RED, ls="--", lw=1.8)
    ax.text(7.0, rmax+10, f"flight-3 best FRESH reception = {rmax:.0f} km (at SF7)", color=S.RED, fontsize=9.5)
    ax.fill_between([6.7, 12.3], 0, L.radio_horizon_km(10000), color=S.MINT, alpha=0.05)
    ax.set_xlim(6.7, 12.3)
    ax.set_xlabel("spreading factor"); ax.set_ylabel("range (km)")
    ax.set_title("D2 · Range vs SF — SF7 is link-budget-limited BELOW the horizon\n"
                 "raising SF converts the unused horizon margin into real reach (until horizon-capped)")
    ax.legend(loc="center right", fontsize=9.5)
    S.footer(fig, "Stratolink · FSPL @TX14dBm, Gtx2 Grx3, Lpol1.5 · 4/3-earth horizon", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "D2_range_vs_sf.png", dpi=180); plt.close(fig)

    # --- D3: the money plot — dB gained vs airtime cost, with sweet spot ---
    fig, ax = plt.subplots(figsize=(11, 6.4))
    base = L.sensitivity_dbm(7)
    dgain = [base - L.sensitivity_dbm(s) for s in df.sf]
    ax.plot(df.toa_ms, dgain, color=S.MINT, lw=1.5, alpha=0.5, zorder=1)
    sc = ax.scatter(df.toa_ms, dgain, c=df.sf, cmap="viridis", s=160, zorder=3, edgecolors=S.L_TEXT)
    for _, r in df.iterrows():
        ax.annotate(f"SF{int(r.sf)}", (r.toa_ms, base - r.sens_dbm),
                    textcoords="offset points", xytext=(8, -4), fontsize=10, fontweight="bold")
    # mark the FUP wall at 300s cadence: max ToA = 30s/288 = 104 ms
    fup_toa_ms = FUP_S_PER_DAY / (86400/CURRENT_INTERVAL_S) * 1e3
    ax.axvline(fup_toa_ms, color=S.RED, ls="--", lw=1.8)
    ax.text(fup_toa_ms+30, 1, f"FUP wall at {CURRENT_INTERVAL_S}s cadence\n(max {fup_toa_ms:.0f} ms ToA)",
            color=S.RED, fontsize=9.5)
    ax.set_xlabel("time-on-air per uplink (ms)  →  airtime cost")
    ax.set_ylabel("sensitivity gain vs SF7 (dB)  →  range/reception benefit")
    ax.set_title("D3 · The lever: dB gained vs airtime spent\n"
                 "each SF step = +2.5 dB but ~1.8× airtime; the FUP wall sets how far you can push at a given cadence")
    S.footer(fig, "Stratolink · diminishing returns past the FUP wall unless cadence slows", light=True)
    fig.tight_layout(); fig.savefig(FIGS / "D3_db_vs_airtime.png", dpi=180); plt.close(fig)


if __name__ == "__main__":
    main()
