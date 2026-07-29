#!/usr/bin/env python3
"""Fail-closed output boundary for the TTN MAC-settings audit."""

from __future__ import annotations

from ttn_mac_settings_audit import FIELD_MASK, TARGETS, safe_report


def main() -> None:
    remote = {
        "ids": {"dev_eui": "secret"},
        "session": {"keys": "secret"},
        "mac_settings": {
            "status_count_periodicity": 1,
            "status_time_periodicity": "0s",
            "use_adr": {"value": False},
            "schedule_downlinks": {"value": True},
            "unrequested_secret": "secret",
        },
        "mac_state": {
            "last_dev_status_f_cnt_up": 109,
            "session_keys": "secret",
        },
        "last_dev_status_received_at": None,
    }
    report = safe_report("na", 200, remote)
    rendered = repr(report)
    assert report["region"] == "na"
    assert report["readable"] is True
    assert report["mac_settings"]["status_count_periodicity"] == 1
    assert report["mac_state"]["last_dev_status_f_cnt_up"] == 109
    assert "secret" not in rendered
    assert "ids" not in rendered
    assert "status_count_periodicity" in FIELD_MASK
    assert "last_dev_status_received_at" in FIELD_MASK

    failed = safe_report("eu", 403, {"message": "credential detail"})
    assert failed["readable"] is False
    assert failed["region"] == "eu"
    assert "credential detail" not in repr(failed)
    assert tuple(target[0] for target in TARGETS) == ("na", "eu", "as")
    print("PASS: TTN MAC-settings audit is read-only and redacted")


if __name__ == "__main__":
    main()
