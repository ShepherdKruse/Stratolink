#!/usr/bin/env python3
"""Regression-test separation of PPK2 preservation from soak acceptance."""

from ppk2_power_rescue import rescue_required


def main() -> None:
    good = {
        "event": "ppk2_power_hold_end",
        "held_seconds": 57600.16,
        "source_mv": 4660,
        "reconnects": 0,
    }
    assert not rescue_required(
        good, source_mv=4660, min_held_seconds=57600
    )
    assert rescue_required(
        {**good, "held_seconds": 57599.999},
        source_mv=4660,
        min_held_seconds=57600,
    )
    assert rescue_required(
        {**good, "source_mv": 4659},
        source_mv=4660,
        min_held_seconds=57600,
    )
    assert rescue_required(
        {**good, "reconnects": 1},
        source_mv=4660,
        min_held_seconds=57600,
    )
    print("PASS: failed qualification triggers rescue while valid handoff stays single-writer")


if __name__ == "__main__":
    main()
