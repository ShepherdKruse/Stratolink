#!/usr/bin/env python3
"""Read-only, secret-free audit of TTN RX settings for StratoLink-2."""

from __future__ import annotations

import json

from ttn_inventory import get_json, load_values


TARGETS = (
    ("nam1.cloud.thethings.network", "TTN_NA_API_KEY", "stratolink", "stratolink-2"),
    ("nam1.cloud.thethings.network", "TTN_APP_KEY", "stratolink", "stratolink-2"),
    ("eu1.cloud.thethings.network", "TTN_EU_API_KEY", "eu-stratolink", "stratolink-2-eu"),
    ("eu1.cloud.thethings.network", "TTN_AS_API_KEY", "as-stratolink", "stratolink-2-as"),
)


def main() -> None:
    values = load_values()
    output: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for host, key_name, app_id, device_id in TARGETS:
        key = values.get(key_name, "")
        target = (host, app_id, device_id)
        if not key or target in seen:
            continue
        seen.add(target)
        status, detail = get_json(
            host,
            f"/ns/applications/{app_id}/devices/{device_id}"
            "?field_mask=frequency_plan_id,lorawan_version,"
            "lorawan_phy_version,mac_settings,"
            "mac_state.current_parameters",
            key,
        )
        current = detail.get("mac_state", {}).get("current_parameters", {})
        configured = detail.get("mac_settings", {})
        output.append(
            {
                "host": host,
                "application_id": app_id,
                "device_id": device_id,
                "status": status,
                "frequency_plan_id": detail.get("frequency_plan_id"),
                "lorawan_version": detail.get("lorawan_version"),
                "lorawan_phy_version": detail.get("lorawan_phy_version"),
                "rx1_delay": current.get("rx1_delay"),
                "rx1_data_rate_offset": current.get("rx1_data_rate_offset"),
                "rx2_data_rate_index": current.get("rx2_data_rate_index"),
                "rx2_frequency": current.get("rx2_frequency"),
                "configured_rx1_delay": configured.get("rx1_delay"),
                "configured_rx1_data_rate_offset": configured.get(
                    "rx1_data_rate_offset"
                ),
                "configured_rx2_data_rate_index": configured.get(
                    "rx2_data_rate_index"
                ),
                "configured_rx2_frequency": configured.get("rx2_frequency"),
                "configured_use_adr": configured.get("use_adr"),
                "configured_adr": configured.get("adr"),
            }
        )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
