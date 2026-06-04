#!/usr/bin/env python3
"""Network-performance figures for the TTN-vs-alternatives study (light theme).

Reads analysis/network/data/receptions.csv + gateway_census_located.csv
(produced by 10_gateway_census.py). Writes light-mode figures to
analysis/network/figs/.

  N1_gateway_diversity.png  gateways-per-uplink, US915 vs EU868 (the pattern)
  N2_rssi_vs_floor.png      RSSI distribution vs SF sensitivity floors, by band
  N3_timeline.png           gw/uplink + RSSI over time (the geographic story)
  N4_coverage_map.png       who heard us: located gateways + flight track
"""
from __future__ import annotations
import pathlib
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ANT = HERE.parent / "antenna"
sys.path.insert(0, str(ANT))
import _style as S  # noqa: E402
from _link import sensitivity_dbm  # noqa: E402

FIGS = HERE / "figs"; FIGS.mkdir(exist_ok=True)
DATA = HERE / "data"
S.use_light()

BAND_COLOR = {"US915": S.TEAL10, "EU868": S.TEAL7, "unknown": S.DIM}  # blue / teal


def load():
    r = pd.read_csv(DATA / "receptions.csv", parse_dates=["time"])
    r = r[~r["is_prelaunch"].astype(bool)].copy()           # flight only
    r["mhz"] = pd.to_numeric(r["frequency_hz"], errors="coerce") / 1e6
    return r


def fig_diversity(r):
    gpu = (r.dropna(subset=["rssi"]).groupby(["time", "device_id"])
           .agg(n=("gateway_id", "size"), band=("band", "first")).reset_index())
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3),
                                   gridspec_kw={"width_ratios": [2, 1]})
    bins = np.arange(0.5, 35, 1)
    for b in ("US915", "EU868"):
        s = gpu[gpu["band"] == b]["n"]
        ax1.hist(s, bins=bins, alpha=0.75, color=BAND_COLOR[b],
                 label=f"{b}  (n={len(s)} uplinks, median {int(s.median())})")
    ax1.set_xlabel("gateways that heard a single uplink")
    ax1.set_ylabel("number of uplinks")
    ax1.set_title("Gateway diversity per uplink")
    ax1.legend()
    # solo% + median bars
    stats = []
    for b in ("US915", "EU868"):
        s = gpu[gpu["band"] == b]["n"]
        stats.append((b, 100 * (s == 1).mean(), s.median()))
    x = np.arange(2)
    ax2.bar(x - 0.2, [v[1] for v in stats], 0.4, color=S.WARM, label="% heard by 1 gw")
    ax2b = ax2.twinx()
    ax2b.bar(x + 0.2, [v[2] for v in stats], 0.4, color=S.MINT, label="median gw/uplink")
    ax2.set_xticks(x); ax2.set_xticklabels([v[0] for v in stats])
    ax2.set_ylabel("% uplinks heard by only 1 gateway", color=S.WARM)
    ax2b.set_ylabel("median gateways / uplink", color=S.MINT)
    ax2.set_title("Redundancy")
    ax2.set_ylim(0, 100)
    fig.suptitle("Stratolink-3: TTN gateway redundancy was geographic, "
                 "thin over CONUS, ~20× over Spain", fontsize=12.5)
    S.footer(fig, "analysis/network/20_network_plots.py · flight receptions, true RF band", light=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(FIGS / "N1_gateway_diversity.png", dpi=140); plt.close(fig)
    print("wrote N1_gateway_diversity.png")


def fig_rssi_floor(r):
    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.arange(-131, -90, 2)
    for b in ("US915", "EU868"):
        s = pd.to_numeric(r[r["band"] == b]["rssi"], errors="coerce").dropna()
        ax.hist(s, bins=bins, alpha=0.75, color=BAND_COLOR[b],
                label=f"{b}  (n={len(s)} receptions, median {s.median():.0f} dBm)")
    for sf, style in ((7, "-"), (9, "--"), (10, ":")):
        f = sensitivity_dbm(sf)
        ax.axvline(f, color=S.RED if sf == 7 else S.TEXT_DIM, ls=style, lw=1.6,
                   label=f"SF{sf} sensitivity ({f:.1f} dBm)")
    ax.set_xlabel("RSSI (dBm)"); ax.set_ylabel("receptions")
    ax.set_title("We flew SF7 at the sensitivity floor, every dB of margin would close more links")
    ax.legend(fontsize=9)
    S.footer(fig, "analysis/network/20_network_plots.py · Semtech sensitivity, BW125 NF6", light=True)
    fig.tight_layout()
    fig.savefig(FIGS / "N2_rssi_vs_floor.png", dpi=140); plt.close(fig)
    print("wrote N2_rssi_vs_floor.png")


def fig_timeline(r):
    gpu = (r.dropna(subset=["rssi"]).groupby(["time", "device_id"])
           .agg(n=("gateway_id", "size"), band=("band", "first"),
                rssi_best=("rssi", "max")).reset_index())
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    for b in ("US915", "EU868"):
        s = gpu[gpu["band"] == b]
        ax1.scatter(s["time"], s["n"], s=22, alpha=0.7, color=BAND_COLOR[b], label=b)
        ax2.scatter(s["time"], s["rssi_best"], s=22, alpha=0.7, color=BAND_COLOR[b], label=b)
    ax1.set_yscale("symlog"); ax1.set_ylabel("gateways / uplink")
    ax1.set_title("Stratolink-3 reception timeline, TTN coverage tracks ground gateway density")
    ax1.legend(loc="upper center")
    ax2.axhline(sensitivity_dbm(7), color=S.RED, ls="-", lw=1.3, label="SF7 floor")
    ax2.set_ylabel("best RSSI / uplink (dBm)"); ax2.set_xlabel("UTC")
    ax2.legend(loc="lower center")
    # annotate the two big silences
    for a in (ax1, ax2):
        a.axvspan(pd.Timestamp("2026-05-19 16:00Z"), pd.Timestamp("2026-05-28 07:00Z"),
                  color=S.DIM, alpha=0.13)
    ax1.text(pd.Timestamp("2026-05-23 12:00Z"), 0.5, "Atlantic\n8.4 d silence\n(0 gateways)",
             ha="center", va="bottom", fontsize=9, color=S.TEXT_DIM)
    S.footer(fig, "analysis/network/20_network_plots.py · flight receptions", light=True)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGS / "N3_timeline.png", dpi=140); plt.close(fig)
    print("wrote N3_timeline.png")


