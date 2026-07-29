#!/usr/bin/env python3
"""Adversarial regression for one-row post-transition telemetry evidence."""

from __future__ import annotations

from copy import deepcopy

from posttransition_telemetry_audit import evaluate


GOOD = {
    "device_id": "stratolink-2",
    "time": "2026-07-27T10:01:35Z",
    "lat": None,
    "lon": None,
    "altitude_m": None,
    "temperature": 24.0,
    "pressure": 1015.6,
    "solar_voltage": 0.002,
    "battery_voltage": 4.604,
    "gps_speed": 0,
    "gps_heading": 0,
    "gps_satellites": 0,
    "mems_accel_x": 0.92,
    "mems_accel_y": 0.61,
    "mems_accel_z": 9.83,
    "uv_index": 0,
    "ambient_lux": 0,
    "rssi": -57,
    "snr": 8.75,
    "lora_sf": 9,
    "lora_bw": 125000,
    "frequency_hz": 904300000,
}


def main() -> None:
    assert evaluate([GOOD])["passed"] is True
    assert evaluate([])["passed"] is False
    assert evaluate([GOOD, GOOD])["passed"] is False
    for key, value in (
        ("lat", 37.0),
        ("gps_satellites", 3),
        ("temperature", 90),
        ("pressure", 100),
        ("solar_voltage", 3.0),
        ("battery_voltage", 4.4),
        ("mems_accel_z", 30),
        ("ambient_lux", 100),
        ("uv_index", 1),
        ("lora_sf", 7),
        ("frequency_hz", 868100000),
    ):
        row = deepcopy(GOOD)
        row[key] = value
        assert evaluate([row])["passed"] is False, key
    print("PASS: post-transition telemetry is atomic, bounded, and narrow-scoped")


if __name__ == "__main__":
    main()
