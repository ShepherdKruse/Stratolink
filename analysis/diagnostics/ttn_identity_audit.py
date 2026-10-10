#!/usr/bin/env python3
"""Compare private firmware OTAA identities with TTN without revealing them.

Output contains only presence/match booleans and HTTP status codes. No EUI,
AppKey, API key, root key, or session key value is printed.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import re

from ttn_inventory import ROOT, get_json, load_values


SECRETS = ROOT / "firmware" / "include" / "secrets.h"
TARGETS = (
    ("na", "nam1.cloud.thethings.network", "TTN_NA_API_KEY",
     "stratolink", "stratolink-2",
     "LORAWAN_DEV_EUI_US", "LORAWAN_APP_KEY_US"),
    ("eu", "eu1.cloud.thethings.network", "TTN_EU_API_KEY",
     "eu-stratolink", "stratolink-2-eu",
     "LORAWAN_DEV_EUI_EU", "LORAWAN_APP_KEY_EU"),
    ("as", "eu1.cloud.thethings.network", "TTN_AS_API_KEY",
     "as-stratolink", "stratolink-2-as",
     "LORAWAN_DEV_EUI_AS", "LORAWAN_APP_KEY_AS"),
)


def direct_string_macros(path: Path) -> dict[str, str]:
    macros: dict[str, str] = {}
    pattern = re.compile(
        r'^\s*#define\s+([A-Z0-9_]+)\s+"([0-9A-Fa-f]*)"\s*(?://.*)?$'
    )
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(raw)
        if match:
            macros[match.group(1)] = match.group(2)
    return macros


def wire_bytes(value: object, size: int) -> bytes | None:
    if not isinstance(value, str):
        return None
    compact = value.replace("-", "").replace(":", "").strip()
    if len(compact) == size * 2 and all(c in "0123456789abcdefABCDEF" for c in compact):
        return bytes.fromhex(compact)
    try:
        decoded = base64.b64decode(compact, validate=True)
    except Exception:
        return None
    return decoded if len(decoded) == size else None


def main() -> None:
    local = direct_string_macros(SECRETS)
    api_keys = load_values()
    join_eui = wire_bytes(local.get("LORAWAN_APP_EUI"), 8)
    rows: list[dict[str, object]] = []

    for (
        region, host, api_key_name, app_id, device_id, dev_eui_name, app_key_name
    ) in TARGETS:
        local_dev_eui = wire_bytes(local.get(dev_eui_name), 8)
        local_app_key = wire_bytes(local.get(app_key_name), 16)
        api_key = api_keys.get(api_key_name, "")
        if not api_key:
            rows.append({
                "region": region,
                "status": "missing_api_key",
                "local_identity_complete": bool(
                    local_dev_eui and local_app_key and join_eui
                ),
            })
            continue

        status, remote = get_json(
            host,
            f"/js/applications/{app_id}/devices/{device_id}"
            "?field_mask=ids.dev_eui,ids.join_eui,root_keys.app_key.key",
            api_key,
        )
        ids = remote.get("ids", {}) if status == 200 else {}
        root_keys = remote.get("root_keys", {}) if status == 200 else {}
        remote_app_key = root_keys.get("app_key", {})
        if isinstance(remote_app_key, dict):
            remote_app_key = remote_app_key.get("key")
        remote_dev_eui = wire_bytes(ids.get("dev_eui"), 8)
        remote_join_eui = wire_bytes(ids.get("join_eui"), 8)
        remote_key = wire_bytes(remote_app_key, 16)

        rows.append({
            "region": region,
            "status": status,
            "local_identity_complete": bool(
                local_dev_eui and local_app_key and join_eui
            ),
            "remote_identity_readable": bool(
                remote_dev_eui and remote_join_eui
            ),
            "remote_root_key_readable": remote_key is not None,
            "dev_eui_matches": (
                local_dev_eui == remote_dev_eui
                if local_dev_eui and remote_dev_eui else None
            ),
            "join_eui_matches": (
                join_eui == remote_join_eui
                if join_eui and remote_join_eui else None
            ),
            "app_key_matches": (
                local_app_key == remote_key
                if local_app_key and remote_key else None
            ),
        })

    au_complete = bool(
        wire_bytes(local.get("LORAWAN_DEV_EUI_AU"), 8)
        and wire_bytes(local.get("LORAWAN_APP_KEY_AU"), 16)
    )
    print(json.dumps({
        "regional_identities": rows,
        "au_local_identity_complete": au_complete,
        "all_configured_regions_match": all(
            row.get("status") == 200
            and row.get("local_identity_complete") is True
            and row.get("dev_eui_matches") is True
            and row.get("join_eui_matches") is True
            and row.get("app_key_matches") is True
            for row in rows
        ),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
