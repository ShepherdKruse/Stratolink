#!/usr/bin/env python3
"""Print a redacted tail of TTN events for the StratoLink-2 device."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
from urllib.request import Request, urlopen

import certifi

from ttn_downlink_test import load_values


SAFE_DETAIL_KEYS = {
    "frequency",
    "data_rate_index",
    "spreading_factor",
    "bandwidth",
    "rx1_delay",
    "scheduled_at",
    "gateway_id",
}


def collect_safe_details(value: object, out: dict[str, list[object]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SAFE_DETAIL_KEYS and isinstance(
                child, (str, int, float, bool)
            ):
                out.setdefault(key, []).append(child)
            collect_safe_details(child, out)
    elif isinstance(value, list):
        for child in value:
            collect_safe_details(child, out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tail", type=int, default=100)
    parser.add_argument("--max-events", type=int, default=100)
    args = parser.parse_args()

    values = load_values()
    app_id = values["TTN_APP_ID"]
    device_id = "stratolink-2"
    payload = {
        "identifiers": [
            {
                "device_ids": {
                    "device_id": device_id,
                    "application_ids": {"application_id": app_id},
                }
            }
        ],
        "tail": args.tail,
    }
    request = Request(
        f"{values['TTN_BASE_URL'].rstrip('/')}/api/v3/events",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {values['TTN_APP_KEY']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "stratolink-launch-audit/1",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    count = 0
    try:
        with urlopen(request, timeout=5, context=context) as response:
            while count < args.max_events:
                line = response.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                if text.startswith("data:"):
                    text = text[5:].strip()
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                # grpc-gateway streaming responses wrap each event in
                # {"result": {...}}.
                event = event.get("result", event)
                data = event.get("data") or {}
                settings = data.get("settings") or {}
                rx_metadata = data.get("rx_metadata") or []
                gateway_id = None
                if rx_metadata:
                    gateway_id = (
                        rx_metadata[0].get("gateway_ids") or {}
                    ).get("gateway_id")
                safe_details: dict[str, list[object]] = {}
                collect_safe_details(data, safe_details)
                print(
                    json.dumps(
                        {
                            "name": event.get("name"),
                            "time": event.get("time"),
                            "data_type": data.get("@type"),
                            "error_namespace": data.get("namespace"),
                            "error_name": data.get("name"),
                            "error_message": data.get("message_format"),
                            "f_cnt": data.get("f_cnt"),
                            "frequency": settings.get("frequency"),
                            "gateway_id": gateway_id,
                            "safe_details": safe_details,
                            "correlation_id_count": len(
                                event.get("correlation_ids", [])
                            ),
                        },
                        sort_keys=True,
                    )
                )
                count += 1
    except (TimeoutError, socket.timeout):
        pass


if __name__ == "__main__":
    main()
