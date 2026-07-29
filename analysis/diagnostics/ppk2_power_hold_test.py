#!/usr/bin/env python3
"""Pin the PPK2 source assertion sequence without touching bench hardware."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import patch

# Keep this regression independent of the hardware-only ppk2-api package.
snapshot_stub = ModuleType("ppk2_snapshot")
snapshot_stub.open_endpoints = lambda: None
sys.modules["ppk2_snapshot"] = snapshot_stub

from ppk2_power_hold import assert_power


class FakeSerial:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    def reset_input_buffer(self) -> None:
        self.calls.append("reset_input_buffer")


class FakeControl:
    def __init__(self, acknowledged: bool = True) -> None:
        self.calls: list[object] = []
        self.ser = FakeSerial(self.calls)
        self.acknowledged = acknowledged

    def stop_measuring(self) -> None:
        self.calls.append("stop_measuring")

    def use_source_meter(self) -> None:
        self.calls.append("use_source_meter")

    def set_source_voltage(self, millivolts: int) -> None:
        self.calls.append(("set_source_voltage", millivolts))

    def toggle_DUT_power(self, state: str) -> None:
        self.calls.append(("toggle_DUT_power", state))

    def get_modifiers(self) -> dict:
        self.calls.append("get_modifiers")
        return {"ack": True} if self.acknowledged else {}


def main() -> None:
    control = FakeControl()
    with patch("ppk2_power_hold.time.sleep"):
        assert_power(control, 4660)
    assert control.calls == [
        "stop_measuring",
        "use_source_meter",
        ("set_source_voltage", 4660),
        ("toggle_DUT_power", "ON"),
        "reset_input_buffer",
        "get_modifiers",
    ]
    assert all(
        call != ("toggle_DUT_power", "OFF")
        for call in control.calls
    )

    unacknowledged = FakeControl(acknowledged=False)
    with patch("ppk2_power_hold.time.sleep"):
        try:
            assert_power(unacknowledged, 4660)
        except RuntimeError as error:
            assert "did not acknowledge" in str(error)
        else:
            raise AssertionError("missing PPK2 acknowledgment was accepted")

    print("PASS: PPK2 source is fixed at 4660 mV, ON, and acknowledged")


if __name__ == "__main__":
    main()
