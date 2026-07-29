#!/usr/bin/env python3
"""Disable unsupported TTN DevStatusReq scheduling for StratoLink-2.

The flight stack authenticates downlink FOpts but deliberately does not
execute MAC commands.  Leaving the Network Server defaults active therefore
causes a DevStatusReq after uplinks that can never receive DevStatusAns.

This wrapper is check-only unless ``--apply`` is supplied.  Before any write
it reads all three regional registrations and refuses any state other than
the known unset defaults or the exact disabled values.  Output is redacted.
"""

from __future__ import annotations

import argparse
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from ttn_inventory import get_json, load_values
from ttn_mac_settings_audit import FIELD_MASK, TARGETS, safe_report


UPDATE_PATHS = (
    "mac_settings.status_count_periodicity",
    "mac_settings.status_time_periodicity",
)


def setting_state(report: dict[str, object]) -> str:
    if report.get("readable") is not True:
        return "unreadable"
    settings = report.get("mac_settings")
    if not isinstance(settings, dict):
        return "unexpected"
    count = settings.get("status_count_periodicity")
    elapsed = settings.get("status_time_periodicity")
    if count is None and elapsed is None:
        return "defaults_active"
    if count == 0 and elapsed == "0s":
        return "disabled"
    return "unexpected"


def update_body() -> bytes:
    return json.dumps({
        "end_device": {
            "mac_settings": {
                "status_count_periodicity": 0,
                "status_time_periodicity": "0s",
            },
        },
        "field_mask": {"paths": list(UPDATE_PATHS)},
    }, separators=(",", ":")).encode("utf-8")


def put_disabled(
    host: str, app_id: str, device_id: str, api_key: str
) -> int:
    request = Request(
        f"https://{host}/api/v3/ns/applications/{app_id}/devices/{device_id}",
        data=update_body(),
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


def read_target(
    region: str, host: str, app_id: str, device_id: str, api_key: str
) -> dict[str, object]:
    status, remote = get_json(
        host,
        f"/ns/applications/{app_id}/devices/{device_id}"
        f"?field_mask={FIELD_MASK}",
        api_key,
    )
    report = safe_report(region, status, remote)
    report["setting_state"] = setting_state(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    values = load_values()
    records: list[tuple[tuple[str, str, str, str, str], dict[str, object]]] = []

    for target in TARGETS:
        region, host, key_name, app_id, device_id = target
        key = values.get(key_name, "")
        report = (
            read_target(region, host, app_id, device_id, key)
            if key else safe_report(region, 0, {})
        )
        report["setting_state"] = setting_state(report)
        records.append((target, report))

    preflight_ok = all(
        report["setting_state"] in ("defaults_active", "disabled")
        for _, report in records
    )
    output: dict[str, object] = {
        "mode": "apply" if args.apply else "check_only",
        "preflight_ok": preflight_ok,
        "regions": [
            {
                "region": report["region"],
                "http_status": report["http_status"],
                "setting_state": report["setting_state"],
            }
            for _, report in records
        ],
        "scope": (
            "only TTN Network Server DevStatusReq count/time periodicities; "
            "no device identity, key, session, counter, or payload is emitted"
        ),
    }
    if not preflight_ok:
        print(json.dumps(output, indent=2, sort_keys=True))
        raise SystemExit("refusing unexpected or unreadable TTN state")
    if not args.apply:
        print(json.dumps(output, indent=2, sort_keys=True))
        return

    applied: list[dict[str, object]] = []
    for target, before in records:
        region, host, key_name, app_id, device_id = target
        if before["setting_state"] == "disabled":
            applied.append({"region": region, "status": "already_disabled"})
            continue
        status = put_disabled(
            host, app_id, device_id, values[key_name]
        )
        if status != 200:
            applied.append({
                "region": region,
                "status": "write_failed",
                "http_status": status,
            })
            output["applied"] = applied
            print(json.dumps(output, indent=2, sort_keys=True))
            raise SystemExit(f"{region} update failed with HTTP {status}")
        after = read_target(
            region, host, app_id, device_id, values[key_name]
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
        })

    output["applied"] = applied
    output["passed"] = all(
        row["status"] in ("already_disabled", "updated_and_verified")
        for row in applied
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
