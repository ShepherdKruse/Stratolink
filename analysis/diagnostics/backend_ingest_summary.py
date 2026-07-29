#!/usr/bin/env python3
"""Prove one-to-one TTN -> Supabase ingestion for the StratoLink-2 soak.

The TTN monitor JSONL is the upstream record.  The cached Supabase JSON export
is the downstream record. Rows are paired one-to-one by nearest timestamp and
every decoded payload/link field is compared, not merely row counts.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any


DEFAULT_TTN = Path(
    "analysis/diagnostics/logs/stratolink2_soak_20260724_ttn.jsonl"
)
DEFAULT_SUPABASE = Path(
    "analysis/diagnostics/logs/stratolink2_soak_20260724_supabase.json"
)


def timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_ttn(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "ttn_uplink" and event.get("device_id") == "stratolink-2":
            rows.append(event)
    return rows


def load_supabase(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Supabase export must be a JSON array")
    return value


def expected_from_ttn(row: dict[str, Any]) -> dict[str, Any]:
    telemetry = row["telemetry"]
    has_fix = telemetry["satellites"] >= 4
    def scaled(field: str, divisor: float) -> float | None:
        value = telemetry[field]
        return None if value is None else value / divisor

    return {
        "device_id": "stratolink-2",
        "lat": telemetry["lat_e7"] / 1e7 if has_fix else None,
        "lon": telemetry["lon_e7"] / 1e7 if has_fix else None,
        "altitude_m": telemetry["altitude_m"] if has_fix else None,
        "temperature": scaled("temperature_deci_c", 10),
        "pressure": scaled("pressure_deci_hpa", 10),
        "solar_voltage": telemetry["solar_mv"] / 1000,
        "battery_voltage": telemetry["vstor_mv"] / 1000,
        "rssi": row["rssi_dbm"],
        "snr": row["snr_db"],
        "gps_speed": telemetry["speed_cm_s"] / 100,
        "gps_heading": telemetry["heading_cdeg"] / 100,
        "gps_satellites": telemetry["satellites"],
        "mems_accel_x": scaled("accel_x_cms2", 100),
        "mems_accel_y": scaled("accel_y_cms2", 100),
        "mems_accel_z": scaled("accel_z_cms2", 100),
        "uv_index": telemetry["uv_index"],
        "ambient_lux": telemetry["ambient_lux"],
        "acoustic_event": telemetry["acoustic_event"],
        "lora_sf": row["spreading_factor"],
        "lora_bw": row["bandwidth_hz"],
        "frequency_hz": int(row["frequency_hz"]),
    }


def equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-9
    return left == right


def summarize(ttn: list[dict[str, Any]], supabase: list[dict[str, Any]]) -> dict[str, Any]:
    unused = set(range(len(supabase)))
    pairs: list[tuple[dict[str, Any], dict[str, Any], float]] = []
    unmatched_ttn: list[int] = []

    for upstream in ttn:
        upstream_time = timestamp(upstream["received_at"])
        candidates = [
            (abs(timestamp(supabase[index]["time"]) - upstream_time), index)
            for index in unused
        ]
        if not candidates:
            unmatched_ttn.append(upstream["f_cnt"])
            continue
        delta, index = min(candidates)
        if delta > 5:
            unmatched_ttn.append(upstream["f_cnt"])
            continue
        unused.remove(index)
        pairs.append((upstream, supabase[index], delta))

    differences: list[dict[str, Any]] = []
    for upstream, downstream, _delta in pairs:
        for field, expected in expected_from_ttn(upstream).items():
            actual = downstream.get(field)
            if not equal(expected, actual):
                differences.append(
                    {
                        "f_cnt": upstream["f_cnt"],
                        "field": field,
                        "expected": expected,
                        "actual": actual,
                    }
                )

    deltas = [pair[2] for pair in pairs]
    return {
        "ttn_rows": len(ttn),
        "supabase_rows": len(supabase),
        "matched_rows": len(pairs),
        "unmatched_ttn_fcnt": unmatched_ttn,
        "unmatched_supabase_times": [supabase[index]["time"] for index in sorted(unused)],
        "field_differences": differences,
        "timestamp_delta_seconds": {
            "min": min(deltas) if deltas else None,
            "mean": sum(deltas) / len(deltas) if deltas else None,
            "max": max(deltas) if deltas else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ttn", type=Path, default=DEFAULT_TTN)
    parser.add_argument("--supabase", type=Path, default=DEFAULT_SUPABASE)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()

    report = summarize(load_ttn(args.ttn), load_supabase(args.supabase))
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.final:
        failures: list[str] = []
        if report["ttn_rows"] != report["supabase_rows"]:
            failures.append("upstream/downstream row counts differ")
        if report["matched_rows"] != report["ttn_rows"]:
            failures.append("not every TTN row has exactly one downstream row")
        if report["unmatched_ttn_fcnt"]:
            failures.append("TTN rows are missing downstream")
        if report["unmatched_supabase_times"]:
            failures.append("unexpected downstream-only rows exist")
        if report["field_differences"]:
            failures.append("decoded payload/link fields differ")
        maximum = report["timestamp_delta_seconds"]["max"]
        if maximum is None or maximum > 5:
            failures.append("webhook delivery timestamp delta exceeds 5 seconds")
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            raise SystemExit(1)
        print("PASS: every TTN soak uplink is stored once with exact decoded fields")


if __name__ == "__main__":
    main()
