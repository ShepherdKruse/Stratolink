#!/usr/bin/env python3
"""Persist sanitized TTN uplink/downlink evidence for a hardware soak."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import struct
from typing import TextIO

import paho.mqtt.client as mqtt

from ttn_downlink_monitor import load_values


TELEMETRY_FORMAT = ">iiihHHHHHBhhhBHB"
TELEMETRY_FIELDS = (
    "lat_e7", "lon_e7", "altitude_m", "temperature_deci_c",
    "pressure_deci_hpa", "solar_mv", "vstor_mv", "speed_cm_s",
    "heading_cdeg", "satellites", "accel_x_cms2", "accel_y_cms2",
    "accel_z_cms2", "uv_index", "ambient_lux", "acoustic_event",
)
TELEMETRY_V1_SIZE = struct.calcsize(TELEMETRY_FORMAT)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def mqtt_reason_code_value(reason_code: object) -> int | str:
    """Return a JSON-safe Paho v1/v2 reason code without callback failure."""
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(reason_code)


def protobuf_uint32(message: dict[str, object], key: str) -> int | None:
    """Decode a protobuf-JSON uint32, including omitted default zero."""
    if key not in message:
        return 0
    value = message[key]
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 0 <= value <= 0xFFFFFFFF:
        return None
    return value


def open_create_once_log(path: Path) -> TextIO:
    """Create one collector-owned evidence log; never reopen or append."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise SystemExit(f"refusing to append to existing TTN evidence: {path}") from error


def decode_telemetry(encoded: str | None) -> tuple[int, dict[str, object] | None]:
    if not encoded:
        return 0, None
    raw = base64.b64decode(encoded)
    if len(raw) not in (TELEMETRY_V1_SIZE, 40):
        return len(raw), None
    telemetry = dict(zip(
        TELEMETRY_FIELDS,
        struct.unpack(TELEMETRY_FORMAT, raw[:TELEMETRY_V1_SIZE]),
    ))
    if telemetry["temperature_deci_c"] == -32768:
        telemetry["temperature_deci_c"] = None
    if telemetry["pressure_deci_hpa"] == 0xFFFE:
        telemetry["pressure_deci_hpa"] = None
    accel_fields = ("accel_x_cms2", "accel_y_cms2", "accel_z_cms2")
    unavailable_axes = sum(
        telemetry[field] == -32768 for field in accel_fields
    )
    if unavailable_axes not in (0, 3):
        return len(raw), None
    if unavailable_axes == 3:
        for field in accel_fields:
            telemetry[field] = None
    if telemetry["uv_index"] == 0xFE:
        telemetry["uv_index"] = None
    if telemetry["ambient_lux"] == 0xFFFE:
        telemetry["ambient_lux"] = None
    if len(raw) == 40:
        status = raw[34]
        acoustic_power_code = status & 0x0F
        if acoustic_power_code <= 9:
            power_tier = acoustic_power_code >> 1
            acoustic_event = acoustic_power_code & 1
        elif acoustic_power_code <= 14:
            power_tier = acoustic_power_code - 10
            acoustic_event = None
        else:
            return len(raw), None
        reset_cause = (status >> 4) & 0x07
        if reset_cause > 6:
            return len(raw), None
        activity = raw[39]
        fix_age = int.from_bytes(raw[36:38], "big")
        telemetry.update({
            "acoustic_event": acoustic_event,
            "telemetry_version": 2,
            "power_tier": power_tier,
            "reset_cause": reset_cause,
            "boot_count": raw[35],
            "gps_fix_age_min": None if fix_age == 0xFFFF else fix_age,
            "command_ack_seq": raw[38] if status & 0x80 else None,
            "relay_enabled": bool(activity & 0x80),
            "relay_fwd_delta": (activity >> 4) & 0x07,
            "ctt_tags_delta": activity & 0x0F,
        })
    else:
        telemetry["telemetry_version"] = 1
    return len(raw), telemetry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--device", default="stratolink-2")
    args = parser.parse_args()

    values = load_values()
    log = open_create_once_log(args.log_file)

    def emit(event: dict[str, object]) -> None:
        line = json.dumps({"utc": utc_now(), **event}, sort_keys=True)
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    app_id = values["TTN_APP_ID"]
    username = f"{app_id}@ttn"
    up_topic = f"v3/{username}/devices/{args.device}/up"
    down_topic = f"v3/{username}/devices/{args.device}/down/#"

    def on_connect(client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code != 0:
            emit({
                "event": "mqtt_connect_failed",
                "reason_code": mqtt_reason_code_value(reason_code),
            })
            return
        client.subscribe([(up_topic, 0), (down_topic, 0)])
        emit({"event": "mqtt_connected", "device_id": args.device})

    def on_disconnect(client, userdata, disconnect_flags, reason_code,
                      properties=None) -> None:
        emit({
            "event": "mqtt_disconnected",
            "reason_code": mqtt_reason_code_value(reason_code),
        })

    def on_message(client, userdata, message) -> None:
        try:
            body = json.loads(message.payload)
        except Exception as error:
            emit({"event": "mqtt_decode_error", "error": type(error).__name__})
            return

        ids = body.get("end_device_ids") or {}
        if message.topic.endswith("/up"):
            uplink = body.get("uplink_message") or {}
            metadata = uplink.get("rx_metadata") or [{}]
            first_rx = metadata[0] if metadata else {}
            settings = uplink.get("settings") or {}
            lora = (settings.get("data_rate") or {}).get("lora") or {}
            payload_len, telemetry = decode_telemetry(uplink.get("frm_payload"))
            emit(
                {
                    "event": "ttn_uplink",
                    "device_id": ids.get("device_id"),
                    "received_at": uplink.get("received_at"),
                    "f_port": uplink.get("f_port"),
                    "f_cnt": protobuf_uint32(uplink, "f_cnt"),
                    "payload_len": payload_len,
                    "rssi_dbm": first_rx.get("rssi"),
                    "snr_db": first_rx.get("snr"),
                    "gateway_id": (
                        first_rx.get("gateway_ids") or {}
                    ).get("gateway_id"),
                    "frequency_hz": settings.get("frequency"),
                    "spreading_factor": lora.get("spreading_factor"),
                    "bandwidth_hz": lora.get("bandwidth"),
                    "telemetry": telemetry,
                }
            )
            return

        downlink = (
            body.get("downlink_queued")
            or body.get("downlink_sent")
            or body.get("downlink_ack")
            or body.get("downlink_nack")
            or body.get("downlink_failed")
            or {}
        )
        error = body.get("error") or downlink.get("error") or {}
        emit(
            {
                "event": "ttn_downlink",
                "topic_suffix": message.topic.rsplit("/", 1)[-1],
                "device_id": ids.get("device_id"),
                "f_port": downlink.get("f_port"),
                "f_cnt": protobuf_uint32(downlink, "f_cnt"),
                "confirmed": downlink.get("confirmed"),
                "error_code": error.get("code"),
                "error_message": error.get("message"),
            }
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, values["TTN_APP_KEY"])
    client.tls_set_context(ssl.create_default_context())
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    try:
        client.connect("nam1.cloud.thethings.network", 8883)
        client.loop_forever()
    finally:
        log.close()


if __name__ == "__main__":
    main()
