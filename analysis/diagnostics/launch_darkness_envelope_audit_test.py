#!/usr/bin/env python3
"""Regression checks for prospective launch-season darkness envelopes."""

from __future__ import annotations

from datetime import date

from launch_darkness_envelope_audit import geometric_nights, first_exceedance


def main() -> None:
    nights = geometric_nights(
        date(2026, 7, 31), 90, 45.995252, 10040.999
    )
    assert len(nights) == 90
    assert float(nights[-1]["hours"]) > float(nights[0]["hours"])
    assert max(float(row["hours"]) for row in nights[:30]) > float(
        nights[0]["hours"]
    )
    assert first_exceedance(nights, 8.0) is not None
    assert first_exceedance(nights, 24.0) is None

    for bad_days in (0, 367):
        try:
            geometric_nights(
                date(2026, 7, 31), bad_days, 45.995252, 10040.999
            )
        except ValueError:
            pass
        else:
            raise AssertionError("invalid mission duration must fail closed")

    print("PASS: planned-launch darkness growth and exceedance gates")


if __name__ == "__main__":
    main()
