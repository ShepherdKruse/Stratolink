#!/usr/bin/env python3
"""Replay Flight-3 fresh fixes through the current compiled region manager."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

from compiled_region import REGION_NAMES, compiled_regions


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ANTENNA = ROOT / "analysis/antenna"
TELEMETRY = ANTENNA / "data/telemetry_raw.csv"

sys.path.insert(0, str(ANTENNA))
from _gps import classify_uplinks  # noqa: E402


def main() -> None:
    telemetry = pd.read_csv(TELEMETRY)
    telemetry["time"] = pd.to_datetime(telemetry["time"], utc=True)
    classified = classify_uplinks(telemetry)
    fresh = classified[classified["gps_class"] == "FRESH"].copy()
    assert len(fresh) == 39, "immutable Flight-3 fresh-fix count changed"

    pairs = [
        (round(float(row.lat) * 10_000_000), round(float(row.lon) * 10_000_000))
        for row in fresh.itertuples()
    ]
    region_ids = compiled_regions(pairs)
    assert len(region_ids) == len(fresh)
    names = [REGION_NAMES[value] for value in region_ids]
    assert names == ["US915"] * 31 + ["EU868"] * 8, names
    assert all(name != "SILENT" for name in names)

    # The final row returned through the NA application despite being over
    # southern Spain. Its coordinate, not its backend stream label, must own
    # the RF decision.
    final = fresh.iloc[-1]
    assert final["region"] == "US"
    assert names[-1] == "EU868"

    print(
        "PASS: all 39 historically fresh Flight-3 fixes replay through the "
        "current compiled geofence as 31 US915 then 8 EU868 fixes"
    )


if __name__ == "__main__":
    main()
