#!/usr/bin/env python3
"""Validate one post-reset precursor telemetry row without overclaiming it."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


US915_FREQUENCIES_HZ = set(range(903_900_000, 905_300_001, 200_000))


def evaluate(rows: list[dict[str, object]]) -> dict[str, object]:
    failures: list[str] = []
    if len(rows) != 1:
        failures.append("expected exactly one post-transition row")
        row: dict[str, object] = rows[0] if rows else {}
    else:
        row = rows[0]

    def number(key: str) -> float:
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            failures.append(f"{key} is not numeric")
            return float("nan")
        return float(value)

    temperature = number("temperature")
    pressure = number("pressure")
    solar = number("solar_voltage")
    battery = number("battery_voltage")
    ax = number("mems_accel_x")
    ay = number("mems_accel_y")
    az = number("mems_accel_z")
    magnitude = math.sqrt(ax * ax + ay * ay + az * az)

    if row.get("device_id") != "stratolink-2":
        failures.append("unexpected device")
    if not 10.0 <= temperature <= 40.0:
        failures.append("temperature is not room-plausible")
    if not 900.0 <= pressure <= 1100.0:
        failures.append("pressure is not room-plausible")
    if not 0.0 <= solar <= 0.05:
        failures.append("solar input is not shaded")
    if not 4.56 <= battery <= 4.66:
        failures.append("VSTOR is outside the supported-source screen")
    if not 8.5 <= magnitude <= 11.2:
        failures.append("acceleration magnitude is not stationary-plausible")

    nofix = {
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "altitude_m": row.get("altitude_m"),
        "gps_satellites": row.get("gps_satellites"),
        "gps_speed": row.get("gps_speed"),
        "gps_heading": row.get("gps_heading"),
    }
    if nofix != {
        "lat": None,
        "lon": None,
        "altitude_m": None,
        "gps_satellites": 0,
        "gps_speed": 0,
        "gps_heading": 0,
    }:
        failures.append("GPS no-fix fields are not atomic")
    if row.get("ambient_lux") not in (0, 1, 2, 3, 4, 5):
        failures.append("ambient light is not shaded")
    if row.get("uv_index") != 0:
        failures.append("UV is not zero under cover")
    if row.get("lora_sf") != 9 or row.get("lora_bw") != 125000:
        failures.append("LoRa data rate is not SF9/BW125")
    if row.get("frequency_hz") not in US915_FREQUENCIES_HZ:
        failures.append("frequency is outside the expected US915 channel set")

    return {
        "passed": not failures,
        "failures": failures,
        "time": row.get("time"),
        "atomic_nogps": "GPS no-fix fields are not atomic" not in failures,
        "room_sensor_plausibility": all(
            item not in failures for item in (
                "temperature is not room-plausible",
                "pressure is not room-plausible",
                "acceleration magnitude is not stationary-plausible",
            )
        ),
        "shaded_inputs": all(
            item not in failures for item in (
                "solar input is not shaded",
                "ambient light is not shaded",
                "UV is not zero under cover",
            )
        ),
        "vstor_v": round(battery, 3),
        "temperature_c": round(temperature, 3),
        "pressure_hpa": round(pressure, 3),
        "acceleration_magnitude_ms2": round(magnitude, 6),
        "radio": {
            "sf": row.get("lora_sf"),
            "bandwidth_hz": row.get("lora_bw"),
            "frequency_hz": row.get("frequency_hz"),
            "rssi_dbm": row.get("rssi"),
            "snr_db": row.get("snr"),
        },
        "scope": (
            "one precursor telemetry row after a power-gap reset; proves atomic "
            "no-fix serialization and room/shaded plausibility only, not sensor "
            "calibration, clear-sky GNSS, flight environment, final candidate, "
            "or power continuity"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    raw = args.input.read_bytes()
    rows = json.loads(raw)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SystemExit("input must be a JSON array of objects")
    report = evaluate(rows)
    report["provenance"] = {
        "path": str(args.input),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "append_allowed": False,
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if not report["passed"]:
        print(payload, end="")
        raise SystemExit("refusing to create non-passing telemetry evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    print(json.dumps({"output": str(args.output), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
