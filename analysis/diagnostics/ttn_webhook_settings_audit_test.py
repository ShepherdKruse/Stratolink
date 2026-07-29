#!/usr/bin/env python3
"""Regression for redacted TTN webhook configuration evidence."""

from __future__ import annotations

from ttn_webhook_settings_audit import safe_region, safe_webhook


def main() -> None:
    raw = {
        "ids": {
            "application_ids": {"application_id": "private-app"},
            "webhook_id": "private-hook",
        },
        "base_url": "https://secret.invalid/token",
        "headers": {"Authorization": "Bearer secret"},
        "format": "json",
        "uplink_message": {"path": "/api/ttn-webhook"},
        "join_accept": {"path": "/api/ttn-webhook"},
        "paused": False,
        "queue": {"enabled": True},
        "health_status": {
            "unhealthy": {
                "failed_attempts": 3,
                "last_failed_attempt_at": "2026-07-27T09:40:33Z",
                "last_failed_attempt_details": {"body": "private"},
            },
        },
        "downlink_api_key": "secret",
    }
    safe = safe_webhook(raw)
    assert safe == {
        "webhook_id_present": True,
        "format": "json",
        "uplink_enabled": True,
        "join_accept_enabled": True,
        "join_accept_shares_uplink_path": True,
        "paused": False,
        "queue_enabled": True,
        "healthy": False,
        "unhealthy": True,
        "failed_attempts": 3,
        "last_failed_attempt_at": "2026-07-27T09:40:33Z",
    }
    rendered = repr(safe_region("na", 200, {"webhooks": [raw]}))
    for forbidden in (
        "private-app", "private-hook", "secret.invalid", "Bearer secret",
        "/api/ttn-webhook", "downlink_api_key", "last_failed_attempt_details",
    ):
        assert forbidden not in rendered

    assert safe_webhook({
        "ids": {"webhook_id": "x"},
        "uplink_message": {"path": ""},
    })["uplink_enabled"] is True
    assert safe_webhook({
        "ids": {"webhook_id": "x"},
        "uplink_message": {},
    })["uplink_enabled"] is True
    assert safe_webhook({
        "ids": {"webhook_id": "x"},
        "uplink_message": {},
        "join_accept": {},
    })["join_accept_shares_uplink_path"] is True
    assert safe_webhook({
        "ids": {"webhook_id": "x"},
    })["join_accept_enabled"] is False
    assert safe_region("eu", 403, {}) == {
        "region": "eu",
        "http_status": 403,
        "readable": False,
        "webhook_count": 0,
        "webhooks": [],
    }
    print("PASS: TTN webhook settings audit is read-only and redacted")


if __name__ == "__main__":
    main()
