#!/usr/bin/env python3
"""Host regressions for soak_sensor_model.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MODEL = HERE / "soak_sensor_model.py"


def rows() -> list[dict]:
    start = datetime(2026, 7, 25, tzinfo=timezone.utc)
    result = []
    for index in range(20):
        result.append(
            {
                "event": "ttn_uplink",
                "f_cnt": 100 + index,
                "utc": (start + timedelta(minutes=20 * index)).isoformat(),
                "telemetry": {
                    "vstor_mv": 4620 + index % 3,
                    "solar_mv": 100 + index * 10,
                    "temperature_deci_c": 250 + index // 5,
                    "pressure_deci_hpa": 10130 + index // 5,
                    "accel_x_cms2": 0,
                    "accel_y_cms2": 0,
                    "accel_z_cms2": 981 + index % 2,
                    "uv_index": 0,
                    "ambient_lux": 200 + index * 20,
                    "acoustic_event": 0,
                    "lat_e7": 0,
                    "lon_e7": 0,
                    "altitude_m": 0,
                    "speed_cm_s": 0,
                    "heading_cdeg": 0,
                    "satellites": 0,
                },
            }
        )
    return result


def run(case: list[dict], expect_success: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="stratolink-sensor-model-") as temp:
        input_path = Path(temp) / "input.jsonl"
        output_path = Path(temp) / "output.json"
        input_path.write_text(
            "".join(json.dumps(row) + "\n" for row in case),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(MODEL),
                "--ttn",
                str(input_path),
                "--output",
                str(output_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert (completed.returncode == 0) == expect_success, completed.stdout
        return json.loads(output_path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="stratolink-sensor-collision-") as temp:
        output = Path(temp) / "output.json"
        output.write_text("preserved\n", encoding="utf-8")
        collision = subprocess.run(
            [
                sys.executable,
                str(MODEL),
                "--ttn", str(Path(temp) / "missing.jsonl"),
                "--output", str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite sensor-model evidence" in collision.stderr
        assert output.read_text(encoding="utf-8") == "preserved\n"

    baseline = rows()
    result = run(baseline, True)
    assert result["passed"]
    assert result["rows"] == 20
    assert result["cadence_temperature"]["scheduled_interval_count"] == 19
    assert (
        result["cadence_temperature"]["excluded_short_or_long_intervals"] == 0
    )
    assert result["cadence_temperature"]["scheduled_interval_seconds"]["mean"] == 1200

    short_wake = rows()
    for index in range(7, len(short_wake)):
        short_wake[index]["utc"] = (
            datetime.fromisoformat(short_wake[index]["utc"])
            - timedelta(minutes=10)
        ).isoformat()
    result = run(short_wake, True)
    assert result["cadence_temperature"]["scheduled_interval_count"] == 18
    assert (
        result["cadence_temperature"]["excluded_short_or_long_intervals"] == 1
    )

    missing = rows()
    del missing[7]["telemetry"]["pressure_deci_hpa"]
    result = run(missing, False)
    assert not result["gates"]["complete_fields"]

    boolean_numeric = rows()
    boolean_numeric[4]["telemetry"]["temperature_deci_c"] = True
    result = run(boolean_numeric, False)
    assert not result["gates"]["finite_numeric_fields"]

    unavailable_numeric = rows()
    unavailable_numeric[4]["telemetry"]["temperature_deci_c"] = None
    result = run(unavailable_numeric, False)
    assert not result["gates"]["finite_numeric_fields"]

    stale = rows()
    stale[5]["telemetry"]["lat_e7"] = 374500000
    result = run(stale, False)
    assert not result["gates"]["gps_fields_consistent"]

    subthreshold = rows()
    subthreshold[6]["telemetry"]["satellites"] = 3
    result = run(subthreshold, False)
    assert not result["gates"]["gps_fields_consistent"]

    invalid_fix = rows()
    invalid_fix[8]["telemetry"].update(
        {
            "satellites": 7,
            "lat_e7": 475000000,
            "lon_e7": -1223000000,
            "altitude_m": 61000,
        }
    )
    result = run(invalid_fix, False)
    assert not result["gates"]["gps_fields_consistent"]

    out_of_order = rows()
    out_of_order[8], out_of_order[9] = out_of_order[9], out_of_order[8]
    result = run(out_of_order, False)
    assert not result["gates"]["timestamps_strictly_increasing"]

    panel_only_shading = rows()
    for index, row in enumerate(panel_only_shading):
        row["telemetry"]["ambient_lux"] = 200 + ((index * 7) % 20) * 20
    result = run(panel_only_shading, True)
    assert result["optical"]["pearson_solar_vs_ambient"] < 0.95

    bad_optical = rows()
    bad_optical[8]["telemetry"]["solar_mv"] = 6501
    result = run(bad_optical, False)
    assert not result["gates"]["optical_ranges_plausible"]

    bad_acoustic = rows()
    bad_acoustic[8]["telemetry"]["acoustic_event"] = 2
    result = run(bad_acoustic, False)
    assert not result["gates"]["acoustic_wire_values_valid"]

    event = rows()
    event[8]["telemetry"]["acoustic_event"] = 1
    result = run(event, True)
    assert result["acoustic"]["event_rows"] == 1
    assert result["acoustic"]["event_fcnt"] == [108]

    solar_charge = rows()
    solar_charge[10]["telemetry"].update(
        {"vstor_mv": 5396, "solar_mv": 5200, "ambient_lux": 65535}
    )
    # Keep the synthetic optical trace monotonic enough that this case isolates
    # the VSTOR gate rather than intentionally failing the correlation gate.
    for index in range(11, len(solar_charge)):
        solar_charge[index]["telemetry"].update(
            {
                "vstor_mv": 5360,
                "solar_mv": 5200 + index,
                "ambient_lux": 65535,
            }
        )
    result = run(solar_charge, True)
    assert result["gates"]["vstor_source_support_floor"]
    assert result["gates"]["vstor_harvester_ceiling_plausible"]
    assert result["vstor_mv"]["above_source_rows"] == 10
    assert result["optical"]["ambient_lux"]["wire_saturated_rows"] == 10
    assert result["optical"]["ambient_lux"]["wire_saturated_fcnt"] == list(
        range(110, 120)
    )

    source_loss = rows()
    source_loss[10]["telemetry"]["vstor_mv"] = 4400
    result = run(source_loss, False)
    assert not result["gates"]["vstor_source_support_floor"]

    overvoltage = rows()
    overvoltage[10]["telemetry"]["vstor_mv"] = 5450
    result = run(overvoltage, False)
    assert not result["gates"]["vstor_harvester_ceiling_plausible"]

    print(
        "soak sensor model: baseline/missing/boolean/order/subthreshold/stale/"
        "range/optical/shading/source/solar-charge/overvoltage adversarial cases passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
