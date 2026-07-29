#!/usr/bin/env python3
"""Bind every shared-radio packet copy to an explicit storage ceiling."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LORAWAN_H = (ROOT / "firmware/include/lorawan.h").read_text(encoding="utf-8")
LORAWAN_CPP = (ROOT / "firmware/src/lorawan.cpp").read_text(encoding="utf-8")
MAIN_CPP = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
FRAME_CPP = (ROOT / "firmware/src/lorawan_frame.cpp").read_text(encoding="utf-8")
MESH_H = (ROOT / "firmware/include/meshtastic_relay_mac.h").read_text(
    encoding="utf-8"
)
MESH_CPP = (ROOT / "firmware/src/meshtastic_relay_mac.cpp").read_text(
    encoding="utf-8"
)
B2B_CPP = (ROOT / "firmware/src/b2b.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require("#define LORAWAN_PAYLOAD_MAX 53" in LORAWAN_H,
            "common DR1 uplink ceiling drifted")
    require("UPLINK_FIXED_BYTES = 13u" in LORAWAN_CPP,
            "uplink overhead is not explicit")
    require("UPLINK_FIXED_BYTES + LORAWAN_PAYLOAD_MAX" in LORAWAN_CPP,
            "uplink storage is not derived from its payload ceiling")
    require("uint8_t pkt[UPLINK_FRAME_BYTES]" in LORAWAN_CPP,
            "uplink copy does not use the derived storage")
    require("UPLINK_FRAME_BYTES <= UINT8_MAX" in LORAWAN_CPP,
            "uplink uint8 packet index has no compile-time bound")
    require("uint8_t pkt[80]" not in LORAWAN_CPP,
            "stale magic uplink buffer returned")

    require("frame_len > 64u" in FRAME_CPP,
            "downlink radio-frame ceiling is missing")
    require("payload_len > sizeof(out->data)" in FRAME_CPP,
            "decoded downlink copy is not destination-sized")
    require(LORAWAN_CPP.count("n > maxlen || radio->readData(buf, n)") == 2,
            "join and data-down radio reads do not both reject oversize")
    require("if (n > maxlen) n = maxlen;" not in LORAWAN_CPP,
            "oversized radio downlink is still authenticated as a prefix")

    require("#define MESH_RELAY_FRAME_MAX 255u" in MESH_H,
            "Meshtastic packet ceiling drifted")
    require("len > MESH_RELAY_FRAME_MAX" in MESH_CPP,
            "Meshtastic copy lacks its frame ceiling")
    require("memcpy(out->frame, frame, len)" in MESH_CPP,
            "expected bounded Meshtastic copy is missing")

    require("f->len > B2B_PAYLOAD_MAX" in B2B_CPP,
            "B2B encoder copy lacks its payload ceiling")
    require("n != B2B_HDR_LEN + len" in B2B_CPP,
            "B2B parser does not require an exact wire length")
    require(
        "capacity < B2B_FRAME_MAX" in LORAWAN_CPP
        and "b2b_encode(frame, out, capacity)" in LORAWAN_CPP,
        "B2B-to-TTN copy is not caller-capacity bounded",
    )
    require(
        "pending_b2b, sizeof(pending_b2b), &pending_b2b_len" in MAIN_CPP,
        "B2B-to-TTN caller does not supply its destination size",
    )
    print("PASS: LoRaWAN RX rejects oversize without prefix authentication; all shared-radio packet copies are storage-bound")


if __name__ == "__main__":
    main()
