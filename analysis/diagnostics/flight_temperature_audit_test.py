#!/usr/bin/env python3
"""Regression checks for the historical flight-temperature audit."""

from __future__ import annotations

import csv
from pathlib import Path
import tempfile

import flight_temperature_audit as temperature


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-temperature-audit-") as raw:
        directory = Path(raw)
        bom = directory / "bom.csv"
        telemetry = directory / "telemetry.csv"
        bom_rows = []
        for component in temperature.COMPONENTS:
            row = {
                "Comment": "fixture",
                "Designator": component["designator"],
                "Footprint": "fixture",
                "LCSC": "",
            }
            row.update(component["bom"])
            bom_rows.append(row)
        write_csv(
            bom,
            ["Comment", "Designator", "Footprint", "LCSC"],
            bom_rows,
        )
        fields = [
            "time", "temperature", "pressure", "solar_voltage",
            "battery_voltage", "ambient_lux", "region", "frequency_hz",
            "rssi", "snr",
        ]
        write_csv(
            telemetry,
            fields,
            [
                {"time": "2026-05-17T13:59:59+00:00", "temperature": "-99"},
                {"time": "2026-05-17T14:00:00+00:00", "temperature": "-20"},
                {
                    "time": "2026-05-18T00:00:00+00:00",
                    "temperature": "-42.1",
                    "pressure": "275.9",
                    "solar_voltage": "1.426",
                    "battery_voltage": "3.322",
                    "ambient_lux": "81",
                    "region": "US",
                    "frequency_hz": "905300000.0",
                    "rssi": "-118",
                    "snr": "-1",
                },
                {"time": "", "temperature": "-80"},
                {"time": "2026-05-18T00:05:00+00:00", "temperature": ""},
            ],
        )
        report = temperature.audit(telemetry, bom)

    assert report["status"] == "OUT_OF_SPEC_HIL_REQUIRED"
    assert report["post_launch_temperature_rows"] == 2
    assert report["observed_min_c"] == -42.1
    assert report["counts_at_or_below_c"] == {"-20": 2, "-30": 1, "-40": 1}
    coldest = report["coldest_received_uplink"]
    assert coldest["time"] == "2026-05-18T00:00:00+00:00"
    assert coldest["temperature_c"] == -42.1
    assert coldest["vstor_v"] == 3.322
    assert coldest["solar_v"] == 1.426
    power = report["cold_power_context"]
    assert power["flight_reported_vstor_plateau_v"] == 3.32
    assert power["coldest_row_margin_above_reported_plateau_v"] == 0.002
    assert power["at_or_below_minus_40_vstor_v"] == {
        "min": 3.322,
        "max": 3.322,
    }
    screen = report["critical_component_screen"]
    assert screen["screened_count"] == len(temperature.COMPONENTS) == 9
    assert screen["outside_reported_board_envelope_count"] == 8
    assert screen["outside_reported_board_envelope"] == [
        "U2", "U3", "U4", "U6", "U7", "U1", "MK1", "C5"
    ]
    by_designator = {
        component["designator"]: component for component in screen["components"]
    }
    assert by_designator["U2"]["part"] == "RAK3172-9-SM-NI"
    assert by_designator["U2"]["reported_board_min_margin_c"] == -22.1
    assert by_designator["U5"]["reported_board_min_margin_c"] == 12.9
    assert by_designator["C5"]["current_bench_fitted"] is False
    assert report["skipped_rows_missing_time"] == 1
    assert report["skipped_post_launch_missing_temperature"] == 1
    print("PASS: flight-temperature audit is source-bound and fail-closed")


if __name__ == "__main__":
    main()
