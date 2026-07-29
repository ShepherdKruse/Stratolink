#!/usr/bin/env python3
"""Fail-closed verifier for the byte-frozen StratoLink-2 flight candidate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from evidence_provenance import record as provenance_record
from generate_flight_hil import SYMBOLS, load_symbols, sha256


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_ELF = ROOT / "firmware/.pio/build/stratolink/firmware.elf"
DEFAULT_BIN = ROOT / "firmware/.pio/build/stratolink/firmware.bin"
DEFAULT_GENERATED = HERE / "generated"
DEFAULT_DYNAMIC_MEMORY_AUDIT = (
    HERE / "logs/stratolink2_flight_candidate_dynamic_memory_20260728_v15.json"
)
DEFAULT_STATIC_STACK_AUDIT = (
    HERE / "logs/stratolink2_flight_candidate_static_stack_20260728_v15.json"
)
EXPECTED_ELF_SHA256 = (
    "8fa10da859b2c542d244cb2f62bebcf388730cbeea9eb4746a94c2d50e3d91f8"
)
EXPECTED_BIN_SHA256 = (
    "920f57c139236b6097caec8936cefe681f82fa3b4c4e084f2861ad54bd1ae20d"
)
EXPECTED_ELF_BYTES = 239736
EXPECTED_BIN_BYTES = 132956
EXPECTED_FLASH_LOAD_BYTES = 132948
EXPECTED_STATIC_RAM_BYTES = 6736
EXPECTED_RESERVED_RAM_BYTES = 1540
EXPECTED_HIL_SYMBOLS = 51
GENERATED_NAMES = (
    "stratolink_flight_hil_manifest.json",
    "jlink_read_flight_health.jlink",
    "jlink_read_tamp32.jlink",
    "jlink_read_flight_state.jlink",
    "jlink_wake_read_flight_state.jlink",
    "jlink_bench_authorize_us.jlink",
    "jlink_bench_clear_region_lease.jlink",
    "jlink_flash_flight.jlink",
)
BANNED_MARKERS = (
    b"bench_seed_region",
    b"stratolink-bench",
    b"stratolink-soak",
    b"main_power_test",
    b"main_region_test",
    b"main_gps_diag",
    b"main_gps_iprobe",
    b"main_gps_power_states",
    b"main_mic_test",
    b"main_meshtastic_diag",
    b"main_ctt_diag",
    b"main_ctt_tx_diag",
    b"main_b2b_diag",
)
FLASH_SECTIONS = (
    ".isr_vector",
    ".text",
    ".rodata",
    ".ARM.extab",
    ".ARM",
    ".preinit_array",
    ".init_array",
    ".fini_array",
    ".data",
)


def find_size_tool() -> str:
    candidates = [
        shutil.which("arm-none-eabi-size"),
        "/Users/twarn/.platformio/packages/toolchain-gccarmnoneeabi/bin/"
        "arm-none-eabi-size",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("arm-none-eabi-size not found")


def section_sizes(elf: Path) -> dict[str, int]:
    output = subprocess.check_output(
        [find_size_tool(), "-A", str(elf)],
        text=True,
    )
    result: dict[str, int] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0].startswith("."):
            result[fields[0]] = int(fields[1])
    required = set(FLASH_SECTIONS) | {".bss", "._user_heap_stack"}
    missing = sorted(required - set(result))
    if missing:
        raise SystemExit("ELF section report is missing: " + ", ".join(missing))
    return result


def flight_source_inputs() -> list[Path]:
    firmware = ROOT / "firmware"
    paths = [firmware / "platformio.ini"]
    for directory in (firmware / "src", firmware / "include", firmware / "boards"):
        paths.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(paths, key=lambda path: str(path))


def atomic_json(path: Path, value: dict) -> None:
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
        # link(2) is the final create-once commit: unlike replace(), it fails if
        # another process created the evidence path after the preflight check.
        os.link(temporary, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite candidate evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def require_create_once_output(path: Path | None) -> None:
    if path is None:
        return
    partials = sorted(
        path.parent.glob(f".{path.name}.*.partial")
    ) if path.parent.is_dir() else []
    collisions = ([path] if path.exists() else []) + partials
    if collisions:
        raise SystemExit(
            "refusing to overwrite candidate evidence: "
            + ", ".join(str(item) for item in collisions)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--bin", dest="binary", type=Path, default=DEFAULT_BIN)
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=DEFAULT_GENERATED,
    )
    parser.add_argument(
        "--dynamic-memory-audit",
        type=Path,
        default=DEFAULT_DYNAMIC_MEMORY_AUDIT,
    )
    parser.add_argument(
        "--static-stack-audit",
        type=Path,
        default=DEFAULT_STATIC_STACK_AUDIT,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require_create_once_output(args.output)
    elf = args.elf.resolve()
    binary = args.binary.resolve()
    failures: list[str] = []

    if not elf.is_file() or not binary.is_file():
        raise SystemExit("candidate ELF/BIN is missing")
    elf_hash = sha256(elf)
    bin_hash = sha256(binary)
    if elf_hash != EXPECTED_ELF_SHA256:
        failures.append("ELF SHA-256 differs from the frozen candidate")
    if bin_hash != EXPECTED_BIN_SHA256:
        failures.append("BIN SHA-256 differs from the frozen candidate")
    if elf.stat().st_size != EXPECTED_ELF_BYTES:
        failures.append("ELF byte length differs from the frozen candidate")
    if binary.stat().st_size != EXPECTED_BIN_BYTES:
        failures.append("BIN byte length differs from the frozen candidate")

    sources = flight_source_inputs()
    newer_sources = [
        str(path.relative_to(ROOT))
        for path in sources
        if path.stat().st_mtime_ns > elf.stat().st_mtime_ns
    ]
    if newer_sources:
        failures.append("one or more firmware inputs are newer than the ELF")

    marker_hits: dict[str, list[str]] = {}
    for artifact in (elf, binary):
        lowered = artifact.read_bytes().lower()
        hits = [
            marker.decode("ascii")
            for marker in BANNED_MARKERS
            if marker in lowered
        ]
        if hits:
            marker_hits[str(artifact)] = hits
    if marker_hits:
        failures.append("candidate contains a bench/diagnostic marker")

    sections = section_sizes(elf)
    flash_load = sum(sections[name] for name in FLASH_SECTIONS)
    static_ram = sections[".data"] + sections[".bss"]
    reserved_ram = sections["._user_heap_stack"]
    if flash_load != EXPECTED_FLASH_LOAD_BYTES:
        failures.append("loadable flash section sum changed")
    if static_ram != EXPECTED_STATIC_RAM_BYTES:
        failures.append("initialized/static RAM size changed")
    if reserved_ram != EXPECTED_RESERVED_RAM_BYTES:
        failures.append("reserved heap/stack size changed")

    memory_audits: dict[str, dict] = {}
    for name, path, schema in (
        (
            "dynamic_memory",
            args.dynamic_memory_audit.resolve(),
            "stratolink.dynamic_memory_audit.v2",
        ),
        (
            "static_stack",
            args.static_stack_audit.resolve(),
            "stratolink.static_stack_usage_audit.v1",
        ),
    ):
        if not path.is_file():
            failures.append(f"{name.replace('_', '-')} audit is missing")
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            failures.append(f"{name.replace('_', '-')} audit is invalid")
            continue
        if not isinstance(value, dict):
            failures.append(f"{name.replace('_', '-')} audit is invalid")
            continue
        memory_audits[name] = value
        if value.get("schema") != schema or value.get("pass") is not True:
            failures.append(f"{name.replace('_', '-')} audit did not pass")
        if value.get("elf_sha256") != elf_hash:
            failures.append(f"{name.replace('_', '-')} audit binds another ELF")
        if name == "static_stack":
            compile_commands = value.get("compile_commands")
            expected_compile_commands_sha = value.get("compile_commands_sha256")
            if (
                not isinstance(compile_commands, str)
                or not isinstance(expected_compile_commands_sha, str)
                or not Path(compile_commands).is_file()
                or sha256(Path(compile_commands)) != expected_compile_commands_sha
            ):
                failures.append("static-stack audit compilation database changed")

    symbols = load_symbols(elf)
    if (
        set(symbols) != set(SYMBOLS)
        or len(symbols) != EXPECTED_HIL_SYMBOLS
    ):
        failures.append("required HIL symbol set changed")

    generated_mismatches: list[str] = []
    with tempfile.TemporaryDirectory(prefix="stratolink-flight-hil-") as raw:
        temporary = Path(raw)
        generation = subprocess.run(
            [
                sys.executable,
                str(HERE / "generate_flight_hil.py"),
                "--elf",
                str(elf),
                "--bin",
                str(binary),
                "--out-dir",
                str(temporary),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if generation.returncode != 0:
            failures.append("exact-candidate HIL generation failed")
        else:
            for name in GENERATED_NAMES:
                expected_path = args.generated_dir / name
                regenerated_path = temporary / name
                if (
                    not expected_path.is_file()
                    or expected_path.read_bytes() != regenerated_path.read_bytes()
                ):
                    generated_mismatches.append(name)
    if generated_mismatches:
        failures.append("checked-in-worktree HIL scripts/manifest are stale")

    provenance = {
        "candidate/elf": provenance_record(elf),
        "candidate/bin": provenance_record(binary),
    }
    provenance.update(
        {
            f"source/{path.relative_to(ROOT)}": provenance_record(path)
            for path in sources
        }
    )
    provenance.update(
        {
            f"memory_audit/{name}": provenance_record(path.resolve())
            for name, path in (
                ("dynamic_memory", args.dynamic_memory_audit),
                ("static_stack", args.static_stack_audit),
            )
            if path.is_file()
        }
    )
    provenance.update(
        {
            f"generated/{name}": provenance_record(args.generated_dir / name)
            for name in GENERATED_NAMES
            if (args.generated_dir / name).is_file()
        }
    )

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "passed": not failures,
        "failures": failures,
        "candidate": {
            "elf": str(elf),
            "elf_bytes": elf.stat().st_size,
            "elf_sha256": elf_hash,
            "bin": str(binary),
            "bin_bytes": binary.stat().st_size,
            "bin_sha256": bin_hash,
        },
        "memory": {
            "loadable_flash_bytes": flash_load,
            "initialized_static_ram_bytes": static_ram,
            "reserved_heap_stack_bytes": reserved_ram,
            "audits": {
                name: {
                    "schema": value.get("schema"),
                    "pass": value.get("pass"),
                    "elf_sha256": value.get("elf_sha256"),
                }
                for name, value in memory_audits.items()
            },
        },
        "source_freshness": {
            "inputs_checked": len(sources),
            "newer_than_elf": newer_sources,
        },
        "banned_marker_hits": marker_hits,
        "hil": {
            "required_symbols": len(symbols),
            "generated_files": list(GENERATED_NAMES),
            "mismatches": generated_mismatches,
        },
        "provenance": provenance,
    }
    if args.output:
        atomic_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
