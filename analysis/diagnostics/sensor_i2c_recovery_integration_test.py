#!/usr/bin/env python3
"""Pin the bounded shared-I2C recovery wiring into the flight path."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware/src/main.cpp"
SENSORS = ROOT / "firmware/src/sensors.cpp"
HIL = ROOT / "analysis/diagnostics/generate_flight_hil.py"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    main_raw = MAIN.read_text(encoding="utf-8")
    sensors_raw = SENSORS.read_text(encoding="utf-8")
    main_source = compact(main_raw)
    sensors_source = compact(sensors_raw)

    all_failed_gate = (
        "if (!(temperature_ok || pressure_ok || accel_ok || uv_ok || lux_ok))"
    )
    assert all_failed_gate in main_source
    # One recovery belongs to the all-sensors-failed retry. Two independent
    # calls contain LTR390 active-state uncertainty (prior-cycle quiet retry
    # and same-cycle post-read standby retry).
    assert main_raw.count("sensors_recover_i2c_bus();") == 3

    gate_start = main_source.index(all_failed_gate)
    gate_end = main_source.index("if (!sensor_ltr390_quiesce())", gate_start)
    gate_slice = main_source[gate_start:gate_end]
    assert gate_slice.count("sensors_recover_i2c_bus();") == 1
    assert gate_slice.count("sensor_tmp117_read_decidegrees") == 1
    assert gate_slice.count("sensor_ms5611_read_pressure_centihpa") == 1
    assert gate_slice.count("sensor_lis2dh12_read_accel_cm_s2") == 1
    assert gate_slice.count("sensor_ltr390_read_uv_index") == 1
    assert gate_slice.count("sensor_ltr390_read_ambient_lux") == 1

    assert "if (s_optical_quiescence_fault && !freefall_wake && !burst_mode)" in main_source
    assert main_source.count("if (!sensor_ltr390_quiesce())") == 1

    # Peripheral teardown must precede the same pin-bound begin helper. The
    # counter is debugger evidence and must advance once per recovery call.
    recovery = sensors_source[
        sensors_source.index("void sensors_recover_i2c_bus(void)") :
    ]
    assert recovery.index("s_sensor_i2c_bus_recoveries++;") < recovery.index(
        "Wire.end();"
    ) < recovery.index("begin_i2c_bus();")
    assert sensors_raw.count("s_sensor_i2c_bus_recoveries++;") == 1
    assert "Wire.setSDA(PIN_I2C_SDA);" in sensors_source
    assert "Wire.setSCL(PIN_I2C_SCL);" in sensors_source
    assert "Wire.begin();" in sensors_source

    hil = HIL.read_text(encoding="utf-8")
    assert '"s_sensor_i2c_bus_recoveries"' in hil
    print(
        "PASS: all-I2C-failed and optical-quiescence paths perform bounded bus "
        "recovery and expose the exact-ELF counter"
    )


if __name__ == "__main__":
    main()
