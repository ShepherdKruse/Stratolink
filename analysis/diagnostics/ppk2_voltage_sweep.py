#!/usr/bin/env python3
"""Sweep VSTOR from PPK2 and compare firmware ADC/tier decisions over J-Link.

The PPK2 control handle remains open for the complete sweep and optional final
hold, so the payload is never accidentally depowered between voltage points.
The board must be running env:power_test with `ptd` at the address below.
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import re
import select
import signal
import subprocess
import time

from ppk2_snapshot import open_endpoints
from ppk2_power_hold import assert_power


PTD_ADDR = "0x20000044"
VOLTAGES_MV = (4660, 4500, 4000, 3600, 3500, 3200, 3000, 2850, 2750, 2600)
JLINK_EXE = "/Applications/SEGGER/JLink/JLinkExe"


class JLinkSession:
    def __init__(self) -> None:
        self.master_fd, slave_fd = pty.openpty()
        self.process = subprocess.Popen(
            [
                JLINK_EXE,
                "-device",
                "STM32WLE5CC",
                "-if",
                "SWD",
                "-speed",
                "4000",
                "-autoconnect",
                "1",
            ],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            # J-Link Commander propagates termination to its process group on
            # macOS. Keep that group separate so closing the helper cannot
            # terminate this supervisor and skip the safe-voltage restore.
            start_new_session=True,
        )
        os.close(slave_fd)
        startup = self._read_until_prompt(15)
        if self.process.poll() is not None or "J-Link>" not in startup:
            raise RuntimeError(f"J-Link failed to start: {startup[-1000:]}")

    def _read_until_prompt(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.master_fd], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(self.master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            data.extend(chunk)
            if data.rstrip().endswith(b"J-Link>"):
                break
        return data.decode(errors="replace")

    def command(self, command: str, timeout: float = 10) -> str:
        os.write(self.master_fd, command.encode() + b"\n")
        return self._read_until_prompt(timeout)

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.command("g", timeout=2)
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=2)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
            os.close(self.master_fd)


def read_ptd(jlink: JLinkSession) -> dict[str, int] | None:
    output = jlink.command("h")
    output += jlink.command(f"mem32 {PTD_ADDR} 10")
    output += jlink.command("g")
    if "Cannot connect" in output or "FAILED" in output:
        return None
    words: list[int] = []
    capture = False
    for line in output.splitlines():
        if line.startswith(f"{PTD_ADDR[2:].upper()} ="):
            capture = True
        if capture and re.match(r"^[0-9A-F]{8} =", line):
            words.extend(
                int(word, 16)
                for word in line.split("=", 1)[1].strip().split()
            )
            if len(words) >= 10:
                break
    if len(words) < 10 or words[0] != 0x50575232:
        return None
    return {
        "loops": words[1],
        "reported_vstor_mv": words[2],
        "reported_solar_mv": words[3],
        "vbat_ok": words[4],
        "tier": words[5],
        "vref_vdda_mv": words[6],
        "vrefint_raw": words[7],
        "vstor_raw": words[8],
        "solar_raw": words[9],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--restore-mv", type=int, default=4660)
    parser.add_argument("--hold-seconds", type=float, default=3600)
    parser.add_argument("--heartbeat-seconds", type=float, default=10)
    args = parser.parse_args()

    control, control_port, data_port = open_endpoints()
    jlink: JLinkSession | None = None
    started = time.monotonic()
    try:
        assert_power(control, args.restore_mv)
        time.sleep(0.5)
        print(
            json.dumps(
                {
                    "event": "sweep_power_on",
                    "control_port": control_port,
                    "data_port": data_port,
                    "source_mv": args.restore_mv,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        jlink = JLinkSession()
        for source_mv in VOLTAGES_MV:
            control.set_source_voltage(source_mv)
            time.sleep(args.settle_seconds)
            reading = read_ptd(jlink)
            print(
                json.dumps(
                    {
                        "event": "voltage_point",
                        "source_mv": source_mv,
                        "reading": reading,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        control.set_source_voltage(args.restore_mv)
        time.sleep(0.5)
        print(
            json.dumps(
                {
                    "event": "sweep_restored",
                    "source_mv": args.restore_mv,
                    "hold_seconds": args.hold_seconds,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        deadline = time.monotonic() + args.hold_seconds
        next_heartbeat = time.monotonic() + args.heartbeat_seconds
        reconnects = 0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_heartbeat:
                time.sleep(min(0.25, next_heartbeat - now))
                continue
            try:
                assert_power(control, args.restore_mv)
            except Exception:
                try:
                    control.ser.close()
                except Exception:
                    pass
                reconnect_deadline = time.monotonic() + 30
                while True:
                    try:
                        control, control_port, data_port = open_endpoints()
                        assert_power(control, args.restore_mv)
                        reconnects += 1
                        break
                    except Exception as error:
                        if time.monotonic() >= reconnect_deadline:
                            raise RuntimeError(
                                "PPK2 unavailable for 30 s during post-sweep "
                                "hold; unable to guarantee DUT power"
                            ) from error
                        time.sleep(0.5)
            print(
                json.dumps(
                    {
                        "event": "sweep_power_heartbeat",
                        "held_seconds": round(
                            args.hold_seconds - max(0, deadline - time.monotonic()),
                            3,
                        ),
                        "source_mv": args.restore_mv,
                        "control_port": control_port,
                        "reconnects": reconnects,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            next_heartbeat = time.monotonic() + args.heartbeat_seconds
    finally:
        if jlink is not None:
            jlink.close()
        # Preserve the restored rail; never issue DUT OFF. If the USB hub
        # re-enumerated, the old serial handle is dead: reconnect and reassert
        # the safe voltage before returning.
        restored = False
        try:
            control.set_source_voltage(args.restore_mv)
            control.toggle_DUT_power("ON")
            restored = True
        except Exception:
            try:
                control.ser.close()
            except Exception:
                pass
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not restored:
                try:
                    control, _, _ = open_endpoints()
                    control.use_source_meter()
                    control.set_source_voltage(args.restore_mv)
                    control.toggle_DUT_power("ON")
                    restored = True
                except Exception:
                    time.sleep(0.5)
        print(
            json.dumps(
                {
                    "event": "sweep_hold_end",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "source_mv": args.restore_mv,
                    "restored": restored,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        control.ser.close()


if __name__ == "__main__":
    main()
