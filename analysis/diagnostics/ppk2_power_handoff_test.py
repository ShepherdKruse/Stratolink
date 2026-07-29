#!/usr/bin/env python3
"""Regression tests for log-gated, single-writer PPK2 handoff."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

from ppk2_power_handoff import (
    preflight_serial_access,
    preflight_runtime,
    terminal_hold_end,
    validated_hold_end,
)


def write_events(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def expect_failure(path: Path) -> None:
    try:
        validated_hold_end(
            path,
            source_mv=4660,
            min_held_seconds=57600,
        )
    except RuntimeError:
        return
    raise AssertionError("invalid primary evidence was accepted")


def main() -> None:
    imports: list[str] = []

    def good_import(name: str) -> object:
        imports.append(name)
        return SimpleNamespace(
            open_endpoints=lambda: None,
            ppk2_ports=lambda: ["/dev/cu.ppk-a", "/dev/cu.ppk-b"],
        )

    runtime = preflight_runtime(good_import)
    assert imports == ["ppk2_snapshot"]

    opened: list[str] = []
    closed: list[str] = []

    class FakeHandle:
        def __init__(self, port: str) -> None:
            self.port = port

        def close(self) -> None:
            closed.append(self.port)

    def fake_serial(port: str, *, timeout: int) -> FakeHandle:
        assert timeout == 0
        opened.append(port)
        return FakeHandle(port)

    ports = preflight_serial_access(
        runtime,
        lambda name: (
            SimpleNamespace(Serial=fake_serial)
            if name == "serial"
            else None
        ),
    )
    assert ports == ["/dev/cu.ppk-a", "/dev/cu.ppk-b"]
    assert opened == ports
    assert closed == list(reversed(ports))

    first_closed: list[str] = []

    class FirstHandle:
        def close(self) -> None:
            first_closed.append("closed")

    def denied_second(port: str, *, timeout: int) -> FirstHandle:
        assert timeout == 0
        if port.endswith("b"):
            raise PermissionError("Operation not permitted")
        return FirstHandle()

    try:
        preflight_serial_access(
            runtime,
            lambda _name: SimpleNamespace(Serial=denied_second),
        )
    except RuntimeError as error:
        message = str(error)
        assert "command-free permission preflight" in message
        assert "outside the app sandbox" in message
        assert "Operation not permitted" in message
    else:
        raise AssertionError("denied PPK2 CDC interface passed preflight")
    assert first_closed == ["closed"]

    def missing_serial(_name: str) -> object:
        raise ModuleNotFoundError("No module named 'serial'")

    try:
        preflight_runtime(missing_serial)
    except RuntimeError as error:
        message = str(error)
        assert "cannot import the PPK2 runtime" in message
        assert "No module named 'serial'" in message
        assert "executable=" in message
    else:
        raise AssertionError("missing pyserial passed handoff preflight")

    try:
        preflight_runtime(
            lambda _name: SimpleNamespace(
                open_endpoints=None,
                ppk2_ports=lambda: [],
            )
        )
    except RuntimeError as error:
        assert "open_endpoints is unavailable" in str(error)
    else:
        raise AssertionError("missing PPK2 entry point passed preflight")

    try:
        preflight_runtime(
            lambda _name: SimpleNamespace(
                open_endpoints=lambda: None,
                ppk2_ports=None,
            )
        )
    except RuntimeError as error:
        assert "ppk2_ports is unavailable" in str(error)
    else:
        raise AssertionError("missing PPK2 port enumerator passed preflight")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "primary.jsonl"
        assert validated_hold_end(
            path,
            source_mv=4660,
            min_held_seconds=57600,
        ) is None

        write_events(
            path,
            [
                {
                    "event": "ppk2_power_on",
                    "source_mv": 4660,
                },
                {
                    "event": "ppk2_power_heartbeat",
                    "held_seconds": 57596.3,
                    "source_mv": 4660,
                    "reconnects": 0,
                },
            ],
        )
        assert validated_hold_end(
            path,
            source_mv=4660,
            min_held_seconds=57600,
        ) is None

        path.write_text(
            json.dumps(
                {
                    "event": "ppk2_power_heartbeat",
                    "held_seconds": 57596.3,
                    "source_mv": 4660,
                    "reconnects": 0,
                }
            )
            + "\n"
            + '{"event":"ppk2_power_hold_',
            encoding="utf-8",
        )
        assert validated_hold_end(
            path,
            source_mv=4660,
            min_held_seconds=57600,
        ) is None

        good_end = {
            "event": "ppk2_power_hold_end",
            "held_seconds": 57600.16,
            "source_mv": 4660,
            "reconnects": 0,
        }
        write_events(path, [good_end])
        assert (
            validated_hold_end(
                path,
                source_mv=4660,
                min_held_seconds=57600,
            )
            == good_end
        )

        for mutation in (
            {**good_end, "held_seconds": 57599.999},
            {**good_end, "source_mv": 4659},
            {**good_end, "reconnects": 1},
        ):
            write_events(path, [mutation])
            assert terminal_hold_end(path) == mutation
            expect_failure(path)

        write_events(path, [good_end, good_end])
        expect_failure(path)
        path.write_text("{not json}\n", encoding="utf-8")
        expect_failure(path)

    print(
        "PASS: runtime and serial access are preflighted before waiting and "
        "terminal takeover is separated from strict soak validation"
    )


if __name__ == "__main__":
    main()
