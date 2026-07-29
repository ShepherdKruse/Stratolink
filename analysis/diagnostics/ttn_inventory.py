#!/usr/bin/env python3
"""Read-only inventory of the regional TTN applications used by StratoLink.

API keys stay in firmware/test/.ttn_keys. Output intentionally excludes keys,
root keys, session keys, and decoded payload bytes.
"""

from __future__ import annotations

import json
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import certifi


ROOT = Path(__file__).resolve().parents[2]
KEY_FILE = ROOT / "firmware" / "test" / ".ttn_keys"

REGIONS = {
    "na_supplied": ("nam1.cloud.thethings.network", "TTN_NA_API_KEY"),
    "na_local": ("nam1.cloud.thethings.network", "TTN_APP_KEY"),
    "eu": ("eu1.cloud.thethings.network", "TTN_EU_API_KEY"),
    "as_eu1": ("eu1.cloud.thethings.network", "TTN_AS_API_KEY"),
    "as_au1": ("au1.cloud.thethings.network", "TTN_AS_API_KEY"),
}

APP_CANDIDATES = (
    "stratolink",
    "stratolink-2",
    "na-stratolink",
    "us-stratolink",
    "stratolink-na",
    "stratolink-us",
    "eu-stratolink",
    "stratolink-2-eu",
    "as-stratolink",
    "stratolink-as",
    "stratolink-2-as",
    "stratolink-2-au",
    "asia-stratolink",
)


def load_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in KEY_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def get_json(host: str, path: str, api_key: str) -> tuple[int, dict]:
    request = Request(
        f"https://{host}/api/v3{path}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=20, context=context) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            body = json.load(exc)
        except Exception:
            body = {}
        return exc.code, body


def main() -> None:
    values = load_values()
    inventory: dict[str, dict] = {}
    for region, (host, key_name) in REGIONS.items():
        api_key = values.get(key_name, "")
        found: list[dict] = []
        errors: list[dict] = []
        if not api_key:
            inventory[region] = {"host": host, "error": "missing local API key"}
            continue
        list_status, listed = get_json(
            host,
            "/applications?field_mask=ids,name&limit=100",
            api_key,
        )
        listed_ids = [
            app.get("ids", {}).get("application_id")
            for app in listed.get("applications", [])
            if app.get("ids", {}).get("application_id")
        ]
        candidates = tuple(dict.fromkeys((*listed_ids, *APP_CANDIDATES)))
        for app_id in candidates:
            status, app = get_json(
                host,
                f"/applications/{app_id}?field_mask=ids,name",
                api_key,
            )
            if status == 200:
                dev_status, devices = get_json(
                    host,
                    f"/applications/{app_id}/devices"
                    "?field_mask=ids,name&limit=100",
                    api_key,
                )
                safe_devices = []
                if dev_status == 200:
                    for device in devices.get("end_devices", []):
                        ids = device.get("ids", {})
                        device_id = ids.get("device_id")
                        detail_status, detail = get_json(
                            host,
                            f"/ns/applications/{app_id}/devices/{device_id}"
                            "?field_mask=frequency_plan_id,supports_join,"
                            "lorawan_version,lorawan_phy_version",
                            api_key,
                        )
                        if detail_status != 200:
                            detail = {}
                        safe_devices.append(
                            {
                                "device_id": device_id,
                                "dev_eui": ids.get("dev_eui"),
                                "name": device.get("name"),
                                "detail_status": detail_status,
                                "frequency_plan_id": detail.get(
                                    "frequency_plan_id"
                                ),
                                "supports_join": detail.get("supports_join"),
                                "lorawan_version": detail.get("lorawan_version"),
                                "lorawan_phy_version": detail.get(
                                    "lorawan_phy_version"
                                ),
                            }
                        )
                found.append(
                    {
                        "application_id": app.get("ids", {}).get(
                            "application_id", app_id
                        ),
                        "name": app.get("name"),
                        "devices_status": dev_status,
                        "devices_error": (
                            devices.get("message") if dev_status != 200 else None
                        ),
                        "devices": safe_devices,
                    }
                )
            elif status not in (403, 404):
                errors.append({"application_id": app_id, "status": status})
        inventory[region] = {
            "host": host,
            "list_status": list_status,
            "list_error": listed.get("message") if list_status != 200 else None,
            "applications": found,
            "errors": errors,
        }
    print(json.dumps(inventory, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
