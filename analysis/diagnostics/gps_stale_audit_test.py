#!/usr/bin/env python3
"""Regression: historical plots must not invent lines through data outages."""

from __future__ import annotations

import math

import pandas as pd

from gps_stale_audit import gap_broken_series


def main() -> None:
    times = pd.Series(pd.to_datetime([
        "2026-05-17T00:00:00Z",
        "2026-05-17T00:05:00Z",
        "2026-05-19T00:00:00Z",
        "2026-05-19T00:05:00Z",
    ], utc=True))
    values = pd.Series([1.0, 2.0, 100.0, 101.0])
    plot_times, plot_values = gap_broken_series(times, values)

    assert len(plot_times) == len(plot_values) == 5
    assert plot_times[2] == times.iloc[2]
    assert math.isnan(plot_values[2])
    assert plot_values[:2] == [1.0, 2.0]
    assert plot_values[3:] == [100.0, 101.0]

    print("PASS: GPS history traces break rather than interpolate across outages")


if __name__ == "__main__":
    main()
