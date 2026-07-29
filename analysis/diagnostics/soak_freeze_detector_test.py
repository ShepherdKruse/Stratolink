#!/usr/bin/env python3
"""Pin honest repeated-GPS-tuple classification semantics."""

from __future__ import annotations

from soak_freeze_detector import classify


def row(
    lat: float | None,
    lon: float | None,
    *,
    altitude: int = 100,
    satellites: int = 7,
) -> dict:
    return {
        "lat": lat,
        "lon": lon,
        "altitude_m": altitude,
        "gps_satellites": satellites,
        "gps_speed": 0,
        "gps_heading": 0,
    }


def main() -> None:
    values = [
        row(None, None),
        row(47.5, -122.3),
        row(47.5, -122.3),
        row(47.500002, -122.3),
        row(91, 0),
    ]
    labels = [label for _, label in classify(values)]
    assert labels == ["NOGPS", "CHANGED", "REPEAT", "CHANGED", "GARBAGE"]
    print("PASS: repeated coordinates are suspect only, never freshness proof")


if __name__ == "__main__":
    main()
