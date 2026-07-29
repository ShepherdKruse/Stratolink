#!/usr/bin/env python3
"""Bind optical-sensor standby to a quiet, mission-safe recovery path."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "firmware/src/sensor_ltr390.cpp"
MAIN = ROOT / "firmware/src/main.cpp"
CONFIG = ROOT / "firmware/include/config.h"
GENERATOR = ROOT / "analysis/diagnostics/generate_flight_hil.py"
DECODER = ROOT / "analysis/diagnostics/decode_flight_state.py"
AUDIT = ROOT / "analysis/diagnostics/ltr390_quiescence_energy_audit.py"


def main() -> None:
    driver = DRIVER.read_text(encoding="utf-8")
    main_source = MAIN.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    decoder = DECODER.read_text(encoding="utf-8")

    assert "static bool ltr390_active_possible = false;" in driver
    assert "static bool standby_readback(void)" in driver
    assert "static bool reset_to_standby_readback(void)" in driver
    standby = driver[driver.index("static bool standby_readback(void)") :]
    assert standby.index("write_reg(LTR390_REG_MAIN_CTRL, 0x00)") < standby.index(
        "read_reg(LTR390_REG_MAIN_CTRL, &control)"
    )
    quiesce = driver[driver.index("bool sensor_ltr390_quiesce(void)") :]
    assert "for (uint8_t attempt = 0; attempt < 3; ++attempt)" in quiesce
    assert "reset_to_standby_readback()" in quiesce
    assert "ltr390_active_possible = false;" in quiesce
    reset = driver[driver.index("static bool reset_to_standby_readback(void)") :]
    assert "write_reg(LTR390_REG_MAIN_CTRL, LTR390_SW_RESET)" in reset
    assert reset.index("delay(2);") < reset.index(
        "read_reg(LTR390_REG_MAIN_CTRL, &control)"
    )
    assert "s_ltr390_soft_reset_recoveries++" in driver
    assert driver.count("ltr390_active_possible = true;") >= 3
    assert driver.count("sensor_ltr390_quiesce()") >= 6

    assert "#define SENSOR_QUIESCE_RETRY_SLEEP_MS 60000u" in config
    assert "#define SENSOR_QUIESCE_FAST_RETRIES   5u" in config
    assert "s_optical_quiescence_fault = !sensor_ltr390_quiesce();" in main_source
    assert "static uint8_t s_optical_quiet_retries = 0;" in main_source
    assert '#include "optical_fault_policy.h"' in main_source
    recovery_start = main_source.index(
        "if (s_optical_quiescence_fault && !freefall_wake && !burst_mode)"
    )
    recovery_end = main_source.index("if (burst_cooldown > 0)", recovery_start)
    recovery = main_source[recovery_start:recovery_end]
    assert "sensors_recover_i2c_bus();" in recovery
    assert "sensor_ltr390_quiesce()" in recovery
    assert "optical_fault_consume_fast_retry(" in recovery
    assert "&s_optical_quiet_retries" in recovery
    assert "(uint8_t)SENSOR_QUIESCE_FAST_RETRIES" in recovery
    assert "gps_ublox_sleep()" in recovery
    assert "lorawan_sleep();" in recovery
    assert "power_manager_sleep_ms(retry_ms);" in recovery
    assert "gps_ublox_get_fix" not in recovery
    assert "lorawan_send" not in recovery
    degraded = main_source[recovery_end:]
    assert "gps_ublox_get_fix" in degraded
    assert "lorawan_send_uplink(tx_payload, TELEMETRY_PAYLOAD_SIZE)" in degraded
    assert main_source.count("if (!s_optical_quiescence_fault)") >= 3
    assert (
        "s_optical_quiet_retries < SENSOR_QUIESCE_FAST_RETRIES &&"
        in main_source
    )
    assert main_source.count("!s_optical_quiescence_fault") >= 2
    aux_start = main_source.index(
        "/* CTT and B2B share a single, hard auxiliary airtime allowance."
    )
    aux_end = main_source.index("if (burst_mode) {", aux_start)
    auxiliary = main_source[aux_start:aux_end]
    assert "if (!gps_quiesced || s_optical_quiescence_fault)" in auxiliary
    assert auxiliary.index("if (!gps_quiesced || s_optical_quiescence_fault)") < (
        auxiliary.index("lorawan_send_uplink_port")
    )

    assert '"s_ltr390_quiesce_failures"' in generator
    assert '"s_ltr390_soft_reset_recoveries"' in generator
    assert '"s_optical_quiet_retries"' in generator
    assert '"s_optical_quiescence_fault"' in generator
    assert '"ltr390_quiesce_failures"' in decoder
    assert '"optical_quiet_retries"' in decoder
    assert '"optical_quiescence_fault"' in decoder

    spec = importlib.util.spec_from_file_location("ltr390_energy", AUDIT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.build_report()
    assert report["source_gate"]["contained"] is True
    exposure = {row["seconds"]: row for row in report["mission_interval_exposure"]}
    assert exposure[1200]["gross_fraction_minimum_cap_reserve"] > 0.21
    assert exposure[1800]["gross_fraction_minimum_cap_reserve"] > 0.32
    print(
        "PASS: LTR390 uncertainty gets bounded quiet retries, then degraded "
        "primary tracking without optical/auxiliary amplification"
    )


if __name__ == "__main__":
    main()
