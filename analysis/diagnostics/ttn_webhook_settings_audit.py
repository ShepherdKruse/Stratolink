#!/usr/bin/env python3
"""Read and redact StratoLink's regional TTN webhook configuration.

This intentionally omits URLs, paths, headers, credentials, device IDs, and
application IDs.  It exposes only whether each message class is enabled,
whether join-accept shares the uplink path, and the safe health counters needed
to diagnose TTN ``as.webhook.fail`` events.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from ttn_downlink_test import load_values
from ttn_inventory import get_json
from ttn_mac_settings_audit import TARGETS


FIELD_MASK = (
    "ids,format,uplink_message,join_accept,health_status,paused,queue"
)


def message_config(
    webhook: dict[str, object], key: str
) -> tuple[bool, str | None]:
    """Return enablement and comparable path without disclosing the path.

    ProtoJSON omits a scalar at its default value.  Consequently an enabled
    message whose path is the webhook base URL is serialized as ``{}``, while
    a disabled message omits the message key altogether.
    """
    if key not in webhook:
        return False, None
    value = webhook.get(key)
    if not isinstance(value, dict):
        return False, None
    path = value.get("path", "")
    return (True, path) if isinstance(path, str) else (True, None)


def safe_webhook(webhook: dict[str, object]) -> dict[str, object]:
    uplink_enabled, uplink = message_config(webhook, "uplink_message")
    join_enabled, join = message_config(webhook, "join_accept")
    health = webhook.get("health_status")
    if not isinstance(health, dict):
        health = {}
    unhealthy = health.get("unhealthy")
    if not isinstance(unhealthy, dict):
        unhealthy = {}
    queue = webhook.get("queue")
    if not isinstance(queue, dict):
        queue = {}
    ids = webhook.get("ids")
    if not isinstance(ids, dict):
        ids = {}
    webhook_id = ids.get("webhook_id")
    return {
        # An ordinal is added by the caller.  Retain only whether an ID exists
        # so an incomplete registry object fails visibly without disclosing it.
        "webhook_id_present": isinstance(webhook_id, str) and bool(webhook_id),
        "format": webhook.get("format"),
        "uplink_enabled": uplink_enabled,
        "join_accept_enabled": join_enabled,
        "join_accept_shares_uplink_path": (
            uplink_enabled and join_enabled and uplink == join
        ),
        "paused": webhook.get("paused", False),
        "queue_enabled": queue.get("enabled"),
        "healthy": "healthy" in health,
        "unhealthy": "unhealthy" in health,
        "failed_attempts": unhealthy.get("failed_attempts"),
        "last_failed_attempt_at": unhealthy.get("last_failed_attempt_at"),
    }


def safe_region(
    region: str, status: int, remote: dict[str, object]
) -> dict[str, object]:
    webhooks = remote.get("webhooks")
    if not isinstance(webhooks, list):
        webhooks = []
    safe = [
        {"ordinal": index, **safe_webhook(item)}
        for index, item in enumerate(webhooks, start=1)
        if isinstance(item, dict)
    ]
    return {
        "region": region,
        "http_status": status,
        "readable": status == 200,
        "webhook_count": len(safe),
        "webhooks": safe,
    }


def main() -> None:
    values = load_values()
    rows: list[dict[str, object]] = []
    for region, host, key_name, app_id, _device_id in TARGETS:
        key = values.get(key_name, "")
        if not key:
            rows.append(safe_region(region, 0, {}))
            continue
        status, remote = get_json(
            host,
            f"/as/webhooks/{quote(app_id, safe='')}"
            f"?field_mask={quote(FIELD_MASK, safe=',')}&limit=100",
            key,
        )
        rows.append(safe_region(region, status, remote))

    print(json.dumps({
        "regions": rows,
        "all_regions_readable": all(row["readable"] is True for row in rows),
        "scope": (
            "read-only TTN webhook message enablement and health; URLs, paths, "
            "headers, credentials, webhook/application/device IDs, payloads, "
            "sessions, and counters are excluded"
        ),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
