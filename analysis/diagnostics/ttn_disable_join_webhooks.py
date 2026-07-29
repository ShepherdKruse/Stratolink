#!/usr/bin/env python3
"""Disable unused TTN join-accept delivery without changing uplink delivery.

The production route accepts authenticated application uplinks only.  TTN's
join-accept message class is separately configurable; sending it to the same
path produces ``as.webhook.fail`` without storing useful data.  This wrapper is
check-only unless ``--apply`` is supplied and reports no identifiers, paths,
URLs, headers, credentials, or payloads.
"""

from __future__ import annotations

import argparse
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import certifi

from ttn_downlink_test import load_values
from ttn_inventory import get_json
from ttn_mac_settings_audit import TARGETS
from ttn_webhook_settings_audit import FIELD_MASK, safe_region


UPDATE_PATHS = ("join_accept",)


def webhook_state(report: dict[str, object]) -> str:
    if report.get("readable") is not True:
        return "unreadable"
    webhooks = report.get("webhooks")
    if not isinstance(webhooks, list) or len(webhooks) != 1:
        return "unexpected"
    webhook = webhooks[0]
    if not isinstance(webhook, dict):
        return "unexpected"
    if (
        webhook.get("webhook_id_present") is not True
        or webhook.get("uplink_enabled") is not True
        or webhook.get("paused") is not False
    ):
        return "unexpected"
    if webhook.get("join_accept_enabled") is False:
        return "disabled"
    if webhook.get("join_accept_shares_uplink_path") is True:
        return "join_collides_with_uplink"
    return "unexpected"


def clear_body(app_id: str, webhook_id: str) -> bytes:
    # With join_accept present in the field mask and absent from the replacement
    # webhook, protobuf FieldMask semantics clear only that message field.
    return json.dumps({
        "webhook": {
            "ids": {
                "application_ids": {"application_id": app_id},
                "webhook_id": webhook_id,
            },
        },
        "field_mask": {"paths": list(UPDATE_PATHS)},
    }, separators=(",", ":")).encode("utf-8")


def list_webhooks(
    region: str, host: str, app_id: str, api_key: str
) -> tuple[dict[str, object], list[dict[str, object]]]:
    status, remote = get_json(
        host,
        f"/as/webhooks/{quote(app_id, safe='')}"
        f"?field_mask={quote(FIELD_MASK, safe=',')}&limit=100",
        api_key,
    )
    raw = remote.get("webhooks")
    if not isinstance(raw, list):
        raw = []
    typed = [item for item in raw if isinstance(item, dict)]
    report = safe_region(region, status, {"webhooks": typed})
    report["setting_state"] = webhook_state(report)
    return report, typed


def put_cleared(
    host: str, app_id: str, webhook_id: str, api_key: str
) -> int:
    request = Request(
        f"https://{host}/api/v3/as/webhooks/"
        f"{quote(app_id, safe='')}/{quote(webhook_id, safe='')}",
        data=clear_body(app_id, webhook_id),
        method="PUT",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=20, context=context) as response:
            json.load(response)
            return response.status
    except HTTPError as error:
        return error.code
    except URLError:
        return 0


def raw_webhook_id(raw: list[dict[str, object]]) -> str | None:
    if len(raw) != 1:
        return None
    ids = raw[0].get("ids")
    if not isinstance(ids, dict):
        return None
    value = ids.get("webhook_id")
    return value if isinstance(value, str) and value else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    values = load_values()
    records: list[
        tuple[tuple[str, str, str, str, str], dict[str, object], list[dict[str, object]]]
    ] = []

    for target in TARGETS:
        region, host, key_name, app_id, _device_id = target
        key = values.get(key_name, "")
        if key:
            report, raw = list_webhooks(region, host, app_id, key)
        else:
            report, raw = safe_region(region, 0, {}), []
            report["setting_state"] = "unreadable"
        records.append((target, report, raw))

    preflight_ok = all(
        report["setting_state"] in ("join_collides_with_uplink", "disabled")
        and raw_webhook_id(raw) is not None
        for _target, report, raw in records
    )
    output: dict[str, object] = {
        "mode": "apply" if args.apply else "check_only",
        "preflight_ok": preflight_ok,
        "regions": [
            {
                "region": report["region"],
                "http_status": report["http_status"],
                "setting_state": report["setting_state"],
                "uplink_enabled": report["webhooks"][0]["uplink_enabled"]
                if report.get("webhooks") else None,
                "join_accept_enabled": report["webhooks"][0]["join_accept_enabled"]
                if report.get("webhooks") else None,
            }
            for _target, report, _raw in records
        ],
        "scope": (
            "only clears TTN Application Server join_accept on the single "
            "same-path webhook; uplink_message remains enabled; no URL, path, "
            "header, credential, webhook/application/device ID, payload, "
            "session, or counter is emitted"
        ),
    }
    if not preflight_ok:
        print(json.dumps(output, indent=2, sort_keys=True))
        raise SystemExit("refusing unexpected or unreadable TTN webhook state")
    if not args.apply:
        print(json.dumps(output, indent=2, sort_keys=True))
        return

    applied: list[dict[str, object]] = []
    for target, before, raw in records:
        region, host, key_name, app_id, _device_id = target
        if before["setting_state"] == "disabled":
            applied.append({"region": region, "status": "already_disabled"})
            continue
        webhook_id = raw_webhook_id(raw)
        assert webhook_id is not None
        status = put_cleared(host, app_id, webhook_id, values[key_name])
        if status != 200:
            applied.append({
                "region": region,
                "status": "write_failed",
                "http_status": status,
            })
            output["applied"] = applied
            print(json.dumps(output, indent=2, sort_keys=True))
            raise SystemExit(f"{region} update failed with HTTP {status}")
        after, _raw_after = list_webhooks(
            region, host, app_id, values[key_name]
        )
        if after["setting_state"] != "disabled":
            applied.append({
                "region": region,
                "status": "verification_failed",
                "http_status": after["http_status"],
                "setting_state": after["setting_state"],
            })
            output["applied"] = applied
            print(json.dumps(output, indent=2, sort_keys=True))
            raise SystemExit(f"{region} update did not verify")
        applied.append({
            "region": region,
            "status": "updated_and_verified",
            "http_status": after["http_status"],
            "uplink_enabled": after["webhooks"][0]["uplink_enabled"],
            "join_accept_enabled": after["webhooks"][0]["join_accept_enabled"],
        })

    output["applied"] = applied
    output["passed"] = all(
        row["status"] in ("already_disabled", "updated_and_verified")
        for row in applied
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
