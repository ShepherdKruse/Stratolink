"""Full-history GPS pattern audit for Stratolink-3.

Pulls every telemetry row from Supabase, classifies each into one of:
  - PRE_LAUNCH   pre-launch ground testing (May 15-16)
  - FRESH        valid GPS fix, distinct from prior
  - STALE        valid-looking GPS data identical to prior fix (THE BUG)
  - NOGPS        firmware correctly reported no fix (lat null, or all-zero)
  - GARBAGE      out-of-range coords from misaligned/old-fw payload

Then summarises:
  - count of each class
  - longest STALE run and when it occurred
  - temperature / altitude / battery at every STALE onset
  - whether STALE bursts ended with FRESH (chip recovered) or with NOGPS (chip un-stuck differently) or never recovered (board reset)
  - any signal from frame-counter resets (= MCU reboot) — would indicate TAMP-survived OTAA
  - correlation: STALE incidence vs temperature, altitude, time-of-day

Plots an optional timeline so it's easy to eyeball.
"""
from __future__ import annotations

import argparse
import os, sys, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"

LAUNCH_UTC = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
DEVICE_IDS = ("stratolink-3", "stratolink-3-eu")

OUT_PNG = Path(__file__).parent / "gps_stale_timeline.png"
TRACE_GAP = pd.Timedelta(minutes=20)


