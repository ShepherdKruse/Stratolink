#!/usr/bin/env python3
"""Pin the authenticated RX1 gate that preserves LoRaWAN RX2 fallback."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "firmware/src/lorawan.cpp").read_text()


def body(signature: str, following: str) -> str:
    start = SOURCE.index(signature)
    end = SOURCE.index(following, start)
    return SOURCE[start:end]


join = body("static bool otaa_join(void)", "/* ========== Uplink MIC")
downlink = body(
    "bool lorawan_receive_downlink(lorawan_downlink_t* out)",
    "/* ========== Runtime region switching",
)

# RX1 and RX2 join candidates must each pass AppKey authentication, and RX2 is
# conditioned on that result rather than mere RF-frame presence.
assert join.count("lorawan_frame_decode_join_accept(") == 2
assert join.count("while (!received &&") == 2
assert "if (!received &&" in join
assert join.index("lorawan_frame_decode_join_accept(") < join.index("if (!received &&")

# Data-down follows the same policy: decode/authenticate RX1 first, enter RX2
# on !authenticated, and decode/authenticate the RX2 candidate independently.
assert downlink.count("lorawan_frame_decode_downlink(") == 2
assert "millis() - rx1_deadline" in downlink
assert "millis() - rx2_deadline" in downlink
fallback = downlink.index("if (!authenticated)")
first_decode = downlink.index("lorawan_frame_decode_downlink(")
second_decode = downlink.index("lorawan_frame_decode_downlink(", first_decode + 1)
assert first_decode < fallback < second_decode
assert "if (rxLen == 0)" not in downlink
assert "fCntDown = decoded.frame_counter + 1u;" in downlink
assert downlink.index("restore_lorawan_or_reset();") < downlink.index(
    "fCntDown = decoded.frame_counter + 1u;"
)

print("LoRaWAN RX2 fallback is gated by authenticated RX1 frames")
