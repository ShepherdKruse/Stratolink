#!/usr/bin/env python3
"""Validate the append-only PPK2 preservation-extension handoff."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


ASSERTION_EVENTS = {"ppk2_power_on", "ppk2_power_heartbeat"}


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("power event timestamp is missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_jsonl(path: Path) -> tuple[list[dict[str, object]], bytes]:
    if not path.exists():
        return [], b""
    raw = path.read_bytes()
    complete = raw
    if raw and not raw.endswith(b"\n"):
        complete = raw[: raw.rfind(b"\n") + 1] if b"\n" in raw else b""
    rows: list[dict[str, object]] = []
    for number, line in enumerate(complete.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL line {number} in {path}") from error
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSONL line {number} in {path}")
        rows.append(value)
    return rows, complete


def prefix_record(path: Path, raw: bytes, append_allowed: bool) -> dict[str, object]:
    return {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "append_allowed": append_allowed,
    }


def strictly_increasing(times: list[datetime]) -> bool:
    return all(later > earlier for earlier, later in zip(times, times[1:]))


def analyze(
    primary_path: Path,
    extension_path: Path,
    *,
    expected_source_mv: int = 4660,
    min_primary_held_seconds: float = 86400.0,
    max_assertion_gap_seconds: float = 31.5,
    max_transition_seconds: float = 2.0,
) -> dict[str, object]:
    primary, primary_raw = load_jsonl(primary_path)
    extension, extension_raw = load_jsonl(extension_path)
    errors: list[str] = []
    pending: list[str] = []

    primary_end = [row for row in primary if row.get("event") == "ppk2_power_hold_end"]
    primary_assertions = [row for row in primary if row.get("event") in ASSERTION_EVENTS]
    primary_on = [row for row in primary if row.get("event") == "ppk2_power_on"]
    if len(primary_end) > 1:
        errors.append("primary contains more than one hold_end")
    elif not primary_end:
        pending.append("primary hold_end not present")

    extension_end = [row for row in extension if row.get("event") == "ppk2_power_hold_end"]
    extension_assertions = [row for row in extension if row.get("event") in ASSERTION_EVENTS]
    extension_on = [row for row in extension if row.get("event") == "ppk2_power_on"]
    extension_heartbeats = [
        row for row in extension if row.get("event") == "ppk2_power_heartbeat"
    ]

    def values(rows: list[dict[str, object]], key: str, default: object) -> list[object]:
        return [row.get(key, default) for row in rows]

    primary_gaps: list[float] = []
    primary_times: list[datetime] = []
    if primary_assertions:
        if len(primary_on) != 1:
            errors.append("primary must contain exactly one power_on")
        if primary_assertions[0].get("event") != "ppk2_power_on":
            errors.append("primary first assertion must be power_on")
        if set(values(primary_assertions, "source_mv", None)) != {
            expected_source_mv
        }:
            errors.append("primary source voltage drifted")
        if max(
            (int(value) for value in values(primary_assertions, "reconnects", 0)),
            default=0,
        ) != 0:
            errors.append("primary reports a reconnect")
        try:
            primary_times = [timestamp(row.get("utc")) for row in primary_assertions]
            if not strictly_increasing(primary_times):
                errors.append("primary assertions are not strictly increasing")
            primary_gaps = [
                (later - earlier).total_seconds()
                for earlier, later in zip(primary_times, primary_times[1:])
            ]
            if any(
                gap < 0.0 or gap > max_assertion_gap_seconds
                for gap in primary_gaps
            ):
                errors.append("primary assertion gap exceeded tolerance")
        except ValueError as error:
            errors.append(str(error))
            primary_gaps = []
            primary_times = []

    if primary_end:
        ending = primary_end[0]
        if len(primary_assertions) < 2:
            errors.append("primary has insufficient source assertions")
        held = ending.get("held_seconds")
        if not isinstance(held, (int, float)) or held < min_primary_held_seconds:
            errors.append("primary hold_end is shorter than required")
        if ending.get("source_mv") != expected_source_mv:
            errors.append("primary hold_end source voltage drifted")
        if int(ending.get("reconnects", 0)) != 0:
            errors.append("primary hold_end reports a reconnect")
        try:
            ending_time = timestamp(ending.get("utc"))
            terminal_gap = (
                (ending_time - primary_times[-1]).total_seconds()
                if primary_times
                else None
            )
            if terminal_gap is None or not 0.0 <= terminal_gap <= max_assertion_gap_seconds:
                errors.append("primary terminal gap exceeded tolerance")
        except ValueError as error:
            errors.append(str(error))
            terminal_gap = None
            ending_time = None
    else:
        held = None
        terminal_gap = None
        ending_time = None

    if len(extension_on) > 1:
        errors.append("extension contains more than one power_on")
    elif not extension_on:
        if primary_end:
            pending.append("extension power_on not present")
    if extension_on and not extension_heartbeats:
        pending.append("extension later heartbeat not present")
    if extension_end:
        errors.append("extension unexpectedly ended before evidence capture")

    transition_seconds: float | None = None
    extension_gaps: list[float] = []
    if extension_on:
        if extension_assertions[0].get("event") != "ppk2_power_on":
            errors.append("extension first assertion must be power_on")
        if set(values(extension_assertions, "source_mv", None)) != {
            expected_source_mv
        }:
            errors.append("extension source voltage drifted")
        if max(
            (int(value) for value in values(extension_assertions, "reconnects", 0)),
            default=0,
        ) != 0:
            errors.append("extension reports a reconnect")
        try:
            extension_times = [timestamp(row.get("utc")) for row in extension_assertions]
            extension_on_time = timestamp(extension_on[0].get("utc"))
            if not strictly_increasing(extension_times):
                errors.append("extension assertions are not strictly increasing")
            if extension_heartbeats and not any(
                timestamp(row.get("utc")) > extension_on_time
                for row in extension_heartbeats
            ):
                errors.append("extension heartbeat is not later than power_on")
            extension_gaps = [
                (later - earlier).total_seconds()
                for earlier, later in zip(extension_times, extension_times[1:])
            ]
            if any(
                gap < 0.0 or gap > max_assertion_gap_seconds
                for gap in extension_gaps
            ):
                errors.append("extension assertion gap exceeded tolerance")
            if ending_time is not None:
                transition_seconds = (
                    extension_on_time - ending_time
                ).total_seconds()
                if not 0.0 <= transition_seconds <= max_transition_seconds:
                    errors.append("extension transition exceeded tolerance or was unordered")
        except ValueError as error:
            errors.append(str(error))

    passed = not errors and not pending and bool(extension_heartbeats)
    status = "PASS" if passed else "FAIL" if errors else "PENDING"
    return {
        "passed": passed,
        "status": status,
        "errors": errors,
        "pending": pending,
        "requirements": {
            "expected_source_mv": expected_source_mv,
            "minimum_primary_held_seconds": min_primary_held_seconds,
            "maximum_assertion_gap_seconds": max_assertion_gap_seconds,
            "maximum_transition_seconds": max_transition_seconds,
            "zero_reconnects": True,
            "later_extension_heartbeat_required": True,
        },
        "primary": {
            "power_on_events": len(primary_on),
            "hold_end_events": len(primary_end),
            "held_seconds": held,
            "assertions": len(primary_assertions),
            "maximum_assertion_gap_seconds": (
                round(max(primary_gaps), 3) if primary_gaps else None
            ),
            "terminal_gap_seconds": (
                round(terminal_gap, 3) if terminal_gap is not None else None
            ),
        },
        "extension": {
            "power_on_events": len(extension_on),
            "heartbeats": len(extension_heartbeats),
            "hold_end_events": len(extension_end),
            "assertions": len(extension_assertions),
            "maximum_assertion_gap_seconds": (
                round(max(extension_gaps), 3) if extension_gaps else None
            ),
            "transition_seconds": (
                round(transition_seconds, 3)
                if transition_seconds is not None
                else None
            ),
        },
        "provenance": {
            "primary": prefix_record(primary_path, primary_raw, False),
            "extension_prefix": prefix_record(extension_path, extension_raw, True),
        },
        "scope": (
            "proves PPK2 supervisor command continuity only; does not prove "
            "uninterrupted VSTOR, 3V3, payload execution, or absence of reset"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--expected-source-mv", type=int, default=4660)
    parser.add_argument("--min-primary-held-seconds", type=float, default=86400.0)
    parser.add_argument("--max-assertion-gap-seconds", type=float, default=31.5)
    parser.add_argument("--max-transition-seconds", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    report = analyze(
        args.primary,
        args.extension,
        expected_source_mv=args.expected_source_mv,
        min_primary_held_seconds=args.min_primary_held_seconds,
        max_assertion_gap_seconds=args.max_assertion_gap_seconds,
        max_transition_seconds=args.max_transition_seconds,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if not args.final:
            raise SystemExit("--output requires --final")
        if not report["passed"]:
            raise SystemExit(payload + "refusing to create non-passing extension evidence")
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite extension evidence: {args.output}")
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if args.final and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
