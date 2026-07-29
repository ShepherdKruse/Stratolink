#!/usr/bin/env python3
"""Verify exact-ID Meshtastic HIL stimulus construction without RF."""

from __future__ import annotations

from unittest.mock import patch

from meshtastic_hil_stimulus import build_private_packet, send_repeated
from meshtastic.protobuf import portnums_pb2


class FakeInterface:
    def __init__(self) -> None:
        self.sent: list[tuple[object, str, bool, int]] = []

    def _generatePacketId(self) -> int:
        return 0x12345678

    def _sendPacket(
        self,
        packet: object,
        destination: str,
        *,
        wantAck: bool,
        hopLimit: int,
    ) -> object:
        self.sent.append((packet, destination, wantAck, hopLimit))
        return packet


def main() -> None:
    interface = FakeInterface()
    payload = bytes(range(32))
    packet = build_private_packet(interface, payload)
    assert packet.id == 0x12345678
    assert packet.channel == 0
    assert packet.decoded.portnum == portnums_pb2.PortNum.PRIVATE_APP
    assert packet.decoded.payload == payload
    assert packet.next_hop == 0

    directed = build_private_packet(
        interface,
        payload,
        directed_next_hop=True,
    )
    assert directed.next_hop == 1
    assert directed.decoded.payload == payload

    with patch("meshtastic_hil_stimulus.time.sleep") as sleeper:
        send_repeated(
            interface,
            packet,
            repeats=3,
            interval_seconds=0.8,
            hop_limit=3,
        )
    assert len(interface.sent) == 3
    assert all(item[0] is packet for item in interface.sent)
    assert all(item[1:] == ("^all", False, 3) for item in interface.sent)
    assert sleeper.call_count == 2

    print("PASS: private Meshtastic stimulus repeats one exact packet ID")


if __name__ == "__main__":
    main()
