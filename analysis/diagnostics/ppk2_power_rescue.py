#!/usr/bin/env python3
"""Preserve DUT power if an older strict standby rejects a failed primary.

This watcher performs no serial or USB access while the primary is active. It
exits without action for a valid terminal record because the normal standby
owns that handoff. It starts the same 4.660 V hold only when the terminal record
is explicitly unqualified and the normal standby therefore refuses takeover.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

from ppk2_power_handoff import (
    HOLD_SCRIPT,
    hold_qualification_errors,
    terminal_hold_end,
)


def rescue_required(
    ending: dict[str, object],
    *,
    source_mv: int,
    min_held_seconds: float,
) -> bool:
    return bool(
        hold_qualification_errors(
            ending,
            source_mv=source_mv,
            min_held_seconds=min_held_seconds,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-log", type=Path, required=True)
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--source-mv", type=int, default=4660)
    parser.add_argument("--min-held-seconds", type=float, default=57600)
    parser.add_argument("--seconds", type=float, default=86400)
    parser.add_argument("--heartbeat-seconds", type=float, default=30)
    parser.add_argument("--poll-seconds", type=float, default=0.02)
    args = parser.parse_args()

    if args.primary_log.resolve() == args.log_file.resolve():
        parser.error("primary and rescue logs must differ")
    if not 0.01 <= args.poll_seconds <= 1:
        parser.error("--poll-seconds must be between 0.01 and 1")

    while True:
        ending = terminal_hold_end(args.primary_log)
        if ending is not None:
            break
        time.sleep(args.poll_seconds)

    if not rescue_required(
        ending,
        source_mv=args.source_mv,
        min_held_seconds=args.min_held_seconds,
    ):
        return
    if args.log_file.exists():
        return

    argv = [
        sys.executable,
        str(HOLD_SCRIPT),
        "--source-mv",
        str(args.source_mv),
        "--seconds",
        str(args.seconds),
        "--heartbeat-seconds",
        str(args.heartbeat_seconds),
        "--log-file",
        str(args.log_file),
    ]
    os.execv(sys.executable, argv)


if __name__ == "__main__":
    main()
