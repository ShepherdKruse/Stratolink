"""WSPR-style signal analysis plots for Stratolink-3's first flight.

Generates four figures using the per-uplink gateway reception data from
the Supabase `telemetry.gateways` column:

  1. signal_boxplots.png       - receiver lat/lon as a function of
                                  balloon TX lat/lon (4-panel box-plot grid)
  2. signal_solar_histograms.png - number of spots vs solar elevation
                                    and vs hour of day, split by longitude
                                    range (CONUS / mid-flight / EU)
  3. signal_solar_distance.png  - 2-D histogram: TX solar elevation vs
                                  signal travel distance
  4. signal_solar_tx_rx.png     - 2-D histogram: TX solar elevation vs
                                  RX solar elevation, with the 1:1 line

A "spot" here = one (uplink, gateway) reception pair, so each balloon
uplink that 10 gateways heard contributes 10 spots. Solar elevation is
computed via pysolar at the actual uplink UTC time, at the balloon
position (TX) and at each gateway position (RX).
"""
from __future__ import annotations

import os, sys, math, json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Rectangle

from pysolar.solar import get_altitude

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
OUT_DIR = Path(__file__).parent


def fetch_telemetry_with_gateways() -> pd.DataFrame:
    r = requests.get(
        f"{SBURL}/rest/v1/telemetry",
        params={
            "device_id": "in.(stratolink-3,stratolink-3-eu)",
            "select": "time,device_id,lat,lon,altitude_m,snr,rssi,gateways",
            "order": "time.asc",
            "limit": "5000",
        },
        headers={"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    df = df[df["lat"].notna() & df["lon"].notna()
            & (df["altitude_m"] > 1000)
            & (df["lat"].abs() <= 90) & (df["lon"].abs() <= 180)]
    return df.reset_index(drop=True)


def _hav_km(la1, lo1, la2, lo2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((la2-la1)*p)/2
         + math.cos(la1*p)*math.cos(la2*p)*(1-math.cos((lo2-lo1)*p))/2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def flatten_to_spots(df: pd.DataFrame) -> pd.DataFrame:
    """Each (uplink, gateway-with-position) pair becomes one spot row."""
    spots = []
    for _, row in df.iterrows():
        gws = row.get("gateways") or []
        if not gws:
            continue
        t = row["time"].to_pydatetime()
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        try:
            tx_elev = float(get_altitude(float(row["lat"]), float(row["lon"]), t))
        except Exception:
            continue
        for g in gws:
            if g.get("lat") is None or g.get("lon") is None:
                continue
            try:
                rx_elev = float(get_altitude(float(g["lat"]), float(g["lon"]), t))
            except Exception:
                continue
            d = _hav_km(row["lat"], row["lon"], g["lat"], g["lon"])
            spots.append({
                "time": t,
                "balloon_lat": float(row["lat"]),
                "balloon_lon": float(row["lon"]),
                "rx_lat": float(g["lat"]),
                "rx_lon": float(g["lon"]),
                "rx_snr": g.get("snr"),
                "rx_rssi": g.get("rssi"),
                "distance_km": d,
                "tx_solar_elev": tx_elev,
                "rx_solar_elev": rx_elev,
                "hour_utc": t.hour + t.minute / 60.0 + t.second / 3600.0,
            })
    return pd.DataFrame(spots)


# Cities for the box-plot right-margin reference labels.
CITY_LATS = [
    ("London",   51.5),
    ("Atlanta",  33.7),
    ("Honolulu", 21.3),
    ("Equator",   0.0),
    ("Sydney",  -33.9),
]
CITY_LONS = [
    ("Sydney",     151.2),
    ("New Delhi",   77.2),
    ("Cape Town",   18.4),
    ("London",       0.0),
    ("New York",   -74.0),
    ("Los Angeles",-118.2),
    ("Honolulu",  -157.8),
]


# ---- Plot 1: box plot grid -------------------------------------------------

def plot_boxplots(spots: pd.DataFrame, out_png: Path):
    """4-panel box plot: receiver lat/lon as function of balloon TX lat/lon.
    Mirrors the reference's WSPR receiver-vs-balloon-TX visualization."""

    fig, axes = plt.subplots(2, 2, figsize=(18, 10), facecolor="white")
    blue_map = plt.cm.Blues
    red_map = plt.cm.Reds

    # Balloon position bin definitions - sized to our flight's ranges so
    # each box has a meaningful sample.
    lat_bin_w = 2.0
    lon_bin_w = 10.0
    lat_bins = np.arange(np.floor(spots["balloon_lat"].min()/lat_bin_w)*lat_bin_w,
                          np.ceil(spots["balloon_lat"].max()/lat_bin_w)*lat_bin_w + lat_bin_w,
                          lat_bin_w)
    lon_bins = np.arange(np.floor(spots["balloon_lon"].min()/lon_bin_w)*lon_bin_w,
                          np.ceil(spots["balloon_lon"].max()/lon_bin_w)*lon_bin_w + lon_bin_w,
                          lon_bin_w)

    def _draw_panel(ax, x_col, y_col, bins, cmap, x_label, y_label, title,
                      city_labels=None, y_range=(-90, 90)):
        # Group spots into x bins
        x_bin_idx = np.digitize(spots[x_col].values, bins) - 1
        data_per_bin = []
        bin_centers = []
        for i in range(len(bins) - 1):
            mask = x_bin_idx == i
            if mask.sum() < 1:
                data_per_bin.append([])
            else:
                data_per_bin.append(spots[y_col].values[mask])
            bin_centers.append((bins[i] + bins[i + 1]) / 2.0)
        # Skip empty bins entirely
        non_empty = [(i, d) for i, d in enumerate(data_per_bin) if len(d) >= 1]
        positions = [bin_centers[i] for i, _ in non_empty]
        values = [d for _, d in non_empty]
        if not values:
            return
        # Color each box by its bin index (lighter -> darker low -> high)
        n_bins = len(bins) - 1
        bp = ax.boxplot(values, positions=positions, widths=lat_bin_w * 0.8
                         if "lat" in x_label.lower() else lon_bin_w * 0.8,
                         patch_artist=True,
                         flierprops=dict(marker="D", markersize=3,
                                          markerfacecolor=(0, 0, 0, 0.6),
                                          markeredgecolor="none"),
                         medianprops=dict(color="black", linewidth=1.0),
                         whiskerprops=dict(color=(0.2, 0.2, 0.2), linewidth=0.8),
                         capprops=dict(color=(0.2, 0.2, 0.2), linewidth=0.8))
        for patch, (i, _) in zip(bp["boxes"], non_empty):
            shade = 0.25 + 0.65 * (i / max(n_bins - 1, 1))
            patch.set_facecolor(cmap(shade))
            patch.set_edgecolor((0.2, 0.2, 0.2))
            patch.set_linewidth(0.7)
        ax.set_xlim(bins[0] - lat_bin_w if "lat" in x_label.lower()
                     else bins[0] - lon_bin_w,
                     bins[-1] + lat_bin_w if "lat" in x_label.lower()
                     else bins[-1] + lon_bin_w)
        ax.set_ylim(y_range)
        ax.set_xlabel(x_label, fontsize=11)
        ax.set_ylabel(y_label, fontsize=11)
        ax.set_title(title, fontsize=12, pad=10)
        ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5)
        # City reference labels just outside the right edge.
        # x in axes fraction (1.005 = a hair right of the axes box),
        # y in data coords via blended transform.
        if city_labels:
            for name, val in city_labels:
                if y_range[0] <= val <= y_range[1]:
                    ax.axhline(val, color="gray", linewidth=0.4,
                                linestyle=":", alpha=0.7)
                    ax.text(1.005, val, " " + name,
                              fontsize=8, va="center", ha="left",
                              color=(0.25, 0.25, 0.25),
                              transform=ax.get_yaxis_transform(),
                              clip_on=False)

    # Top row: receiver LAT vs balloon TX lat / lon  (blue)
    _draw_panel(axes[0, 0],
                  "balloon_lat", "rx_lat", lat_bins, blue_map,
                  "Balloon Transmission Latitude (degrees)",
                  "Stratolink Receiver Latitude (degrees)",
                  "Stratolink Receiver Latitude vs. Balloon TX Latitude",
                  city_labels=CITY_LATS, y_range=(-90, 90))
    _draw_panel(axes[0, 1],
                  "balloon_lon", "rx_lat", lon_bins, blue_map,
                  "Balloon Transmission Longitude (degrees)",
                  "Stratolink Receiver Latitude (degrees)",
                  "Stratolink Receiver Latitude vs. Balloon TX Longitude",
                  city_labels=CITY_LATS, y_range=(-90, 90))
    # Bottom row: receiver LON vs balloon TX lat / lon  (red)
    _draw_panel(axes[1, 0],
                  "balloon_lat", "rx_lon", lat_bins, red_map,
                  "Balloon Transmission Latitude (degrees)",
                  "Stratolink Receiver Longitude (degrees)",
                  "Stratolink Receiver Longitude vs. Balloon TX Latitude",
                  city_labels=CITY_LONS, y_range=(-180, 180))
    _draw_panel(axes[1, 1],
                  "balloon_lon", "rx_lon", lon_bins, red_map,
                  "Balloon Transmission Longitude (degrees)",
                  "Stratolink Receiver Longitude (degrees)",
                  "Stratolink Receiver Longitude vs. Balloon TX Longitude",
                  city_labels=CITY_LONS, y_range=(-180, 180))

    # Reserve right margin so the city labels (drawn with clip_on=False
    # outside the axes box) have somewhere to live.
    plt.subplots_adjust(left=0.06, right=0.93, top=0.94, bottom=0.07,
                          wspace=0.30, hspace=0.30)
    plt.savefig(out_png, dpi=200, bbox_inches="tight", pad_inches=0.15,
                facecolor="white")
    print(f"  wrote {out_png.name}")


# ---- Plot 2: solar elevation + hour histograms by region -------------------

def plot_solar_histograms(spots: pd.DataFrame, out_png: Path):
    """Histograms of spot count vs solar elevation and hour of day, split
    into three balloon-position bins. The reference uses Southern-hemisphere
    latitude bands; we use longitude bands matching our transatlantic flight
    (CONUS / Atlantic transit / EU)."""

    regions = [
        ("CONUS (lon < -75°)",  (spots["balloon_lon"] < -75),  "tab:blue"),
        ("Atlantic (-75° to -10°)",
         (spots["balloon_lon"] >= -75) & (spots["balloon_lon"] < -10), "tab:orange"),
        ("Iberia / EU (lon ≥ -10°)",
         (spots["balloon_lon"] >= -10), "tab:red"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(15, 8), facecolor="white")
    for col, (title, mask, color) in enumerate(regions):
        sub = spots[mask]
        # Top row: solar elevation histogram
        ax_e = axes[0, col]
        if len(sub):
            ax_e.hist(sub["tx_solar_elev"].values,
                       bins=np.arange(-30, 91, 5),
                       color=color, edgecolor="black", linewidth=0.4)
        ax_e.set_title(f"Spots - {title}", fontsize=11)
        ax_e.set_xlabel("Solar elevation at TX (degrees)", fontsize=10)
        ax_e.set_ylabel("Number of spots", fontsize=10)
        ax_e.grid(True, linestyle="--", linewidth=0.3, alpha=0.4)
        # Bottom row: hour-of-day histogram
        ax_h = axes[1, col]
        if len(sub):
            ax_h.hist(sub["hour_utc"].values, bins=np.arange(0, 25, 1),
                       color=color, edgecolor="black", linewidth=0.4)
        ax_h.set_xlabel("Hour of day (UTC)", fontsize=10)
        ax_h.set_ylabel("Number of spots", fontsize=10)
        ax_h.grid(True, linestyle="--", linewidth=0.3, alpha=0.4)
        ax_h.set_xticks(np.arange(0, 25, 4))

    fig.suptitle("Number of spots vs solar elevation and hour of day, "
                  "by balloon longitude band",
                  fontsize=13, y=1.00)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200, bbox_inches="tight", pad_inches=0.15,
                facecolor="white")
    print(f"  wrote {out_png.name}")


# ---- Plot 3: 2-D hist of TX solar elevation vs signal distance --------------

def plot_solar_vs_distance(spots: pd.DataFrame, out_png: Path):
    """2-D histogram of solar elevation at the balloon vs signal travel
    distance. The reference goes out to 20,000 km on the WSPR data; our
    LoRa-at-10-km-altitude line-of-sight horizon is around 430 km."""

    fig, ax = plt.subplots(1, 1, figsize=(10, 7), facecolor="white")
    # Bin so the histogram still reads at our short distance range.
    x_edges = np.arange(0, 500, 10)
    y_edges = np.arange(-30, 91, 2)
    hb = ax.hist2d(spots["distance_km"].values,
                   spots["tx_solar_elev"].values,
                   bins=[x_edges, y_edges],
                   cmap="jet", cmin=1)
    cbar = plt.colorbar(hb[3], ax=ax, label="Number of spots", fraction=0.046, pad=0.04)
    ax.set_xlabel("Signal travel distance (km)", fontsize=11)
    ax.set_ylabel("Solar elevation at balloon TX (degrees)", fontsize=11)
    ax.set_title("Solar elevation angle at TX vs. signal travel distance",
                  fontsize=13, pad=10)
    ax.grid(True, linestyle="--", linewidth=0.3, alpha=0.5)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200, bbox_inches="tight", pad_inches=0.15,
                facecolor="white")
    print(f"  wrote {out_png.name}")


