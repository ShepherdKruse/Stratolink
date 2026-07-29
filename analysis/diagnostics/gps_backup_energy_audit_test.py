#!/usr/bin/env python3
"""Regression checks for the GNSS backup energy source-bound model."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


SCRIPT = Path(__file__).with_name("gps_backup_energy_audit.py")
SPEC = importlib.util.spec_from_file_location("gps_backup_energy_audit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> None:
    audit = MODULE.build_audit()
    assert audit["timing_bound_ms"] == {
        "confirmation_attempt": 2360,
        "hardware_reset_and_reconfigure": 4880,
        "full_three_attempt_two_reset_path": 16840,
        "low_rail_path_before_reset_suppression": 2360,
    }
    assert all(audit["gates"].values())
    energy = audit["energy_model"]
    assert energy["capacitance_f"] == 0.8
    assert energy["acquisition_floor_v"] == 3.6
    assert energy["reset_floor_v"] == 4.4
    assert energy["acquisition_floor_reserve_j"] == 0.77504
    assert energy["reset_floor_reserve_j"] == 3.33504
    assert 2.61 < energy["full_recovery_j"] < 2.62
    assert 0.719 < energy["reset_floor_margin_j"] < 0.721
    assert energy["reset_floor_margin_percent_of_recovery"] > 27.0
    assert energy["terminal_retry_sleep_s"] == 5.0
    assert 0.58 < energy["terminal_retry_sleep_with_awake_gnss_j"] < 0.59
    assert 0.94 < energy["terminal_retry_epoch_j"] < 0.96
    assert energy["terminal_retry_epoch_exceeds_acquisition_reserve"] is True

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "audit.json"
        MODULE.write_create_once(output, b"first\n")
        assert output.read_bytes() == b"first\n"
        try:
            MODULE.write_create_once(output, b"second\n")
        except SystemExit:
            pass
        else:
            raise AssertionError("evidence overwrite was not rejected")
        assert output.read_bytes() == b"first\n"

    print("PASS: GNSS backup energy bound and create-once evidence")


if __name__ == "__main__":
    main()
