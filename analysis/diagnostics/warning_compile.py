#!/usr/bin/env python3
"""Replay flight-source compile commands with stricter warning diagnostics."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


WARNING_FLAGS = (
    "-Wall",
    "-Wextra",
    "-Wshadow",
    "-Wconversion",
    "-Wsign-conversion",
    "-Wdouble-promotion",
    "-Wformat=2",
    "-Wundef",
)
ANALYZER_FLAGS = (
    "-fanalyzer",
    "-Wanalyzer-too-complex",
)


def syntax_command(command: str, analyzer: bool = False) -> list[str]:
    args = shlex.split(command)
    result: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg == "-o":
            skip_next = True
            continue
        if arg == "-c":
            continue
        if arg.startswith("-I") and arg not in ("-Iinclude", "-Isrc"):
            include_path = arg[2:]
            if include_path.startswith((".pio/", "/Users/")):
                result.extend(("-isystem", include_path))
                continue
        result.append(arg)
    result.extend(WARNING_FLAGS)
    if analyzer:
        result.extend(ANALYZER_FLAGS)
    result.append("-fsyntax-only")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compile-commands",
        type=Path,
        default=Path("firmware/compile_commands.json"),
    )
    parser.add_argument(
        "--analyzer",
        action="store_true",
        help="also enable GCC's interprocedural -fanalyzer diagnostics",
    )
    args = parser.parse_args()

    database_path = args.compile_commands.resolve()
    entries = json.loads(database_path.read_text())
    project_entries = sorted(
        (entry for entry in entries if str(entry["file"]).startswith("src/")),
        key=lambda entry: entry["file"],
    )
    if not project_entries:
        print("FAIL: compilation database contains no flight project sources")
        return 2

    warnings: list[str] = []
    failures: list[str] = []
    for entry in project_entries:
        completed = subprocess.run(
            syntax_command(entry["command"], analyzer=args.analyzer),
            cwd=entry["directory"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        diagnostics = completed.stdout + completed.stderr
        if diagnostics.strip():
            warnings.append(f"--- {entry['file']} ---\n{diagnostics.rstrip()}")
        if completed.returncode:
            failures.append(entry["file"])

    if warnings:
        print("\n".join(warnings))
    print(
        f"Strict {'analyzer + ' if args.analyzer else ''}warning compile: "
        f"{len(project_entries)} sources, "
        f"{len(warnings)} with diagnostics, {len(failures)} failures"
    )
    return 1 if failures or warnings else 0


if __name__ == "__main__":
    sys.exit(main())