# ---- Plot 4: 2-D hist of TX vs RX solar elevation ---------------------------

def plot_tx_vs_rx_solar(spots: pd.DataFrame, out_png: Path):
    """2-D histogram of solar elevation at balloon TX vs at the receiving
    gateway, with the 1:1 line drawn. The reference WSPR plot also marks
    'RX Nighttime' (negative rx_elev) and 'RX Daytime' regions and a
    short-hop overlay; we follow the same conventions."""

    fig, ax = plt.subplots(1, 1, figsize=(10, 7), facecolor="white")
    x_edges = np.arange(-90, 91, 2)
    y_edges = np.arange(-30, 91, 2)
    hb = ax.hist2d(spots["rx_solar_elev"].values,
                   spots["tx_solar_elev"].values,
                   bins=[x_edges, y_edges],
                   cmap="jet", cmin=1)
    cbar = plt.colorbar(hb[3], ax=ax, label="Number of spots", fraction=0.046, pad=0.04)
    # 1:1 reference line
    lim = (max(x_edges[0], y_edges[0]), min(x_edges[-1], y_edges[-1]))
    ax.plot([lim[0], lim[1]], [lim[0], lim[1]],
            color="black", linewidth=1.2, label="1:1")
    # Day/night divider
    ax.axvline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.text(-45, ax.get_ylim()[1] - 6, "← RX Nighttime",
             fontsize=11, color=(0.2, 0.2, 0.2), ha="center")
    ax.text( 45, ax.get_ylim()[1] - 6, "RX Daytime →",
             fontsize=11, color=(0.2, 0.2, 0.2), ha="center")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_xlabel("RX solar elevation angles (degrees)", fontsize=11)
    ax.set_ylabel("TX solar elevation angles (degrees)", fontsize=11)
    ax.set_title("TX vs. RX solar elevation angles", fontsize=13, pad=10)
    ax.grid(True, linestyle="--", linewidth=0.3, alpha=0.5)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200, bbox_inches="tight", pad_inches=0.15,
                facecolor="white")
    print(f"  wrote {out_png.name}")


