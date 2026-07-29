#!/usr/bin/env python3
"""Adversarial checks for PPK2 preservation-extension evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile

from power_extension_summary import analyze


BASE = datetime(2026, 7, 27, tzinfo=timezone.utc)


def row(event: str, seconds: float, **values: object) -> dict[str, object]:
    return {
        "event": event,
        "utc": (BASE + timedelta(seconds=seconds)).isoformat(),
        "source_mv": 4660,
        "reconnects": 0,
        **values,
    }


def write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(value) + "\n" for value in rows), encoding="utf-8"
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        primary = root / "primary.jsonl"
        extension = root / "extension.jsonl"
        primary_rows = [
            row("ppk2_power_on", 0.0, held_seconds=0.0),
            row("ppk2_power_heartbeat", 30.0, held_seconds=86370.0),
            row("ppk2_power_hold_end", 60.5, held_seconds=86400.1),
        ]
        extension_rows = [
            row("ppk2_power_on", 61.5, held_seconds=0.0),
            row("ppk2_power_heartbeat", 91.5, held_seconds=30.0),
        ]
        write(primary, primary_rows[:-1])
        pending = analyze(primary, extension)
        assert pending["status"] == "PENDING"
        assert pending["passed"] is False
        assert pending["primary"]["maximum_assertion_gap_seconds"] == 30.0

        write(
            primary,
            [
                primary_rows[0],
                {
                    **row("ppk2_power_heartbeat", 32.0, held_seconds=32.0),
                    "source_mv": 4659,
                    "reconnects": 1,
                },
            ],
        )
        pending_failure = analyze(primary, extension)
        assert pending_failure["status"] == "FAIL"
        assert "primary assertion gap exceeded tolerance" in pending_failure["errors"]
        assert "primary source voltage drifted" in pending_failure["errors"]
        assert "primary reports a reconnect" in pending_failure["errors"]

        write(primary, primary_rows)
        write(extension, extension_rows)
        good = analyze(primary, extension)
        assert good["passed"] is True
        assert good["status"] == "PASS"
        assert good["extension"]["transition_seconds"] == 1.0
        assert good["primary"]["terminal_gap_seconds"] == 30.5
        assert good["provenance"]["extension_prefix"]["append_allowed"] is True

        mutations = [
            [*extension_rows, row("ppk2_power_hold_end", 92.0, held_seconds=30.5)],
            [{**extension_rows[0], "utc": row("x", 63.0)["utc"]}, extension_rows[1]],
            [extension_rows[0], {**extension_rows[1], "reconnects": 1}],
            [extension_rows[0], {**extension_rows[1], "source_mv": 4659}],
            [extension_rows[0], row("ppk2_power_heartbeat", 94.0, held_seconds=32.5)],
            [
                row("ppk2_power_heartbeat", 61.2, held_seconds=0.7),
                row("ppk2_power_on", 61.5, held_seconds=0.0),
            ],
        ]
        for mutation in mutations:
            write(extension, mutation)
            failed = analyze(primary, extension)
            assert failed["status"] == "FAIL"
            assert failed["passed"] is False

        write(primary, [*primary_rows, primary_rows[-1]])
        write(extension, extension_rows)
        assert analyze(primary, extension)["status"] == "FAIL"

    print("PASS: PPK2 preservation-extension handoff is fail-closed")


if __name__ == "__main__":
    main()
