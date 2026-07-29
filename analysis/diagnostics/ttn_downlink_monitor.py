#!/usr/bin/env python3
"""Read-only MQTT monitor for safe TTN downlink lifecycle evidence."""

from __future__ import annotations

import json
import ssl
from pathlib import Path

import paho.mqtt.client as mqtt


ROOT = Path(__file__).resolve().parents[2]
KEY_FILE = ROOT / "firmware" / "test" / ".ttn_keys"


def load_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in KEY_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def on_connect(client, userdata, flags, reason_code, properties=None) -> None:
    if reason_code != 0:
        print(
            json.dumps(
                {"event": "mqtt_connect_failed", "reason_code": int(reason_code)}
            ),
            flush=True,
        )
        return
    client.subscribe(userdata["topic"])
    print(
        json.dumps(
            {"event": "mqtt_connected", "topic": userdata["topic"]},
            sort_keys=True,
        ),
        flush=True,
    )


def on_message(client, userdata, message) -> None:
    try:
        body = json.loads(message.payload)
    except Exception:
        body = {}
    ids = body.get("end_device_ids", {})
    downlink = (
        body.get("downlink_queued")
        or body.get("downlink_sent")
        or body.get("downlink_ack")
        or body.get("downlink_nack")
        or body.get("downlink_failed")
        or {}
    )
    error = body.get("error") or downlink.get("error") or {}
    print(
        json.dumps(
            {
                "event": "ttn_downlink_event",
                "topic_suffix": message.topic.rsplit("/", 2)[-1],
                "device_id": ids.get("device_id"),
                "f_port": downlink.get("f_port"),
                "f_cnt": downlink.get("f_cnt"),
                "confirmed": downlink.get("confirmed"),
                "priority": downlink.get("priority"),
                "correlation_id_count": len(body.get("correlation_ids", [])),
                "error_code": error.get("code"),
                "error_message": error.get("message"),
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> None:
    values = load_values()
    app_id = values["TTN_APP_ID"]
    username = f"{app_id}@ttn"
    topic = f"v3/{username}/devices/+/down/#"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, values["TTN_APP_KEY"])
    client.tls_set_context(ssl.create_default_context())
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.user_data_set({"topic": topic})
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("nam1.cloud.thethings.network", 8883)
    client.loop_forever()


if __name__ == "__main__":
    main()
