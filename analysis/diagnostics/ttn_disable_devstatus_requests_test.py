#!/usr/bin/env python3
"""Fail-closed regression for the guarded TTN DevStatusReq update."""

from __future__ import annotations

import json

from ttn_disable_devstatus_requests import setting_state, update_body
from ttn_mac_settings_audit import safe_report


def state(count: object, elapsed: object) -> str:
    value = safe_report("na", 200, {
        "mac_settings": {
            "status_count_periodicity": count,
            "status_time_periodicity": elapsed,
        },
    })
    return setting_state(value)


def main() -> None:
    assert state(None, None) == "defaults_active"
    assert state(0, "0s") == "disabled"
    assert state(1, "0s") == "unexpected"
    assert state(0, "1s") == "unexpected"
    assert setting_state(safe_report("na", 403, {})) == "unreadable"

    body = json.loads(update_body())
    assert body == {
        "end_device": {
            "mac_settings": {
                "status_count_periodicity": 0,
                "status_time_periodicity": "0s",
            },
        },
        "field_mask": {"paths": [
            "mac_settings.status_count_periodicity",
            "mac_settings.status_time_periodicity",
        ]},
    }
    rendered = repr(body)
    assert "api_key" not in rendered
    assert "device_id" not in rendered
    print("PASS: guarded TTN DevStatusReq update is narrow and fail-closed")


if __name__ == "__main__":
    main()
