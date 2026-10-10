#!/usr/bin/env python3
"""Preserve raw TTN uplinks, then normalize them with explicit offline errors.

With no ``--input`` this performs one read-only TTN Storage query, routing the
registered Board1 EU/AS/AU device names to their own application and credential.
Other device names retain the existing NA application behavior. With
``--input`` it performs no network access and accepts this tool's archive,
bare webhook JSON, JSON arrays, TTN Storage SSE/NDJSON, or raw MQTT wrappers
of the form ``{"collector_utc": ..., "topic": ..., "body": ...}``.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from evidence_provenance import write_create_once
from ttn_downlink_monitor import load_values
from ttn_soak_monitor import decode_telemetry
from ttn_storage_replay import (
    DEV_ADDR_RE,
    fetch_storage,
    parse_storage_stream,
    parse_timestamp,
    validate_record,
)


ARCHIVE_SCHEMA = "stratolink.ttn_uplink_archive.v1"
REPORT_SCHEMA = "stratolink.ttn_uplink_offline_report.v2"
CLUSTER = "nam1.cloud.thethings.network"
APPLICATION_ID = "stratolink"
REGIONAL_STORAGE_TARGETS = {
    "stratolink-1-eu": ("eu1.cloud.thethings.network", "eu-stratolink", "TTN_EU_API_KEY"),
    "stratolink-1-as": ("eu1.cloud.thethings.network", "as-stratolink", "TTN_AS_API_KEY"),
    "stratolink-1-au": ("nam1.cloud.thethings.network", "stratolink", "TTN_NA_API_KEY"),
}
FORBIDDEN_SECRET_KEYS = {
    "authorization", "api_key", "app_key", "nwk_key", "root_keys",
    "session_keys", "app_s_key", "f_nwk_s_int_key", "s_nwk_s_int_key",
    "nwk_s_enc_key", "webhook_secret", "access_token", "refresh_token",
    "password",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def storage_target(device_id: str) -> tuple[str, str, str]:
    return REGIONAL_STORAGE_TARGETS.get(
        device_id, (CLUSTER, APPLICATION_ID, "TTN_NA_API_KEY")
    )


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ) + "\n").encode("utf-8")


def assert_no_credentials(value: object, path: str = "$") -> None:
    """Fail rather than accidentally persisting credentials from loose JSON."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(
                r"(?<!^)(?=[A-Z])", "_", str(key)
            ).lower().replace("-", "_")
            # session_key_id is an opaque identifier, not a LoRaWAN key.
            if normalized in FORBIDDEN_SECRET_KEYS:
                raise ValueError(f"credential-bearing field rejected at {path}.{key}")
            assert_no_credentials(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_credentials(child, f"{path}[{index}]")


def _unwrap(value: object, capture: dict[str, object] | None = None) -> list[tuple[dict, dict]]:
    if isinstance(value, list):
        rows: list[tuple[dict, dict]] = []
        for child in value:
            rows.extend(_unwrap(child, capture))
        return rows
    if not isinstance(value, dict):
        raise ValueError("uplink input must contain JSON objects")
    if value.get("schema") == ARCHIVE_SCHEMA:
        records = value.get("records")
        if not isinstance(records, list):
            raise ValueError("archive records must be an array")
        if value.get("record_count") != len(records):
            raise ValueError("archive record count mismatch")
        expected = value.get("records_sha256")
        observed = hashlib.sha256(canonical_bytes(records)).hexdigest()
        if expected != observed:
            raise ValueError("archive records digest mismatch")
        return _unwrap(records)
    if "collector_utc" in value or "topic" in value or "body" in value:
        if "body" not in value:
            raise ValueError("collector wrapper lacks body")
        wrapper = {
            "collector_utc": value.get("collector_utc"),
            "topic": value.get("topic"),
        }
        body = value["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError as error:
                raise ValueError("collector wrapper body is not JSON") from error
        return _unwrap(body, wrapper)
    if set(value) == {"result"}:
        return _unwrap(value["result"], capture)
    if "application_up" in value:
        return _unwrap(value["application_up"], value.get("capture", capture))
    return [(value, capture or {})]


def parse_input(raw: bytes) -> list[tuple[dict, dict]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("uplink input is not UTF-8") from error
    try:
        return _unwrap(json.loads(text))
    except json.JSONDecodeError:
        # parse_storage_stream accepts both TTN's SSE and one-object-per-line
        # NDJSON. Parse wrappers separately because they are not Storage rows.
        rows: list[tuple[dict, dict]] = []
        for line_number, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith((":", "event:", "id:", "retry:")):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on input line {line_number}") from error
            rows.extend(_unwrap(value))
        if not rows:
            # Retain the stricter Storage parser's useful empty/junk behavior.
            parsed = parse_storage_stream(raw)
            rows.extend(_unwrap(parsed))
        return rows


def validate_raw_record(row: dict, expected_device: str) -> tuple[str, str, int, object]:
    """Transport/identity gate only; payload semantics must not erase evidence.

    Keep the website replay validator unchanged and strict. Missing application
    IDs remain compatible with existing archives; present IDs must match the
    known device route. A malformed present inner RF timestamp is retained for
    a per-record normalization error, never substituted during capture.
    """
    ids, uplink = row.get("end_device_ids"), row.get("uplink_message")
    if not isinstance(ids, dict) or not isinstance(uplink, dict):
        raise ValueError("raw row lacks end_device_ids or uplink_message")
    device = ids.get("device_id")
    if not isinstance(device, str) or not 1 <= len(device) <= 64 or device != expected_device:
        raise ValueError("raw row has invalid target device identity")
    address = ids.get("dev_addr")
    if not isinstance(address, str) or not DEV_ADDR_RE.fullmatch(address):
        raise ValueError("raw row has invalid DevAddr")
    application = ids.get("application_ids")
    if application is not None:
        if not isinstance(application, dict):
            raise ValueError("raw row has invalid application identity")
        if "application_id" in application and application["application_id"] != storage_target(device)[1]:
            raise ValueError("raw row application does not match target route")
    received_at = row.get("received_at")
    parse_timestamp(received_at)
    counter = uplink.get("f_cnt", 0)
    if type(counter) is not int or not 0 <= counter <= 0xFFFFFFFF:
        raise ValueError("raw row has invalid FCntUp")
    if not isinstance(uplink.get("frm_payload"), str):
        raise ValueError("raw row frm_payload must be a string")
    return device, received_at, counter, uplink.get("f_port")


def _select(rows: list[tuple[dict, dict]], device_id: str) -> list[tuple[dict, dict]]:
    selected: list[tuple[dict, dict]] = []
    for row, capture in rows:
        ids = row.get("end_device_ids")
        if isinstance(ids, dict) and ids.get("device_id") != device_id:
            continue
        validate_raw_record(row, device_id)
        assert_no_credentials(row)
        if capture:
            if not isinstance(capture, dict):
                raise ValueError("capture metadata must be an object")
            assert_no_credentials(capture)
        selected.append((row, capture))
    # Preserve capture order so delayed Storage timestamps cannot move an
    # undecodable row away from the observations whose continuity it breaks.
    if not selected:
        raise ValueError(f"input contains no valid {device_id} uplinks")
    identities: set[tuple[str, str, int]] = set()
    for row, _capture in selected:
        device, received_at, counter, _port = validate_raw_record(row, device_id)
        identity = (device, received_at, counter)
        if identity in identities:
            raise ValueError("duplicate TTN delivery identity in selected rows")
        identities.add(identity)
    return selected


def build_archive(records: list[dict], device_id: str, after: str, limit: int,
                  *, created_utc: str | None = None) -> dict[str, object]:
    cluster, application_id, _key_name = storage_target(device_id)
    selected = _select([(record, {}) for record in records], device_id)
    raw_rows = [row for row, _capture in selected]
    # Raw capture deliberately precedes payload/metadata normalization. A
    # malformed packet must not prevent preserving this whole retention window.
    return {
        "schema": ARCHIVE_SCHEMA,
        "created_utc": created_utc or utc_now(),
        "source": {
            "kind": "ttn_storage_read_only",
            "cluster": cluster,
            "application_id": application_id,
            "after_utc_exclusive": after,
            "limit": limit,
        },
        "device_id": device_id,
        "record_count": len(raw_rows),
        "records_sha256": hashlib.sha256(canonical_bytes(raw_rows)).hexdigest(),
        "records": raw_rows,
        "credentials_included": False,
        "session_key_id_is_identifier_not_secret": True,
    }


def _exact_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def normalize(row: dict, capture: dict) -> dict[str, object]:
    if type(row["uplink_message"].get("f_port")) is not int:
        raise ValueError("uplink_message.f_port must be an integer")
    device_id, received_at, counter, f_port = validate_record(row)
    ids = row["end_device_ids"]
    uplink = row["uplink_message"]
    session_key_id = uplink.get("session_key_id")
    if session_key_id is not None and (
        not isinstance(session_key_id, str)
        or not session_key_id
        or len(session_key_id) > 4096
    ):
        raise ValueError(f"{device_id} FCnt {counter}: invalid session_key_id")
    encoded = uplink["frm_payload"]
    raw_payload = base64.b64decode(encoded, validate=True)
    telemetry = None
    if f_port == 1:
        _length, telemetry = decode_telemetry(encoded)
        if telemetry is None:
            raise ValueError(f"{device_id} FCnt {counter}: primary payload did not decode")
    settings = uplink.get("settings")
    rx_metadata = uplink.get("rx_metadata")
    if not isinstance(settings, dict):
        raise ValueError(f"{device_id} FCnt {counter}: missing radio settings")
    if not isinstance(rx_metadata, list) or not rx_metadata:
        raise ValueError(f"{device_id} FCnt {counter}: missing rx_metadata")
    first_rx = rx_metadata[0]
    if not isinstance(first_rx, dict):
        raise ValueError(f"{device_id} FCnt {counter}: invalid rx_metadata")
    gateway_id = (first_rx.get("gateway_ids") or {}).get("gateway_id")
    if not isinstance(gateway_id, str) or not gateway_id:
        raise ValueError(f"{device_id} FCnt {counter}: missing gateway_id")
    for field in ("rssi", "snr"):
        value = first_rx.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{device_id} FCnt {counter}: invalid {field}")
    lora = ((settings.get("data_rate") or {}).get("lora") or {})
    frequency = _exact_int(settings.get("frequency"))
    sf = _exact_int(lora.get("spreading_factor"))
    bandwidth = _exact_int(lora.get("bandwidth"))
    if frequency is None or sf is None or bandwidth is None:
        raise ValueError(f"{device_id} FCnt {counter}: incomplete LoRa settings")
    if not (100_000_000 <= frequency <= 1_000_000_000):
        raise ValueError(f"{device_id} FCnt {counter}: invalid frequency")
    if not (5 <= sf <= 12) or not (7_800 <= bandwidth <= 500_000):
        raise ValueError(f"{device_id} FCnt {counter}: invalid LoRa data rate")
    uplink_received_at = uplink.get("received_at")
    if "received_at" in uplink:
        parse_timestamp(uplink_received_at)
    event_received_at = uplink_received_at or received_at
    return {
        "device_id": device_id,
        "dev_addr": str(ids["dev_addr"]).upper(),
        "session_key_id": session_key_id,
        "received_at": received_at,
        "storage_received_at": received_at,
        "uplink_received_at": uplink_received_at,
        "event_received_at": event_received_at,
        "f_cnt": counter,
        "f_port": f_port,
        "confirmed": uplink.get("confirmed"),
        "frm_payload": encoded,
        "payload_bytes": len(raw_payload),
        "payload_sha256": hashlib.sha256(raw_payload).hexdigest(),
        "settings": settings,
        "rx_metadata": rx_metadata,
        "frequency_hz": frequency,
        "spreading_factor": sf,
        "bandwidth_hz": bandwidth,
        "telemetry": telemetry,
        "capture": capture,
    }


def normalize_forensic_rows(selected: list[tuple[dict, dict]]) -> list[dict]:
    """Keep every selected raw row and sort only within uninterrupted good runs."""
    result, good_run = [], []

    def flush():
        good_run.sort(key=lambda item: parse_timestamp(item["event_received_at"]))
        result.extend(good_run)
        good_run.clear()

    for row, capture in selected:
        try:
            item = normalize(row, capture)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
            flush()
            ids, uplink = row["end_device_ids"], row["uplink_message"]
            item = {
                "device_id": ids["device_id"], "dev_addr": ids["dev_addr"].upper(),
                "f_cnt": uplink.get("f_cnt", 0), "f_port": uplink.get("f_port"),
                "received_at": row["received_at"], "storage_received_at": row["received_at"],
                "event_received_at": None, "telemetry": None, "capture": capture,
                "normalization_status": "error", "payload_decode_status": "not_run",
                "normalization_errors": [str(error) if isinstance(error, ValueError)
                                         else "malformed normalization field shape"],
                "raw_record": row,
            }
            result.append(item)
        else:
            item.update(normalization_status="ok", normalization_errors=[], raw_record=row,
                        payload_decode_status="decoded" if item["f_port"] == 1 else "deferred")
            good_run.append(item)
    flush()
    return result


def build_report(raw: bytes, device_id: str, source_name: str,
                 *, created_utc: str | None = None) -> dict[str, object]:
    selected = _select(parse_input(raw), device_id)
    normalized = normalize_forensic_rows(selected)
    successful = [row for row in normalized if row["normalization_status"] == "ok"]
    normalization_complete = len(successful) == len(normalized)
    event_order = sorted(successful, key=lambda row: parse_timestamp(row["event_received_at"]))
    # A failed packet may be delivered after its RF-time neighbors. Its capture
    # position cannot prove even apparently clean segments are uninterrupted.
    adjacent = list(zip(normalized, normalized[1:])) if normalization_complete else []
    intervals = [
        (parse_timestamp(right["event_received_at"]) - parse_timestamp(left["event_received_at"])).total_seconds()
        for left, right in adjacent
    ]
    counter_transitions = [
        {
            "previous": left["f_cnt"],
            "current": right["f_cnt"],
            "delta": int(right["f_cnt"]) - int(left["f_cnt"]),
            "interval_seconds": interval,
        }
        for (left, right), interval in zip(adjacent, intervals)
    ]
    session_transitions = []
    dev_addr_transitions = []
    boot_transitions = []
    for left, right in adjacent:
        left_session = left["session_key_id"] or left["dev_addr"]
        right_session = right["session_key_id"] or right["dev_addr"]
        if left_session != right_session:
            session_transitions.append({
                "at_f_cnt": right["f_cnt"],
                "from": left_session,
                "to": right_session,
            })
        if left["dev_addr"] != right["dev_addr"]:
            dev_addr_transitions.append({
                "at_f_cnt": right["f_cnt"],
                "from": left["dev_addr"],
                "to": right["dev_addr"],
            })
    boot_observations = [
        row for row in successful
        if (row.get("telemetry") or {}).get("boot_count") is not None
    ]
    previous_boot = None
    for row in (normalized if normalization_complete else []):
        current_boot = (row.get("telemetry") or {}).get("boot_count")
        if current_boot is None:
            continue
        if previous_boot is not None and previous_boot != current_boot:
            boot_transitions.append({
                "at_f_cnt": row["f_cnt"], "from": previous_boot, "to": current_boot,
            })
        previous_boot = current_boot
    session_observations: list[dict[str, object]] = []
    previous_signature = None
    for row in normalized:
        if row["normalization_status"] != "ok":
            previous_signature = None
            continue
        signature = (row["session_key_id"], row["dev_addr"])
        if not normalization_complete or previous_signature != signature:
            session_observations.append({
                "session_key_id": signature[0],
                "dev_addr": signature[1],
                "identity_basis": (
                    "session_key_id" if signature[0] is not None
                    else "dev_addr_fallback"
                ),
                "first_f_cnt": row["f_cnt"],
                "last_f_cnt": row["f_cnt"],
                "record_count": 1,
            })
        else:
            session_observations[-1]["last_f_cnt"] = row["f_cnt"]
            session_observations[-1]["record_count"] = int(
                session_observations[-1]["record_count"]
            ) + 1
        previous_signature = signature
    gaps = [
        {"after_f_cnt": left["f_cnt"], "before_f_cnt": right["f_cnt"],
         "missing": right["f_cnt"] - left["f_cnt"] - 1}
        for left, right in adjacent if right["f_cnt"] > left["f_cnt"] + 1
    ]
    non_increasing = [
        {"previous": left["f_cnt"], "current": right["f_cnt"]}
        for left, right in adjacent if right["f_cnt"] <= left["f_cnt"]
    ]
    return {
        "schema": REPORT_SCHEMA,
        "created_utc": created_utc or utc_now(),
        "source": {
            "name": source_name,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "network_access_required": False,
        },
        "device_id": device_id,
        "record_count": len(normalized),
        "normalization_complete": normalization_complete,
        "normalization_success_count": len(successful),
        "normalization_failure_count": len(normalized) - len(successful),
        "normalization_scope": "transport/RF metadata and existing Python primary decoder; typed auxiliary decoding deferred to standalone Node formatter",
        "primary_record_count": sum(type(row["uplink_message"].get("f_port")) is int
                                    and row["uplink_message"]["f_port"] == 1 for row, _ in selected),
        "auxiliary_record_count": sum(type(row["uplink_message"].get("f_port")) is int
                                      and row["uplink_message"]["f_port"] in (11, 12) for row, _ in selected),
        "boot_observation_count": len(boot_observations),
        "timing_basis": "uplink_message.received_at; root received_at fallback only when inner timestamp absent",
        "first_received_at": event_order[0]["event_received_at"] if event_order else None,
        "last_received_at": event_order[-1]["event_received_at"] if event_order else None,
        "continuity_scope": (
            "adjacent successfully normalized uplinks across all ports; not primary-only cadence"
            if normalization_complete else
            "continuity unavailable for entire incomplete window; each successful row is a separate session observation"
        ),
        "interval_seconds": intervals,
        "first_f_cnt": event_order[0]["f_cnt"] if event_order else None,
        "last_f_cnt": event_order[-1]["f_cnt"] if event_order else None,
        "counter_transitions": counter_transitions,
        "session_observations": session_observations,
        "session_identity_limit": (
            "session_key_id when TTN supplies it; DevAddr fallback cannot "
            "distinguish a same-DevAddr restart without separate DevNonce evidence"
        ),
        "session_transitions": session_transitions,
        "dev_addr_transitions": dev_addr_transitions,
        "boot_transitions": boot_transitions,
        "counter_gaps": gaps,
        "counter_non_increasing": non_increasing,
        "records": normalized,
        "credentials_included": False,
        "session_key_id_is_identifier_not_secret": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--after", help="exclusive TTN Storage RFC3339 lower bound")
    parser.add_argument("--device", default="stratolink-1")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be 1..1000")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")

    try:
        if args.input is not None:
            if args.after is not None:
                parser.error("--after cannot be used with offline --input")
            raw = args.input.read_bytes()
            payload = build_report(raw, args.device, str(args.input))
        else:
            if not args.after:
                parser.error("--after is required for an online Storage archive")
            parse_timestamp(args.after)
            values = load_values()
            cluster, application_id, key_name = storage_target(args.device)
            api_key = values.get(key_name, "")
            if not api_key:
                raise SystemExit(f"missing local {key_name}")
            records = fetch_storage(
                cluster, application_id, api_key, args.after, args.limit
            )
            payload = build_archive(records, args.device, args.after, args.limit)
        assert_no_credentials(payload)
        write_create_once(args.output, canonical_bytes(payload))
    except (OSError, ValueError, FileExistsError) as error:
        raise SystemExit(str(error)) from error
    summary = {
        "output": str(args.output),
        "schema": payload["schema"],
        "record_count": payload["record_count"],
    }
    if args.input is not None:
        summary["normalization_complete"] = payload["normalization_complete"]
    print(json.dumps(summary, sort_keys=True))
    if args.input is not None and not payload["normalization_complete"]:
        raise SystemExit(1)  # Incomplete evidence is saved, never reported as success.


if __name__ == "__main__":
    main()
