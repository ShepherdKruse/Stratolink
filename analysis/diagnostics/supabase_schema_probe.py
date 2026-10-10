#!/usr/bin/env python3
"""Read-only production probe for Stratolink's public Data API contract.

Loads the ignored local credential file, requires its publishable key, never
prints keys, and asks PostgREST for zero rows containing every publicly readable
column required by the hardened webhook. Raw authenticated B2B rows are
service-only, so the same key must be denied access to that table. A public
PostgreSQL 42501 denial distinguishes the intended private table from a missing
PostgREST relation, but it cannot verify the table's private columns, indexes,
RLS, or service-role grants. The report therefore still requires a separate
database-admin schema verification. Secret/service-role keys are never accepted.
"""

from __future__ import annotations

import base64
import binascii
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
PUBLIC_PROBES = {
    "telemetry": COMMON_INGEST_COLUMNS
    + (
        "frm_payload",
        "f_port",
        "gateways",
        "rx_metadata",
        "telemetry_version",
        "power_tier",
        "reset_cause",
        "boot_count",
        "gps_fix_age_min",
        "server_proof_count_mod8",
        "server_qualified_miss_streak",
        "server_recovery_parity",
        "command_ack_seq",
        "relay_enabled",
        "relay_fwd_delta",
        "ctt_tags_delta",
    ),
    "wildlife_detections": COMMON_INGEST_COLUMNS
    + ("event_version", "detection_age_min", "detected_at"),
}
PRIVATE_DENIAL_PROBES = {"b2b_packets": ("id",)}
PRIVATE_DENIAL_STATUSES = {401, 403}
PRIVATE_DENIAL_CODES = {"42501"}


def is_publishable_key(value: str) -> bool:
    """Accept current publishable keys or legacy JWTs carrying role=anon."""
    if value.startswith("sb_publishable_"):
        return len(value) > len("sb_publishable_")
    if value.startswith("sb_secret_"):
        return False
    parts = value.split(".")
    if len(parts) != 3:
        return False
    try:
        payload_text = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(payload_text).decode("utf-8")
        )
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("role") == "anon"


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
    if not base or not key or not is_publishable_key(key):
        raise SystemExit("missing or non-publishable Supabase URL/key")

    context = ssl.create_default_context(cafile=certifi.where())
    public_results: list[dict[str, object]] = []
    for table, columns in PUBLIC_PROBES.items():
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
                public_results.append(
                    {
                        "table": table,
                        "status": response.status,
                        "expected_access": "public_read",
                        "contract_columns": len(columns),
                        "contract_ready": response.status == 200,
                    }
                )
        except HTTPError as error:
            try:
                detail = json.load(error)
            except Exception:
                detail = {}
            public_results.append(
                {
                    "table": table,
                    "status": error.code,
                    "code": detail.get("code"),
                    "message": detail.get("message"),
                    "expected_access": "public_read",
                    "contract_columns": len(columns),
                    "contract_ready": False,
                }
            )

    private_results: list[dict[str, object]] = []
    for table, columns in PRIVATE_DENIAL_PROBES.items():
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
                private_results.append(
                    {
                        "table": table,
                        "status": response.status,
                        "expected_access": "service_role_only",
                        "public_access_denied": False,
                        "private_table_existence_verified": False,
                        "private_columns_verified": False,
                        "contract_ready": False,
                    }
                )
        except HTTPError as error:
            try:
                detail = json.load(error)
            except Exception:
                detail = {}
            database_code = detail.get("code")
            denied = (
                error.code in PRIVATE_DENIAL_STATUSES
                and database_code in PRIVATE_DENIAL_CODES
            )
            private_results.append(
                {
                    "table": table,
                    "status": error.code,
                    "code": database_code,
                    "message": detail.get("message"),
                    "expected_access": "service_role_only",
                    "public_access_denied": denied,
                    "private_table_existence_verified": denied,
                    "private_columns_verified": False,
                    "contract_ready": denied,
                }
            )

    public_ready = all(
        bool(result["contract_ready"]) for result in public_results
    )
    private_boundary_ready = all(
        bool(result["contract_ready"]) for result in private_results
    )
    print(
        json.dumps(
            {
                "contract_ready": public_ready and private_boundary_ready,
                "public_contract_ready": public_ready,
                "private_boundary_ready": private_boundary_ready,
                "admin_verification_required": sorted(
                    PRIVATE_DENIAL_PROBES.keys()
                ),
                "probes": public_results + private_results,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
