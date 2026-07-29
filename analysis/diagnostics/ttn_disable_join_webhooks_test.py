#!/usr/bin/env python3
"""Fail-closed regression for the guarded join-webhook update."""

from __future__ import annotations

import json

from ttn_disable_join_webhooks import clear_body, raw_webhook_id, webhook_state
from ttn_webhook_settings_audit import safe_region


def report(webhook: dict[str, object], status: int = 200) -> dict[str, object]:
    return safe_region("na", status, {"webhooks": [webhook]})


def main() -> None:
    same = {
        "ids": {"webhook_id": "hook"},
        "uplink_message": {},
        "join_accept": {},
        "paused": False,
    }
    assert webhook_state(report(same)) == "join_collides_with_uplink"
    assert webhook_state(report({
        **same, "join_accept": {"path": "/dedicated-join"},
    })) == "unexpected"
    assert webhook_state(report({
        "ids": {"webhook_id": "hook"},
        "uplink_message": {},
        "paused": False,
    })) == "disabled"
    assert webhook_state(report({
        "ids": {"webhook_id": "hook"},
        "join_accept": {},
        "paused": False,
    })) == "unexpected"
    assert webhook_state(report({**same, "paused": True})) == "unexpected"
    assert webhook_state(report(same, 403)) == "unreadable"
    assert webhook_state(safe_region("na", 200, {"webhooks": []})) == "unexpected"
    assert webhook_state(safe_region("na", 200, {"webhooks": [same, same]})) == "unexpected"

    raw = [{"ids": {"webhook_id": "hook"}}]
    assert raw_webhook_id(raw) == "hook"
    assert raw_webhook_id([]) is None
    body = json.loads(clear_body("private-app", "private-hook"))
    assert body == {
        "webhook": {
            "ids": {
                "application_ids": {"application_id": "private-app"},
                "webhook_id": "private-hook",
            },
        },
        "field_mask": {"paths": ["join_accept"]},
    }
    assert "join_accept" not in body["webhook"]
    assert "uplink_message" not in body["webhook"]
    print("PASS: join webhook update is single-field, guarded, and redacted")


if __name__ == "__main__":
    main()
