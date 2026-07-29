#!/usr/bin/env python3
"""Quantify StratoLink-2 sensor behavior during the supervised room soak.

This is a bench-plausibility and continuity gate. It does not claim calibration
outside the observed room conditions and cannot replace clear-sky GNSS,
altitude/chamber, calibrated UV/acoustic, or supercap qualification.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from evidence_provenance import record as provenance_record

HERE = Path(__file__).resolve().parent
DEFAULT_TTN = HERE / "logs/stratolink2_soak_20260724_ttn.jsonl"

FIELDS = (
    "vstor_mv",
    "solar_mv",
    "temperature_deci_c",
    "pressure_deci_hpa",
    "accel_x_cms2",
    "accel_y_cms2",
    "accel_z_cms2",
    "uv_index",
    "ambient_lux",
    "acoustic_event",
    "lat_e7",
    "lon_e7",
    "altitude_m",
    "speed_cm_s",
    "heading_cdeg",
    "satellites",
)
UINT16_MAX = 65535


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_uplinks(path: Path, raw: bytes) -> list[dict]:
    rows = [
        json.loads(line)
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    # The JSONL is append-only evidence. Preserve recorded order so continuity
    # checks can detect replays or timestamp regressions rather than sorting
    # the anomaly away.
    return [row for row in rows if row.get("event") == "ttn_uplink"]


def stats(values: np.ndarray) -> dict:
    return {
        "min": round(float(np.min(values)), 6),
        "max": round(float(np.max(values)), 6),
        "mean": round(float(np.mean(values)), 6),
        "stddev": round(float(np.std(values)), 6),
        "max_step": round(
            float(np.max(np.abs(np.diff(values)))) if len(values) > 1 else 0.0,
            6,
        ),
    }


def slope_per_hour(times_s: np.ndarray, values: np.ndarray) -> float:
    if len(values) < 2 or times_s[-1] == times_s[0]:
        return 0.0
    centered = times_s - np.mean(times_s)
    denominator = float(np.dot(centered, centered))
    if denominator == 0:
        return 0.0
    return round(
        float(np.dot(centered, values - np.mean(values)) / denominator * 3600),
        6,
    )


def max_rate_per_minute(times_s: np.ndarray, values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    elapsed = np.diff(times_s)
    if np.any(elapsed <= 0):
        return math.inf
    return round(float(np.max(np.abs(np.diff(values)) / elapsed * 60.0)), 6)


def correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0:
        return None
    return round(float(np.corrcoef(left, right)[0, 1]), 6)


def linear_slope_x_to_y(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2:
        return None
    centered = x - np.mean(x)
    denominator = float(np.dot(centered, centered))
    if denominator == 0:
        return None
    return round(float(np.dot(centered, y - np.mean(y)) / denominator), 6)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite sensor-model evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def require_create_once(path: Path | None) -> None:
    if path is None:
        return
    partials = sorted(
        path.parent.glob(f".{path.name}.*.tmp")
    ) if path.parent.is_dir() else []
    collisions = ([path] if path.exists() else []) + partials
    if collisions:
        raise SystemExit(
            "refusing to overwrite sensor-model evidence: "
            + ", ".join(str(item) for item in collisions)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ttn", type=Path, default=DEFAULT_TTN)
    parser.add_argument("--source-mv", type=int, default=4660)
    parser.add_argument("--vbat-ov-mv", type=int, default=5363)
    parser.add_argument("--vbat-ov-tolerance-mv", type=int, default=75)
    parser.add_argument("--minimum-rows", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require_create_once(args.output)

    ttn_raw = args.ttn.read_bytes()
    uplinks = load_uplinks(args.ttn, ttn_raw)
    missing: list[dict] = []
    invalid_numeric: list[dict] = []
    telemetry: list[dict] = []
    valid_uplinks: list[dict] = []
    for row in uplinks:
        data = row.get("telemetry")
        if not isinstance(data, dict):
            missing.append({"f_cnt": row.get("f_cnt"), "fields": ["telemetry"]})
            continue
        absent = [field for field in FIELDS if field not in data]
        if absent:
            missing.append({"f_cnt": row.get("f_cnt"), "fields": absent})
        bad = [
            field
            for field in FIELDS
            if field in data
            and (
                isinstance(data[field], bool)
                or not isinstance(data[field], (int, float))
                or not math.isfinite(float(data[field]))
            )
        ]
        if bad:
            invalid_numeric.append({"f_cnt": row.get("f_cnt"), "fields": bad})
        if absent or bad:
            continue
        telemetry.append(data)
        valid_uplinks.append(row)

    if not telemetry:
        raise SystemExit("no decoded telemetry rows")

    timestamps = np.array(
        [
            (utc(row["utc"]) - utc(valid_uplinks[0]["utc"])).total_seconds()
            for row in valid_uplinks
        ],
        dtype=float,
    )
    temperature_c = np.array(
        [row["temperature_deci_c"] / 10.0 for row in telemetry], dtype=float
    )
    pressure_hpa = np.array(
        [row["pressure_deci_hpa"] / 10.0 for row in telemetry], dtype=float
    )
    accel = np.array(
        [
            math.sqrt(
                row["accel_x_cms2"] ** 2
                + row["accel_y_cms2"] ** 2
                + row["accel_z_cms2"] ** 2
            )
            for row in telemetry
        ],
        dtype=float,
    )
    vstor = np.array([row["vstor_mv"] for row in telemetry], dtype=float)
    solar = np.array([row["solar_mv"] for row in telemetry], dtype=float)
    ambient = np.array([row["ambient_lux"] for row in telemetry], dtype=float)

    nogps_errors: list[int] = []
    gps_range_errors: list[int] = []
    for uplink, row in zip(valid_uplinks, telemetry):
        fcnt = (
            int(uplink["f_cnt"])
            if uplink.get("f_cnt") is not None
            else None
        )
        satellites = row["satellites"]
        if satellites < 4:
            if satellites != 0 or any(
                row[field] != 0
                for field in (
                    "lat_e7",
                    "lon_e7",
                    "altitude_m",
                    "speed_cm_s",
                    "heading_cdeg",
                )
            ):
                nogps_errors.append(fcnt)
        elif not (
            satellites <= 64
            and -900000000 <= row["lat_e7"] <= 900000000
            and -1800000000 <= row["lon_e7"] <= 1800000000
            and -500 <= row["altitude_m"] <= 60000
            and 0 <= row["speed_cm_s"] <= 50000
            and 0 <= row["heading_cdeg"] <= 35999
        ):
            gps_range_errors.append(fcnt)

    optical_correlation = correlation(solar, ambient)
    interval_seconds = np.diff(timestamps)
    # The flight scheduler's ordinary room-soak interval is nominally about
    # 20 minutes plus active acquisition/TX work. Exclude explicit short wakes
    # and outages before describing cadence/temperature behavior; this is not
    # an acceptance gate or a calibrated LSI-frequency measurement because
    # active-cycle duration is not independently phase-timestamped.
    scheduled_interval_mask = (
        (interval_seconds >= 1100.0) & (interval_seconds <= 1350.0)
    )
    scheduled_intervals = interval_seconds[scheduled_interval_mask]
    scheduled_end_temperature = temperature_c[1:][scheduled_interval_mask]
    cadence_temperature_correlation = correlation(
        scheduled_intervals, scheduled_end_temperature
    )
    cadence_seconds_per_c = linear_slope_x_to_y(
        scheduled_end_temperature, scheduled_intervals
    )
    acoustic_event_fcnt = [
        int(uplink["f_cnt"]) if uplink.get("f_cnt") is not None else None
        for uplink, row in zip(valid_uplinks, telemetry)
        if row["acoustic_event"] == 1
    ]
    gates = {
        "minimum_rows": len(telemetry) >= args.minimum_rows,
        "complete_fields": not missing,
        "finite_numeric_fields": not invalid_numeric,
        "timestamps_strictly_increasing": bool(
            len(timestamps) == 1 or np.all(np.diff(timestamps) > 0)
        ),
        # The PPK2 is connected to VSTOR while the solar harvester remains
        # connected. It can source but cannot sink, so sunlight may correctly
        # lift VSTOR above the 4.660 V source setting until the BQ25570's
        # resistor-programmed VBAT_OV threshold (~5.363 V). The old
        # source+25 mV/100 mV-step gate falsely called that healthy behavior a
        # source failure. Keep the two independent safety claims explicit:
        # the source prevents a low rail, and the harvester does not exceed its
        # hardware ceiling beyond ADC/divider tolerance.
        "vstor_source_support_floor": bool(
            np.min(vstor) >= args.source_mv - 100
        ),
        "vstor_harvester_ceiling_plausible": bool(
            np.max(vstor)
            <= args.vbat_ov_mv + args.vbat_ov_tolerance_mv
        ),
        "temperature_bench_plausible": bool(
            np.min(temperature_c) >= 10
            and np.max(temperature_c) <= 55
            and max_rate_per_minute(timestamps, temperature_c) <= 1.0
        ),
        "pressure_room_plausible": bool(
            np.min(pressure_hpa) >= 850
            and np.max(pressure_hpa) <= 1100
            and max_rate_per_minute(timestamps, pressure_hpa) <= 0.2
        ),
        "stationary_acceleration_plausible": bool(
            np.min(accel) >= 850
            and np.max(accel) <= 1120
            and np.max(np.abs(np.diff(accel))) <= 150
        ),
        "optical_ranges_plausible": bool(
            np.min(solar) >= 0
            and np.max(solar) <= 6500
            and np.min(ambient) >= 0
            and np.max(ambient) <= 65535
        ),
        "optical_response_observed": bool(
            np.ptp(solar) >= 100 and np.ptp(ambient) >= 100
        ),
        "uv_wire_values_plausible": all(
            0 <= row["uv_index"] <= 25 for row in telemetry
        ),
        "acoustic_wire_values_valid": all(
            row["acoustic_event"] in (0, 1) for row in telemetry
        ),
        "gps_fields_consistent": not nogps_errors and not gps_range_errors,
    }

    result = {
        "provenance": {
            "ttn": provenance_record(args.ttn, ttn_raw),
        },
        "scope": (
            "room-condition continuity/plausibility only; not flight-envelope "
            "calibration or physical GNSS/UV/acoustic/supercap qualification"
        ),
        "rows": len(telemetry),
        "f_cnt_first": valid_uplinks[0]["f_cnt"],
        "f_cnt_last": valid_uplinks[-1]["f_cnt"],
        "duration_hours": round(float(timestamps[-1] / 3600), 6),
        "missing_fields": missing,
        "invalid_numeric_fields": invalid_numeric,
        "vstor_mv": {
            **stats(vstor),
            "source_minus_vstor_min": round(float(args.source_mv - np.max(vstor)), 6),
            "source_minus_vstor_max": round(float(args.source_mv - np.min(vstor)), 6),
            "above_source_rows": int(np.sum(vstor > args.source_mv + 25)),
            "vbat_ov_mv": args.vbat_ov_mv,
            "vbat_ov_tolerance_mv": args.vbat_ov_tolerance_mv,
            "interpretation": (
                "PPK2 is a source, not a sink; solar may raise VSTOR above "
                "source_mv up to the BQ25570 VBAT_OV ceiling"
            ),
        },
        "temperature_c": {
            **stats(temperature_c),
            "linear_slope_per_hour": slope_per_hour(timestamps, temperature_c),
            "max_rate_per_minute": max_rate_per_minute(
                timestamps, temperature_c
            ),
        },
        "pressure_hpa": {
            **stats(pressure_hpa),
            "linear_slope_per_hour": slope_per_hour(timestamps, pressure_hpa),
            "max_rate_per_minute": max_rate_per_minute(
                timestamps, pressure_hpa
            ),
        },
        "accel_magnitude_cms2": stats(accel),
        "cadence_temperature": {
            "scheduled_interval_count": int(len(scheduled_intervals)),
            "excluded_short_or_long_intervals": int(
                len(interval_seconds) - len(scheduled_intervals)
            ),
            "scheduled_interval_seconds": (
                stats(scheduled_intervals)
                if len(scheduled_intervals) else None
            ),
            "pearson_interval_vs_end_temperature": (
                cadence_temperature_correlation
            ),
            "linear_seconds_per_c": cadence_seconds_per_c,
            "interpretation": (
                "descriptive only: a longer interval as temperature falls is "
                "consistent with a slowing LSI-backed RTC, but active-cycle "
                "duration is not separately timestamped and the room trend "
                "must not be extrapolated to flight temperature"
            ),
        },
        "optical": {
            "solar_mv": stats(solar),
            "ambient_lux": {
                **stats(ambient),
                "wire_saturated_rows": int(np.sum(ambient == UINT16_MAX)),
                "wire_saturated_fcnt": [
                    int(uplink["f_cnt"])
                    if uplink.get("f_cnt") is not None
                    else None
                    for uplink, row in zip(valid_uplinks, telemetry)
                    if row["ambient_lux"] == UINT16_MAX
                ],
                "interpretation": (
                    "65535 is the telemetry uint16 ceiling, not the LTR390 "
                    "ADC ceiling; saturated rows prove bright-light response "
                    "but do not preserve lux magnitude above the wire limit"
                ),
            },
            "pearson_solar_vs_ambient": optical_correlation,
            "interpretation": (
                "correlation is descriptive only because panel shading and "
                "LTR390 exposure can differ"
            ),
        },
        "gps": {
            "nogps_rows": sum(row["satellites"] == 0 for row in telemetry),
            "fix_rows": sum(row["satellites"] >= 4 for row in telemetry),
            "nogps_field_errors_fcnt": nogps_errors,
            "range_errors_fcnt": gps_range_errors,
        },
        "uv": {
            "nonzero_rows": sum(row["uv_index"] != 0 for row in telemetry),
            "note": "zero indoors/night is not a calibrated UV-source test",
        },
        "acoustic": {
            "event_rows": len(acoustic_event_fcnt),
            "event_fcnt": acoustic_event_fcnt,
            "note": (
                "one-bit events are retained but cannot be classified as real "
                "sound or false positive without controlled stimulus and the "
                "post-soak exact-ELF variance/floor diagnostics"
            ),
        },
        "gates": gates,
        "passed": all(gates.values()),
    }

    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
