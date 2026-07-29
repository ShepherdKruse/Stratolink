#!/usr/bin/env python3
"""Align the EU TTN RX2 override with the EU_863_870_TTN SF9 plan.

This is intentionally narrow and preconditioned: it only changes the known
StratoLink-2 EU device, only from DR0 to DR3, only when its frequency plan and
RX2 frequency already match the expected TTN EU plan. API keys are read from
the ignored local key file and are never printed.
"""

from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import certifi

from ttn_inventory import get_json, load_values


HOST = "eu1.cloud.thethings.network"
APP_ID = "eu-stratolink"
DEVICE_ID = "stratolink-2-eu"
PATH = f"/ns/applications/{APP_ID}/devices/{DEVICE_ID}"


def main() -> None:
    api_key = load_values().get("TTN_EU_API_KEY", "")
    if not api_key:
        raise SystemExit("missing TTN_EU_API_KEY")

    mask = (
        "frequency_plan_id,mac_settings.rx2_data_rate_index,"
        "mac_settings.rx2_frequency"
    )
    status, before = get_json(HOST, f"{PATH}?field_mask={mask}", api_key)
    if status != 200:
        raise SystemExit(f"read failed with HTTP {status}")

    settings = before.get("mac_settings", {})
    actual = {
        "frequency_plan_id": before.get("frequency_plan_id"),
        "rx2_data_rate_index": settings.get("rx2_data_rate_index"),
        "rx2_frequency": settings.get("rx2_frequency"),
    }
    expected_before = {
        "frequency_plan_id": "EU_863_870_TTN",
        "rx2_data_rate_index": 0,
        "rx2_frequency": "869525000",
    }
    expected_after = {**expected_before, "rx2_data_rate_index": 3}

    if actual == expected_after:
        print(json.dumps({"status": "already_aligned", **actual}, sort_keys=True))
        return
    if actual != expected_before:
        raise SystemExit(
            "refusing unexpected TTN state: " + json.dumps(actual, sort_keys=True)
        )

    body = json.dumps(
        {
            "end_device": {
                "mac_settings": {
                    "rx2_data_rate_index": 3,
                }
            },
            "field_mask": {
                "paths": ["mac_settings.rx2_data_rate_index"],
            },
        }
    ).encode()
    request = Request(
        f"https://{HOST}/api/v3{PATH}",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=20, context=context) as response:
            if response.status != 200:
                raise SystemExit(f"update failed with HTTP {response.status}")
            json.load(response)
    except HTTPError as error:
        message = error.read().decode(errors="replace")
        raise SystemExit(f"update failed with HTTP {error.code}: {message}") from error

    status, after = get_json(HOST, f"{PATH}?field_mask={mask}", api_key)
    updated = after.get("mac_settings", {})
    verified = {
        "frequency_plan_id": after.get("frequency_plan_id"),
        "rx2_data_rate_index": updated.get("rx2_data_rate_index"),
        "rx2_frequency": updated.get("rx2_frequency"),
    }
    if status != 200 or verified != expected_after:
        raise SystemExit(
            "write did not verify: " + json.dumps(verified, sort_keys=True)
        )
    print(json.dumps({"status": "updated_and_verified", **verified}, sort_keys=True))


if __name__ == "__main__":
    main()
