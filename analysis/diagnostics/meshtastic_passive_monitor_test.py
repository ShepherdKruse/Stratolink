#!/usr/bin/env python3
"""Privacy and metadata tests for the passive Meshtastic monitor."""

from __future__ import annotations

from datetime import datetime, timezone

from meshtastic_passive_monitor import sanitize_packet


def main() -> None:
    packet = {
        "from": 0x12345678,
        "to": 0xFFFFFFFF,
        "rxRssi": -91,
        "rxSnr": 7.25,
        "hopStart": 3,
        "hopLimit": 2,
        "nextHop": 0,
        "relayNode": 0,
        "channel": 0,
        "decoded": {
            "portnum": "TEXT_MESSAGE_APP",
            "payload": b"private nearby message",
            "text": "private nearby message",
            "position": {"latitude": 47.0, "longitude": -122.0},
        },
    }
    event = sanitize_packet(
        packet,
        b"a" * 32,
        1.25,
        sync_complete=True,
        local_node_num=7,
    )
    rendered = repr(event)
    assert event["source_opaque"] != str(packet["from"])
    assert event["destination_opaque"] != str(packet["to"])
    assert event["payload_bytes"] == len(packet["decoded"]["payload"])
    assert event["portnum"] == "TEXT_MESSAGE_APP"
    assert event["rx_rssi_dbm"] == -91
    assert event["classification"] == "live_rf"
    assert event["next_hop"] == 0
    assert event["relay_node"] == 0
    assert "private nearby message" not in rendered
    assert "latitude" not in rendered
    assert "longitude" not in rendered

    same = sanitize_packet(packet, b"a" * 32, 2.0)
    other_salt = sanitize_packet(packet, b"b" * 32, 2.0)
    assert same["source_opaque"] == event["source_opaque"]
    assert other_salt["source_opaque"] != event["source_opaque"]

    sync = sanitize_packet(packet, b"a" * 32, 2.0, sync_complete=False)
    assert sync["classification"] == "configuration_sync"
    local = sanitize_packet(
        packet,
        b"a" * 32,
        2.0,
        local_node_num=packet["from"],
    )
    assert local["classification"] == "local_origin_rf_echo"
    local_without_rf = sanitize_packet(
        {**packet, "rxRssi": None, "rxSnr": None},
        b"a" * 32,
        2.0,
        local_node_num=packet["from"],
    )
    assert local_without_rf["classification"] == "local_node"

    now = datetime.now(timezone.utc).timestamp()
    cached = sanitize_packet(
        {**packet, "rxTime": now - 3600},
        b"a" * 32,
        3.0,
        sync_complete=True,
        local_node_num=7,
        now_epoch=now,
    )
    assert cached["classification"] == "cached_history"
    assert cached["radio_age_seconds"] == 3600.0
    recent = sanitize_packet(
        {**packet, "rxTime": now - 2},
        b"a" * 32,
        3.0,
        sync_complete=True,
        local_node_num=7,
        now_epoch=now,
    )
    assert recent["classification"] == "live_rf"
    future_cached = sanitize_packet(
        {**packet, "rxTime": now + 60},
        b"a" * 32,
        3.0,
        sync_complete=True,
        local_node_num=7,
        now_epoch=now,
    )
    assert future_cached["classification"] == "cached_history"

    # Configuration sync remains the strongest classification even when the
    # node DB record also carries an old receive timestamp.
    sync_cached = sanitize_packet(
        {**packet, "rxTime": now - 3600},
        b"a" * 32,
        3.0,
        sync_complete=False,
        now_epoch=now,
    )
    assert sync_cached["classification"] == "configuration_sync"

    print("PASS: passive Meshtastic metadata, cache rejection, and privacy redaction")


if __name__ == "__main__":
    main()
