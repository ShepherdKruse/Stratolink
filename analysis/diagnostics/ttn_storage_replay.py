#!/usr/bin/env python3
"""Safely reconcile missed TTN Storage uplinks through the hardened webhook.

Dry-run is the default. Applying a replay is deliberately fail-closed:

* the TTN and webhook credentials come only from environment variables;
* no credential or application payload is printed;
* the target must first return HTTP 401 to an unauthenticated probe;
* every selected Storage row must have a valid device ID, DevAddr, TTN server
  timestamp, FCntUp, supported fPort, and base64 payload;
* the batch aborts on the first non-2xx replay response.

Do not use --apply until the ingest-integrity migration and hardened route are
deployed. The production legacy route does not provide replay idempotency.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import json
import os
import re
import ssl
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


ALLOWED_FPORTS = {1, 11, 12}
DEV_ADDR_RE = re.compile(r"^[0-9A-Fa-f]{8}$")
MAX_STORAGE_LIMIT = 1000
MINIMUM_WEBHOOK_SECRET_LENGTH = 32


def parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("missing or invalid TTN server received_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("missing or invalid TTN server received_at") from error
    if parsed.tzinfo is None:
        raise ValueError("TTN server received_at must include a timezone")
    return parsed


def parse_storage_stream(body: bytes) -> list[dict[str, Any]]:
    """Parse TTN's SSE/NDJSON Storage response without accepting junk lines."""
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(body.decode("utf-8").splitlines(), 1):
        line = raw.strip()
        if (
            not line
            or line.startswith(":")
            or line.startswith(("event:", "id:", "retry:"))
        ):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"invalid TTN Storage JSON on response line {line_number}"
            ) from error
        result = decoded.get("result", decoded)
        if not isinstance(result, dict):
            raise ValueError(
                f"invalid TTN Storage object on response line {line_number}"
            )
        rows.append(result)
    return rows


def validate_record(record: dict[str, Any]) -> tuple[str, str, int, int]:
    ids = record.get("end_device_ids")
    uplink = record.get("uplink_message")
    if not isinstance(ids, dict) or not isinstance(uplink, dict):
        raise ValueError("Storage row lacks end_device_ids or uplink_message")

    device_id = ids.get("device_id")
    dev_addr = ids.get("dev_addr")
    if not isinstance(device_id, str) or not 1 <= len(device_id) <= 64:
        raise ValueError("Storage row has invalid device_id")
    if not isinstance(dev_addr, str) or not DEV_ADDR_RE.fullmatch(dev_addr):
        raise ValueError(f"{device_id}: Storage row has invalid DevAddr")

    received_at = record.get("received_at")
    parse_timestamp(received_at)

    # TTN's API uses protobuf JSON mapping. An unsigned scalar at its default
    # value is omitted from JSON, so the first uplink in a fresh session can
    # legitimately have no ``f_cnt`` member while meaning FCntUp 0. Explicit
    # null and malformed/present values remain invalid.
    frame_counter = 0 if "f_cnt" not in uplink else uplink["f_cnt"]
    if (
        isinstance(frame_counter, bool)
        or not isinstance(frame_counter, int)
        or not 0 <= frame_counter <= 0xFFFFFFFF
    ):
        raise ValueError(f"{device_id}: Storage row has invalid FCntUp")

    f_port = uplink.get("f_port")
    if isinstance(f_port, bool) or f_port not in ALLOWED_FPORTS:
        raise ValueError(f"{device_id}: Storage row has unsupported fPort")

    encoded = uplink.get("frm_payload")
    if not isinstance(encoded, str):
        raise ValueError(f"{device_id}: Storage row lacks frm_payload")
    try:
        raw_payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{device_id}: Storage row has invalid base64") from error
    if not raw_payload:
        raise ValueError(f"{device_id}: Storage row has empty frm_payload")
    if f_port == 1 and len(raw_payload) not in {35, 40}:
        raise ValueError(
            f"{device_id}: fPort-1 payload is {len(raw_payload)} bytes, not 35 or 40"
        )
    if f_port == 11 and len(raw_payload) != 17:
        raise ValueError(
            f"{device_id}: fPort-11 payload is {len(raw_payload)} bytes, not 17"
        )
    if f_port == 12 and not 9 <= len(raw_payload) <= 53:
        raise ValueError(
            f"{device_id}: fPort-12 payload length is outside 9-53 bytes"
        )

    return device_id, str(received_at), frame_counter, int(f_port)


def select_device_records(
    records: list[dict[str, Any]], device_id: str
) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    skipped = 0
    for record in records:
        ids = record.get("end_device_ids")
        if isinstance(ids, dict) and ids.get("device_id") != device_id:
            skipped += 1
            continue
        validate_record(record)
        selected.append(record)
    selected.sort(key=lambda row: parse_timestamp(row["received_at"]))
    return selected, skipped


def request_bytes(request: Request, timeout: float = 30) -> tuple[int, bytes]:
    try:
        with urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        ) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()
    except URLError as error:
        raise SystemExit(f"network request failed: {error.reason}") from error


