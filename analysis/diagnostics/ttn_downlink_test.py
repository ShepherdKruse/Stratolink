#!/usr/bin/env python3
"""Inspect or explicitly queue one bounded StratoLink-2 Class-A command.

Credentials stay in the repository's ignored firmware/test/.ttn_keys file.
The default is read-only. The script refuses a mismatched TTN device identity
or an occupied queue so a bench test cannot silently misaddress, reorder, or
overwrite an operator command.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import certifi


ROOT = Path(__file__).resolve().parents[2]
KEY_FILE = ROOT / "firmware" / "test" / ".ttn_keys"


def load_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in KEY_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def request_json(
    method: str, url: str, api_key: str, payload: dict | None = None
) -> tuple[int, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "stratolink-launch-audit/1",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=20, context=context) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="stratolink-2")
    parser.add_argument("--seq", type=int, required=True)
    parser.add_argument(
        "--relay",
        choices=("on", "off"),
        help="queue the bounded public-Meshtastic relay toggle instead of PING",
    )
    parser.add_argument(
        "--queue",
        action="store_true",
        help="perform the queue mutation; default is inspect/dry-run only",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="create-once redacted queue evidence",
    )
    args = parser.parse_args()
    if not 0 <= args.seq <= 255:
        parser.error("--seq must be 0..255")
    if args.device != "stratolink-2":
        parser.error(
            "this addressed command is bound to TTN device stratolink-2"
        )

    values = load_values()
    app_id = values["TTN_APP_ID"]
    api_key = values["TTN_APP_KEY"]
    base_url = values["TTN_BASE_URL"].rstrip("/")
    endpoint = (
        f"{base_url}/api/v3/as/applications/{app_id}/devices/"
        f"{args.device}/down"
    )

    list_status, queued = request_json("GET", endpoint, api_key)
    downlinks = queued.get("downlinks", [])
    if list_status != 200:
        raise SystemExit(
            f"queue list failed: HTTP {list_status} "
            f"{queued.get('message', 'unknown error')}"
        )
    if args.queue and downlinks:
        raise SystemExit(
            f"refusing to push: device already has {len(downlinks)} "
            "queued downlink(s)"
        )

    opcode_name = "PING" if args.relay is None else "RELAY"
    command = bytes((0x00, 0x02, 0x00, args.seq))
    if args.relay is not None:
        command = bytes((0x00, 0x02, 0x02, args.seq, args.relay == "on"))
    if args.queue:
        status, response = request_json(
            "POST",
            f"{endpoint}/push",
            api_key,
            {
                "downlinks": [
                    {
                        "frm_payload": base64.b64encode(command).decode(),
                        "f_port": 10,
                        "priority": "NORMAL",
                    }
                ]
            },
        )
        if status not in (200, 204):
            raise SystemExit(
                f"{opcode_name} queue failed: HTTP {status} "
                f"{response.get('message', 'unknown error')}"
            )
    else:
        status = None

    evidence = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": (
            f"{opcode_name.lower()}_queued" if args.queue
            else f"{opcode_name.lower()}_queue_dry_run"
        ),
        "device_id": args.device,
        "target_balloon_id": 2,
        "opcode": opcode_name,
        "relay_requested": args.relay,
        "f_port": 10,
        "application_payload_bytes": len(command),
        "seq": args.seq,
        "preexisting_queue_depth": len(downlinks),
        "queue_http_status": status,
        "privacy": "credentials and command payload bytes excluded",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(evidence, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as error:
            raise SystemExit(
                f"refusing to overwrite TTN queue evidence: {args.output}"
            ) from error
    print(
        json.dumps(
            evidence,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
