#!/usr/bin/env python3
"""Cache the public StratoLink-2 Supabase soak rows without logging credentials."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_URL = "https://iazmnyyfsobucndqncgw.supabase.co"
DEFAULT_OUTPUT = Path(
    "analysis/diagnostics/logs/stratolink2_soak_20260724_supabase.json"
)
FIELDS = (
    "device_id,time,lat,lon,altitude_m,temperature,pressure,solar_voltage,"
    "battery_voltage,rssi,snr,gps_speed,gps_heading,gps_satellites,"
    "mems_accel_x,mems_accel_y,mems_accel_z,uv_index,ambient_lux,"
    "acoustic_event,lora_sf,lora_bw,frequency_hz"
)


def require_create_once(path: Path) -> None:
    partials = sorted(
        path.parent.glob(f".{path.name}.*.partial")
    ) if path.parent.is_dir() else []
    collisions = ([path] if path.exists() else []) + partials
    if collisions:
        raise SystemExit(
            "refusing to overwrite Supabase evidence: "
            + ", ".join(str(item) for item in collisions)
        )


def write_create_once(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".partial",
        delete=False,
    ) as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite Supabase evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def through_ttn_time(path: Path) -> str:
    received: list[datetime] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid TTN JSONL at line {number}: {error}") from error
        if (
            row.get("event") == "ttn_uplink"
            and row.get("device_id") == "stratolink-2"
        ):
            value = row.get("received_at")
            if not isinstance(value, str):
                raise ValueError(f"TTN uplink at line {number} lacks received_at")
            received.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
    if not received:
        raise ValueError("TTN log contains no StratoLink-2 uplinks")
    # Supabase's row timestamp is the webhook insertion time. The parity gate
    # already allows at most five seconds from TTN's server receive timestamp;
    # close the export at that same bound so post-collector uplinks cannot leak
    # into this create-once evidence set.
    return (max(received) + timedelta(seconds=5)).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.environ.get("SUPABASE_URL", DEFAULT_URL),
    )
    parser.add_argument(
        "--key-env",
        default="SUPABASE_PUBLISHABLE_KEY",
        help="name of the environment variable holding a public/anon key",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--since", default="2026-07-25T01:30:00Z")
    parser.add_argument("--until")
    parser.add_argument(
        "--through-ttn-log",
        type=Path,
        help="set the inclusive upper bound to the final TTN uplink plus 5 s",
    )
    args = parser.parse_args()
    if args.until and args.through_ttn_log:
        parser.error("use only one of --until and --through-ttn-log")
    try:
        until = (
            through_ttn_time(args.through_ttn_log)
            if args.through_ttn_log else args.until
        )
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error

    require_create_once(args.output)

    key = os.environ.get(args.key_env, "").strip()
    if not key:
        raise SystemExit(f"set {args.key_env}; the key value is never printed")

    query_items = [
        ("device_id", "eq.stratolink-2"),
        ("time", f"gte.{args.since}"),
    ]
    if until:
        query_items.append(("time", f"lte.{until}"))
    query_items.extend(
        (("select", FIELDS), ("order", "time.asc"), ("limit", "1000"))
    )
    query = urlencode(query_items)
    request = Request(
        f"{args.url.rstrip('/')}/rest/v1/telemetry?{query}",
        headers={"apikey": key, "Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        body = response.read()
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise SystemExit("Supabase response was not a row array")
    if any(row.get("device_id") != "stratolink-2" for row in rows):
        raise SystemExit("Supabase response contained an unexpected device")
    times = [row.get("time") for row in rows]
    if any(not isinstance(value, str) for value in times):
        raise SystemExit("Supabase response contained a row without time")
    if times != sorted(times):
        raise SystemExit("Supabase rows are not ordered by time")

    write_create_once(args.output, rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "first": times[0] if times else None,
                "last": times[-1] if times else None,
                "query_since": args.since,
                "query_until": until,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Supabase export failed: {type(error).__name__}", file=sys.stderr)
        raise
