#!/usr/bin/env python3
"""Generate exact-ELF J-Link scripts and a machine-readable HIL manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


SYMBOLS = {
    "_joined": "LoRaWAN session joined/restored flag",
    "REGION_ID": "active LoRaWAN regulatory plan",
    "boot_count": "retained boot counter snapshot",
    "boot_reset_cause": "RCC reset-cause snapshot",
    "s_boot_reset_code": "compact retained-domain-aware reset classification",
    "fCntUp": "next LoRaWAN uplink frame counter",
    "fCntDown": "next LoRaWAN downlink frame counter",
    "region_fix_age_sec": "retained RF-region lease age",
    "region_known": "fresh or valid-retained region authorization",
    "region_lease_trusted": "loaded-valid or fresh-PVT lease provenance",
    "tx_fail_streak": "consecutive primary TX failures",
    "join_retry_skip": "normal cycles until the next OTAA attempt",
    "burst_mode": "freefall rapid-beacon mode",
    "burst_cycles": "cycles spent in the current burst",
    "burst_cooldown": "post-burst cooldown cycles",
    "spurious_ff_streak": "consecutive acceleration-cleared INT1 wakes",
    "ff_suppress_clean": "clean scheduled wakes during chatter suppression",
    "s_ff_suppressed": "freefall wake chatter-suppression latch",
    "s_burst_wake": "unconsumed freefall wake flag",
    "last_gps_fix": "last accepted advancing GNSS fix in RAM",
    "s_have_fix_this_boot": "fresh-fix-age validity flag",
    "s_last_fix_monotonic_sec": "RTC time of last accepted fix",
    "s_gps_diag": "GNSS model/sleep/freshness recovery statistics",
    "s_stats": "command dispatcher statistics",
    "s_have_seq": "retained command acknowledgement validity",
    "s_last_seq": "last durably applied command sequence",
    "s_relay_enabled": "retained public Meshtastic relay policy",
    "s_dl_stats": "Class-A RX1/RX2 statistics",
    "s_relay": "Meshtastic relay statistics",
    "s_ctt": "wildlife CTT listener statistics",
    "s_radio_diag": "checked PHY configuration/recovery statistics",
    "s_mic_diag": "acoustic capture, event, variance, and floor statistics",
    "s_tmp117_reinit_attempts": "post-boot TMP117 recovery attempts",
    "s_tmp117_direct_reads": "successful direct TMP117 temperature samples",
    "s_tmp117_fallback_reads": "successful MS5611 temperature fallbacks",
    "s_tmp117_poweron_sentinels": "rejected TMP117 reset-value samples",
    "s_ms5611_reinit_attempts": "post-boot MS5611 PROM recovery attempts",
    "s_ltr390_reinit_attempts": "post-boot LTR390 recovery attempts",
    "s_ltr390_quiesce_failures": "unconfirmed LTR390 standby transactions",
    "s_ltr390_soft_reset_recoveries": "LTR390 reset-to-standby recoveries",
    "s_optical_quiet_retries": "bounded LTR390 fast-recovery attempts consumed",
    "s_optical_quiescence_fault": "active LTR390 quiet-recovery state",
    "s_lis2dh12_reconfig_attempts": "post-boot LIS2DH12 configuration repairs",
    "s_sensor_i2c_bus_recoveries": "bounded shared-I2C bus recoveries",
    "s_b2b_origin_id_ready": "B2B retained origin ID loaded/seeded",
    "s_b2b_origin_n": "B2B local-origin queue depth",
    "s_b2b_uplink_n": "B2B-to-TTN queue depth",
    "s_b2b_crumb_pending": "fresh local crumb awaiting relay window",
    "s_b2b_crumb_frame_ready": "local crumb has a reserved origin ID",
    "s_reported_relay_fwd": "relay-forward baseline after last primary uplink",
    "s_reported_ctt_tags": "CTT-tag baseline after last primary uplink",
}

TAMP_BKP0 = 0x4000B100
TAMP_LAYOUT = {
    "session_words": [0, 14],
    "session_crc": 15,
    "command_state": 16,
    "b2b_next_origin_id": 17,
    "region_lease_record": 18,
    "boot_record": 19,
}
TAMP_WORD_COUNT = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_nm() -> str:
    candidates = [
        shutil.which("arm-none-eabi-nm"),
        "/Users/twarn/.platformio/packages/toolchain-gccarmnoneeabi/bin/"
        "arm-none-eabi-nm",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("arm-none-eabi-nm not found")


def load_symbols(elf: Path) -> dict[str, dict[str, int | str]]:
    output = subprocess.check_output(
        [find_nm(), "-C", "-S", str(elf)], text=True
    )
    found: dict[str, dict[str, int | str]] = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) != 4:
            continue
        address, size, kind, name = fields
        if name not in SYMBOLS:
            continue
        if name in found:
            raise SystemExit(f"ambiguous ELF symbol: {name}")
        found[name] = {
            "address": int(address, 16),
            "size": int(size, 16),
            "kind": kind,
            "purpose": SYMBOLS[name],
        }
    missing = sorted(set(SYMBOLS) - set(found))
    if missing:
        raise SystemExit("missing ELF symbols: " + ", ".join(missing))
    return found


def jlink_read_command(address: int, size: int) -> str:
    if size == 1:
        return f"mem8 0x{address:08X} 1"
    if size == 2:
        return f"mem16 0x{address:08X} 1"
    if address % 4 == 0 and size % 4 == 0:
        return f"mem32 0x{address:08X} {size // 4}"
    return f"mem8 0x{address:08X} {size}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--elf",
        type=Path,
        default=Path("firmware/.pio/build/stratolink/firmware.elf"),
    )
    parser.add_argument(
        "--bin",
        dest="binary",
        type=Path,
        default=Path("firmware/.pio/build/stratolink/firmware.bin"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis/diagnostics/generated"),
    )
    args = parser.parse_args()
    elf = args.elf.resolve()
    binary = args.binary.resolve()
    if not elf.is_file() or not binary.is_file():
        raise SystemExit("build the exact stratolink flight environment first")

    symbols = load_symbols(elf)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "elf": str(elf),
        "elf_sha256": sha256(elf),
        "bin": str(binary),
        "bin_sha256": sha256(binary),
        "symbols": symbols,
        "tamp_bkp0_address": TAMP_BKP0,
        "tamp_layout": TAMP_LAYOUT,
    }
    (args.out_dir / "stratolink_flight_hil_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    health = ["connect", "h"]
    for name in SYMBOLS:
        entry = symbols[name]
        health.append(
            jlink_read_command(int(entry["address"]), int(entry["size"]))
        )
    health.extend(["g", "exit"])
    (args.out_dir / "jlink_read_flight_health.jlink").write_text(
        "\n".join(health) + "\n", encoding="utf-8"
    )

    tamp = [
        "connect",
        "h",
        f"mem32 0x{TAMP_BKP0:08X} 0x{TAMP_WORD_COUNT:X}",
        "g",
        "exit",
    ]
    (args.out_dir / "jlink_read_tamp32.jlink").write_text(
        "\n".join(tamp) + "\n", encoding="utf-8"
    )

    # Atomic state snapshot: RAM counters and retained TAMP fields must be read
    # under one halt. Running between separate scripts can advance the mission
    # loop and manufacture a false FCnt/lease mismatch.
    state = health[:-2]
    state.extend(
        [
            f"mem32 0x{TAMP_BKP0:08X} 0x{TAMP_WORD_COUNT:X}",
            "g",
            "exit",
        ]
    )
    (args.out_dir / "jlink_read_flight_state.jlink").write_text(
        "\n".join(state) + "\n", encoding="utf-8"
    )

    # STOP1 disables debug attachment on this target. Commander may then
    # connect under reset, in which case a read before setup would see zeroed
    # RAM and clock-gated RTC/TAMP registers. This explicit recovery script
    # runs the exact image for five seconds so setup enables RTCAPB and commits
    # the retained boot record, then re-halts before taking the atomic snapshot.
    wake_state = ["connect", "h", "g", "sleep 5000", "h"]
    wake_state.extend(state[2:])
    (args.out_dir / "jlink_wake_read_flight_state.jlink").write_text(
        "\n".join(wake_state) + "\n", encoding="utf-8"
    )

    # Test-only exact-image bench unlock. STOP1 disables debug attachment on
    # this target, so Commander can connect under reset at Reset_Handler. Run
    # setup before writing the BSS-backed variables or C runtime initialization
    # will erase the injected authorization. After the write, allow one full
    # worst-case indoor cycle (30 s GNSS + join/RX/sensors) to reach the normal
    # trusted-lease commit. The caller must first prove REGION_ID == US915 at
    # the US bench. The paired cleanup invalidates the lease and resets.
    bench_authorize = [
        "connect",
        "h",
        "g",
        "sleep 5000",
        "h",
        f"w4 0x{int(symbols['region_fix_age_sec']['address']):08X} 0",
        f"w1 0x{int(symbols['region_known']['address']):08X} 1",
        f"w1 0x{int(symbols['region_lease_trusted']['address']):08X} 1",
        "g",
        "sleep 75000",
        "h",
        "g",
        "exit",
    ]
    (args.out_dir / "jlink_bench_authorize_us.jlink").write_text(
        "\n".join(bench_authorize) + "\n", encoding="utf-8"
    )

    lease_record_address = TAMP_BKP0 + 4 * int(TAMP_LAYOUT["region_lease_record"])
    bench_cleanup = [
        "connect",
        "h",
        f"w4 0x{lease_record_address:08X} 0",
        "r",
        "g",
        "sleep 2000",
        "exit",
    ]
    (args.out_dir / "jlink_bench_clear_region_lease.jlink").write_text(
        "\n".join(bench_cleanup) + "\n", encoding="utf-8"
    )

    flash = [
        "connect",
        "h",
        f"loadfile {binary} 0x08000000",
        f"verifybin {binary} 0x08000000",
        "r",
        "g",
        "sleep 2000",
        "exit",
    ]
    (args.out_dir / "jlink_flash_flight.jlink").write_text(
        "\n".join(flash) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "elf_sha256": manifest["elf_sha256"],
        "bin_sha256": manifest["bin_sha256"],
        "symbols": len(symbols),
        "out_dir": str(args.out_dir.resolve()),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
