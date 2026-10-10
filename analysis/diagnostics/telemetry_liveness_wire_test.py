#!/usr/bin/env python3
"""Cross-check the two Python decoders for telemetry-v3 liveness packing."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import struct
import sys

from ttn_soak_monitor import (
    TELEMETRY_FIELDS,
    TELEMETRY_FORMAT,
    decode_fix_liveness_word as monitor_decode_word,
    decode_telemetry as monitor_decode,
)


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "firmware/test"))
from ttn_listener import (  # noqa: E402
    decode_fix_liveness_word as listener_decode_word,
    decode_telemetry as listener_decode,
)

audit_spec = importlib.util.spec_from_file_location(
    "ttn_vs_supabase_audit",
    ROOT / "analysis/visualization/ttn_vs_supabase_audit.py",
)
assert audit_spec is not None and audit_spec.loader is not None
audit_module = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit_module)


def encoded(word: int) -> str:
    values = {
        "lat_e7": 0,
        "lon_e7": 0,
        "altitude_m": 0,
        "temperature_deci_c": 225,
        "pressure_deci_hpa": 10127,
        "solar_mv": 1026,
        "vstor_mv": 4660,
        "speed_cm_s": 0,
        "heading_cdeg": 0,
        "satellites": 0,
        "accel_x_cms2": 78,
        "accel_y_cms2": 109,
        "accel_z_cms2": 1019,
        "uv_index": 0,
        "ambient_lux": 511,
        "acoustic_event": 0,
    }
    base = struct.pack(
        TELEMETRY_FORMAT, *(values[field] for field in TELEMETRY_FIELDS)
    )
    wire = base + bytes((17,)) + word.to_bytes(2, "big") + bytes((0, 0))
    assert len(wire) == 40
    return base64.b64encode(wire).decode("ascii")


def assert_word(word: int, expected: dict[str, object]) -> None:
    assert monitor_decode_word(word) == expected
    assert listener_decode_word(word) == expected
    size, monitor = monitor_decode(encoded(word))
    listener = listener_decode(encoded(word))
    assert size == 40 and monitor is not None and listener is not None
    for field, value in expected.items():
        assert monitor[field] == value
        assert listener[field] == value
    audit = audit_module.decode_payload(encoded(word))
    assert audit is not None
    assert audit["wire_version"] == expected["telemetry_version"]
    assert audit["fix_age_min"] == expected["gps_fix_age_min"]
    assert (
        audit.get("server_proof_count_mod8") ==
        expected["server_proof_count_mod8"]
    )
    assert (
        audit.get("server_qualified_miss_streak") ==
        expected["server_qualified_miss_streak"]
    )
    assert (
        audit.get("server_recovery_parity") ==
        expected["server_recovery_parity"]
    )


def main() -> None:
    assert_word(0x1234, {
        "telemetry_version": 2,
        "gps_fix_age_min": 0x1234,
        "server_proof_count_mod8": None,
        "server_qualified_miss_streak": None,
        "server_recovery_parity": None,
    })
    assert_word(0xFFFF, {
        "telemetry_version": 2,
        "gps_fix_age_min": None,
        "server_proof_count_mod8": None,
        "server_qualified_miss_streak": None,
        "server_recovery_parity": None,
    })
    # The approved marker intentionally repurposes high-bit legacy ages.
    # Only v2 ages 0..0x7FFF and the exact 0xFFFF sentinel are preserved.
    assert_word(0x9234, {
        "telemetry_version": 3,
        "gps_fix_age_min": 0x34,
        "server_proof_count_mod8": 1,
        "server_qualified_miss_streak": 0,
        "server_recovery_parity": 1,
    })
    assert_word(0xDB23, {
        "telemetry_version": 3,
        "gps_fix_age_min": 0x123,
        "server_proof_count_mod8": 5,
        "server_qualified_miss_streak": 2,
        "server_recovery_parity": 1,
    })
    assert_word(0xEFFF, {
        "telemetry_version": 3,
        "gps_fix_age_min": None,
        "server_proof_count_mod8": 6,
        "server_qualified_miss_streak": 3,
        "server_recovery_parity": 1,
    })
    assert_word(0xFBFF, {
        "telemetry_version": 3,
        "gps_fix_age_min": None,
        "server_proof_count_mod8": 7,
        "server_qualified_miss_streak": 2,
        "server_recovery_parity": 1,
    })

    unavailable_mic = bytearray(base64.b64decode(encoded(0x8000)))
    unavailable_mic[34] = 14  # microphone unavailable at CRITICAL tier
    unavailable_encoded = base64.b64encode(unavailable_mic).decode("ascii")
    _, monitor = monitor_decode(unavailable_encoded)
    listener = listener_decode(unavailable_encoded)
    assert monitor is not None and listener is not None
    assert monitor["power_tier"] == listener["power_tier"] == 4
    assert monitor["acoustic_event"] is listener["acoustic_event"] is None
    print("PASS: monitor/listener preserve legacy v2 and decode v3 liveness")


if __name__ == "__main__":
    main()
