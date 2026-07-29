#!/usr/bin/env python3
"""Model the worst-case GNSS standby-recovery draw from current flight source.

This is a conservative source-bound model, not a substitute for the final
supercapacitor / PPK2 capture. It uses the exact part's 0.8 F datasheet minimum,
deliberately treats every library timeout as fully consumed, and includes two
RESET_N recovery paths.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "firmware/include/gps_backup_policy.h"
CONFIG = ROOT / "firmware/include/config.h"
GPS = ROOT / "firmware/src/gps_ublox.cpp"
MAIN = ROOT / "firmware/src/main.cpp"

CAPACITANCE_F = 0.8
CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V = 3.32
OUTPUT_V = 3.3
GNSS_CURRENT_A = 0.030
# Existing flight model uses 5 mA for the active MCU. Double that allowance to
# cover control/I/O overhead during the exceptional recovery path.
ACTIVE_CONTROL_CURRENT_A = 0.010
CONVERSION_EFFICIENCY = 0.85
TERMINAL_RETRY_SLEEP_MS = 5000


def define_u(text: str, name: str) -> int:
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(\d+)u?\b", text, re.M)
    if not match:
        raise AssertionError(f"missing integer define {name}")
    return int(match.group(1))


def cap_reserve_j(start_v: float) -> float:
    return 0.5 * CAPACITANCE_F * (
        start_v**2 - CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V**2
    )


def load_energy_j(duration_ms: int) -> float:
    current = GNSS_CURRENT_A + ACTIVE_CONTROL_CURRENT_A
    return OUTPUT_V * current * (duration_ms / 1000.0) / CONVERSION_EFFICIENCY


def gnss_awake_energy_j(duration_ms: int) -> float:
    """Conservative cap draw while MCU sleeps but an uncontained GNSS is awake."""
    return (
        OUTPUT_V
        * GNSS_CURRENT_A
        * (duration_ms / 1000.0)
        / CONVERSION_EFFICIENCY
    )


def build_audit() -> dict[str, object]:
    policy = POLICY.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    gps = GPS.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")

    attempts = define_u(policy, "GPS_BACKUP_MAX_ATTEMPTS")
    marker_ms = define_u(policy, "GPS_BACKUP_MARKER_WAIT_MS")
    confirm_ms = define_u(policy, "GPS_BACKUP_CONFIRM_MS")
    reset_floor_mv = define_u(policy, "GPS_BACKUP_RESET_FLOOR_MV")
    acquisition_floor_mv = define_u(config, "GPS_ACQ_FLOOR_MV")
    dyn_wait_ms = define_u(config, "GPS_DYNMODEL_MAX_WAIT_MS")
    begin_wait_ms = define_u(config, "GPS_BEGIN_MAX_WAIT_MS")

    # Pin every structural input to the current implementation. If the source
    # changes, the audit fails instead of silently preserving an obsolete bound.
    assert gps.count("VAL_LAYER_RAM, 300)") == 5
    assert gps.count("gnss.begin(GPS_SERIAL, GPS_BEGIN_MAX_WAIT_MS)") == 2
    assert "for (uint8_t attempt = 0; attempt < 3; ++attempt)" in gps
    assert "delay(20);" in gps
    assert "delay(1000);" in gps
    assert "delay(10);" in gps
    assert "!gps_backup_reset_allowed(power_adc_read_vSTOR_mv())" in gps
    assert re.search(
        r"if\s*\(!gps_attempted_this_cycle\)\s*\{\s*"
        r"gps_quiesced\s*=\s*gps_ublox_sleep\(\);\s*\}",
        main,
    )
    assert "!gps_attempted_this_cycle || !gps_quiesced" not in main

    configuration_commands = 5
    wake_settle_ms = 10
    reset_pulse_ms = 20
    reset_boot_ms = 1000
    dyn_attempts = 3
    dyn_operations_per_attempt = 3  # get, set, readback
    dyn_retry_delay_ms = 20

    confirmation_attempt_ms = (
        wake_settle_ms
        + configuration_commands * 300
        + marker_ms
        + confirm_ms
    )
    dynamic_model_ms = dyn_attempts * (
        dyn_operations_per_attempt * dyn_wait_ms + dyn_retry_delay_ms
    )
    hardware_reset_ms = (
        reset_pulse_ms + reset_boot_ms + begin_wait_ms + dynamic_model_ms
    )
    hardware_resets = attempts - 1
    full_recovery_ms = (
        attempts * confirmation_attempt_ms + hardware_resets * hardware_reset_ms
    )

    full_energy = load_energy_j(full_recovery_ms)
    low_rail_attempt_energy = load_energy_j(confirmation_attempt_ms)
    acquisition_reserve = cap_reserve_j(acquisition_floor_mv / 1000.0)
    reset_reserve = cap_reserve_j(reset_floor_mv / 1000.0)
    terminal_retry_sleep_energy = gnss_awake_energy_j(TERMINAL_RETRY_SLEEP_MS)
    terminal_retry_epoch_energy = (
        low_rail_attempt_energy + terminal_retry_sleep_energy
    )
    gates = {
        "reset_floor_above_acquisition_floor": reset_floor_mv > acquisition_floor_mv,
        "one_low_rail_attempt_fits_acquisition_reserve": (
            low_rail_attempt_energy < acquisition_reserve
        ),
        "full_recovery_fits_reset_floor_reserve": full_energy < reset_reserve,
        "reset_gate_wired_before_hardware_reset": True,
        "normal_cycle_has_at_most_one_shutdown_recovery_call": True,
    }
    if not all(gates.values()):
        raise AssertionError(f"GNSS backup energy gate failed: {gates}")

    return {
        "status": "PASS_MODEL_ONLY_FINAL_SUPERCAP_HIL_REQUIRED",
        "source": {
            "gps_backup_policy": str(POLICY.relative_to(ROOT)),
            "config": str(CONFIG.relative_to(ROOT)),
            "gps_implementation": str(GPS.relative_to(ROOT)),
        },
        "timing_bound_ms": {
            "confirmation_attempt": confirmation_attempt_ms,
            "hardware_reset_and_reconfigure": hardware_reset_ms,
            "full_three_attempt_two_reset_path": full_recovery_ms,
            "low_rail_path_before_reset_suppression": confirmation_attempt_ms,
        },
        "energy_model": {
            "capacitance_f": CAPACITANCE_F,
            "conservative_flight3_reported_plateau_floor_v": (
                CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V
            ),
            "output_v": OUTPUT_V,
            "gnss_current_ma": GNSS_CURRENT_A * 1000,
            "active_control_allowance_ma": ACTIVE_CONTROL_CURRENT_A * 1000,
            "conversion_efficiency": CONVERSION_EFFICIENCY,
            "acquisition_floor_v": acquisition_floor_mv / 1000.0,
            "reset_floor_v": reset_floor_mv / 1000.0,
            "acquisition_floor_reserve_j": round(acquisition_reserve, 6),
            "reset_floor_reserve_j": round(reset_reserve, 6),
            "one_low_rail_attempt_j": round(low_rail_attempt_energy, 6),
            "full_recovery_j": round(full_energy, 6),
            "reset_floor_margin_j": round(reset_reserve - full_energy, 6),
            "reset_floor_margin_percent_of_recovery": round(
                100.0 * (reset_reserve - full_energy) / full_energy, 3
            ),
            "terminal_retry_sleep_s": TERMINAL_RETRY_SLEEP_MS / 1000.0,
            "terminal_retry_sleep_with_awake_gnss_j": round(
                terminal_retry_sleep_energy, 6
            ),
            "terminal_retry_epoch_j": round(terminal_retry_epoch_energy, 6),
            "terminal_retry_epoch_exceeds_acquisition_reserve": (
                terminal_retry_epoch_energy > acquisition_reserve
            ),
        },
        "gates": gates,
        "limits": [
            "Timeouts and currents are deliberately conservative source/model bounds, not measured path waveforms.",
            "Final proof requires PPK2 phase-current and VSTOR sag capture with the exact flight supercapacitor installed, including measured capacitance and ESR.",
            "RESET_N-held current is not assumed safe and is not used as a fallback.",
            "A persistent terminal standby failure can still drain the rail through an awake GNSS and five-second retry cycles; no source-only model can qualify survival without measured containment current.",
            "At the 3.6 V acquisition floor, one modeled low-rail attempt plus five seconds with a 30 mA awake GNSS is 0.949 J versus 0.775 J stored to the conservative 3.32 V reported-plateau floor, so persistent terminal-failure survival deliberately fails closed.",
        ],
    }


def write_create_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise SystemExit(f"refusing to overwrite evidence: {path}") from exc
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = build_audit()
    payload = (json.dumps(audit, indent=2, sort_keys=True) + "\n").encode()
    if args.output:
        write_create_once(args.output, payload)
    else:
        print(payload.decode(), end="")


if __name__ == "__main__":
    main()
