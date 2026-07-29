#!/usr/bin/env python3
"""Fail closed when release-facing firmware docs drift from flight constants."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CONFIG = (ROOT / "firmware/include/config.h").read_text(encoding="utf-8")
PLATFORMIO = (ROOT / "firmware/platformio.ini").read_text(encoding="utf-8")
PINS = (ROOT / "firmware/include/stratolink_pins.h").read_text(encoding="utf-8")
README = (ROOT / "firmware/README.md").read_text(encoding="utf-8")
DOCS = (ROOT / "firmware/DOCUMENTATION.md").read_text(encoding="utf-8")
RADIO = (ROOT / "analysis/network/06_firmware_radio_sharing.md").read_text(
    encoding="utf-8"
)
GPS_RCA = (ROOT / "analysis/diagnostics/WAKE_WEDGE_ROOT_CAUSE.md").read_text(
    encoding="utf-8"
)


def macro(name: str) -> int:
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(\d+)", CONFIG, re.MULTILINE)
    assert match, f"missing integer macro {name}"
    return int(match.group(1))


assert macro("SLEEP_INTERVAL_FULL_SEC") == 1200
assert macro("SLEEP_INTERVAL_REDUCED_SEC") == 1800
assert macro("SLEEP_INTERVAL_NO_GPS_SEC") == 1800
assert macro("SLEEP_INTERVAL_EMERGENCY_SEC") == 1800
assert macro("CTT_LISTEN_MS") == 60000
assert macro("RELAY_FLOOR_MV") == 4200
assert macro("RELAY_AIRTIME_CAP_PCT") == 5
assert macro("AUX_UPLINK_INTERVAL_CYCLES") == 8
assert "platform = ststm32@19.6.0" in PLATFORMIO

assert "FULL 1200 s" in DOCS
assert "REDUCED/NO_GPS/EMERGENCY/CRITICAL 1800 s" in DOCS
assert "fPorts 11 and 12" in DOCS
assert "40-byte" in README and "40-byte" in DOCS
assert "eight successful primary cycles" in DOCS
assert "Command ACK valid" in DOCS and "design-only" in DOCS
assert "~642 us" in README and "~642 us" in DOCS
assert "6.730 µA" in DOCS
assert "6.688 µA" in DOCS
assert "0.042 µA" in DOCS
assert "33–35 µA" not in DOCS
assert "shallow CPU sleep" in RADIO
assert "radio-only" in RADIO and "lower screen" in RADIO
assert "4.2 V" in RADIO and "5%" in RADIO
assert "36-check sanitized freshness/recovery suite" in GPS_RCA
assert "It is not a frozen flight candidate" in GPS_RCA

combined = "\n".join((PINS, README, DOCS, RADIO, GPS_RCA))
for stale in (
    "50 ms settle",
    "current cycle is uplink-only",
    "Quiescent ~3-5 µA",
    "MCU sleeps in STOP2",
    "floor-abort (<4.7 V)",
    "≤7.5% AirUtilTX",
    "Streaming RMS energy detection",
    "The frozen StratoLink-2 candidate",
    "29-check sanitized freshness/recovery suite",
):
    assert stale not in combined, f"stale release claim returned: {stale}"

print("PASS: release-facing firmware documentation matches flight constants")
