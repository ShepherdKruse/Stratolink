#!/usr/bin/env python3
"""Supervise the PPK2 source-meter output while another tool uses the DUT.

The launch bench's PPK2 does not reliably preserve DUT power after its control
CDC endpoint is closed.  Keep this process alive across J-Link flashes and
other hardware tests.  It periodically reasserts source mode, voltage, and DUT
power, and reconnects after USB re-enumeration.  JSON heartbeats make loss of
power control visible instead of silently assuming that the last command held.
This intentionally does not start the sample stream, leaving the data endpoint
idle.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time

from ppk2_snapshot import open_endpoints


MAX_HOLD_SECONDS = 7 * 24 * 60 * 60


def assert_power(control: object, source_mv: int) -> None:
    # ppk2-api's command writer catches and merely logs serial exceptions.
    # A successful return from toggle_DUT_power therefore proves nothing after
    # a USB reset. Follow every assertion with a metadata round trip; that read
    # raises (or returns no object) when the old CDC handle has gone stale.
    control.stop_measuring()
    time.sleep(0.05)
    control.use_source_meter()
    control.set_source_voltage(source_mv)
    control.toggle_DUT_power("ON")
    time.sleep(0.05)
    control.ser.reset_input_buffer()
    modifiers = control.get_modifiers()
    if not modifiers:
        raise RuntimeError("PPK2 did not acknowledge power assertion")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-mv", type=int, default=4660)
    parser.add_argument("--seconds", type=float, default=3600)
    parser.add_argument("--heartbeat-seconds", type=float, default=10)
    parser.add_argument(
        "--log-file",
        type=Path,
        help="append every JSON event to this file and flush immediately",
    )
    parser.add_argument(
        "--wait-for-control-seconds",
        type=float,
        default=0,
        help="wait this long for another holder or USB reset to release PPK2",
    )
    args = parser.parse_args()
    if not 800 <= args.source_mv <= 5000:
        parser.error("--source-mv must be within the PPK2 800-5000 mV range")
    if not 1 <= args.seconds <= MAX_HOLD_SECONDS:
        parser.error(
            f"--seconds must be between 1 and {MAX_HOLD_SECONDS}"
        )
    if not 1 <= args.heartbeat_seconds <= 60:
        parser.error("--heartbeat-seconds must be between 1 and 60")
    if not 0 <= args.wait_for_control_seconds <= 86400:
        parser.error("--wait-for-control-seconds must be between 0 and 86400")

    log_handle = None
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log_file.open("a", encoding="utf-8")

    def emit(event: dict[str, object]) -> None:
        event = {"utc": utc_now(), **event}
        line = json.dumps(event, sort_keys=True)
        print(line, flush=True)
        if log_handle:
            log_handle.write(line + "\n")
            log_handle.flush()

    open_deadline = time.monotonic() + args.wait_for_control_seconds
    while True:
        try:
            control, control_port, data_port = open_endpoints()
            break
        except Exception:
            if time.monotonic() >= open_deadline:
                if log_handle:
                    log_handle.close()
                raise
            # Keep post-soak handoff latency below the board's decoupling-only
            # tolerance when no supercap is fitted. This loop runs only while
            # another process owns the CDC endpoint.
            time.sleep(0.02)

    stop = False
    reconnects = 0

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    started = time.monotonic()
    try:
        assert_power(control, args.source_mv)
        time.sleep(0.5)
        emit(
            {
                "event": "ppk2_power_on",
                "source_mv": args.source_mv,
                "control_port": control_port,
                "data_port": data_port,
            }
        )
        deadline = started + args.seconds
        next_heartbeat = time.monotonic() + args.heartbeat_seconds
        while not stop and time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_heartbeat:
                time.sleep(min(0.25, next_heartbeat - now))
                continue
            try:
                assert_power(control, args.source_mv)
                control_port_now = control_port
            except Exception as error:
                try:
                    control.ser.close()
                except Exception:
                    pass
                reconnect_deadline = time.monotonic() + 30
                while True:
                    try:
                        control, control_port, data_port = open_endpoints()
                        assert_power(control, args.source_mv)
                        reconnects += 1
                        control_port_now = control_port
                        break
                    except Exception:
                        if time.monotonic() >= reconnect_deadline:
                            raise RuntimeError(
                                "PPK2 unavailable for 30 s; unable to "
                                "guarantee DUT power"
                            ) from error
                        time.sleep(0.5)
            emit(
                {
                    "event": "ppk2_power_heartbeat",
                    "held_seconds": round(time.monotonic() - started, 3),
                    "source_mv": args.source_mv,
                    "control_port": control_port_now,
                    "reconnects": reconnects,
                }
            )
            next_heartbeat = time.monotonic() + args.heartbeat_seconds
    finally:
        # Do not issue DUT OFF: preserving payload state is deliberate.  The
        # open control handle is what makes power reliable on this bench.
        held = time.monotonic() - started
        emit(
            {
                "event": "ppk2_power_hold_end",
                "held_seconds": round(held, 3),
                "source_mv": args.source_mv,
                "reconnects": reconnects,
            }
        )
        control.ser.close()
        if log_handle:
            log_handle.close()


if __name__ == "__main__":
    main()
