#!/usr/bin/env python3
"""Read-only production probe for Stratolink's event-table contract.

Loads the ignored local credential file, requires its publishable key, never
prints keys, and asks PostgREST for zero rows containing every column required
by the hardened webhook. HTTP 200 proves the table and selected columns are
exposed and readable at the public Data API boundary; PostgREST errors identify
missing tables or columns. Secret/service-role keys are never accepted.
"""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


ENV_FILE = Path.home() / ".config" / "stratolink" / "env"
COMMON_INGEST_COLUMNS = (
    "ttn_device_id",
    "dev_addr",
    "session_key_id",
    "ttn_received_at",
    "f_cnt",
)
PROBES = {
    "telemetry": COMMON_INGEST_COLUMNS
    + (
        "telemetry_version",
        "power_tier",
        "reset_cause",
        "boot_count",
        "gps_fix_age_min",
        "command_ack_seq",
        "relay_enabled",
        "relay_fwd_delta",
        "ctt_tags_delta",
    ),
    "wildlife_detections": COMMON_INGEST_COLUMNS
    + ("event_version", "detection_age_min", "detected_at"),
    "b2b_packets": COMMON_INGEST_COLUMNS,
}


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, value = line.split("=", 1)
        values[key] = shlex.split(value, comments=True)[0] if value else ""
    return values


def main() -> None:
    values = load_env()
    base = values.get("SUPABASE_URL") or values.get("SBURL")
    key = values.get("SUPABASE_PUBLISHABLE_KEY")
    if not base or not key:
        raise SystemExit("missing local Supabase URL/publishable key")

    context = ssl.create_default_context(cafile=certifi.where())
    results: list[dict[str, object]] = []
    for table, columns in PROBES.items():
        query = urlencode({"select": ",".join(columns), "limit": "0"})
        request = Request(
            f"{base.rstrip('/')}/rest/v1/{table}?{query}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
        )
        try:
            with urlopen(request, timeout=20, context=context) as response:
                results.append(
                    {
                        "table": table,
                        "status": response.status,
                        "contract_columns": len(columns),
                        "contract_ready": response.status == 200,
                    }
                )
        except HTTPError as error:
            try:
                detail = json.load(error)
            except Exception:
                detail = {}
            results.append(
                {
                    "table": table,
                    "status": error.code,
                    "code": detail.get("code"),
                    "message": detail.get("message"),
                    "contract_columns": len(columns),
                    "contract_ready": False,
                }
            )
    print(
        json.dumps(
            {
                "contract_ready": all(
                    bool(result["contract_ready"]) for result in results
                ),
                "probes": results,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
