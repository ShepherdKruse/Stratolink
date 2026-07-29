#!/usr/bin/env python3
"""Regression vectors for the unquiesced-radio energy screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "radio_sleep_fault_energy_audit.py"
SPEC = importlib.util.spec_from_file_location("radio_sleep_fault_energy_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> None:
    assert abs(MODULE.usable_cap_energy_j(0.8, 4.66, 3.32) - 4.27728) < 1e-9
    assert abs(MODULE.usable_cap_energy_j(1.0, 4.66, 3.32) - 5.3466) < 1e-9
    assert abs(MODULE.unquiesced_energy_j(1200) - 2.795294117647059) < 1e-9

    report = MODULE.build_report()
    assert report["source_gate"]["contained"] is True
    full = report["sleep_intervals"]["SLEEP_INTERVAL_FULL_SEC"]
    reduced = report["sleep_intervals"]["SLEEP_INTERVAL_REDUCED_SEC"]
    assert full["seconds"] == 1200
    assert reduced["seconds"] == 1800
    assert full["fraction_minimum_cap_reserve"] > 0.65
    assert reduced["fraction_minimum_cap_reserve"] > 0.98
    print("PASS: unquiesced-radio reserve exposure is source-bound and quantified")


if __name__ == "__main__":
    main()