def main():
    if not SBKEY: sys.exit("Set SBKEY env")
    print("[1/3] Fetching telemetry...")
    df = fetch_telemetry_with_gateways()
    print(f"  {len(df)} valid fixes with sane lat/lon/altitude")

    print("[2/3] Flattening to spots + solar-elevation lookups (pysolar)...")
    spots = flatten_to_spots(df)
    print(f"  {len(spots)} (uplink, positioned-gateway) spots")
    if not len(spots):
        sys.exit("no spots - nothing to plot")
    print(f"  balloon lat range: {spots.balloon_lat.min():.2f} → {spots.balloon_lat.max():.2f}")
    print(f"  balloon lon range: {spots.balloon_lon.min():.2f} → {spots.balloon_lon.max():.2f}")
    print(f"  rx lat range:      {spots.rx_lat.min():.2f} → {spots.rx_lat.max():.2f}")
    print(f"  rx lon range:      {spots.rx_lon.min():.2f} → {spots.rx_lon.max():.2f}")
    print(f"  distance range:    {spots.distance_km.min():.1f} → {spots.distance_km.max():.1f} km")
    print(f"  tx solar elev:     {spots.tx_solar_elev.min():.1f} → {spots.tx_solar_elev.max():.1f}°")
    print(f"  rx solar elev:     {spots.rx_solar_elev.min():.1f} → {spots.rx_solar_elev.max():.1f}°")

    print("[3/3] Rendering 4 plots...")
    plot_boxplots(spots, OUT_DIR / "signal_boxplots.png")
    plot_solar_histograms(spots, OUT_DIR / "signal_solar_histograms.png")
    plot_solar_vs_distance(spots, OUT_DIR / "signal_solar_distance.png")
    plot_tx_vs_rx_solar(spots, OUT_DIR / "signal_solar_tx_rx.png")


if __name__ == "__main__":
    main()
