#!/usr/bin/env python3
"""Isolated GCC stack-frame audit for an exact PlatformIO flight build."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from evidence_provenance import write_create_once


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_su_line(line: str) -> dict[str, object] | None:
    parts = line.rstrip().split("\t")
    if len(parts) < 3:
        return None
    location_and_name, byte_text, qualifier = parts[0], parts[1], parts[2]
    match = re.match(r"^(.*?):(\d+):(\d+):(.*)$", location_and_name)
    if match is None:
        return None
    return {
        "source": match.group(1),
        "line": int(match.group(2)),
        "column": int(match.group(3)),
        "function": match.group(4),
        "bytes": int(byte_text),
        "qualifier": qualifier,
    }


def linked_function_names(elf: Path) -> set[str]:
    output = subprocess.run(
        ["arm-none-eabi-nm", "-C", "--defined-only", str(elf)],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    names: set[str] = set()
    for line in output.splitlines():
        match = re.match(r"^[0-9a-fA-F]+\s+([TtWw])\s+(.+)$", line)
        if match:
            names.add(match.group(2))
    return names


def instruction_relocation_dump(path: Path) -> str:
    output = subprocess.run(
        ["arm-none-eabi-objdump", "-dr", str(path)],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return re.sub(
        r"^.*?:\s+file format ",
        "<object>: file format ",
        output,
        count=1,
        flags=re.MULTILINE,
    )


def function_is_linked(function: str, names: set[str]) -> bool:
    if function in names:
        return True
    return any(function.endswith(" " + name) for name in names)


def compile_one(entry: dict[str, str], firmware: Path, root: Path) -> dict[str, object]:
    arguments = shlex.split(entry["command"])
    output_index = arguments.index("-o") + 1
    relative_output = Path(entry["output"])
    probe_output = root / relative_output
    probe_output.parent.mkdir(parents=True, exist_ok=True)
    arguments[output_index] = str(probe_output)
    arguments.insert(arguments.index("-c"), "-fstack-usage")
    completed = subprocess.run(
        arguments,
        cwd=firmware,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {
            "file": entry["file"],
            "error": completed.stderr[-2000:],
            "returncode": completed.returncode,
        }
    original = firmware / relative_output
    su_path = probe_output.with_suffix(".su")
    rows = []
    if su_path.is_file():
        rows = [row for line in su_path.read_text().splitlines() if (row := parse_su_line(line))]
    original_code = instruction_relocation_dump(original)
    probe_code = instruction_relocation_dump(probe_output)
    object_identical = original.is_file() and sha256(original) == sha256(probe_output)
    normalized_object_identical = object_identical
    normalization = None
    if not object_identical and str(entry["file"]).endswith("RadioLib/src/Module.cpp"):
        source = firmware / entry["file"]
        source_text = source.read_text()
        if "static volatile const char info[] = RADIOLIB_INFO;" in source_text:
            original_normalized = root / "normalized" / "Module.original.o"
            probe_normalized = root / "normalized" / "Module.probe.o"
            original_normalized.parent.mkdir(parents=True, exist_ok=True)
            for input_path, output_path in (
                (original, original_normalized),
                (probe_output, probe_normalized),
            ):
                subprocess.run(
                    [
                        "arm-none-eabi-objcopy",
                        "--remove-section=.data._ZL4info",
                        str(input_path),
                        str(output_path),
                    ],
                    check=True,
                )
            normalized_object_identical = (
                sha256(original_normalized) == sha256(probe_normalized)
            )
            normalization = (
                "removed RadioLib's GC-discarded volatile RADIOLIB_INFO "
                "compile-date section"
            )
    return {
        "file": entry["file"],
        "object_identical": object_identical,
        "normalized_object_identical": normalized_object_identical,
        "object_normalization": normalization,
        "instruction_relocation_dump_identical": original_code == probe_code,
        "rows": rows,
    }


def audit(repo: Path, compiledb: Path, elf: Path, jobs: int) -> dict[str, object]:
    firmware = repo / "firmware"
    entries = json.loads(compiledb.read_text())
    entries = [
        entry for entry in entries
        if str(entry.get("output", "")).startswith(".pio/build/stratolink/")
    ]
    linked_names = linked_function_names(elf)
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="stratolink-stack-audit-") as tmp:
        root = Path(tmp)
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
            futures = [executor.submit(compile_one, entry, firmware, root) for entry in entries]
            for future in as_completed(futures):
                results.append(future.result())

    failures = [row for row in results if "error" in row]
    object_mismatches = [row["file"] for row in results if row.get("object_identical") is not True]
    normalized_object_mismatches = [
        row["file"] for row in results
        if row.get("normalized_object_identical") is not True
    ]
    object_normalizations = [
        {"file": row["file"], "normalization": row["object_normalization"]}
        for row in results if row.get("object_normalization")
    ]
    code_mismatches = [
        row["file"] for row in results
        if row.get("instruction_relocation_dump_identical") is not True
    ]
    all_frames = [frame for result in results for frame in result.get("rows", [])]
    linked_frames = [
        frame for frame in all_frames
        if function_is_linked(str(frame["function"]), linked_names)
    ]
    non_static = [frame for frame in linked_frames if frame["qualifier"] != "static"]
    ublox_header = (
        firmware
        / ".pio/libdeps/stratolink/SparkFun u-blox GNSS v3/src/u-blox_GNSS.h"
    ).read_text()
    i2c_vla_source_bound = (
        "uint8_t i2cTransactionSize = 32;" in ublox_header
        and "void setI2CTransactionSize(uint8_t transactionSize);" in ublox_header
    )
    bounded_dynamic = [
        {**frame, "maximum_modeled_frame_bytes": 296}
        for frame in non_static
        if i2c_vla_source_bound and str(frame["function"]).endswith(
            "DevUBLOXGNSS::sendI2cCommand(ubxPacket*)"
        )
    ]
    unbounded_or_unrecognized = [
        frame for frame in non_static
        if not i2c_vla_source_bound or not str(frame["function"]).endswith(
            "DevUBLOXGNSS::sendI2cCommand(ubxPacket*)"
        )
    ]
    largest = sorted(linked_frames, key=lambda row: int(row["bytes"]), reverse=True)[:25]
    passed = (
        not failures
        and not normalized_object_mismatches
        and not code_mismatches
        and not unbounded_or_unrecognized
        and bool(linked_frames)
    )
    return {
        "schema": "stratolink.static_stack_usage_audit.v1",
        "pass": passed,
        "elf": str(elf),
        "elf_sha256": sha256(elf),
        "compile_commands": str(compiledb),
        "compile_commands_sha256": sha256(compiledb),
        "compiled_translation_units": len(entries),
        "compile_failures": failures,
        "probe_object_mismatches": object_mismatches,
        "probe_normalized_object_mismatches": normalized_object_mismatches,
        "probe_object_normalizations": object_normalizations,
        "probe_instruction_relocation_mismatches": code_mismatches,
        "parsed_frames": len(all_frames),
        "linked_frames": len(linked_frames),
        "linked_non_static_frames": non_static,
        "linked_source_bounded_dynamic_frames": bounded_dynamic,
        "ublox_i2c_vla_has_8_bit_source_bound": i2c_vla_source_bound,
        "linked_unbounded_or_unrecognized_dynamic_frames": unbounded_or_unrecognized,
        "largest_linked_frames": largest,
        "maximum_linked_single_frame_bytes": max(
            (int(frame["bytes"]) for frame in linked_frames), default=None
        ),
        "scope": {
            "proves": [
                "probe instruction and relocation dumps match the exact build objects",
                "GCC reports static frames or the one source-bounded 8-bit u-blox I2C VLA for matched linked functions",
                "largest matched linked single-function frame",
            ],
            "does_not_prove": [
                "byte-identical relocatable objects when discarded compile-date data differs",
                "maximum nested call-chain stack",
                "interrupt nesting or library callbacks not matched by demangled name",
                "on-target stack high-water mark",
                "absence of stack corruption",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--compiledb", type=Path)
    parser.add_argument("--elf", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    result = audit(
        repo,
        (args.compiledb or repo / "firmware/compile_commands.json").resolve(),
        (args.elf or repo / "firmware/.pio/build/stratolink/firmware.elf").resolve(),
        args.jobs,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_create_once(args.output, encoded.encode("utf-8"))
    print(encoded, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
