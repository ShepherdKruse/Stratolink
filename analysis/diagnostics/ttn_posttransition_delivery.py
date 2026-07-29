#!/usr/bin/env python3
"""Bind event, Storage, webhook-config, and Supabase post-transition proof."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


REQUIRED_EVENT_NAMES = {
    "ns.up.data.receive",
    "ns.up.data.process",
    "as.up.data.receive",
    "as.up.data.forward",
}


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def provenance(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "append_allowed": False,
    }


def evaluate(
    event_report: dict[str, object],
    storage_report: dict[str, object],
    supabase_rows: list[dict[str, object]],
    remediation: dict[str, object],
) -> dict[str, object]:
    failures: list[str] = []
    events = event_report.get("events")
    if not isinstance(events, list):
        events = []
        failures.append("event evidence lacks events")
    names = {
        event.get("name") for event in events if isinstance(event, dict)
    }
    missing = sorted(REQUIRED_EVENT_NAMES - names)
    if missing:
        failures.append("required TTN forwarding events are missing")
    forbidden = event_report.get("forbidden_events")
    if forbidden != []:
        failures.append("event evidence contains forbidden events")
    if event_report.get("pending_requests_clear") is not True:
        failures.append("TTN pending MAC requests are not clear")

    # The first watcher remains a failed artifact because its audit-stream
    # Storage event was absent.  Accept no broader watcher failure here.
    if event_report.get("status") != "FAIL_FOLLOWING_UPLINK":
        failures.append("unexpected first-watcher status")
    if event_report.get("missing_required_events") != [
        "as.packages.storage.up.store"
    ]:
        failures.append("first watcher failed for more than Storage audit omission")

    if storage_report.get("passed") is not True:
        failures.append("authoritative TTN Storage evidence did not pass")
    if storage_report.get("selected_rows") != 1:
        failures.append("TTN Storage evidence is not exactly one row")
    storage_time = timestamp(storage_report.get("first_received_at"))
    if storage_report.get("last_received_at") != storage_report.get("first_received_at"):
        failures.append("TTN Storage interval contains multiple timestamps")

    if len(supabase_rows) != 1:
        failures.append("Supabase evidence is not exactly one row")
        supabase_time = storage_time
    else:
        if supabase_rows[0].get("device_id") != "stratolink-2":
            failures.append("Supabase row belongs to an unexpected device")
        supabase_time = timestamp(supabase_rows[0].get("time"))
    delta = abs((supabase_time - storage_time).total_seconds())
    if delta > 0.001:
        failures.append("TTN Storage and Supabase timestamps differ by more than 1 ms")

    readback = remediation.get("readback")
    if not isinstance(readback, dict):
        readback = {}
    if remediation.get("passed") is not True:
        failures.append("join-webhook remediation did not pass")
    if readback.get("all_regions_uplink_enabled") is not True:
        failures.append("regional uplink webhooks are not all enabled")
    if readback.get("all_regions_join_accept_disabled") is not True:
        failures.append("regional join-accept webhooks are not all disabled")

    uplink_received = event_report.get("uplink_received_utc")
    try:
        event_to_storage = (storage_time - timestamp(uplink_received)).total_seconds()
    except ValueError:
        failures.append("event evidence lacks a valid uplink receive time")
        event_to_storage = None

    return {
        "passed": not failures,
        "failures": failures,
        "required_forwarding_events": sorted(REQUIRED_EVENT_NAMES),
        "missing_forwarding_events": missing,
        "forbidden_events": forbidden,
        "pending_requests_clear": event_report.get("pending_requests_clear"),
        "uplink_received_utc": uplink_received,
        "ttn_storage_rows": storage_report.get("selected_rows"),
        "ttn_storage_received_at": storage_report.get("first_received_at"),
        "supabase_rows": len(supabase_rows),
        "supabase_time": supabase_rows[0].get("time") if len(supabase_rows) == 1 else None,
        "event_to_storage_seconds": (
            round(event_to_storage, 6) if event_to_storage is not None else None
        ),
        "storage_to_supabase_seconds": round(delta, 6),
        "all_regions_uplink_enabled": readback.get("all_regions_uplink_enabled"),
        "all_regions_join_accept_disabled": readback.get(
            "all_regions_join_accept_disabled"
        ),
        "interpretation": (
            "The first event-stream watcher remains failed because its Storage "
            "audit event was absent. Direct TTN Storage and Supabase APIs prove "
            "the row was stored and delivered; this corrected artifact does not "
            "rewrite or reclassify the first artifact."
        ),
        "scope": (
            "proves one post-transition precursor uplink reached TTN Network "
            "Server, Application Server, TTN Storage, and the current Supabase "
            "telemetry table after join-webhook remediation; it does not prove "
            "the missing telemetry-v2 schema, authenticated hardened route, "
            "retry/idempotency, downlink, final candidate, or power continuity"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--supabase", type=Path, required=True)
    parser.add_argument("--remediation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    event_report = load_json(args.events)
    storage_report = load_json(args.storage)
    supabase_rows = load_json(args.supabase)
    remediation = load_json(args.remediation)
    if not isinstance(event_report, dict) or not isinstance(storage_report, dict):
        raise SystemExit("event/storage evidence must be JSON objects")
    if not isinstance(supabase_rows, list) or not isinstance(remediation, dict):
        raise SystemExit("Supabase/remediation evidence has the wrong JSON shape")
    report = evaluate(event_report, storage_report, supabase_rows, remediation)
    report["provenance"] = {
        "events": provenance(args.events),
        "storage": provenance(args.storage),
        "supabase": provenance(args.supabase),
        "remediation": provenance(args.remediation),
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if not report["passed"]:
        print(payload, end="")
        raise SystemExit("refusing to create non-passing delivery evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    print(json.dumps({"output": str(args.output), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
