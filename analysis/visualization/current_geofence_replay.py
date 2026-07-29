#!/usr/bin/env python3
"""Render the current compiled geofence and historically fresh Flight-3 fixes."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "analysis/antenna"))
sys.path.insert(0, str(ROOT / "analysis/diagnostics"))

from _gps import classify_uplinks  # noqa: E402
from compiled_region import REGION_NAMES, compiled_regions  # noqa: E402


COLORS = {
    "US915": "#2f76b7",
    "EU868": "#399267",
    "AS923": "#e5b642",
    "AU915": "#8065a8",
    "SILENT": "#b6bec8",
}
ORDER = ["US915", "EU868", "AS923", "AU915", "SILENT"]


def main() -> None:
    longitude = np.arange(-180, 181, 1, dtype=np.int32)
    latitude = np.arange(-90, 91, 1, dtype=np.int32)
    lon_grid, lat_grid = np.meshgrid(longitude, latitude)
    pairs = zip(
        (lat_grid.ravel() * 10_000_000).tolist(),
        (lon_grid.ravel() * 10_000_000).tolist(),
    )
    region_ids = np.array(compiled_regions(pairs), dtype=np.int16).reshape(
        lat_grid.shape
    )
    id_to_index = {value: ORDER.index(name) for value, name in REGION_NAMES.items()}
    indexed = np.vectorize(id_to_index.__getitem__)(region_ids)

    telemetry = pd.read_csv(ROOT / "analysis/antenna/data/telemetry_raw.csv")
    telemetry["time"] = pd.to_datetime(telemetry["time"], utc=True)
    classified = classify_uplinks(telemetry)
    fresh = classified[classified["gps_class"] == "FRESH"].copy()
    historical_pairs = [
        (round(float(row.lat) * 10_000_000), round(float(row.lon) * 10_000_000))
        for row in fresh.itertuples()
    ]
    historical_names = [
        REGION_NAMES[value] for value in compiled_regions(historical_pairs)
    ]
    assert historical_names == ["US915"] * 31 + ["EU868"] * 8

    figure = plt.figure(figsize=(16, 9), facecolor="white")
    axis = plt.axes(projection=ccrs.PlateCarree())
    axis.set_global()
    axis.imshow(
        indexed,
        origin="lower",
        extent=[-180.5, 180.5, -90.5, 90.5],
        transform=ccrs.PlateCarree(),
        cmap=ListedColormap([COLORS[name] for name in ORDER]),
        alpha=0.42,
        interpolation="nearest",
        zorder=0,
    )
    axis.add_feature(cfeature.LAND, facecolor="none", zorder=1)
    axis.add_feature(cfeature.COASTLINE, edgecolor="#606b78", linewidth=0.55)
    axis.add_feature(cfeature.BORDERS, edgecolor="#8f98a4", linewidth=0.3)
    grid = axis.gridlines(
        draw_labels=True,
        linewidth=0.35,
        color="#8793a0",
        alpha=0.45,
        linestyle=":",
    )
    grid.top_labels = False
    grid.right_labels = False

    for name in ("US915", "EU868"):
        subset = fresh[np.array(historical_names) == name]
        axis.scatter(
            subset["lon"],
            subset["lat"],
            s=30,
            color=COLORS[name],
            edgecolor="white",
            linewidth=0.65,
            transform=ccrs.PlateCarree(),
            zorder=5,
        )
    launch = fresh.iloc[0]
    final = fresh.iloc[-1]
    axis.scatter(
        [launch.lon, final.lon],
        [launch.lat, final.lat],
        marker="*",
        s=260,
        color=[COLORS["US915"], COLORS["EU868"]],
        edgecolor="white",
        linewidth=1.1,
        transform=ccrs.PlateCarree(),
        zorder=6,
    )
    axis.text(
        launch.lon - 3,
        launch.lat + 6,
        "first fresh fix\nUS915",
        color="#174d7c",
        ha="center",
        fontsize=9,
        fontweight="bold",
        transform=ccrs.PlateCarree(),
        zorder=7,
    )
    axis.text(
        final.lon + 2,
        final.lat - 9,
        "final fresh fix (Spain)\nEU868 from position\n(though received via NA stream)",
        color="#1f6e49",
        ha="center",
        fontsize=9,
        fontweight="bold",
        transform=ccrs.PlateCarree(),
        zorder=7,
    )

    axis.set_title(
        "StratoLink current RF geofence — executed from region_manager.cpp\n"
        "Flight-3 fresh-fix replay: 31 US915 → 8 EU868; unsupported or mixed-plan land fails silent",
        fontsize=14,
        fontweight="bold",
        color="#26313d",
        pad=14,
    )
    legend = [
        Patch(facecolor=COLORS[name], alpha=0.55, label=name)
        for name in ORDER
    ]
    legend.extend(
        [
            Line2D(
                [0], [0], marker="o", color="none", markerfacecolor=COLORS["US915"],
                markeredgecolor="white", markersize=7, label="historical fresh US fix"
            ),
            Line2D(
                [0], [0], marker="o", color="none", markerfacecolor=COLORS["EU868"],
                markeredgecolor="white", markersize=7, label="historical fresh EU fix"
            ),
        ]
    )
    axis.legend(handles=legend, loc="lower left", ncol=2, fontsize=8.5)

    source = ROOT / "firmware/src/region_manager.cpp"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    figure.text(
        0.995,
        0.012,
        f"Current C++ executed at render time · source SHA-256 {digest}… · "
        "39 fresh fixes only; stale/NOGPS/garbage excluded",
        ha="right",
        fontsize=8,
        color="#5e6874",
    )
    figure.savefig(
        HERE / "stratolink2_current_geofence_replay.png",
        dpi=170,
        bbox_inches="tight",
    )
    print("wrote stratolink2_current_geofence_replay.png")


if __name__ == "__main__":
    main()
