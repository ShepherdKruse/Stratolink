#!/usr/bin/env python3
"""Characterize the RF link; write the markdown report + diagnostic figures.

Run (no creds needed; reads cached receptions):
  analysis/.venv/bin/python analysis/antenna/30_characterize.py

Outputs:
  analysis/antenna/01_signal_characterization.md
  analysis/antenna/figs/rssi_vs_distance.png
  analysis/antenna/figs/rssi_snr_hist_by_region.png
  analysis/antenna/figs/elevation_angle_hist.png
Prints a NUMERIC SUMMARY block to stdout for relaying upstream.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from _common import DATA, FIGS, HERE  # noqa: E402

REPORT = HERE / "01_signal_characterization.md"


def q(s, p):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(np.percentile(s, p)) if len(s) else float("nan")


def fmt(x, nd=1):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def main() -> int:
    pq, csv = DATA / "receptions.parquet", DATA / "receptions.csv"
    if pq.exists():
        r = pd.read_parquet(pq)
    elif csv.exists():
        r = pd.read_csv(csv)
    else:
        sys.stderr.write("No receptions table. Run 20_receptions.py first.\n")
        sys.exit(2)
    if "time" in r.columns:
        r["time"] = pd.to_datetime(r["time"], utc=True, errors="coerce")

    L: list[str] = []
    emit = L.append

    # uplink-level frame (dedupe receptions back to uplinks)
    keys = [c for c in ("time", "device_id") if c in r.columns]
    uplinks = r.drop_duplicates(subset=keys) if keys else r
    n_uplinks = len(uplinks)
    n_us = int((uplinks["region"] == "US").sum())
    n_eu = int((uplinks["region"] == "EU").sum())

    geo = r[r["gc_km"].notna()].copy()
    named = r[~r["anonymized"].fillna(True)]
    n_named_gw = named["gateway_id"].nunique()
    n_recs = len(r)
    n_anon = int(r["anonymized"].fillna(True).sum())
    n_coords = int(r["gc_km"].notna().sum())
    # coord provenance: geolocation comes from BOTH named gateways and the
    # Packet-Broker entries (some of each carry lat/lon, some don't).
    n_coords_named = int((geo["anonymized"] == False).sum())  # noqa: E712
    n_coords_pb = int((geo["anonymized"] == True).sum())  # noqa: E712

    emit("# Stratolink-3 signal characterization")
    emit("")
    emit("Source: TTN webhook -> Supabase `public.telemetry` "
         "(project iazmnyyfsobucndqncgw), devices `stratolink-3` (US915/nam1) "
         "and `stratolink-3-eu` (EU868/eu1).")
    emit("Per-reception rows are exploded from the `gateways` JSONB column "
         "(one entry per gateway that decoded the uplink).")
    if r["time"].notna().any():
        emit(f"Time span: {r['time'].min()} -> {r['time'].max()} (UTC).")
    emit("")
    emit("**Geometry caveat:** only a subset of `gateways[]` entries carry "
         "lat/lon. Coordinates come from BOTH named gateways (e.g. niharramikrotik, "
         "italr0005, meceiot-*, cdtic-multitech-4, tef-mls-01) AND Packet-Broker "
         "(`gateway_id='packetbroker'`) entries; the rest (cicytex, mtcdtip, "
         "ext-sg50, mjv-*, ...) report null coords. All distance/angle stats below "
         "are over the geolocated receptions only; RSSI/SNR/SF stats use every "
         "reception.")
    emit("")

    emit("## Counts")
    emit(f"- Uplinks total: **{n_uplinks}** (US {n_us}, EU {n_eu})")
    emit(f"- Receptions (uplink x gateway): **{n_recs}**")
    emit(f"- Unique NAMED gateways: **{n_named_gw}**; "
         f"packetbroker-anonymized receptions: **{n_anon}**")
    emit(f"- Receptions with usable gateway coords (geometry): **{n_coords}** "
         f"(of which {n_coords_named} from named gateways, {n_coords_pb} from packetbroker)")
    emit("")

    # RSSI / SNR by region
    emit("## RSSI / SNR (per reception)")
    emit("")
    emit("| region | n | RSSI min | RSSI med | RSSI max | SNR min | SNR med | SNR max |")
    emit("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for reg in ("US", "EU", "ALL"):
        sub = r if reg == "ALL" else r[r["region"] == reg]
        emit(f"| {reg} | {len(sub)} | {fmt(q(sub['rssi'],0))} | {fmt(q(sub['rssi'],50))} "
             f"| {fmt(q(sub['rssi'],100))} | {fmt(q(sub['snr'],0))} | {fmt(q(sub['snr'],50))} "
             f"| {fmt(q(sub['snr'],100))} |")
    emit("")

    # SF / freq
    emit("## Spreading factor and frequency")
    sf_counts = r["spreading_factor"].value_counts(dropna=True).sort_index()
    emit("- SF usage (receptions): " +
         ", ".join(f"SF{int(k)}: {int(v)}" for k, v in sf_counts.items()))
    sf_up = uplinks["spreading_factor"].value_counts(dropna=True).sort_index()
    emit("- SF usage (uplinks): " +
         ", ".join(f"SF{int(k)}: {int(v)}" for k, v in sf_up.items()))
    freqs = sorted(set(round(f / 1e6, 2) for f in r["frequency_hz"].dropna()))
    emit(f"- Frequencies seen (MHz): {freqs}")
    emit("")

    # distance
    emit("## Distance reached (geolocated receptions)")
    if len(geo):
        emit(f"- Great-circle: median {fmt(q(geo['gc_km'],50))} km, "
             f"max {fmt(q(geo['gc_km'],100))} km")
        emit(f"- Slant range: median {fmt(q(geo['slant_km'],50))} km, "
             f"max {fmt(q(geo['slant_km'],100))} km")
        far = geo.loc[geo["slant_km"].idxmax()]
        emit("")
        emit("Longest-range successful reception:")
        emit(f"- slant {fmt(far['slant_km'])} km (great-circle {fmt(far['gc_km'])} km), "
             f"RSSI {fmt(far['rssi'])} dBm, SNR {fmt(far['snr'])} dB, "
             f"SF{int(far['spreading_factor']) if pd.notna(far['spreading_factor']) else '?'}, "
             f"balloon alt {fmt(far['balloon_alt'],0)} m, region {far['region']}, "
             f"elev {fmt(far['elev_gw_deg'])} deg, at {far['time']}")
    else:
        emit("- No receptions with usable coordinates.")
    emit("")

    # look angles
    emit("## Look angles (geolocated receptions)")
    if len(geo):
        emit(f"- Gateway elevation above horizon (deg): "
             f"min {fmt(q(geo['elev_gw_deg'],0))}, p25 {fmt(q(geo['elev_gw_deg'],25))}, "
             f"median {fmt(q(geo['elev_gw_deg'],50))}, p75 {fmt(q(geo['elev_gw_deg'],75))}, "
             f"max {fmt(q(geo['elev_gw_deg'],100))}")
        emit(f"- Balloon depression below local horizontal (0=side, 90=nadir): "
             f"min {fmt(q(geo['depr_balloon_deg'],0))}, median {fmt(q(geo['depr_balloon_deg'],50))}, "
             f"max {fmt(q(geo['depr_balloon_deg'],100))}")
        bins = [0, 1, 2, 5, 10, 20, 40, 90]
        cats = pd.cut(geo["elev_gw_deg"].clip(lower=0), bins=bins, include_lowest=True)
        emit("- Gateway elevation-angle histogram: " +
             ", ".join(f"{str(iv)}deg: {int(c)}" for iv, c in cats.value_counts().sort_index().items()))
    emit("")

    # path-loss fit
    emit("## RSSI vs distance (path-loss fit)")
    fit_n = fit_A = r2v = np.nan
    if len(geo) >= 5:
        g = geo[(geo["slant_km"] > 0) & geo["rssi"].notna()].copy()
        x = np.log10(g["slant_km"].astype(float).values)
        y = g["rssi"].astype(float).values
        if len(g) >= 5 and np.ptp(x) > 0:
            slope, intercept = np.polyfit(x, y, 1)
            fit_A, fit_n = intercept, -slope / 10.0
            yhat = slope * x + intercept
            ss_res = float(np.sum((y - yhat) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2v = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
            emit(f"- Fit RSSI ~= A - 10*n*log10(d_km): A = {fmt(fit_A)} dBm, "
                 f"n = **{fmt(fit_n,2)}** (free space = 2.0), R^2 = {fmt(r2v,2)}, "
                 f"n_points = {len(g)}.")
            note = ("n below 2 means the link beats free space along the "
                    "as-the-crow-flies distance: at altitude the longest links "
                    "go to high-elevation / overhead gateways with the clearest "
                    "path, so RSSI falls slower than 1/d^2 -- expect heavy "
                    "scatter (R^2 low) because the balloon antenna pattern and "
                    "orientation, not distance, dominate."
                    if fit_n < 2 else
                    "n above 2 means excess loss beyond free space.")
            emit(f"- Interpretation: {note}")
    else:
        emit("- Too few geolocated points for a fit.")
    emit("")

    # altitude vs reception
    emit("## Altitude vs reception")
    a = pd.to_numeric(r["balloon_alt"], errors="coerce").dropna()
    if len(a):
        emit(f"- Balloon altitude at receptions: min {fmt(a.min(),0)} m, "
             f"median {fmt(a.median(),0)} m, max {fmt(a.max(),0)} m")
        abins = [-100, 1000, 5000, 10000, 12000, 13000, 14000, 100000]
        ac = pd.cut(a, bins=abins, include_lowest=True)
        emit("- Receptions by altitude band: " +
             ", ".join(f"{int(iv.left)}-{int(iv.right)}m: {int(c)}"
                       for iv, c in ac.value_counts().sort_index().items()))
        # uplink-level altitude reach
        ua = pd.to_numeric(uplinks["balloon_alt"], errors="coerce").dropna()
        emit(f"- Uplink altitude: min {fmt(ua.min(),0)} m, median {fmt(ua.median(),0)} m, "
             f"max {fmt(ua.max(),0)} m (n={len(ua)} uplinks w/ altitude)")
    else:
        emit("- No altitude data.")
    emit("")

    # time of day
    emit("## RSSI vs time-of-day (UTC)")
    if r["time"].notna().any():
        rr = r.dropna(subset=["time"]).copy()
        rr["hour"] = rr["time"].dt.hour
        bh = rr.groupby("hour")["rssi"].median()
        emit("- Median RSSI by UTC hour: " +
             ", ".join(f"{int(h):02d}h:{fmt(v,0)}" for h, v in bh.items()))
        emit("- (Flight crossed ~8 timezones SF->Spain; local-solar effects are "
             "confounded with longitude/phase, so read this as indicative only.)")
    emit("")

    # ---- figures ----
    if len(geo):
        fig, ax = plt.subplots(figsize=(7, 5))
        for reg, col in (("US", "tab:blue"), ("EU", "tab:orange")):
            s = geo[geo["region"] == reg]
            ax.scatter(s["slant_km"], s["rssi"], s=14, alpha=0.5, label=f"{reg} (n={len(s)})", color=col)
        if not np.isnan(fit_n):
            xs = np.linspace(max(1, geo["slant_km"].min()), geo["slant_km"].max(), 100)
            ax.plot(xs, fit_A - 10 * fit_n * np.log10(xs), "k--",
                    label=f"fit n={fit_n:.2f}, R^2={r2v:.2f}")
        ax.set_xscale("log")
        ax.set_xlabel("slant range (km, log)"); ax.set_ylabel("RSSI (dBm)")
        ax.set_title("Stratolink-3 RSSI vs slant range (packetbroker gateways)")
        ax.legend(); ax.grid(True, which="both", alpha=0.3)
        fig.tight_layout(); fig.savefig(FIGS / "rssi_vs_distance.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for reg, col in (("US", "tab:blue"), ("EU", "tab:orange")):
        s = r[r["region"] == reg]
        ax[0].hist(pd.to_numeric(s["rssi"], errors="coerce").dropna(), bins=30, alpha=0.55, label=reg, color=col)
        ax[1].hist(pd.to_numeric(s["snr"], errors="coerce").dropna(), bins=30, alpha=0.55, label=reg, color=col)
    ax[0].set_xlabel("RSSI (dBm)"); ax[0].set_ylabel("receptions"); ax[0].set_title("RSSI by region"); ax[0].legend()
    ax[1].set_xlabel("SNR (dB)"); ax[1].set_title("SNR by region"); ax[1].legend()
    fig.tight_layout(); fig.savefig(FIGS / "rssi_snr_hist_by_region.png", dpi=130); plt.close(fig)

    if len(geo):
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(geo["elev_gw_deg"].dropna(), bins=40, color="tab:green", alpha=0.8)
        ax.set_xlabel("gateway elevation angle to balloon (deg)")
        ax.set_ylabel("receptions"); ax.set_title("Where gateways heard us (look-up angle)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout(); fig.savefig(FIGS / "elevation_angle_hist.png", dpi=130); plt.close(fig)

    REPORT.write_text("\n".join(L) + "\n")
    print(f"wrote {REPORT}")
    print("figures in", FIGS)

    print("\n==== NUMERIC SUMMARY ====")
    print(f"uplinks={n_uplinks} US={n_us} EU={n_eu} receptions={n_recs} "
          f"named_gw={n_named_gw} coords={n_coords} anon={n_anon}")
    print(f"RSSI all: min={fmt(q(r['rssi'],0))} med={fmt(q(r['rssi'],50))} max={fmt(q(r['rssi'],100))}")
    print(f"SNR  all: min={fmt(q(r['snr'],0))} med={fmt(q(r['snr'],50))} max={fmt(q(r['snr'],100))}")
    for reg in ("US", "EU"):
        s = r[r["region"] == reg]
        print(f"RSSI {reg}: med={fmt(q(s['rssi'],50))} min={fmt(q(s['rssi'],0))} | "
              f"SNR {reg}: med={fmt(q(s['snr'],50))} min={fmt(q(s['snr'],0))}")
    if len(geo):
        print(f"gc_km med={fmt(q(geo['gc_km'],50))} max={fmt(q(geo['gc_km'],100))} | "
              f"slant_km med={fmt(q(geo['slant_km'],50))} max={fmt(q(geo['slant_km'],100))}")
        print(f"elev_deg med={fmt(q(geo['elev_gw_deg'],50))} min={fmt(q(geo['elev_gw_deg'],0))} max={fmt(q(geo['elev_gw_deg'],100))}")
        print(f"depr_deg med={fmt(q(geo['depr_balloon_deg'],50))} min={fmt(q(geo['depr_balloon_deg'],0))} max={fmt(q(geo['depr_balloon_deg'],100))}")
        print(f"pathloss n={fmt(fit_n,2)} A={fmt(fit_A)} R2={fmt(r2v,2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
