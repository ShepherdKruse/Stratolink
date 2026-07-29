#!/usr/bin/env python3
"""Prevent private flight evidence and credentials from public staging."""

from __future__ import annotations

from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main() -> None:
    ignore = (ROOT / ".gitignore").read_bytes()
    assert b"\0" not in ignore, ".gitignore contains NUL bytes"
    ignore.decode("ascii")

    private_paths = (
        "firmware/include/secrets.h",
        "firmware/include/secrets_board2.h",
        "firmware/.pio/build/stratolink/firmware.bin",
        "analysis/diagnostics/logs/private-flight-evidence.json",
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", *private_paths],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert ignored.returncode == 0, ignored.stderr
    observed = set(ignored.stdout.splitlines())
    assert observed == set(private_paths), (
        "a private release path is not ignored: "
        + ", ".join(sorted(set(private_paths) - observed))
    )

    tracked = subprocess.run(
        [
            "git", "grep", "-n", "-I", "-E",
            r"NNSXS\.[A-Z0-9]{8,}|sb_secret_[A-Za-z0-9_-]{8,}",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode in (0, 1), tracked.stderr
    assert tracked.returncode == 1, (
        "tracked files contain a live-looking TTN/Supabase secret:\n"
        + tracked.stdout
    )

    activation = (ROOT / "web/lib/actions/activate.ts").read_text(
        encoding="utf-8"
    )
    assert "NEXT_PUBLIC_DEV_MODE" not in activation, (
        "a browser-visible environment flag must not authorize service-role "
        "device auto-creation"
    )
    assert ".includes(process.env.ADMIN_ACTIVATION_KEY)" not in activation, (
        "never place an admin secret inside a device ID or URL-bearing field"
    )
    print("PASS: public staging excludes credentials and private flight evidence")


if __name__ == "__main__":
    main()
