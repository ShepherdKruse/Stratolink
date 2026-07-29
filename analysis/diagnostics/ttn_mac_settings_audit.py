#!/usr/bin/env python3
"""Read only the safe TTN MAC settings relevant to repeated DevStatusReq."""

from __future__ import annotations

import json

from ttn_downlink_test import load_values
from ttn_inventory import get_json


FIELD_MASK = (
    "mac_settings.status_count_periodicity,"
    "mac_settings.status_time_periodicity,"
    "mac_settings.use_adr,"
    "mac_settings.schedule_downlinks,"
    "mac_state.last_dev_status_f_cnt_up,"
    "last_dev_status_received_at"
)

TARGETS = (
    ("na", "nam1.cloud.thethings.network", "TTN_NA_API_KEY",
     "stratolink", "stratolink-2"),
    ("eu", "eu1.cloud.thethings.network", "TTN_EU_API_KEY",
     "eu-stratolink", "stratolink-2-eu"),
    ("as", "eu1.cloud.thethings.network", "TTN_AS_API_KEY",
     "as-stratolink", "stratolink-2-as"),
)


def safe_report(
    region: str, status: int, remote: dict[str, object]
) -> dict[str, object]:
    mac_settings = remote.get("mac_settings")
    mac_state = remote.get("mac_state")
    if not isinstance(mac_settings, dict):
        mac_settings = {}
    if not isinstance(mac_state, dict):
        mac_state = {}
    return {
        "region": region,
        "http_status": status,
        "readable": status == 200,
        "mac_settings": {
            "status_count_periodicity": mac_settings.get(
                "status_count_periodicity"
            ),
            "status_time_periodicity": mac_settings.get(
                "status_time_periodicity"
            ),
            "use_adr": mac_settings.get("use_adr"),
            "schedule_downlinks": mac_settings.get("schedule_downlinks"),
        },
        "mac_state": {
            "last_dev_status_f_cnt_up": mac_state.get(
                "last_dev_status_f_cnt_up"
            )
        },
        "last_dev_status_received_at": remote.get(
            "last_dev_status_received_at"
        ),
        "scope": (
            "read-only selected TTN Network Server MAC settings; no device "
            "identifier, EUI, key, session, counter payload, or application "
            "data is emitted"
        ),
    }


def main() -> None:
    values = load_values()
    rows: list[dict[str, object]] = []
    for region, host, key_name, app_id, device_id in TARGETS:
        api_key = values.get(key_name, "")
        if not api_key:
            rows.append(safe_report(region, 0, {}))
            continue
        status, remote = get_json(
            host,
            f"/ns/applications/{app_id}/devices/{device_id}"
            f"?field_mask={FIELD_MASK}",
            api_key,
        )
        rows.append(safe_report(region, status, remote))
    print(json.dumps({
        "regions": rows,
        "all_regions_readable": all(row["readable"] is True for row in rows),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
