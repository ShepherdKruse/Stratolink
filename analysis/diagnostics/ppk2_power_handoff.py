#!/usr/bin/env python3
"""Start a PPK2 standby after the primary hold emits its terminal record.

macOS does not give the PPK2 CDC endpoint exclusive-open semantics, so trying
to infer ownership by repeatedly opening the port can create two simultaneous
command writers. This wrapper performs one command-free open/close permission
preflight on both CDC interfaces before the primary starts, then watches the
primary's append-only JSONL without touching USB until the primary emits its
terminal hold record. Qualification and preservation are deliberately
separate: even a short or otherwise failed primary must hand power over; the
final soak validator still rejects its evidence.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
HOLD_SCRIPT = HERE / "ppk2_power_hold.py"
MAX_HOLD_SECONDS = 7 * 24 * 60 * 60


def preflight_runtime(
    import_module: object = importlib.import_module,
) -> object:
    """Prove this interpreter can run the hold process before waiting.

    The handoff can spend hours waiting for the primary terminal record.  A
    missing dependency must therefore fail at queue time, not after the source
    supervisor has released the PPK2.  Importing ``ppk2_snapshot`` loads only
    Python modules and definitions; it does not enumerate or open USB devices.
    The actual target-facing call remains deferred to ``ppk2_power_hold.py``
    after the terminal record appears.
    """
    if not HOLD_SCRIPT.is_file():
        raise RuntimeError(f"power-hold script is missing: {HOLD_SCRIPT}")
    try:
        module = import_module("ppk2_snapshot")  # type: ignore[operator]
    except Exception as error:
        raise RuntimeError(
            "handoff interpreter cannot import the PPK2 runtime; "
            f"executable={sys.executable!r}; dependency_error={error}"
        ) from error
    if not callable(getattr(module, "open_endpoints", None)):
        raise RuntimeError("ppk2_snapshot.open_endpoints is unavailable")
    if not callable(getattr(module, "ppk2_ports", None)):
        raise RuntimeError("ppk2_snapshot.ppk2_ports is unavailable")
    return module


def preflight_serial_access(
    snapshot_module: object,
    import_module: object = importlib.import_module,
) -> list[str]:
    """Prove the queued process can open both PPK2 CDC devices.

    Import success does not prove that a sandboxed macOS process may open
    ``/dev/cu.*``.  The retry-3 standby learned that only after waiting a full
    day.  Opening each interface as a raw serial handle and closing it
    immediately sends no PPK2 command and therefore does not create a second
    command writer.  This function must run before the primary holder starts.
    """
    ports = list(snapshot_module.ppk2_ports())  # type: ignore[attr-defined]
    if len(ports) != 2:
        raise RuntimeError(
            f"serial permission preflight expected two PPK2 CDC interfaces, "
            f"found {ports}"
        )

    serial_module = import_module("serial")  # type: ignore[operator]
    serial_factory = getattr(serial_module, "Serial", None)
    if not callable(serial_factory):
        raise RuntimeError("serial.Serial is unavailable")

    handles: list[object] = []
    try:
        for port in ports:
            handles.append(serial_factory(port, timeout=0))
    except Exception as error:
        raise RuntimeError(
            "cannot open both PPK2 CDC interfaces during the command-free "
            "permission preflight; launch this standby outside the app "
            f"sandbox before starting the primary holder; ports={ports}; "
            f"executable={sys.executable!r}; access_error={error}"
        ) from error
    finally:
        for handle in reversed(handles):
            try:
                handle.close()  # type: ignore[attr-defined]
            except Exception:
                pass
    return ports


def terminal_hold_end(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    # The primary appends through a flushed text stream. A reader can
    # theoretically observe the final write between bytes even though these
    # small regular-file writes are normally atomic. Ignore only a trailing
    # unterminated record; it will be parsed on the next poll once its newline
    # appears. Malformed completed records remain a hard failure.
    if content and not content.endswith("\n"):
        lines = lines[:-1]

    events: list[dict[str, object]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"primary power log has invalid JSON on line {number}"
            ) from error
        if not isinstance(value, dict):
            raise RuntimeError(
                f"primary power log line {number} is not an object"
            )
        events.append(value)

    endings = [
        event
        for event in events
        if event.get("event") == "ppk2_power_hold_end"
    ]
    if not endings:
        return None
    if len(endings) != 1:
        raise RuntimeError("primary power log must contain exactly one hold_end")

    return endings[0]


def hold_qualification_errors(
    ending: dict[str, object],
    *,
    source_mv: int,
    min_held_seconds: float,
) -> list[str]:
    errors: list[str] = []
    if ending.get("source_mv") != source_mv:
        errors.append("primary hold_end source voltage is wrong")
    if ending.get("reconnects") != 0:
        errors.append("primary hold_end reports a reconnect")
    held = ending.get("held_seconds")
    if not isinstance(held, (int, float)) or held < min_held_seconds:
        errors.append("primary hold_end is shorter than the required soak")
    return errors


def validated_hold_end(
    path: Path,
    *,
    source_mv: int,
    min_held_seconds: float,
) -> dict[str, object] | None:
    """Compatibility validator used by regression and evidence tooling."""
    ending = terminal_hold_end(path)
    if ending is None:
        return None
    errors = hold_qualification_errors(
        ending,
        source_mv=source_mv,
        min_held_seconds=min_held_seconds,
    )
    if errors:
        raise RuntimeError("; ".join(errors))
    return ending


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
        parser.error("primary and standby logs must differ")
    if args.log_file.exists():
        parser.error("standby log already exists; refusing to append")
    if not 1 <= args.seconds <= MAX_HOLD_SECONDS:
        parser.error(
            f"--seconds must be between 1 and {MAX_HOLD_SECONDS}"
        )
    if not 0.01 <= args.poll_seconds <= 1:
        parser.error("--poll-seconds must be between 0.01 and 1")

    # These must precede the wait loop and the primary holder launch.  The
    # serial check opens and immediately closes raw CDC handles without issuing
    # PPK2 commands, so dependency and macOS sandbox failures are rejected at
    # queue time instead of after the completed soak.
    try:
        runtime = preflight_runtime()
        preflight_serial_access(runtime)
    except RuntimeError as error:
        parser.error(str(error))

    while True:
        ending = terminal_hold_end(args.primary_log)
        if ending is not None:
            break
        time.sleep(args.poll_seconds)

    qualification_errors = hold_qualification_errors(
        ending,
        source_mv=args.source_mv,
        min_held_seconds=args.min_held_seconds,
    )
    if qualification_errors:
        print(
            json.dumps(
                {
                    "event": "ppk2_power_preservation_after_failed_hold",
                    "qualification_errors": qualification_errors,
                },
                sort_keys=True,
            ),
            flush=True,
        )

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
