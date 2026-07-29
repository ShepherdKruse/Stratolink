#!/usr/bin/env python3
"""Draft immutable verifier bindings from two byte-identical flight builds.

This tool is deliberately non-blessing: it never touches the target, rewrites
the checked-in HIL files, or changes verify_flight_candidate.py.  It creates a
single, overwrite-protected report whose values can be independently reviewed
before the static verifier bindings are patched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from evidence_provenance import record as provenance_record
from generate_flight_hil import SYMBOLS, load_symbols, sha256
from verify_flight_candidate import (
    BANNED_MARKERS,
    FLASH_SECTIONS,
    ROOT,
    flight_source_inputs,
    section_sizes,
)


DEFAULT_ELF = ROOT / "firmware/.pio/build/stratolink/firmware.elf"
DEFAULT_BIN = ROOT / "firmware/.pio/build/stratolink/firmware.bin"


def require_create_once(path: Path) -> None:
    partials = sorted(
        path.parent.glob(f".{path.name}.*.partial")
    ) if path.parent.is_dir() else []
    collisions = ([path] if path.exists() else []) + partials
    if collisions:
        raise SystemExit(
            "refusing to overwrite candidate-identity evidence: "
            + ", ".join(str(item) for item in collisions)
        )


def write_create_once(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".partial",
        delete=False,
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite candidate-identity evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def marker_hits(path: Path) -> list[str]:
    lowered = path.read_bytes().lower()
    return [
        marker.decode("ascii") for marker in BANNED_MARKERS
        if marker in lowered
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--bin", dest="binary", type=Path, default=DEFAULT_BIN)
    parser.add_argument("--independent-elf", type=Path, required=True)
    parser.add_argument("--independent-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_create_once(args.output)
    elf = args.elf.resolve()
    binary = args.binary.resolve()
    independent_elf = args.independent_elf.resolve()
    independent_bin = args.independent_bin.resolve()
    artifacts = (elf, binary, independent_elf, independent_bin)
    missing = [str(path) for path in artifacts if not path.is_file()]
    if missing:
        raise SystemExit("candidate artifact is missing: " + ", ".join(missing))
    if elf.read_bytes() != independent_elf.read_bytes():
        raise SystemExit("independent ELF is not byte-identical")
    if binary.read_bytes() != independent_bin.read_bytes():
        raise SystemExit("independent BIN is not byte-identical")

    hits = {
        str(path): found
        for path in artifacts
        if (found := marker_hits(path))
    }
    if hits:
        raise SystemExit("candidate contains a bench/diagnostic marker")

    sources = flight_source_inputs()
    oldest_artifact_mtime = min(
        elf.stat().st_mtime_ns, independent_elf.stat().st_mtime_ns
    )
    newer_sources = [
        str(path.relative_to(ROOT))
        for path in sources
        if path.stat().st_mtime_ns > oldest_artifact_mtime
    ]
    if newer_sources:
        raise SystemExit(
            "firmware inputs changed after a candidate build: "
            + ", ".join(newer_sources)
        )

    sections = section_sizes(elf)
    independent_sections = section_sizes(independent_elf)
    if sections != independent_sections:
        raise SystemExit("independent ELF section layout differs")
    symbols = load_symbols(elf)
    independent_symbols = load_symbols(independent_elf)
    if symbols != independent_symbols or set(symbols) != set(SYMBOLS):
        raise SystemExit("independent required-symbol layout differs")

    flash_load = sum(sections[name] for name in FLASH_SECTIONS)
    static_ram = sections[".data"] + sections[".bss"]
    reserved_ram = sections["._user_heap_stack"]
    bindings = {
        "EXPECTED_ELF_SHA256": sha256(elf),
        "EXPECTED_BIN_SHA256": sha256(binary),
        "EXPECTED_ELF_BYTES": elf.stat().st_size,
        "EXPECTED_BIN_BYTES": binary.stat().st_size,
        "EXPECTED_FLASH_LOAD_BYTES": flash_load,
        "EXPECTED_STATIC_RAM_BYTES": static_ram,
        "EXPECTED_RESERVED_RAM_BYTES": reserved_ram,
        "EXPECTED_HIL_SYMBOLS": len(symbols),
    }
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "passed": True,
        "scope": (
            "local build reproducibility and static binding draft only; not a "
            "target flash, HIL result, or launch-readiness verdict"
        ),
        "byte_identical": {"elf": True, "bin": True},
        "bindings": bindings,
        "memory_sections": sections,
        "symbols": symbols,
        "source_freshness": {
            "inputs_checked": len(sources),
            "newer_than_oldest_build": [],
        },
        "banned_marker_hits": {},
        "provenance": {
            "canonical/elf": provenance_record(elf),
            "canonical/bin": provenance_record(binary),
            "independent/elf": provenance_record(independent_elf),
            "independent/bin": provenance_record(independent_bin),
            **{
                f"source/{path.relative_to(ROOT)}": provenance_record(path)
                for path in sources
            },
        },
    }
    write_create_once(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