def fetch_all() -> pd.DataFrame:
    if not SBKEY:
        sys.exit("Set SBKEY env")
    url = f"{SBURL}/rest/v1/telemetry"
    params = {
        # The physical payload changed TTN application/device identity at the
        # US915-to-EU868 handoff. Query both halves of the circumnavigation.
        "device_id": "in.(" + ",".join(DEVICE_IDS) + ")",
        "select": "device_id,time,lat,lon,altitude_m,pressure,temperature,gps_satellites,"
                  "gps_speed,gps_heading,battery_voltage,solar_voltage,uv_index,ambient_lux",
        "order": "time.asc",
        "limit": "5000",
    }
    h = {"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"}
    r = requests.get(url, params=params, headers=h, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    return df


def load_cached(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "device_id", "time", "lat", "lon", "altitude_m", "pressure",
        "temperature", "gps_satellites", "gps_speed", "gps_heading",
        "battery_voltage", "solar_voltage",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit("cached telemetry is missing: " + ", ".join(missing))
    df = df[df["device_id"].isin(DEVICE_IDS)].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    return df.sort_values("time").reset_index(drop=True)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    df["class"] = "?"
    last_fresh = None  # tuple (lat, lon, alt, sats, speed, heading)
    consecutive_stale = 0
    df["consec_stale"] = 0

    for i, r in df.iterrows():
        if r["time"] < LAUNCH_UTC:
            df.at[i, "class"] = "PRE_LAUNCH"
            continue

        lat = r["lat"]; lon = r["lon"]; alt = r["altitude_m"]
        sats = r["gps_satellites"]; spd = r["gps_speed"]; hdg = r["gps_heading"]

        # Pre-launch garbage with impossible coords slipped through earlier (lat=-208)
        if lat is not None and not pd.isna(lat) and (abs(lat) > 90 or abs(lon) > 180):
            df.at[i, "class"] = "GARBAGE"
            continue

        # Clean NOGPS — firmware correctly zeroed everything
        if (pd.isna(lat) or lat is None or
                (lat == 0 and lon == 0 and alt == 0 and
                 (pd.isna(sats) or sats == 0))):
            df.at[i, "class"] = "NOGPS"
            consecutive_stale = 0
            continue

        # Now we have a non-null position. Is it stale?
        cur = (round(lat, 6), round(lon, 6), int(alt) if alt is not None else None,
               int(sats) if sats is not None else None,
               round(spd, 2) if spd is not None else None,
               round(hdg, 2) if hdg is not None else None)
        if last_fresh is not None and cur == last_fresh:
            df.at[i, "class"] = "STALE"
            consecutive_stale += 1
            df.at[i, "consec_stale"] = consecutive_stale
        else:
            df.at[i, "class"] = "FRESH"
            consecutive_stale = 0
            last_fresh = cur

    return df


def summarise(df: pd.DataFrame) -> dict:
    flight = df[df["time"] >= LAUNCH_UTC]
    counts = flight["class"].value_counts().to_dict()
    total = len(flight)

    # Find STALE bursts
    bursts = []
    in_burst = False
    burst_start = None
    for i, r in flight.iterrows():
        if r["class"] == "STALE":
            if not in_burst:
                in_burst = True
                burst_start = i
        else:
            if in_burst:
                bursts.append((burst_start, i - 1))
                in_burst = False
                burst_start = None
    if in_burst:
        bursts.append((burst_start, flight.index[-1]))

    burst_info = []
    for (s, e) in bursts:
        s_row = flight.loc[s]
        e_row = flight.loc[e]
        prior_fresh = flight.loc[:s-1]
        prior_fresh = prior_fresh[prior_fresh["class"] == "FRESH"]
        prior_fresh_row = prior_fresh.iloc[-1] if len(prior_fresh) else None
        # What ended the burst?
        next_idx = e + 1
        next_class = flight.loc[next_idx, "class"] if next_idx in flight.index else "END"
        burst_info.append({
            "start_time": s_row["time"],
            "end_time": e_row["time"],
            "duration_min": (e_row["time"] - s_row["time"]).total_seconds() / 60,
            "n_packets": e - s + 1,
            "lat": s_row["lat"], "lon": s_row["lon"], "alt": s_row["altitude_m"],
            "sats": s_row["gps_satellites"],
            "T_at_onset": s_row["temperature"],
            "P_at_onset": s_row["pressure"],
            "vbat_at_onset": s_row["battery_voltage"],
            "ended_by": next_class,
            "prior_fresh_at": prior_fresh_row["time"] if prior_fresh_row is not None else None,
        })

    return {
        "total_flight_rows": total,
        "counts": counts,
        "bursts": burst_info,
        "flight_df": flight,
    }


def gap_broken_series(
    times: pd.Series,
    values: pd.Series,
    maximum_gap: pd.Timedelta = TRACE_GAP,
) -> tuple[list[pd.Timestamp], list[float]]:
    """Insert NaNs so matplotlib never interpolates across telemetry outages."""
    plot_times: list[pd.Timestamp] = []
    plot_values: list[float] = []
    previous: pd.Timestamp | None = None
    for raw_time, raw_value in zip(times, values, strict=True):
        timestamp = pd.Timestamp(raw_time)
        if previous is not None and timestamp - previous > maximum_gap:
            plot_times.append(timestamp)
            plot_values.append(float("nan"))
        plot_times.append(timestamp)
        plot_values.append(float(raw_value) if not pd.isna(raw_value) else float("nan"))
        previous = timestamp
    return plot_times, plot_values


def plot_timeline(flight: pd.DataFrame):
    fig, axes = plt.subplots(4, 1, figsize=(16, 11), sharex=True,
                             gridspec_kw={"height_ratios": [1.4, 1, 1, 1]})

    class_colors = {
        "FRESH": "#2a9d4e",
        "STALE": "#d62a1a",
        "NOGPS": "#888888",
        "GARBAGE": "#aa00aa",
    }

    # 1) GPS state strip
    ax = axes[0]
    y_for = {"FRESH": 3, "STALE": 2, "NOGPS": 1, "GARBAGE": 0}
    for cls, col in class_colors.items():
        sub = flight[flight["class"] == cls]
        if len(sub) == 0:
            continue
        ax.scatter(sub["time"], [y_for[cls]] * len(sub),
                   c=col, s=22, marker="s", label=f"{cls} ({len(sub)})")
    ax.set_yticks([0, 1, 2, 3])
    ax.set_yticklabels(["GARBAGE", "NOGPS", "STALE", "FRESH"])
    ax.set_ylim(-0.5, 3.5)
    ax.set_ylabel("GPS state")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9, ncol=4)

    # 2) Altitude (proxy from pressure)
    ax = axes[1]
    # USSA76 troposphere inversion: h = (T0/L) * (1 - (p/p0)^(L*R/g*M))
    # quick approx: 18.4 * log10(1013.25/p) gives km (Holton)
    alt_km = 18.4 * np.log10(1013.25 / flight["pressure"])
    trace_time, trace_alt = gap_broken_series(flight["time"], alt_km)
    ax.plot(trace_time, trace_alt, color="#1a3a8f", linewidth=0.8)
    ax.set_ylabel("altitude (km)\nfrom pressure")
    ax.grid(True, alpha=0.3)

    # 3) Temperature
    ax = axes[2]
    trace_time, trace_temperature = gap_broken_series(
        flight["time"], flight["temperature"]
    )
    ax.plot(trace_time, trace_temperature, color="#d62a1a", linewidth=0.8)
    ax.axhline(0, color="#888888", linewidth=0.5, linestyle="--")
    ax.set_ylabel("T (°C)\n(payload internal)")
    ax.grid(True, alpha=0.3)

    # 4) Voltages
    ax = axes[3]
    trace_time, trace_battery = gap_broken_series(
        flight["time"], flight["battery_voltage"]
    )
    _, trace_solar = gap_broken_series(flight["time"], flight["solar_voltage"])
    ax.plot(trace_time, trace_battery, color="#2a9d4e",
            linewidth=0.8, label="battery")
    ax.plot(trace_time, trace_solar, color="#e6a800",
            linewidth=0.8, label="solar")
    ax.set_ylabel("voltage (V)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)

    # Mark STALE bursts on every axis
    in_burst = False
    burst_t0 = None
    for _, r in flight.iterrows():
        if r["class"] == "STALE" and not in_burst:
            in_burst = True
            burst_t0 = r["time"]
        elif r["class"] != "STALE" and in_burst:
            in_burst = False
            for a in axes:
                a.axvspan(burst_t0, r["time"], color="#d62a1a", alpha=0.10, zorder=0)
    if in_burst:
        for a in axes:
            a.axvspan(burst_t0, flight["time"].iloc[-1], color="#d62a1a",
                      alpha=0.10, zorder=0)

    locator = mdates.AutoDateLocator(minticks=5, maxticks=11)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    plt.suptitle("Stratolink-3 GPS health timeline", fontsize=13, y=0.995)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=180, bbox_inches="tight")
    print(f"  wrote {OUT_PNG}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        help="use a cached telemetry export instead of querying Supabase",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="skip regenerating the PNG timeline",
    )
    args = parser.parse_args()

    if args.csv:
        print(f"Loading cached history from {args.csv}...")
        df = load_cached(args.csv)
    else:
        print("Fetching Supabase history...")
        df = fetch_all()
    print(f"  {len(df)} total rows ({df['time'].min()} → {df['time'].max()})")

    print("\nClassifying...")
    df = classify(df)

    s = summarise(df)
    print(f"\nFlight rows (post-launch): {s['total_flight_rows']}")
    print("Class counts:")
    for cls, n in sorted(s['counts'].items(), key=lambda x: -x[1]):
        pct = 100.0 * n / s['total_flight_rows']
        print(f"  {cls:<10} {n:>4}  ({pct:5.1f}%)")

    print(f"\nSTALE bursts: {len(s['bursts'])}")
    print(f"{'#':>2} {'start':<20} {'end':<20} {'min':>5} {'pkts':>4} {'sats':>4} "
          f"{'T_onset':>7} {'P_onset':>7} {'vbat':>5} {'ended_by'}")
    for i, b in enumerate(s['bursts']):
        print(f"{i:>2} {b['start_time'].isoformat()[:19]:<20} "
              f"{b['end_time'].isoformat()[:19]:<20} "
              f"{b['duration_min']:>5.0f} {b['n_packets']:>4} {b['sats']:>4} "
              f"{b['T_at_onset']:>7.1f} {b['P_at_onset']:>7.1f} "
              f"{b['vbat_at_onset']:>5.2f} {b['ended_by']}")

    # Temperature distribution at STALE onset vs flight overall
    flight = s["flight_df"]
    fresh_T = flight.loc[flight["class"] == "FRESH", "temperature"].dropna()
    stale_T = pd.Series([b["T_at_onset"] for b in s["bursts"]])
    print(f"\nTemperature at STALE-burst onset:")
    if len(stale_T):
        print(f"  mean={stale_T.mean():.1f}°C  min={stale_T.min():.1f}  max={stale_T.max():.1f}")
    print(f"All FRESH rows temperature:")
    if len(fresh_T):
        print(f"  mean={fresh_T.mean():.1f}°C  min={fresh_T.min():.1f}  max={fresh_T.max():.1f}")

    # Altitude at STALE onset
    stale_P = pd.Series([b["P_at_onset"] for b in s["bursts"]])
    stale_alt_km = 18.4 * np.log10(1013.25 / stale_P) if len(stale_P) else pd.Series([])
    if len(stale_alt_km):
        print(f"\nAltitude at STALE-burst onset:")
        print(f"  mean={stale_alt_km.mean():.1f}km  min={stale_alt_km.min():.1f}  max={stale_alt_km.max():.1f}")

    if not args.no_plot:
        print("\nGenerating timeline plot...")
        plot_timeline(flight)


if __name__ == "__main__":
    main()
