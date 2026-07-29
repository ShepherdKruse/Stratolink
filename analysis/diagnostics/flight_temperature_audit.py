#!/usr/bin/env python3
"""Audit StratoLink-3's observed cold envelope against critical BOM ratings.

This is intentionally a qualification gate, not a reliability claim. Received
uplinks prove that one assembly operated at the reported temperature; they do
not qualify oscillator start-up, radio margin, reset/rejoin behavior, sensors,
or the energy store across the same envelope.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_TELEMETRY = HERE.parent / "antenna" / "data" / "telemetry_raw.csv"
DEFAULT_BOM = HERE.parent.parent / "hardware" / "gerbers" / "production_files" / "BOM-stratolink.csv"
LAUNCH_UTC = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
THRESHOLDS_C = (-20.0, -30.0, -40.0)
FLIGHT_REPORTED_PLATEAU_V = 3.32

# Ratings and identities are pinned to primary manufacturer documentation.
# This is a flight-critical active/storage screen, not a claim that every
# passive, connector, solder joint, solar cell, or adhesive is qualified.
COMPONENTS = (
    {
        "designator": "U2",
        "bom": {"LCSC": "C18548052"},
        "part": "RAK3172-9-SM-NI",
        "role": "MCU and LoRa radio module",
        "rated_min_c": -20.0,
        "rated_max_c": 85.0,
        "current_bench_fitted": True,
        "source_url": "https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/",
    },
    {
        "designator": "U3",
        "bom": {"LCSC": "C4153167"},
        "part": "MAX-M10S-00B",
        "role": "GNSS module",
        "rated_min_c": -40.0,
        "rated_max_c": 85.0,
        "current_bench_fitted": True,
        "source_url": "https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf",
    },
    {
        "designator": "U4",
        "bom": {"LCSC": "C15639"},
        "part": "MS561101BA03-50",
        "role": "barometer and fallback temperature",
        "rated_min_c": -40.0,
        "rated_max_c": 85.0,
        "current_bench_fitted": True,
        "source_url": "https://www.te.com/en/product-MS561101BA03-50.html",
    },
    {
        "designator": "U5",
        "bom": {"LCSC": "C2871893"},
        "part": "TMP117NAIYBGR",
        "role": "temperature sensor",
        "rated_min_c": -55.0,
        "rated_max_c": 150.0,
        "current_bench_fitted": True,
        "source_url": "https://www.ti.com/lit/ds/symlink/tmp117.pdf",
    },
    {
        "designator": "U6",
        "bom": {"LCSC": "C492374"},
        "part": "LTR-390UV-01",
        "role": "UV and ambient-light sensor",
        "rated_min_c": -40.0,
        "rated_max_c": 85.0,
        "current_bench_fitted": True,
        "source_url": "https://optoelectronics.liteon.com/upload/download/DS86-2015-0004/LTR-390UV_Final_%20DS_V1%201.pdf",
    },
    {
        "designator": "U7",
        "bom": {"LCSC": "C110926"},
        "part": "LIS2DH12TR",
        "role": "accelerometer and freefall wake",
        "rated_min_c": -40.0,
        "rated_max_c": 85.0,
        "current_bench_fitted": True,
        "source_url": "https://www.st.com/en/mems-and-sensors/lis2dh12.html",
    },
    {
        "designator": "U1",
        "bom": {"LCSC": "C506250"},
        "part": "BQ25570RGRR",
        "role": "energy harvester and buck converter",
        "rated_min_c": -40.0,
        "rated_max_c": 125.0,
        "current_bench_fitted": True,
        "source_url": "https://www.ti.com/product/BQ25570",
    },
    {
        "designator": "MK1",
        "bom": {"LCSC": "C3171752"},
        "part": "T3902",
        "role": "PDM microphone",
        "rated_min_c": -40.0,
        "rated_max_c": 85.0,
        "current_bench_fitted": True,
        "source_url": "https://invensense.tdk.com/wp-content/uploads/2020/05/DS-000357-T3902-v1.0.pdf",
    },
    {
        "designator": "C5",
        "bom": {
            "Comment": "1F",
            "Footprint": "DMF4B5R5G105M3DTA0",
        },
        "part": "DMF4B5R5G105M3DTA0",
        "role": "flight supercapacitor",
        "rated_min_c": -40.0,
        "rated_max_c": 70.0,
        "current_bench_fitted": False,
        "source_url": "https://www.murata.com/products/productdata/8796857237534/MFCDSF2E.pdf",
    },
)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"telemetry time lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


def verify_component_bom(path: Path) -> None:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    def bom_value(row: dict[str, str], field: str) -> str | None:
        if field == "LCSC":
            return row.get("LCSC") or row.get("LCSC Part #")
        return row.get(field)

    for component in COMPONENTS:
        expected = component["bom"]
        matches = [
            row for row in rows
            if row.get("Designator") == component["designator"]
            and all(
                bom_value(row, field) == value
                for field, value in expected.items()
            )
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"expected exactly one BOM row for {component['designator']} "
                f"{component['part']} with {expected}; found {len(matches)}"
            )


def audit(telemetry_path: Path, bom_path: Path) -> dict[str, object]:
    verify_component_bom(bom_path)
    records: list[dict[str, object]] = []

    def optional_float(row: dict[str, str], field: str) -> float | None:
        return float(row[field]) if row.get(field) else None

    missing_time = 0
    missing_temperature = 0
    with telemetry_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not row.get("time"):
                missing_time += 1
                continue
            timestamp = parse_time(row["time"])
            if timestamp < LAUNCH_UTC:
                continue
            if not row.get("temperature"):
                missing_temperature += 1
                continue
            records.append(
                {
                    "time": timestamp.isoformat(),
                    "temperature_c": float(row["temperature"]),
                    "region": row.get("region") or None,
                    "frequency_hz": (
                        int(float(row["frequency_hz"]))
                        if row.get("frequency_hz") else None
                    ),
                    "pressure_hpa": optional_float(row, "pressure"),
                    "solar_v": optional_float(row, "solar_voltage"),
                    "vstor_v": optional_float(row, "battery_voltage"),
                    "ambient_lux": optional_float(row, "ambient_lux"),
                    "rssi_dbm": optional_float(row, "rssi"),
                    "snr_db": optional_float(row, "snr"),
                }
            )
    if not records:
        raise SystemExit("no post-launch telemetry temperatures found")

    coldest = min(records, key=lambda record: float(record["temperature_c"]))
    observed_min = float(coldest["temperature_c"])
    component_screen = []
    for component in COMPONENTS:
        minimum = float(component["rated_min_c"])
        item = {
            key: value for key, value in component.items() if key != "bom"
        }
        item["reported_board_min_margin_c"] = round(observed_min - minimum, 1)
        item["reported_board_envelope_within_rating"] = observed_min >= minimum
        component_screen.append(item)
    outside = [
        component for component in component_screen
        if not component["reported_board_envelope_within_rating"]
    ]
    deepest_cold = [
        record for record in records if float(record["temperature_c"]) <= -40.0
    ]
    deepest_cold_vstor = [
        float(record["vstor_v"])
        for record in deepest_cold
        if record["vstor_v"] is not None
    ]
    coldest_vstor = coldest["vstor_v"]
    return {
        "status": (
            "OUT_OF_SPEC_HIL_REQUIRED"
            if outside
            else "WITHIN_SCREENED_COMPONENT_RATINGS"
        ),
        "source": str(telemetry_path),
        "launch_utc": LAUNCH_UTC.isoformat(),
        "post_launch_temperature_rows": len(records),
        "skipped_post_launch_missing_temperature": missing_temperature,
        "skipped_rows_missing_time": missing_time,
        "observed_min_c": observed_min,
        "counts_at_or_below_c": {
            f"{threshold:g}": sum(
                float(record["temperature_c"]) <= threshold for record in records
            )
            for threshold in THRESHOLDS_C
        },
        "coldest_received_uplink": coldest,
        "cold_power_context": {
            "flight_reported_vstor_plateau_v": FLIGHT_REPORTED_PLATEAU_V,
            "coldest_row_vstor_v": coldest_vstor,
            "coldest_row_margin_above_reported_plateau_v": (
                round(float(coldest_vstor) - FLIGHT_REPORTED_PLATEAU_V, 3)
                if coldest_vstor is not None else None
            ),
            "at_or_below_minus_40_vstor_v": {
                "min": min(deepest_cold_vstor),
                "max": max(deepest_cold_vstor),
            } if deepest_cold_vstor else None,
            "interpretation": (
                "The coldest received row was also almost at the historical "
                "reported 3.32 V plateau. The flown fixed-VDDA ADC could not "
                "measure actual VSTOR in buck dropout, so this is neither a "
                "brownout threshold nor proof that cold caused the low-energy "
                "episode; cold ESR/capacitance and load-step margin require HIL."
            ),
        },
        "critical_component_screen": {
            "scope": (
                "critical active modules/sensors/power IC and planned flight "
                "supercapacitor; not every material or passive"
            ),
            "components": component_screen,
            "screened_count": len(component_screen),
            "outside_reported_board_envelope_count": len(outside),
            "outside_reported_board_envelope": [
                component["designator"] for component in outside
            ],
        },
        "qualification_interpretation": (
            "The telemetry temperature is a board reading, not proof that "
            "every component reached the same temperature. Received cold "
            "uplinks are out-of-spec operating evidence only; qualify the "
            "exact frozen, supercap-equipped assembly across the observed "
            "envelope before launch."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    args = parser.parse_args()
    print(json.dumps(audit(args.telemetry, args.bom), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
