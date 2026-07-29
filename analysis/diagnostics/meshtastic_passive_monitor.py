#!/usr/bin/env python3
"""Passively inventory a Meshtastic node and log metadata-only RF events.

No message text, payload bytes, positions, owner names, channel names, PSKs,
or stable node identifiers are emitted. The serial configuration exchange is
read-only; this tool never calls a Meshtastic send/config/admin method.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import time

from pubsub import pub

import meshtastic.serial_interface

MAX_LIVE_RADIO_AGE_SECONDS = 30.0
MAX_FUTURE_RADIO_SKEW_SECONDS = 5.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def enum_name(message: object, field: str) -> str:
    descriptor = message.DESCRIPTOR.fields_by_name[field]
    value = int(getattr(message, field))
    enum_value = descriptor.enum_type.values_by_number.get(value)
    return enum_value.name if enum_value else f"UNKNOWN_{value}"


def opaque_node(value: object, salt: bytes) -> str | None:
    if value is None:
        return None
    digest = hashlib.sha256(salt + str(value).encode("ascii", errors="replace"))
    return digest.hexdigest()[:12]


def payload_length(decoded: dict) -> int:
    payload = decoded.get("payload")
    if isinstance(payload, (bytes, bytearray)):
        return len(payload)
    encrypted = decoded.get("encrypted")
    if isinstance(encrypted, (bytes, bytearray)):
        return len(encrypted)
    return 0


def sanitize_packet(
    packet: dict,
    salt: bytes,
    elapsed_seconds: float,
    *,
    sync_complete: bool = True,
    local_node_num: int | None = None,
    now_epoch: float | None = None,
) -> dict:
    decoded = packet.get("decoded")
    if not isinstance(decoded, dict):
        decoded = {}
    portnum = decoded.get("portnum")
    if hasattr(portnum, "name"):
        portnum = portnum.name
    elif portnum is not None:
        portnum = str(portnum)
    source_num = packet.get("from")
    from_local = local_node_num is not None and source_num == local_node_num
    rx_time = packet.get("rxTime")
    rx_time_utc = None
    radio_age_seconds = None
    if isinstance(rx_time, (int, float)) and rx_time > 0:
        if now_epoch is None:
            now_epoch = datetime.now(timezone.utc).timestamp()
        rx_time_utc = datetime.fromtimestamp(
            rx_time, timezone.utc
        ).isoformat(timespec="seconds")
        radio_age_seconds = round(now_epoch - float(rx_time), 3)
    has_rf_metadata = (
        packet.get("rxRssi") is not None
        and packet.get("rxSnr") is not None
    )
    if not sync_complete:
        classification = "configuration_sync"
    elif (
        radio_age_seconds is not None
        and (
            radio_age_seconds > MAX_LIVE_RADIO_AGE_SECONDS
            or radio_age_seconds < -MAX_FUTURE_RADIO_SKEW_SECONDS
        )
    ):
        # SerialInterface can continue replaying the node's packet database
        # after its constructor returns and configuration sync is marked done.
        # Cached records retain real RSSI/SNR, so RF metadata alone cannot
        # distinguish them from a packet heard during this observation.
        classification = "cached_history"
    elif bool(packet.get("viaMqtt", False)):
        classification = "mqtt"
    elif from_local and has_rf_metadata:
        # A relay preserves the original `from`. When this node originates a
        # broadcast, StratoLink's over-air forward therefore looks local by
        # source ID but carries genuine receiver RSSI/SNR. Preserve that as the
        # strongest peer-side relay proof instead of hiding it as local TX.
        classification = "local_origin_rf_echo"
    elif from_local:
        classification = "local_node"
    elif has_rf_metadata:
        classification = "live_rf"
    else:
        classification = "live_unverified"
    return {
        "utc": utc_now(),
        "event": "meshtastic_packet_metadata",
        "elapsed_seconds": round(elapsed_seconds, 3),
        "classification": classification,
        "source_opaque": opaque_node(packet.get("fromId", packet.get("from")), salt),
        "destination_opaque": opaque_node(
            packet.get("toId", packet.get("to")), salt
        ),
        "portnum": portnum,
        "payload_bytes": payload_length(decoded),
        "rx_rssi_dbm": packet.get("rxRssi"),
        "rx_snr_db": packet.get("rxSnr"),
        "hop_start": packet.get("hopStart"),
        "hop_limit": packet.get("hopLimit"),
        "next_hop": packet.get("nextHop", packet.get("next_hop")),
        "relay_node": packet.get("relayNode", packet.get("relay_node")),
        "channel_index": packet.get("channel"),
        "via_mqtt": bool(packet.get("viaMqtt", False)),
        "radio_rx_time_utc": rx_time_utc,
        "radio_age_seconds": radio_age_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbmodem2113201")
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 3600:
        parser.error("--seconds must be between 5 and 3600")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite passive RF evidence: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    salt = os.urandom(32)
    stop = False
    interface = None
    packet_count = 0
    live_rf_count = 0
    local_origin_rf_echo_count = 0
    source_tokens: set[str] = set()
    sync_complete = False
    local_node_num: int | None = None

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    with args.output.open("x", encoding="utf-8") as output:
        def emit(value: dict) -> None:
            output.write(json.dumps(value, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())

        def on_receive(
            packet: dict,
            interface: object | None = None,
        ) -> None:
            del interface
            nonlocal packet_count, live_rf_count, local_origin_rf_echo_count
            event = sanitize_packet(
                packet,
                salt,
                time.monotonic() - started,
                sync_complete=sync_complete,
                local_node_num=local_node_num,
            )
            packet_count += 1
            if event["classification"] in (
                "live_rf",
                "local_origin_rf_echo",
            ):
                live_rf_count += 1
            if event["classification"] == "local_origin_rf_echo":
                local_origin_rf_echo_count += 1
            if (
                event["classification"] in (
                    "live_rf",
                    "local_origin_rf_echo",
                )
                and event["source_opaque"]
            ):
                source_tokens.add(event["source_opaque"])
            emit(event)

        pub.subscribe(on_receive, "meshtastic.receive")
        try:
            interface = meshtastic.serial_interface.SerialInterface(
                devPath=args.port,
                timeout=30,
            )
            local = interface.localNode
            local_node_num = int(local.nodeNum)
            lora = local.localConfig.lora
            metadata = interface.metadata
            emit(
                {
                    "utc": utc_now(),
                    "event": "meshtastic_passive_monitor_start",
                    "port": args.port,
                    "duration_seconds": args.seconds,
                    "firmware_version": (
                        getattr(metadata, "firmware_version", None)
                        if metadata else None
                    ),
                    "hardware_model": (
                        enum_name(metadata, "hw_model")
                        if metadata and "hw_model" in metadata.DESCRIPTOR.fields_by_name
                        else None
                    ),
                    "region": enum_name(lora, "region"),
                    "modem_preset": enum_name(lora, "modem_preset"),
                    "use_preset": bool(lora.use_preset),
                    "tx_enabled": bool(lora.tx_enabled),
                    "hop_limit": int(lora.hop_limit),
                    "node_db_entries": len(interface.nodes or {}),
                    "live_radio_age_window_seconds": [
                        -MAX_FUTURE_RADIO_SKEW_SECONDS,
                        MAX_LIVE_RADIO_AGE_SECONDS,
                    ],
                    "privacy": (
                        "payloads, text, positions, names, PSKs, and stable "
                        "node identifiers excluded"
                    ),
                }
            )
            sync_complete = True
            deadline = started + args.seconds
            while not stop and time.monotonic() < deadline:
                time.sleep(min(0.25, deadline - time.monotonic()))
        finally:
            if interface is not None:
                interface.close()
            pub.unsubscribe(on_receive, "meshtastic.receive")
            emit(
                {
                    "utc": utc_now(),
                    "event": "meshtastic_passive_monitor_end",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "packet_count": packet_count,
                    "live_rf_packet_count": live_rf_count,
                    "local_origin_rf_echo_count": local_origin_rf_echo_count,
                    "live_rf_opaque_source_count": len(source_tokens),
                }
            )


if __name__ == "__main__":
    main()
