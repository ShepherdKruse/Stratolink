#!/usr/bin/env python3
"""Source- and ELF-bound dynamic-memory audit for the flight image.

This does not execute or mutate the target.  It quantifies the allocations
which are easy to miss in PlatformIO's static RAM summary and keeps the
remaining stack-watermark limitation explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from evidence_provenance import write_create_once


RADIO_OBJECT_BYTES = 444
RADIO_MODULE_BYTES = 72
RADIO_HAL_BYTES = 44
GNSS_PACKET_CFG_BYTES = 300
GNSS_NAV_PVT_BYTES = 112
GMTIME_STATE_BYTES = 36
MAX_SX126X_DATA_BYTES = 256
SX126X_STREAM_OVERHEAD_BYTES = 4
ALLOCATOR_OVERHEAD_BOUND_BYTES = 8
MIN_UNCOMMITTED_RAM_BYTES = 32 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def symbol_value(nm: str, name: str) -> int:
    match = re.search(rf"^([0-9a-fA-F]+)\s+\S\s+{re.escape(name)}$", nm, re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing ELF symbol: {name}")
    return int(match.group(1), 16)


def require(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE) is None:
        raise RuntimeError(f"missing source/ELF contract: {label}")


def audit(repo: Path, elf: Path) -> dict[str, object]:
    nm = run("arm-none-eabi-nm", "-n", "-C", str(elf))
    disassembly = run("arm-none-eabi-objdump", "-d", "-C", str(elf))
    platformio = (repo / "firmware/platformio.ini").read_text()
    lorawan = (repo / "firmware/src/lorawan.cpp").read_text()
    gps = (repo / "firmware/src/gps_ublox.cpp").read_text()
    ublox_types = (
        repo
        / "firmware/.pio/libdeps/stratolink/SparkFun u-blox GNSS v3/src/u-blox_external_typedefs.h"
    ).read_text()
    radiolib_module = (
        repo / "firmware/.pio/libdeps/stratolink/RadioLib/src/Module.cpp"
    ).read_text()

    require(platformio, r"SparkFun u-blox GNSS v3@3\.1\.13", "pinned u-blox version")
    require(platformio, r"RadioLib@7\.6\.0", "pinned RadioLib version")
    require(platformio, r"(?m)^\s*-fcheck-new\s*$", "null-returning new semantics")
    if "new STM32WLx(new STM32WLx_Module())" in lorawan:
        raise RuntimeError(
            "missing source/ELF contract: nested unchecked radio allocation remains"
        )
    require(
        lorawan,
        r"STM32WLx_Module\* module = new STM32WLx_Module\(\);\s*"
        r"if \(!module \|\| !module->hal\)",
        "staged module/HAL allocation and null gate",
    )
    require(
        lorawan,
        r"STM32WLx\* candidate = new STM32WLx\(module\);\s*if \(!candidate\)",
        "staged radio allocation and null gate",
    )
    require(lorawan, r"delete module->hal;", "HAL allocation cleanup")
    require(lorawan, r"module->hal = nullptr;", "HAL cleanup ownership clear")
    require(lorawan, r"delete module;", "module allocation cleanup")
    require(
        lorawan,
        r"if \(!radio && !allocate_radio\(\)\) return false;",
        "allocation failure blocks radio initialization",
    )
    require(gps, r"static SFE_UBLOX_GNSS_SERIAL gnss;", "flight UART GNSS instance")
    require(gps, r"if \(gnss\.getPVT\(\)\)", "NAV-PVT use")
    require(ublox_types, r"#define MAX_PAYLOAD_SIZE 300\b", "u-blox packet buffer size")
    require(radiolib_module, r"buffOut = new uint8_t\[buffLen\]", "RadioLib output scratch")
    require(radiolib_module, r"buffIn = new uint8_t\[buffLen\]", "RadioLib input scratch")
    require(radiolib_module, r"delete\[\] buffOut;", "RadioLib output release")
    require(radiolib_module, r"delete\[\] buffIn;", "RadioLib input release")

    # These immediates are emitted by the exact ARM ABI and independently
    # confirm sizeof(STM32WLx), sizeof(STM32WLx_Module), and Stm32wlxHal. The
    # bounded spans also prove that -fcheck-new emitted a null branch before
    # each constructor: the source-level checks above would be unsafe if the
    # compiler still assumed allocation could never return null.
    require(
        disassembly,
        r"movs\s+r0, #72\b[\s\S]{0,100}operator new[\s\S]{0,80}"
        r"(?:cbz|cmp)\b[\s\S]{0,100}STM32WLx_Module::STM32WLx_Module\(\)",
        "STM32WLx_Module size and pre-constructor null branch",
    )
    require(
        disassembly,
        r"mov\.w\s+r0, #444\b[\s\S]{0,100}operator new[\s\S]{0,80}"
        r"(?:cbnz|cmp)\b[\s\S]{0,600}STM32WLx::STM32WLx\(STM32WLx_Module\*\)",
        "STM32WLx size and pre-constructor null branch",
    )
    require(disassembly, r"STM32WLx_Module::STM32WLx_Module\(\)[\s\S]{0,180}movs\s+r0, #44\b[\s\S]{0,100}operator new", "Stm32wlxHal size")
    require(disassembly, r"DevUBLOXGNSS::initPacketUBXNAVPVT\(\)[\s\S]{0,180}movs\s+r0, #112\b[\s\S]{0,100}operator new", "NAV-PVT size")

    ram_end = symbol_value(nm, "_estack")
    static_end = symbol_value(nm, "_end")
    uncommitted_ram = ram_end - static_end

    persistent_payload = (
        RADIO_OBJECT_BYTES
        + RADIO_MODULE_BYTES
        + RADIO_HAL_BYTES
        + GNSS_PACKET_CFG_BYTES
        + GNSS_NAV_PVT_BYTES
        + GMTIME_STATE_BYTES
    )
    persistent_allocations = 6
    persistent_bound = persistent_payload + persistent_allocations * ALLOCATOR_OVERHEAD_BOUND_BYTES
    stream_buffer_bytes = MAX_SX126X_DATA_BYTES + SX126X_STREAM_OVERHEAD_BYTES
    transient_payload = 2 * stream_buffer_bytes
    transient_bound = transient_payload + 2 * ALLOCATOR_OVERHEAD_BOUND_BYTES
    modeled_peak_heap = persistent_bound + transient_bound
    residual = uncommitted_ram - modeled_peak_heap

    checks = {
        "positive_ram_interval": uncommitted_ram > 0,
        "uncommitted_ram_at_least_32k": uncommitted_ram >= MIN_UNCOMMITTED_RAM_BYTES,
        "modeled_peak_below_uncommitted_ram": modeled_peak_heap < uncommitted_ram,
        "radio_object_sizes_exact": True,
        "radio_allocation_staged_and_null_checked": True,
        "radio_scratch_release_paths_present": True,
        "dependency_versions_pinned": True,
    }
    passed = all(checks.values())
    return {
        "schema": "stratolink.dynamic_memory_audit.v2",
        "pass": passed,
        "elf": str(elf),
        "elf_sha256": sha256(elf),
        "addresses": {"static_end": hex(static_end), "ram_end": hex(ram_end)},
        "uncommitted_ram_bytes": uncommitted_ram,
        "persistent_heap_payload_bytes": persistent_payload,
        "persistent_heap_bound_bytes": persistent_bound,
        "radio_transient_peak_payload_bytes": transient_payload,
        "radio_transient_peak_bound_bytes": transient_bound,
        "modeled_peak_heap_bytes": modeled_peak_heap,
        "modeled_ram_after_peak_heap_before_stack_bytes": residual,
        "modeled_margin_ratio": round(uncommitted_ram / modeled_peak_heap, 3),
        "checks": checks,
        "scope": {
            "proves": [
                "exact ELF allocation-site object sizes",
                "source-bound persistent GNSS/radio allocation model",
                "staged RadioLib allocation and emitted pre-constructor null branches",
                "bounded SX126x command scratch model",
                "large static-to-stack-top RAM interval",
            ],
            "does_not_prove": [
                "on-target stack high-water mark",
                "absence of arbitrary memory corruption",
                "graceful behavior if allocator failure is externally forced",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--elf", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    elf = (args.elf or repo / "firmware/.pio/build/stratolink/firmware.elf").resolve()
    result = audit(repo, elf)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_create_once(args.output, encoded.encode("utf-8"))
    print(encoded, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
