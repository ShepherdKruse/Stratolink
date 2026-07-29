#!/usr/bin/env python3
"""Read-only, redacted TTN pending-MAC-request inventory."""

from __future__ import annotations

import json

from ttn_inventory import get_json, load_values
from ttn_mac_settings_audit import TARGETS


FIELD_MASK = "mac_state.pending_requests"


def safe_pending(region: str, status: int, remote: object) -> dict[str, object]:
    state = remote.get("mac_state", {}) if isinstance(remote, dict) else {}
    pending = state.get("pending_requests", []) if isinstance(state, dict) else []
    if not isinstance(pending, list):
        pending = []
    cids = sorted({
        row.get("cid")
        for row in pending
        if isinstance(row, dict) and isinstance(row.get("cid"), str)
    })
    return {
        "region": region,
        "http_status": status,
        "readable": status == 200,
        "pending_request_count": len(pending) if status == 200 else None,
        "pending_request_cids": cids if status == 200 else [],
        "scope": (
            "read-only MAC request count/CID inventory; no request payload, "
            "device identity, key, session, counter, or application data"
        ),
    }


def main() -> None:
    values = load_values()
    rows: list[dict[str, object]] = []
    for region, host, key_name, app_id, device_id in TARGETS:
        key = values.get(key_name, "")
        if not key:
            rows.append(safe_pending(region, 0, {}))
            continue
        status, remote = get_json(
            host,
            f"/ns/applications/{app_id}/devices/{device_id}"
            f"?field_mask={FIELD_MASK}",
            key,
        )
        rows.append(safe_pending(region, status, remote))
    print(json.dumps({
        "regions": rows,
        "all_regions_readable": all(row["readable"] is True for row in rows),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
