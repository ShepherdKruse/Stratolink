#!/usr/bin/env python3
"""Adversarial passive Meshtastic evidence validation tests."""

from __future__ import annotations

from copy import deepcopy

from validate_meshtastic_passive import validate


def fixture() -> list[dict]:
    return [
        {
            "event": "meshtastic_passive_monitor_start",
            "region": "US",
            "modem_preset": "LONG_FAST",
            "use_preset": True,
            "live_radio_age_window_seconds": [-5.0, 30.0],
        },
        {
            "event": "meshtastic_packet_metadata",
            "classification": "cached_history",
            "source_opaque": "cached",
            "rx_rssi_dbm": -90,
            "rx_snr_db": 2.0,
            "radio_age_seconds": 3600.0,
            "via_mqtt": False,
        },
        {
            "event": "meshtastic_packet_metadata",
            "classification": "live_rf",
            "source_opaque": "opaque-a",
            "rx_rssi_dbm": -111,
            "rx_snr_db": -14.25,
            "radio_age_seconds": 1.25,
            "via_mqtt": False,
        },
        {
            "event": "meshtastic_passive_monitor_end",
            "elapsed_seconds": 3600.0,
            "packet_count": 2,
            "live_rf_packet_count": 1,
            "local_origin_rf_echo_count": 0,
            "live_rf_opaque_source_count": 1,
        },
    ]


def main() -> None:
    good = validate(
        fixture(), minimum_live_rf=1, minimum_elapsed_seconds=3590
    )
    assert good["passed"], good
    assert good["observed"]["cached_history_packets_excluded"] == 1

    stale_live = fixture()
    stale_live[2]["radio_age_seconds"] = 31.0
    rejected = validate(
        stale_live, minimum_live_rf=1, minimum_elapsed_seconds=3590
    )
    assert not rejected["passed"]
    assert any("cached" in value for value in rejected["failures"])

    false_count = deepcopy(fixture())
    false_count[-1]["live_rf_packet_count"] = 2
    rejected = validate(
        false_count, minimum_live_rf=1, minimum_elapsed_seconds=3590
    )
    assert not rejected["passed"]
    assert "live RF count mismatch" in rejected["failures"]

    short = validate(
        fixture(), minimum_live_rf=1, minimum_elapsed_seconds=3601
    )
    assert not short["passed"]
    print("PASS: passive Meshtastic validation rejects cached/short/count claims")


if __name__ == "__main__":
    main()
