#!/usr/bin/env python3
"""Cross-layer regression for explicit unavailable sensor wire states."""

from __future__ import annotations

import base64
from pathlib import Path
import struct

from ttn_soak_monitor import TELEMETRY_FORMAT, decode_telemetry


ROOT = Path(__file__).resolve().parents[2]


def encoded(values: tuple[int, ...], suffix: bytes = b"") -> str:
    return base64.b64encode(struct.pack(TELEMETRY_FORMAT, *values) + suffix).decode()


def main() -> None:
    # Pressure is unsigned on wire. This also catches the former monitor
    # format's signed-h typo, which normal ~1013 hPa packets could not expose.
    assert struct.calcsize(TELEMETRY_FORMAT) == 35
    valid = (
        0, 0, 0, 250, 40000, 100, 4600, 0, 0, 0,
        10, 20, 980, 1, 1234, 0,
    )
    size, telemetry = decode_telemetry(encoded(valid))
    assert size == 35 and telemetry is not None
    assert telemetry["pressure_deci_hpa"] == 40000

    unavailable = (
        0, 0, 0, -32768, 0xFFFE, 100, 4600, 0, 0, 0,
        -32768, -32768, -32768, 0xFE, 0xFFFE, 0,
    )
    size, telemetry = decode_telemetry(encoded(unavailable, bytes(5)))
    assert size == 40 and telemetry is not None
    for field in (
        "temperature_deci_c", "pressure_deci_hpa", "accel_x_cms2",
        "accel_y_cms2", "accel_z_cms2", "uv_index", "ambient_lux",
    ):
        assert telemetry[field] is None

    for tier in range(5):
        mic_unavailable = list(valid)
        mic_unavailable[-1] = 10 + tier
        size, telemetry = decode_telemetry(
            encoded(tuple(mic_unavailable), bytes(5)))
        assert size == 40 and telemetry is not None
        assert telemetry["acoustic_event"] is None
        assert telemetry["power_tier"] == tier

    invalid_status = list(valid)
    invalid_status[-1] = 15
    assert decode_telemetry(encoded(tuple(invalid_status), bytes(5)))[1] is None

    mixed = list(unavailable)
    mixed[11] = 0
    assert decode_telemetry(encoded(tuple(mixed)))[1] is None

    header = (ROOT / "firmware/include/telemetry.h").read_text(encoding="utf-8")
    source = (ROOT / "firmware/src/telemetry.cpp").read_text(encoding="utf-8")
    main_source = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
    conversion = (
        ROOT / "firmware/include/ltr390_conversion.h"
    ).read_text(encoding="utf-8")
    assert "TELEMETRY_TEMP_INVALID_DC     INT16_MIN" in header
    assert "TELEMETRY_PRESSURE_INVALID_CH ((uint16_t)0xFFFEu)" in header
    assert "TELEMETRY_ACCEL_INVALID_CMS2  INT16_MIN" in header
    assert "TELEMETRY_UV_INVALID          ((uint8_t)0xFEu)" in header
    assert "TELEMETRY_LUX_INVALID         ((uint16_t)0xFFFEu)" in header
    assert "uint8_t acoustic_valid;" in header
    assert "void telemetry_input_init(telemetry_input_t* out)" in source
    assert "10u + power" in source
    assert "telemetry_input_init(&ti);" in main_source
    assert "mic_acoustic_detect(&ti.acoustic_event) ? 1u : 0u" in main_source
    assert "uvi >= UINT8_MAX - 1u" in conversion
    assert "raw >= 109224u" in conversion

    print(
        "PASS: failed environmental/acoustic sensors are explicit nulls, "
        "optical saturation stays distinct, and invalid status/axis states "
        "fail closed"
    )


if __name__ == "__main__":
    main()
