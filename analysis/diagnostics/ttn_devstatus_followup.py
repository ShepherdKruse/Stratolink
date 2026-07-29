#!/usr/bin/env python3
"""Create-once proof that DevStatusReq stays disabled on a later uplink."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import ssl
import time
from urllib.request import Request, urlopen

import certifi

from ttn_downlink_test import load_values
from ttn_inventory import get_json
from ttn_mac_settings_audit import TARGETS
from ttn_pending_mac_audit import FIELD_MASK as PENDING_FIELD_MASK
from ttn_pending_mac_audit import safe_pending


# Application Server receive/forward plus Storage is direct end-to-end proof
# that Network Server forwarding occurred. ``ns.up.data.forward`` is useful
# when emitted but is not a stable audit-stream event and must not be required
# redundantly when those downstream events are present.
REQUIRED_EVENTS = {
    "ns.up.data.receive",
    "ns.up.data.process",
    "as.up.data.receive",
    "as.up.data.forward",
    "as.packages.storage.up.store",
}
FORBIDDEN_EVENTS = {
    "ns.mac.command.unanswered",
    "ns.mac.dev_status.request",
    "ns.down.data.schedule.attempt",
    "ns.down.data.schedule.success",
    "ns.down.transmission.success",
}


def fetch_redacted_tail(values: dict[str, str], tail: int = 100) -> list[dict[str, str]]:
    payload = {
        "identifiers": [{
            "device_ids": {
                "device_id": "stratolink-2",
                "application_ids": {"application_id": values["TTN_APP_ID"]},
            },
        }],
        "tail": tail,
    }
    request = Request(
        f"{values['TTN_BASE_URL'].rstrip('/')}/api/v3/events",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {values['TTN_APP_KEY']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "stratolink-launch-audit/1",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    events: list[dict[str, str]] = []
    try:
        with urlopen(request, timeout=5, context=context) as response:
            while len(events) < tail:
                raw = response.readline()
                if not raw:
                    break
                text = raw.decode(errors="replace").strip()
                if not text:
                    continue
                if text.startswith("data:"):
                    text = text[5:].strip()
                try:
                    event = json.loads(text).get("result", {})
                except json.JSONDecodeError:
                    continue
                name, when = event.get("name"), event.get("time")
                if isinstance(name, str) and isinstance(when, str):
                    events.append({"name": name, "time": when})
    except (TimeoutError, socket.timeout):
        pass
    return events


def evaluate(
    events: list[dict[str, str]], after: str
) -> tuple[dict[str, object], str | None]:
    anchors = sorted(
        event["time"] for event in events
        if event.get("name") == "ns.up.data.receive"
        and event.get("time", "") > after
    )
    if not anchors:
        return {"status": "PENDING", "passed": False}, None
    anchor = anchors[0]
    window = sorted(
        (
            {"name": event["name"], "time": event["time"]}
            for event in events if event.get("time", "") >= anchor
        ),
        key=lambda event: (event["time"], event["name"]),
    )
    names = {event["name"] for event in window}
    missing = sorted(REQUIRED_EVENTS - names)
    forbidden = sorted(FORBIDDEN_EVENTS & names)
    report: dict[str, object] = {
        "status": "PASS_CLEAN_FOLLOWING_UPLINK" if not missing and not forbidden
        else "FAIL_FOLLOWING_UPLINK",
        "passed": not missing and not forbidden,
        "uplink_received_utc": anchor,
        "events": window,
        "missing_required_events": missing,
        "forbidden_events": forbidden,
    }
    return report, anchor


def pending_inventory(values: dict[str, str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for region, host, key_name, app_id, device_id in TARGETS:
        key = values.get(key_name, "")
        if not key:
            rows.append(safe_pending(region, 0, {}))
            continue
        status, remote = get_json(
            host,
            f"/ns/applications/{app_id}/devices/{device_id}"
            f"?field_mask={PENDING_FIELD_MASK}",
            key,
        )
        rows.append(safe_pending(region, status, remote))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--grace-seconds", type=float, default=8.0)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    values = load_values()
    deadline = time.monotonic() + args.timeout_seconds
    observed: dict[tuple[str, str], dict[str, str]] = {}
    report: dict[str, object] = {"status": "PENDING", "passed": False}
    anchor: str | None = None
    while time.monotonic() < deadline:
        for event in fetch_redacted_tail(values):
            observed[(event["name"], event["time"])] = event
        report, anchor = evaluate(list(observed.values()), args.after)
        if anchor:
            time.sleep(args.grace_seconds)
            for event in fetch_redacted_tail(values):
                observed[(event["name"], event["time"])] = event
            report, _ = evaluate(list(observed.values()), args.after)
            break
        time.sleep(args.poll_seconds)
    if not anchor:
        report = {
            "status": "FAIL_TIMEOUT_NO_FOLLOWING_UPLINK",
            "passed": False,
            "missing_required_events": sorted(REQUIRED_EVENTS),
            "forbidden_events": [],
            "events": [],
        }

    pending = pending_inventory(values)
    pending_ok = all(
        row.get("readable") is True
        and row.get("pending_request_count") == 0
        for row in pending
    )
    report["pending_requests"] = [
        {
            "region": row["region"],
            "http_status": row["http_status"],
            "pending_request_count": row["pending_request_count"],
            "pending_request_cids": row["pending_request_cids"],
        }
        for row in pending
    ]
    report["pending_requests_clear"] = pending_ok
    report["passed"] = report.get("passed") is True and pending_ok
    if not report["passed"] and report.get("status") == "PASS_CLEAN_FOLLOWING_UPLINK":
        report["status"] = "FAIL_PENDING_REQUESTS_REMAIN"
    report["after_utc_exclusive"] = args.after
    report["scope"] = (
        "redacted read-only TTN event names/times and pending request counts/CIDs; "
        "no identifier, counter, payload, key, or session value is retained"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({
        "output": str(args.output),
        "status": report["status"],
        "passed": report["passed"],
    }, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
