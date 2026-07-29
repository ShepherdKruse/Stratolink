#!/usr/bin/env python3
"""Emit a privacy-preserving Meshtastic HIL stimulus from the local node.

The default is check-only. RF transmission requires --transmit. Payload bytes,
channel secrets, owner data, positions, and stable node identifiers are never
written to the evidence log.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import meshtastic.serial_interface
from meshtastic.protobuf import mesh_pb2, portnums_pb2
from pubsub import pub

from evidence_provenance import record as provenance_record
from meshtastic_passive_monitor import sanitize_packet
from preserve_precursor import atomic_manifest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def enum_name(message: object, field: str) -> str:
    descriptor = message.DESCRIPTOR.fields_by_name[field]
    value = int(getattr(message, field))
    enum_value = descriptor.enum_type.values_by_number.get(value)
    return enum_value.name if enum_value else f"UNKNOWN_{value}"


def build_private_packet(
    interface: object,
    payload: bytes,
    *,
    directed_next_hop: bool = False,
) -> object:
    packet = mesh_pb2.MeshPacket()
    packet.channel = 0
    packet.decoded.payload = payload
    packet.decoded.portnum = portnums_pb2.PortNum.PRIVATE_APP
    packet.id = int(interface._generatePacketId())  # pinned Meshtastic 2.7.3 API
    packet.priority = mesh_pb2.MeshPacket.Priority.BACKGROUND
    if directed_next_hop:
        # Deliberately nonzero synthetic routing preference. Evidence records
        # only presence, never a real/stable node identity.
        packet.next_hop = 1
    return packet


def send_repeated(
    interface: object,
    packet: object,
    *,
    repeats: int,
    interval_seconds: float,
    hop_limit: int,
) -> None:
    for index in range(repeats):
        interface._sendPacket(
            packet,
            "^all",
            wantAck=False,
            hopLimit=hop_limit,
        )
        if index + 1 < repeats:
            time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbmodem2113201")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="create-once manifest (default: OUTPUT.manifest.json)",
    )
    parser.add_argument("--payload-bytes", type=int, default=180)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--interval-seconds", type=float, default=0.8)
    parser.add_argument("--hop-limit", type=int, default=3)
    parser.add_argument(
        "--directed-next-hop",
        action="store_true",
        help="set a synthetic nonzero next-hop preference for drop-path HIL",
    )
    parser.add_argument(
        "--observe-seconds",
        type=float,
        default=0,
        help="keep the same serial interface open for peer-side RF echoes",
    )
    parser.add_argument(
        "--transmit",
        action="store_true",
        help="actually enqueue RF packets; otherwise validate only",
    )
    args = parser.parse_args()
    if not 1 <= args.payload_bytes <= 200:
        parser.error("--payload-bytes must be between 1 and 200")
    if not 1 <= args.repeats <= 16:
        parser.error("--repeats must be between 1 and 16")
    if not 0.1 <= args.interval_seconds <= 10:
        parser.error("--interval-seconds must be between 0.1 and 10")
    if not 0 <= args.hop_limit <= 7:
        parser.error("--hop-limit must be between 0 and 7")
    if not 0 <= args.observe_seconds <= 600:
        parser.error("--observe-seconds must be between 0 and 600")
    manifest_path = args.manifest or args.output.with_name(
        args.output.name + ".manifest.json"
    )
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite Meshtastic HIL evidence: {args.output}")
    if manifest_path.exists():
        raise SystemExit(
            f"refusing to overwrite Meshtastic HIL manifest: {manifest_path}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)

    payload = os.urandom(args.payload_bytes)
    evidence_salt = os.urandom(32)
    interface = None
    sync_complete = False
    local_node_num: int | None = None
    packet_count = 0
    live_rf_count = 0
    local_origin_rf_echo_count = 0
    completed = False
    config_ok = False
    started = time.monotonic()

    with args.output.open("x", encoding="utf-8") as output:
        def emit(row: dict[str, object]) -> None:
            output.write(json.dumps(row, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())

        def on_receive(
            packet: dict,
            callback_interface: object | None = None,
        ) -> None:
            del callback_interface
            nonlocal packet_count, live_rf_count, local_origin_rf_echo_count
            event = sanitize_packet(
                packet,
                evidence_salt,
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
            emit(event)

        pub.subscribe(on_receive, "meshtastic.receive")
        try:
            interface = meshtastic.serial_interface.SerialInterface(
                devPath=args.port,
                timeout=30,
            )
            local_node_num = int(interface.localNode.nodeNum)
            lora = interface.localNode.localConfig.lora
            region = enum_name(lora, "region")
            preset = enum_name(lora, "modem_preset")
            config_ok = (
                region == "US"
                and preset == "LONG_FAST"
                and bool(lora.use_preset)
                and bool(lora.tx_enabled)
            )
            emit(
                {
                    "utc": utc_now(),
                    "event": "meshtastic_hil_stimulus_start",
                    "port": args.port,
                    "region": region,
                    "modem_preset": preset,
                    "use_preset": bool(lora.use_preset),
                    "tx_enabled": bool(lora.tx_enabled),
                    "transmit_requested": args.transmit,
                    "observe_seconds": args.observe_seconds,
                    "config_ok": config_ok,
                    "privacy": (
                        "payload, PSK, owner, position, and stable node "
                        "identifiers excluded"
                    ),
                }
            )
            sync_complete = True
            if not config_ok:
                raise RuntimeError("local node is not a US LongFast transmitter")

            packet = build_private_packet(
                interface,
                payload,
                directed_next_hop=args.directed_next_hop,
            )
            fingerprint = hashlib.sha256(
                evidence_salt
                + int(packet.id).to_bytes(4, "little")
                + payload
            ).hexdigest()[:16]
            if args.transmit:
                send_repeated(
                    interface,
                    packet,
                    repeats=args.repeats,
                    interval_seconds=args.interval_seconds,
                    hop_limit=args.hop_limit,
                )
            emit(
                {
                    "utc": utc_now(),
                    "event": (
                        "meshtastic_hil_stimulus_transmitted"
                        if args.transmit
                        else "meshtastic_hil_stimulus_check_only"
                    ),
                    "opaque_packet_fingerprint": fingerprint,
                    "application": "PRIVATE_APP",
                    "channel_index": 0,
                    "payload_bytes": len(payload),
                    "repeats_same_packet_id": args.repeats,
                    "interval_seconds": args.interval_seconds,
                    "hop_limit": args.hop_limit,
                    "directed_next_hop_nonzero": args.directed_next_hop,
                    "want_ack": False,
                }
            )
            deadline = time.monotonic() + args.observe_seconds
            while time.monotonic() < deadline:
                time.sleep(min(0.25, deadline - time.monotonic()))
            completed = True
        finally:
            if interface is not None:
                interface.close()
            pub.unsubscribe(on_receive, "meshtastic.receive")
            emit(
                {
                    "utc": utc_now(),
                    "event": "meshtastic_hil_stimulus_end",
                    "completed": completed,
                    "packet_count": packet_count,
                    "live_rf_packet_count": live_rf_count,
                    "local_origin_rf_echo_count": local_origin_rf_echo_count,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )

    manifest = {
        "passed": completed and config_ok,
        "completed": completed,
        "config_ok": config_ok,
        "transmitted": args.transmit,
        "parameters": {
            "payload_bytes": args.payload_bytes,
            "repeats": args.repeats,
            "interval_seconds": args.interval_seconds,
            "hop_limit": args.hop_limit,
            "directed_next_hop_nonzero": args.directed_next_hop,
            "observe_seconds": args.observe_seconds,
        },
        "counts": {
            "packet_count": packet_count,
            "live_rf_packet_count": live_rf_count,
            "local_origin_rf_echo_count": local_origin_rf_echo_count,
        },
        "provenance": {
            "evidence_log": provenance_record(args.output),
            "stimulus_tool": provenance_record(Path(__file__)),
            "packet_sanitizer": provenance_record(
                Path(__file__).with_name("meshtastic_passive_monitor.py")
            ),
        },
    }
    atomic_manifest(manifest_path, manifest)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "manifest": str(manifest_path),
                "transmitted": args.transmit,
                "repeats": args.repeats,
                "hop_limit": args.hop_limit,
                "directed_next_hop_nonzero": args.directed_next_hop,
                "observe_seconds": args.observe_seconds,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