def fetch_storage(
    cluster: str,
    application_id: str,
    api_key: str,
    after: str,
    limit: int,
) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "after": after,
            "order": "received_at",
            "limit": str(limit),
        }
    )
    url = (
        f"https://{cluster}/api/v3/as/applications/"
        f"{quote(application_id, safe='')}/packages/storage/uplink_message?{query}"
    )
    status, body = request_bytes(
        Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
            },
        )
    )
    if status != 200:
        raise SystemExit(f"TTN Storage query failed with HTTP {status}")
    records = parse_storage_stream(body)
    if len(records) >= limit:
        raise SystemExit(
            "TTN Storage result reached the requested limit; narrow --after "
            "so no rows can be silently truncated"
        )
    return records


def require_safe_webhook_url(value: str) -> str:
    parsed = urlparse(value)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        parsed.scheme not in ({"http", "https"} if local else {"https"})
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "--webhook-url must be HTTPS (or loopback HTTP) without query/fragment"
        )
    return value.rstrip("/")


def prove_hardened_auth(webhook_url: str) -> None:
    """The legacy route returns 400 for {}, while the hardened route returns 401."""
    status, _ = request_bytes(
        Request(
            webhook_url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    )
    if status != 401:
        raise SystemExit(
            "refusing replay: unauthenticated webhook probe returned "
            f"HTTP {status}, expected 401 from the hardened route"
        )


def replay_records(
    records: list[dict[str, Any]],
    webhook_url: str,
    webhook_secret: str,
) -> tuple[int, int]:
    inserted = 0
    duplicates = 0
    for index, record in enumerate(records, 1):
        device_id, received_at, frame_counter, f_port = validate_record(record)
        status, body = request_bytes(
            Request(
                webhook_url,
                data=json.dumps(
                    record,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8"),
                method="POST",
                headers={
                    "Authorization": f"Bearer {webhook_secret}",
                    "Content-Type": "application/json",
                },
            )
        )
        if not 200 <= status <= 299:
            raise SystemExit(
                f"replay aborted at row {index}: {device_id} "
                f"received_at={received_at} fCnt={frame_counter} "
                f"fPort={f_port} returned HTTP {status}"
            )
        try:
            response = json.loads(body)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"replay aborted at row {index}: webhook returned invalid JSON"
            ) from error
        if response.get("duplicate") is True:
            duplicates += 1
        elif response.get("success") is True:
            inserted += 1
        else:
            raise SystemExit(
                f"replay aborted at row {index}: webhook did not confirm success"
            )
    return inserted, duplicates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cluster",
        default="nam1.cloud.thethings.network",
        help="TTN cluster hostname",
    )
    parser.add_argument("--application-id", default="stratolink")
    parser.add_argument("--device", default="stratolink-2")
    parser.add_argument(
        "--after",
        required=True,
        help="exclusive RFC3339 lower bound for TTN Storage",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--webhook-url")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="replay through a proven-hardened webhook; default is dry-run",
    )
    args = parser.parse_args()

    parse_timestamp(args.after)
    if not 1 <= args.limit <= MAX_STORAGE_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_STORAGE_LIMIT}")

    api_key = os.environ.get("TTN_API_KEY", "")
    if not api_key:
        raise SystemExit("TTN_API_KEY is required")

    records = fetch_storage(
        args.cluster,
        args.application_id,
        api_key,
        args.after,
        args.limit,
    )
    selected, skipped = select_device_records(records, args.device)
    counters = [validate_record(row)[2] for row in selected]
    times = [validate_record(row)[1] for row in selected]
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "application_id": args.application_id,
                "device_id": args.device,
                "storage_rows": len(records),
                "selected_rows": len(selected),
                "other_device_rows": skipped,
                "first_received_at": times[0] if times else None,
                "last_received_at": times[-1] if times else None,
                "first_f_cnt": counters[0] if counters else None,
                "last_f_cnt": counters[-1] if counters else None,
            },
            indent=2,
            sort_keys=True,
        )
    )

    if not args.apply:
        return
    if not selected:
        print("No selected Storage rows to replay.")
        return
    if not args.webhook_url:
        parser.error("--webhook-url is required with --apply")
    try:
        webhook_url = require_safe_webhook_url(args.webhook_url)
    except ValueError as error:
        parser.error(str(error))
    webhook_secret = os.environ.get("TTN_WEBHOOK_SECRET", "").strip()
    if len(webhook_secret) < MINIMUM_WEBHOOK_SECRET_LENGTH:
        raise SystemExit(
            "TTN_WEBHOOK_SECRET of at least 32 characters is required with --apply"
        )

    prove_hardened_auth(webhook_url)
    inserted, duplicates = replay_records(
        selected,
        webhook_url,
        webhook_secret,
    )
    print(
        json.dumps(
            {
                "replayed_rows": len(selected),
                "inserted_rows": inserted,
                "duplicate_rows": duplicates,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
