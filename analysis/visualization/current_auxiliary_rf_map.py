#!/usr/bin/env python3
"""Render shared Meshtastic/B2B TX eligibility from current compiled policy."""

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
from auxiliary_rf_region_policy_test import source_mapping  # noqa: E402
from compiled_region import REGION_NAMES, compiled_regions  # noqa: E402


CATEGORY = {
    "US915": 0,
    "EU868": 1,
    "AU915": 2,
    "AS923": 3,
    "SILENT": 4,
}
COLORS = ["#2f76b7", "#399267", "#8065a8", "#d9b85f", "#b6bec8"]


def main() -> None:
    mapping = source_mapping()
    assert mapping == {
        "US915": 906.875,
        "EU868": 869.525,
        "AS923": 0.0,
        "AU915": 919.875,
    }

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
    names = np.vectorize(REGION_NAMES.__getitem__)(region_ids)
    indexed = np.vectorize(CATEGORY.__getitem__)(names)

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
        cmap=ListedColormap(COLORS),
        alpha=0.45,
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

    for region, color in (("US915", COLORS[0]), ("EU868", COLORS[1])):
        subset = fresh[np.array(historical_names) == region]
        axis.scatter(
            subset["lon"],
            subset["lat"],
            s=26,
            color=color,
            edgecolor="white",
            linewidth=0.6,
            transform=ccrs.PlateCarree(),
            zorder=5,
        )

    axis.set_title(
        "StratoLink shared LongFast auxiliary-TX eligibility — current flight source\n"
        "Meshtastic relay + authenticated balloon mesh share this gate; AS923 intentionally has LoRaWAN only",
        fontsize=14,
        fontweight="bold",
        color="#26313d",
        pad=14,
    )
    legend = [
        Patch(facecolor=COLORS[0], alpha=0.6, label="US915 · 906.875 MHz"),
        Patch(facecolor=COLORS[1], alpha=0.6, label="EU868 · 869.525 MHz"),
        Patch(facecolor=COLORS[2], alpha=0.6, label="AU915 · 919.875 MHz"),
        Patch(
            facecolor=COLORS[3],
            alpha=0.6,
            label="AS923 · LoRaWAN supported; auxiliary TX disabled",
        ),
        Patch(facecolor=COLORS[4], alpha=0.6, label="SILENT · all TX disabled"),
        Line2D(
            [0], [0], marker="o", color="none", markerfacecolor="#26313d",
            markeredgecolor="white", markersize=7,
            label="Flight-3 fresh-fix replay (31 US → 8 EU)",
        ),
    ]
    axis.legend(handles=legend, loc="lower left", ncol=2, fontsize=8.5)

    region_source = ROOT / "firmware/src/region_manager.cpp"
    lora_source = ROOT / "firmware/src/lorawan.cpp"
    region_digest = hashlib.sha256(region_source.read_bytes()).hexdigest()[:12]
    lora_digest = hashlib.sha256(lora_source.read_bytes()).hexdigest()[:12]
    figure.text(
        0.995,
        0.012,
        "Geofence C++ executed; LongFast mapping parsed from lorawan.cpp · "
        f"region {region_digest}… / radio {lora_digest}… · "
        "434 MHz CTT listening is receive-only and separate",
        ha="right",
        fontsize=8,
        color="#5e6874",
    )
    output = HERE / "stratolink2_current_auxiliary_rf_eligibility.png"
    figure.savefig(output, dpi=170, bbox_inches="tight")
    print(f"wrote {output.name}")


if __name__ == "__main__":
    main()