def fig_map(r):
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except Exception as e:
        print("cartopy unavailable, skipping map:", e)
        return
    loc = pd.read_csv(DATA / "gateway_census_located.csv")
    loc = loc[loc["final_lat"].notna()].copy()
    track = (r[r["fresh"].astype(bool)].dropna(subset=["balloon_lat", "balloon_lon"])
             .drop_duplicates(["balloon_lat", "balloon_lon"]).sort_values("time"))

    fig = plt.figure(figsize=(13, 6))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([-125, 5, 28, 48], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="#eef1f4")
    ax.add_feature(cfeature.OCEAN, facecolor="#dce6ee")
    ax.add_feature(cfeature.COASTLINE, lw=0.5, edgecolor=S.TEXT_DIM)
    ax.add_feature(cfeature.BORDERS, lw=0.3, edgecolor=S.DIM)
    # gateways, sized by receptions, colored by median RSSI
    sc = ax.scatter(loc["final_lon"], loc["final_lat"],
                    s=8 + loc["receptions"].clip(upper=120),
                    c=loc["rssi_med"], cmap="turbo", vmin=-125, vmax=-100,
                    edgecolor="k", linewidth=0.3, zorder=5,
                    transform=ccrs.PlateCarree())
    # balloon fresh-fix track, break the line across big time gaps (the Atlantic
    # crossing has no telemetry, so don't draw a fictitious geodesic across it).
    t = track.sort_values("time")
    gap = t["time"].diff().dt.total_seconds().fillna(0) > 6 * 3600
    for _, g in t.groupby(gap.cumsum()):
        ax.plot(g["balloon_lon"], g["balloon_lat"], "-", color=S.RED, lw=1.1,
                alpha=0.85, zorder=4, transform=ccrs.Geodetic())
    ax.scatter(t["balloon_lon"], t["balloon_lat"], s=10, color=S.RED,
               zorder=6, transform=ccrs.PlateCarree(), label="balloon (fresh fixes)")
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.01)
    cb.set_label("gateway median RSSI (dBm)")
    n_us = int((loc["final_lon"] < -30).sum()); n_eu = int((loc["final_lon"] >= -30).sum())
    ax.set_title(f"Who heard Stratolink-3: {len(loc)} geolocated TTN gateways "
                 f"({n_us} N. America, {n_eu} Iberia) across a 9,400 km drift", pad=12)
    ax.text(-108, 31.5, "CONUS\n9 named gw\nmostly roamed\n(Packet Broker)",
            fontsize=8.5, color=S.TEXT, ha="center",
            bbox=dict(boxstyle="round", fc="white", ec=S.DIM, alpha=0.85),
            transform=ccrs.PlateCarree())
    ax.text(-62, 44.5, "Atlantic: 0 gateways → 8.4-day silence",
            fontsize=9.5, color=S.TEXT_DIM, ha="center", style="italic",
            transform=ccrs.PlateCarree())
    ax.text(-14.5, 33, "Iberia\n140 named gw\ndense ag-IoT mesh",
            fontsize=8.5, color=S.TEXT, ha="center",
            bbox=dict(boxstyle="round", fc="white", ec=S.L_ACCENT, alpha=0.9),
            transform=ccrs.PlateCarree())
    S.footer(fig, "analysis/network/20_network_plots.py · gateways: self-reported + TTN registry", light=True)
    fig.tight_layout()
    fig.savefig(FIGS / "N4_coverage_map.png", dpi=140); plt.close(fig)
    print("wrote N4_coverage_map.png")


def main():
    r = load()
    print(f"flight receptions: {len(r)}")
    fig_diversity(r)
    fig_rssi_floor(r)
    fig_timeline(r)
    fig_map(r)
    print("figs in", FIGS)


if __name__ == "__main__":
    main()
