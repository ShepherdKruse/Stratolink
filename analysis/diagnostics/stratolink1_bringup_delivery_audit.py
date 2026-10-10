#!/usr/bin/env python3
"""Bind one Board1 MQTT uplink to TTN Storage and production Supabase."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from ttn_storage_replay import parse_timestamp


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-9)
    return left == right


def evaluate(
    events: list[dict[str, object]],
    storage: dict[str, object],
    rows: list[dict[str, object]],
    *,
    device_id: str,
    after: str,
    until: str,
    expected_f_cnt: int = 0,
    expected_command_ack: int | None = None,
) -> dict[str, object]:
    lower = parse_timestamp(after)
    upper = parse_timestamp(until)
    failures: list[str] = []

    uplinks = []
    for event in events:
        received_at = event.get("received_at")
        if (
            event.get("event") == "ttn_uplink"
            and event.get("device_id") == device_id
            and isinstance(received_at, str)
            and lower < parse_timestamp(received_at) <= upper
        ):
            uplinks.append(event)
    if len(uplinks) != 1:
        failures.append(f"expected exactly one MQTT uplink, found {len(uplinks)}")
    uplink = uplinks[0] if uplinks else {}

    if storage.get("passed") is not True or storage.get("selected_rows") != 1:
        failures.append("TTN Storage did not prove exactly one selected row")
    if len(rows) != 1:
        failures.append(f"expected exactly one Supabase row, found {len(rows)}")
    row = rows[0] if rows else {}

    if uplink.get("f_port") != 1 or uplink.get("f_cnt") != expected_f_cnt:
        failures.append(
            f"MQTT uplink is not fPort 1 / FCnt {expected_f_cnt}"
        )
    if uplink.get("payload_len") != 40:
        failures.append("MQTT payload is not the 40-byte telemetry contract")
    if storage.get("first_f_cnt") != uplink.get("f_cnt"):
        failures.append("TTN Storage FCnt does not match MQTT")
    if row.get("device_id") != device_id:
        failures.append("Supabase device ID does not match MQTT")

    mqtt_received = uplink.get("received_at")
    storage_received = storage.get("first_received_at")
    database_time = row.get("time")
    delivery_latency_seconds: float | None = None
    storage_database_delta_seconds: float | None = None
    if all(isinstance(value, str) for value in (
        mqtt_received, storage_received, database_time
    )):
        mqtt_time = parse_timestamp(mqtt_received)
        storage_time = parse_timestamp(storage_received)
        db_time = parse_timestamp(database_time)
        delivery_latency_seconds = (storage_time - mqtt_time).total_seconds()
        storage_database_delta_seconds = abs((db_time - storage_time).total_seconds())
        if not 0.0 <= delivery_latency_seconds <= 5.0:
            failures.append("TTN MQTT-to-Storage latency is outside 0-5 seconds")
        if storage_database_delta_seconds > 0.000001:
            failures.append("Supabase time does not match TTN Storage to one microsecond")
    else:
        failures.append("one delivery layer lacks a server timestamp")

    telemetry = uplink.get("telemetry")
    if not isinstance(telemetry, dict):
        telemetry = {}
        failures.append("MQTT telemetry did not decode")
    if (
        expected_command_ack is not None
        and telemetry.get("command_ack_seq") != expected_command_ack
    ):
        failures.append(
            "MQTT telemetry did not report the expected durable command ACK "
            f"sequence {expected_command_ack}"
        )

    expected = {
        "temperature": telemetry.get("temperature_deci_c", 0) / 10.0,
        "pressure": telemetry.get("pressure_deci_hpa", 0) / 10.0,
        "solar_voltage": telemetry.get("solar_mv", 0) / 1000.0,
        "battery_voltage": telemetry.get("vstor_mv", 0) / 1000.0,
        "rssi": uplink.get("rssi_dbm"),
        "snr": uplink.get("snr_db"),
        "gps_speed": telemetry.get("speed_cm_s", 0) / 100.0,
        "gps_heading": telemetry.get("heading_cdeg", 0) / 100.0,
        "gps_satellites": telemetry.get("satellites"),
        "mems_accel_x": telemetry.get("accel_x_cms2", 0) / 100.0,
        "mems_accel_y": telemetry.get("accel_y_cms2", 0) / 100.0,
        "mems_accel_z": telemetry.get("accel_z_cms2", 0) / 100.0,
        "uv_index": telemetry.get("uv_index"),
        "ambient_lux": telemetry.get("ambient_lux"),
        "acoustic_event": telemetry.get("acoustic_event"),
        "telemetry_version": telemetry.get("telemetry_version"),
        "power_tier": telemetry.get("power_tier"),
        "reset_cause": telemetry.get("reset_cause"),
        "boot_count": telemetry.get("boot_count"),
        "gps_fix_age_min": telemetry.get("gps_fix_age_min"),
        "server_proof_count_mod8": telemetry.get(
            "server_proof_count_mod8"
        ),
        "server_qualified_miss_streak": telemetry.get(
            "server_qualified_miss_streak"
        ),
        "server_recovery_parity": telemetry.get("server_recovery_parity"),
        "command_ack_seq": telemetry.get("command_ack_seq"),
        "relay_enabled": telemetry.get("relay_enabled"),
        "relay_fwd_delta": telemetry.get("relay_fwd_delta"),
        "ctt_tags_delta": telemetry.get("ctt_tags_delta"),
        "lora_sf": uplink.get("spreading_factor"),
        "lora_bw": uplink.get("bandwidth_hz"),
        "frequency_hz": int(uplink["frequency_hz"])
            if str(uplink.get("frequency_hz", "")).isdigit() else None,
    }
    if telemetry.get("telemetry_version") != 3:
        failures.append("MQTT payload is not the current telemetry-v3 contract")
    mismatches = [
        {"field": field, "mqtt": value, "supabase": row.get(field)}
        for field, value in expected.items()
        if not _equal(value, row.get(field))
    ]

    satellites = telemetry.get("satellites")
    if satellites == 0:
        expected_nogps = {
            "lat": None,
            "lon": None,
            "altitude_m": None,
            "gps_speed": 0,
            "gps_heading": 0,
        }
        for field, value in expected_nogps.items():
            if not _equal(value, row.get(field)):
                mismatches.append(
                    {"field": field, "mqtt": value, "supabase": row.get(field)}
                )
    else:
        expected_position = {
            "lat": telemetry.get("lat_e7", 0) / 10_000_000.0,
            "lon": telemetry.get("lon_e7", 0) / 10_000_000.0,
            "altitude_m": telemetry.get("altitude_m"),
        }
        for field, value in expected_position.items():
            if not _equal(value, row.get(field)):
                mismatches.append(
                    {"field": field, "mqtt": value, "supabase": row.get(field)}
                )

    if mismatches:
        failures.append("Supabase payload fields do not exactly match MQTT")

    transport_passed = not any(
        failure != "Supabase payload fields do not exactly match MQTT"
        for failure in failures
    )
    # Keep transport and field integrity separate: the production legacy route
    # can insert a row while silently dropping a newer payload field.
    delivery_layers_present = (
        len(uplinks) == 1
        and storage.get("passed") is True
        and storage.get("selected_rows") == 1
        and len(rows) == 1
    )
    return {
        "passed": not failures,
        "delivery_layers_present": delivery_layers_present,
        "exact_payload_parity": not mismatches,
        "failures": failures,
        "field_mismatches": mismatches,
        "device_id": device_id,
        "f_cnt": uplink.get("f_cnt"),
        "f_port": uplink.get("f_port"),
        "payload_len": uplink.get("payload_len"),
        "command_ack_seq": telemetry.get("command_ack_seq"),
        "mqtt_received_at": mqtt_received,
        "storage_received_at": storage_received,
        "supabase_time": database_time,
        "mqtt_to_storage_seconds": delivery_latency_seconds,
        "storage_to_supabase_seconds": storage_database_delta_seconds,
        "transport_passed": transport_passed,
        "scope": (
            "one Board1 primary uplink; proves radio/TTN/Storage/webhook/database "
            "delivery only, not clear-sky GNSS or flight readiness"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ttn-log", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--supabase", type=Path, required=True)
    parser.add_argument("--device", default="stratolink-1")
    parser.add_argument("--after", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--expected-fcnt", type=int, default=0)
    parser.add_argument("--expected-command-ack", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")

    events = [
        json.loads(line)
        for line in args.ttn_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    storage = json.loads(args.storage.read_text(encoding="utf-8"))
    rows = json.loads(args.supabase.read_text(encoding="utf-8"))
    report = evaluate(
        events,
        storage,
        rows,
        device_id=args.device,
        after=args.after,
        until=args.until,
        expected_f_cnt=args.expected_fcnt,
        expected_command_ack=args.expected_command_ack,
    )
    report["provenance"] = {
        "ttn_log_sha256": _sha256(args.ttn_log),
        "storage_sha256": _sha256(args.storage),
        "supabase_sha256": _sha256(args.supabase),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({
        "output": str(args.output),
        "passed": report["passed"],
        "delivery_layers_present": report["delivery_layers_present"],
        "exact_payload_parity": report["exact_payload_parity"],
    }, sort_keys=True))
    if not report["passed"]:
        raise SystemExit("delivery evidence preserved, but exact parity failed")


if __name__ == "__main__":
    main()
