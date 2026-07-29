#!/usr/bin/env python3
"""Regression checks for Flight-3 solar-horizon darkness modeling."""

from __future__ import annotations

from datetime import datetime, timezone
import math

import numpy as np

from flight3_darkness_audit import (
    dark_intervals,
    horizon_dip_deg,
    solar_elevation_deg,
)


def unix(year: int, month: int, day: int, hour: int) -> float:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp()


def main() -> None:
    # Equinox/noon at the equator and Greenwich must be close to zenith, while
    # midnight is deeply dark.  The compact solar oracle is intentionally
    # screened with tolerant physical bounds rather than circular exact values.
    times = np.asarray([unix(2026, 3, 20, 12), unix(2026, 3, 20, 0)])
    elevation = solar_elevation_deg(times, np.zeros(2), np.zeros(2))
    assert elevation[0] > 88.0
    assert elevation[1] < -88.0

    dip = horizon_dip_deg(np.asarray([0.0, 10_000.0]))
    assert dip[0] == 0.0
    assert 3.1 < dip[1] < 3.3

    # Two linearly interpolated crossings around a four-hour dark plateau.
    t = np.asarray([0.0, 3600.0, 5 * 3600.0, 6 * 3600.0])
    margin = np.asarray([1.0, -1.0, -1.0, 1.0])
    intervals = dark_intervals(t, margin)
    assert len(intervals) == 1
    assert math.isclose(intervals[0][0], 1800.0)
    assert math.isclose(intervals[0][1], 5.5 * 3600.0)

    try:
        dark_intervals(np.asarray([0.0, 0.0]), np.asarray([-1.0, 1.0]))
    except ValueError:
        pass
    else:
        raise AssertionError("non-increasing time must fail closed")

    print("PASS: Flight-3 geometric-darkness oracle and crossings")


if __name__ == "__main__":
    main()
