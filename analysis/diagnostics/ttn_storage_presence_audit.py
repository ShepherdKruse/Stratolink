#!/usr/bin/env python3
"""Create redacted, create-once TTN Storage presence evidence.

The live event stream does not emit every Storage audit event reliably.  This
tool queries the authoritative Storage Integration API and retains only server
times, frame counters, row counts, and pass/fail state—never payloads, keys,
sessions, device/application identifiers, or radio metadata.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from ttn_downlink_test import load_values
from ttn_storage_replay import (
    fetch_storage,
    parse_timestamp,
    select_device_records,
    validate_record,
)


def summarize(
    records: list[dict],
    device_id: str,
    *,
    after: str,
    until: str | None,
    expected_rows: int | None,
) -> dict[str, object]:
    lower = parse_timestamp(after)
    upper = parse_timestamp(until) if until else None
    selected, skipped = select_device_records(records, device_id)
    selected = [
        row for row in selected
        if parse_timestamp(row["received_at"]) > lower
        and (upper is None or parse_timestamp(row["received_at"]) <= upper)
    ]
    details = [validate_record(row) for row in selected]
    times = [detail[1] for detail in details]
    counters = [detail[2] for detail in details]
    passed = bool(selected) and (
        expected_rows is None or len(selected) == expected_rows
    )
    return {
        "passed": passed,
        "expected_rows": expected_rows,
        "selected_rows": len(selected),
        "other_device_rows": skipped,
        "first_received_at": times[0] if times else None,
        "last_received_at": times[-1] if times else None,
        "first_f_cnt": counters[0] if counters else None,
        "last_f_cnt": counters[-1] if counters else None,
        "after_utc_exclusive": after,
        "until_utc_inclusive": until,
        "scope": (
            "authoritative read-only TTN Storage presence; payloads, keys, "
            "sessions, device/application identifiers, and radio metadata "
            "are excluded"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", required=True)
    parser.add_argument("--until")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parse_timestamp(args.after)
    if args.until:
        if parse_timestamp(args.until) <= parse_timestamp(args.after):
            parser.error("--until must be later than --after")
    if args.expected_rows is not None and args.expected_rows < 1:
        parser.error("--expected-rows must be positive")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")

    values = load_values()
    key = values.get("TTN_NA_API_KEY", "")
    if not key:
        raise SystemExit("missing local NA TTN API key")
    records = fetch_storage(
        "nam1.cloud.thethings.network",
        "stratolink",
        key,
        args.after,
        args.limit,
    )
    report = summarize(
        records,
        "stratolink-2",
        after=args.after,
        until=args.until,
        expected_rows=args.expected_rows,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if not report["passed"]:
        print(payload, end="")
        raise SystemExit("refusing to create non-passing Storage evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    print(json.dumps({
        "output": str(args.output),
        "passed": True,
        "selected_rows": report["selected_rows"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
