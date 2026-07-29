#!/usr/bin/env python3
"""Summarize the supervised PPK2 + TTN soak logs without external packages."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
from statistics import fmean

from backend_ingest_summary import (
    summarize as summarize_backend,
)
from evidence_provenance import record as provenance_record

US915_FSB2_FREQUENCIES_HZ = [
    903900000,
    904100000,
    904300000,
    904500000,
    904700000,
    904900000,
    905100000,
    905300000,
]

QUALIFICATION_SCOPES = {
    "relay_soak": {
        "proves": [
            "PPK2 source continuity; supervised handoff only when an explicit matching handoff log is supplied and validated",
            "primary TTN cadence/counter/channel/link continuity",
            "room-condition telemetry continuity",
            "LoRaWAN health across cycles configured to offer auxiliary windows",
        ],
        "does_not_prove": [
            "CTT/shared-radio window entry, traffic, or restore counters until the post-soak target snapshot",
            "watchdog housekeeping inside an auxiliary window without those counters",
            "STOP1 sleep current or repeated STOP1 wake behavior",
            "flight-supercap energy reserve",
            "the exact final flight binary",
            "clear-sky GNSS or flight-envelope sensor calibration",
        ],
        "reason": (
            "env:stratolink_soak sets RELAY_SOLAR_MIN_MV=0 and is designed to "
            "offer nearly the complete idle budget to CTT plus the shared-radio "
            "window; entry remains a post-soak counter claim"
        ),
    },
    "power_profile": {
        "proves": [
            "only the power/current behaviors present in the supplied logs",
        ],
        "does_not_prove": [
            "shared-radio operation unless separately evidenced",
            "flight-supercap reserve unless the flight capacitor is installed",
            "the exact final flight binary",
        ],
        "reason": "env:stratolink_profile retains the real solar gate",
    },
    "flight": {
        "proves": [
            "only behaviors directly present in the supplied exact-image logs",
        ],
        "does_not_prove": [
            "any unobserved physical or environmental behavior",
        ],
        "reason": "scope must remain limited to the supplied direct evidence",
    },
}


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_jsonl(path: Path, raw: bytes | None = None) -> list[dict]:
    data = path.read_bytes() if raw is None else raw
    rows: list[dict] = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"{path}: invalid UTF-8: {error}") from error
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise SystemExit(f"{path}:{line_number}: invalid JSON: {error}") from error
    return rows


def load_json_array(path: Path, raw: bytes) -> list[dict]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: invalid JSON array: {error}") from error
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{path}: expected an array of JSON objects")
    return value


def numeric_range(values: list[float | int]) -> dict[str, float]:
    return {
        "min": min(values),
        "mean": round(fmean(values), 3),
        "max": max(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--power",
        type=Path,
        default=Path("analysis/diagnostics/logs/stratolink2_soak_20260724_power.jsonl"),
    )
    parser.add_argument(
        "--ttn",
        type=Path,
        default=Path("analysis/diagnostics/logs/stratolink2_soak_20260724_ttn.jsonl"),
    )
    parser.add_argument(
        "--handoff-power",
        type=Path,
        help=(
            "explicit standby-supervisor log used to prove post-soak power "
            "continuity; required with --final"
        ),
    )
    parser.add_argument(
        "--supabase",
        type=Path,
        help=(
            "explicit cached read-only production export for TTN-to-database "
            "parity; required with --final"
        ),
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="enforce the overnight acceptance gates and exit nonzero on failure",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="atomically preserve the complete JSON report at this path",
    )
    parser.add_argument("--expected-source-mv", type=int, default=4660)
    parser.add_argument("--vbat-ov-mv", type=int, default=5363)
    parser.add_argument("--vbat-ov-tolerance-mv", type=int, default=75)
    parser.add_argument(
        "--firmware-profile",
        choices=sorted(QUALIFICATION_SCOPES),
        default="relay_soak",
        help="bind the report to the behavior of the image that produced it",
    )
    parser.add_argument("--min-held-seconds", type=float, default=57600)
    parser.add_argument("--min-uplinks", type=int, default=40)
    parser.add_argument("--max-heartbeat-gap-seconds", type=float, default=31.5)
    parser.add_argument("--max-handoff-gap-seconds", type=float, default=2.0)
    parser.add_argument("--scheduled-gap-min-seconds", type=float, default=1200)
    parser.add_argument("--scheduled-gap-max-seconds", type=float, default=1350)
    args = parser.parse_args()

    if args.final and (args.handoff_power is None or args.supabase is None):
        raise SystemExit(
            "--final requires explicit --handoff-power and --supabase paths; "
            "implicit evidence from another soak is forbidden"
        )

    if args.output is not None:
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        collisions = [
            path for path in (args.output, temporary) if path.exists()
        ]
        if collisions:
            raise SystemExit(
                "refusing to overwrite soak-summary evidence: "
                + ", ".join(str(path) for path in collisions)
            )

    power_raw = args.power.read_bytes()
    ttn_raw = args.ttn.read_bytes()
    handoff_raw = (
        args.handoff_power.read_bytes()
        if args.handoff_power is not None and args.handoff_power.exists()
        else None
    )
    supabase_raw = (
        args.supabase.read_bytes()
        if args.supabase is not None and args.supabase.exists()
        else None
    )
    power = load_jsonl(args.power, power_raw)
    ttn = load_jsonl(args.ttn, ttn_raw)
    handoff_power = (
        load_jsonl(args.handoff_power, handoff_raw)
        if args.handoff_power is not None and handoff_raw is not None else []
    )
    assertions = [
        row for row in power
        if row.get("event") in ("ppk2_power_on", "ppk2_power_heartbeat")
    ]
    power_on_events = [row for row in power if row.get("event") == "ppk2_power_on"]
    hold_end_events = [
        row for row in power if row.get("event") == "ppk2_power_hold_end"
    ]
    heartbeats = [row for row in power if row.get("event") == "ppk2_power_heartbeat"]
    # Preserve append order. Sorting here would make the later
    # timestamps_strictly_increasing assertion tautological and could hide a
    # replayed or out-of-order record in the immutable collector log.
    uplinks = [row for row in ttn if row.get("event") == "ttn_uplink"]

    power_times = [timestamp(row["utc"]) for row in assertions]
    heartbeat_gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(power_times, power_times[1:])
    ]
    terminal_control_gap = (
        timestamp(hold_end_events[-1]["utc"]) - power_times[-1]
        if hold_end_events and power_times else None
    )
    source_values = [int(row["source_mv"]) for row in assertions]
    reconnects = [int(row.get("reconnects", 0)) for row in heartbeats]

    # Collector revisions before 2026-07-27 serialized TTN's omitted
    # protobuf-default FCntUp 0 as JSON null. Preserve those raw bytes while
    # interpreting only null at the semantic boundary as the initial zero.
    counters = [
        0 if row.get("f_cnt") is None else int(row["f_cnt"])
        for row in uplinks
    ]
    counter_steps = [later - earlier for earlier, later in zip(counters, counters[1:])]
    uplink_times = [timestamp(row["utc"]) for row in uplinks]
    cadence = [
        (later - earlier).total_seconds()
        for earlier, later in zip(uplink_times, uplink_times[1:])
    ]
    telemetry_all = [row.get("telemetry") for row in uplinks]
    decoded_telemetry = [row for row in telemetry_all if isinstance(row, dict)]
    required_numeric_fields = (
        "lat_e7", "lon_e7", "altitude_m", "temperature_deci_c",
        "pressure_deci_hpa", "solar_mv", "vstor_mv", "speed_cm_s",
        "heading_cdeg", "satellites", "accel_x_cms2", "accel_y_cms2",
        "accel_z_cms2", "uv_index", "ambient_lux", "acoustic_event",
    )
    def invalid_fields(row: object) -> list[str]:
        if not isinstance(row, dict):
            return ["telemetry"]
        return [
            field for field in required_numeric_fields
            if field not in row
            or isinstance(row[field], bool)
            or not isinstance(row[field], (int, float))
            or not math.isfinite(float(row[field]))
        ]

    invalid_telemetry_rows = [
        {
            "f_cnt": uplink.get("f_cnt"),
            "fields": invalid_fields(row),
        }
        for uplink, row in zip(uplinks, telemetry_all)
        if invalid_fields(row)
    ]
    telemetry = [
        row for row in decoded_telemetry
        if all(
            field in row
            and not isinstance(row[field], bool)
            and isinstance(row[field], (int, float))
            and math.isfinite(float(row[field]))
            for field in required_numeric_fields
        )
    ]
    vstor = [int(row["vstor_mv"]) for row in telemetry]
    accel_magnitude = [
        math.sqrt(
            float(row["accel_x_cms2"]) ** 2
            + float(row["accel_y_cms2"]) ** 2
            + float(row["accel_z_cms2"]) ** 2
        )
        for row in telemetry
    ]
    source_setpoint = source_values[-1] if source_values else 0
    scheduled_gaps = [value for value in cadence if value >= 900]
    mqtt_connects = [row for row in ttn if row.get("event") == "mqtt_connected"]
    mqtt_disconnects = [
        row for row in ttn if row.get("event") == "mqtt_disconnected"
    ]
    mqtt_failures = [
        row for row in ttn
        if row.get("event") in ("mqtt_connect_failed", "mqtt_decode_error")
    ]
    downlinks = [row for row in ttn if row.get("event") == "ttn_downlink"]
    downlink_errors = [
        row for row in downlinks
        if row.get("error_code")
        or row.get("topic_suffix") in ("failed", "nack")
    ]
    handoff_assertions = [
        row for row in handoff_power
        if row.get("event") in ("ppk2_power_on", "ppk2_power_heartbeat")
    ]
    handoff_power_on = [
        row for row in handoff_power if row.get("event") == "ppk2_power_on"
    ]
    handoff_heartbeats = [
        row for row in handoff_power if row.get("event") == "ppk2_power_heartbeat"
    ]
    handoff_times = [timestamp(row["utc"]) for row in handoff_assertions]
    handoff_gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(handoff_times, handoff_times[1:])
    ]
    handoff_sources = [
        int(row["source_mv"]) for row in handoff_assertions
    ]
    handoff_reconnects = [
        int(row.get("reconnects", 0)) for row in handoff_heartbeats
    ]
    handoff_transition_seconds = (
        (
            timestamp(handoff_power_on[0]["utc"])
            - timestamp(hold_end_events[-1]["utc"])
        ).total_seconds()
        if hold_end_events and handoff_power_on else None
    )
    backend = (
        summarize_backend(uplinks, load_json_array(args.supabase, supabase_raw))
        if supabase_raw is not None else None
    )

    report = {
        "qualification_scope": {
            "firmware_profile": args.firmware_profile,
            **QUALIFICATION_SCOPES[args.firmware_profile],
        },
        "provenance": {
            "power": provenance_record(args.power, power_raw),
            "ttn": provenance_record(args.ttn, ttn_raw),
            "handoff_power": (
                provenance_record(
                    args.handoff_power,
                    handoff_raw,
                    append_allowed=True,
                )
                if handoff_raw is not None else None
            ),
            "supabase": (
                provenance_record(args.supabase, supabase_raw)
                if args.supabase is not None and supabase_raw is not None else None
            ),
        },
        "power": {
            "assertions": len(assertions),
            "heartbeats": len(heartbeats),
            "held_seconds": (
                float(hold_end_events[-1]["held_seconds"])
                if hold_end_events
                else round((power_times[-1] - power_times[0]).total_seconds(), 3)
                if len(power_times) >= 2 else 0
            ),
            "source_mv_unique": sorted(set(source_values)),
            "max_heartbeat_gap_seconds": (
                round(max(heartbeat_gaps), 3) if heartbeat_gaps else None
            ),
            "terminal_control_gap_seconds": (
                round(terminal_control_gap.total_seconds(), 3)
                if terminal_control_gap is not None else None
            ),
            "max_reconnects": max(reconnects, default=0),
            "power_on_events": len(power_on_events),
            "hold_end_events": len(hold_end_events),
            "hold_end_seen": bool(hold_end_events),
            "hold_end_held_seconds": (
                float(hold_end_events[-1]["held_seconds"])
                if hold_end_events else None
            ),
            "timestamps_strictly_increasing": all(
                later > earlier
                for earlier, later in zip(power_times, power_times[1:])
            ),
        },
        "uplinks": {
            "count": len(uplinks),
            "f_cnt_first": counters[0] if counters else None,
            "f_cnt_last": counters[-1] if counters else None,
            "counter_steps": counter_steps,
            "counter_contiguous": all(step == 1 for step in counter_steps),
            "cadence_seconds": [round(value, 3) for value in cadence],
            "scheduled_scale_gaps": len(scheduled_gaps),
            "short_wake_gaps": sum(value < 900 for value in cadence),
            "timestamps_strictly_increasing": all(
                later > earlier
                for earlier, later in zip(uplink_times, uplink_times[1:])
            ),
            "payload_lengths": sorted(
                {int(row["payload_len"]) for row in uplinks}
            ),
            "f_ports": sorted({int(row["f_port"]) for row in uplinks}),
            "spreading_factors": sorted(
                {int(row["spreading_factor"]) for row in uplinks}
            ),
            "bandwidth_hz": sorted(
                {int(row["bandwidth_hz"]) for row in uplinks}
            ),
        },
        "supply": {
            "vstor_mv": numeric_range(vstor) if vstor else None,
            "source_minus_vstor_mv": (
                numeric_range([source_setpoint - value for value in vstor])
                if vstor and source_setpoint else None
            ),
            "interpretation": (
                "PPK2 is a source, not a sink: it establishes the low-rail "
                "floor while solar may raise VSTOR to the BQ25570 VBAT_OV "
                "ceiling"
            ),
            "vbat_ov_mv": args.vbat_ov_mv,
            "vbat_ov_tolerance_mv": args.vbat_ov_tolerance_mv,
        },
        "link": {
            "rssi_dbm": numeric_range(
                [float(row["rssi_dbm"]) for row in uplinks]
            ) if uplinks else None,
            "snr_db": numeric_range(
                [float(row["snr_db"]) for row in uplinks]
            ) if uplinks else None,
            "frequencies_hz": sorted(
                {int(row["frequency_hz"]) for row in uplinks}
            ),
            "gateway_ids": sorted(
                {str(row["gateway_id"]) for row in uplinks if row.get("gateway_id")}
            ),
        },
        "sensors": {
            key: numeric_range([float(row[key]) for row in telemetry])
            for key in (
                "solar_mv",
                "temperature_deci_c",
                "pressure_deci_hpa",
                "ambient_lux",
                "accel_x_cms2",
                "accel_y_cms2",
                "accel_z_cms2",
            )
        } | {
            "accel_magnitude_cms2": numeric_range(accel_magnitude)
        } if telemetry else {},
        "gps": {
            "nogps_rows": sum(
                row["satellites"] == 0
                and row["lat_e7"] == 0
                and row["lon_e7"] == 0
                for row in telemetry
            ),
            "nonzero_fix_rows": sum(row["satellites"] >= 4 for row in telemetry),
        },
        "monitor": {
            "mqtt_connects": len(mqtt_connects),
            "mqtt_disconnects": len(mqtt_disconnects),
            "mqtt_failures": len(mqtt_failures),
            "downlink_events": len(downlinks),
            "downlink_errors": len(downlink_errors),
            "decoded_telemetry_rows": len(decoded_telemetry),
            "complete_numeric_telemetry_rows": len(telemetry),
            "invalid_or_unavailable_telemetry": invalid_telemetry_rows,
        },
        "handoff": {
            "power_on_events": len(handoff_power_on),
            "heartbeats": len(handoff_heartbeats),
            "transition_seconds": (
                round(handoff_transition_seconds, 3)
                if handoff_transition_seconds is not None else None
            ),
            "source_mv_unique": sorted(set(handoff_sources)),
            "max_heartbeat_gap_seconds": (
                round(max(handoff_gaps), 3) if handoff_gaps else None
            ),
            "max_reconnects": max(handoff_reconnects, default=0),
            "timestamps_strictly_increasing": all(
                later > earlier
                for earlier, later in zip(handoff_times, handoff_times[1:])
            ),
        },
        "backend": backend,
    }

    if args.final:
        failures: list[str] = []

        def require(condition: bool, message: str) -> None:
            if not condition:
                failures.append(message)

        held = report["power"]["held_seconds"]
        hold_end_held = report["power"]["hold_end_held_seconds"]
        max_gap = report["power"]["max_heartbeat_gap_seconds"]
        terminal_gap = report["power"]["terminal_control_gap_seconds"]
        handoff_gap = report["handoff"]["transition_seconds"]
        require(
            report["power"]["power_on_events"] == 1,
            "expected exactly one PPK2 power_on event",
        )
        require(
            report["power"]["hold_end_events"] == 1,
            "expected exactly one terminal PPK2 hold_end event",
        )
        require(
            report["power"]["timestamps_strictly_increasing"],
            "PPK2 assertion timestamps are not strictly increasing",
        )
        require(
            held >= args.min_held_seconds,
            f"power held {held}s, expected at least {args.min_held_seconds}s",
        )
        require(
            hold_end_held is not None and hold_end_held >= args.min_held_seconds,
            "PPK2 terminal hold duration is missing or too short",
        )
        require(
            report["power"]["source_mv_unique"] == [args.expected_source_mv],
            "PPK2 source changed or did not match the expected setpoint",
        )
        require(report["power"]["max_reconnects"] == 0, "PPK2 reconnected")
        require(
            max_gap is not None and max_gap <= args.max_heartbeat_gap_seconds,
            f"PPK2 heartbeat gap exceeded {args.max_heartbeat_gap_seconds}s",
        )
        require(
            terminal_gap is not None
            and 0 <= terminal_gap <= args.max_heartbeat_gap_seconds,
            "PPK2 final assertion-to-hold_end gap exceeded tolerance or was unordered",
        )
        require(
            report["handoff"]["power_on_events"] == 1,
            "standby PPK2 supervisor did not acquire exactly once",
        )
        require(
            report["handoff"]["heartbeats"] >= 1,
            "standby PPK2 supervisor has no post-acquisition heartbeat",
        )
        require(
            handoff_gap is not None
            and 0 <= handoff_gap <= args.max_handoff_gap_seconds,
            f"PPK2 handoff exceeded {args.max_handoff_gap_seconds}s or was unordered",
        )
        require(
            report["handoff"]["source_mv_unique"] == [args.expected_source_mv],
            "standby PPK2 source did not match the expected setpoint",
        )
        require(
            report["handoff"]["timestamps_strictly_increasing"],
            "standby PPK2 assertion timestamps are not strictly increasing",
        )
        require(
            report["handoff"]["max_reconnects"] == 0,
            "standby PPK2 supervisor reconnected",
        )
        require(
            report["handoff"]["max_heartbeat_gap_seconds"] is not None
            and report["handoff"]["max_heartbeat_gap_seconds"]
            <= args.max_heartbeat_gap_seconds,
            "standby PPK2 heartbeat gap exceeded tolerance",
        )
        require(len(uplinks) >= args.min_uplinks, "too few overnight uplinks")
        require(
            report["uplinks"]["timestamps_strictly_increasing"],
            "uplink timestamps are not strictly increasing",
        )
        require(report["uplinks"]["counter_contiguous"], "LoRaWAN fCnt gap or duplicate")
        require(report["uplinks"]["payload_lengths"] == [35], "payload length changed")
        require(report["uplinks"]["f_ports"] == [1], "primary uplink FPort changed")
        require(report["uplinks"]["spreading_factors"] == [9], "uplink SF changed")
        require(report["uplinks"]["bandwidth_hz"] == [125000], "uplink bandwidth changed")
        require(
            report["link"]["frequencies_hz"] == US915_FSB2_FREQUENCIES_HZ,
            "uplinks did not stay on and exercise all eight US915 FSB2 channels",
        )
        require(
            bool(report["link"]["gateway_ids"]),
            "no gateway identity was captured",
        )
        require(
            all(
                -140 <= float(row["rssi_dbm"]) <= 0
                and -30 <= float(row["snr_db"]) <= 30
                for row in uplinks
            ),
            "one or more RF metadata values are missing or implausible",
        )
        require(
            all(
                args.scheduled_gap_min_seconds
                <= gap
                <= args.scheduled_gap_max_seconds
                for gap in scheduled_gaps
            ),
            "one or more scheduled-scale cadence gaps left the acceptance window",
        )
        require(len(scheduled_gaps) >= args.min_uplinks - 3, "too few scheduled cycles")
        require(report["monitor"]["mqtt_connects"] == 1, "TTN MQTT connected more or less than once")
        require(not mqtt_disconnects, "TTN MQTT monitor disconnected")
        require(not mqtt_failures, "TTN MQTT connect/decode failure occurred")
        require(not downlink_errors, "TTN reported a downlink failure or NACK")
        require(
            len(telemetry) == len(uplinks),
            "one or more uplinks failed decoding or reported an unavailable sensor",
        )
        require(
            bool(vstor) and min(vstor) >= args.expected_source_mv - 100,
            "VSTOR fell below the PPK2-supported source floor",
        )
        require(
            bool(vstor)
            and max(vstor)
            <= args.vbat_ov_mv + args.vbat_ov_tolerance_mv,
            "VSTOR exceeded the plausible BQ25570 harvester ceiling",
        )
        require(
            all(
                8000 <= float(row["pressure_deci_hpa"]) <= 12000
                and -500 <= float(row["temperature_deci_c"]) <= 850
                and 0 <= float(row["solar_mv"]) <= 6000
                and 0 <= float(row["ambient_lux"]) <= 65535
                for row in telemetry
            ),
            "one or more environmental sensor values are implausible",
        )
        require(
            all(
                0 <= int(row["uv_index"]) <= 255
                and int(row["acoustic_event"]) in (0, 1)
                and 0 <= int(row["speed_cm_s"]) <= 50000
                and 0 <= int(row["heading_cdeg"]) <= 35999
                and 0 <= int(row["satellites"]) <= 64
                for row in telemetry
            ),
            "one or more bounded telemetry fields are invalid",
        )
        require(
            bool(accel_magnitude)
            and all(800 <= value <= 1200 for value in accel_magnitude),
            "stationary acceleration magnitude left the 0.8-1.2 g envelope",
        )
        require(
            all(
                (
                    row["satellites"] == 0
                    and row["lat_e7"] == 0
                    and row["lon_e7"] == 0
                )
                or (
                    row["satellites"] >= 4
                    and -900000000 <= row["lat_e7"] <= 900000000
                    and -1800000000 <= row["lon_e7"] <= 1800000000
                    and -500 <= row["altitude_m"] <= 60000
                )
                for row in telemetry
            ),
            "GPS fields contain an inconsistent or out-of-range row",
        )
        require(backend is not None, "final Supabase export is missing")
        if backend is not None:
            require(
                backend["ttn_rows"] == backend["supabase_rows"],
                "TTN and Supabase final row counts differ",
            )
            require(
                backend["matched_rows"] == backend["ttn_rows"],
                "not every TTN row has exactly one Supabase row",
            )
            require(
                not backend["unmatched_ttn_fcnt"],
                "one or more TTN uplinks are missing from Supabase",
            )
            require(
                not backend["unmatched_supabase_times"],
                "unexpected Supabase-only soak rows exist",
            )
            require(
                not backend["field_differences"],
                "TTN and Supabase decoded fields differ",
            )
            backend_max_delta = backend["timestamp_delta_seconds"]["max"]
            require(
                backend_max_delta is not None and backend_max_delta <= 5,
                "TTN-to-Supabase delivery timestamp delta exceeded 5 s",
            )
        report["final_gate"] = {
            "passed": not failures,
            "failures": failures,
            "criteria": {
                "expected_source_mv": args.expected_source_mv,
                "vbat_ov_mv": args.vbat_ov_mv,
                "vbat_ov_tolerance_mv": args.vbat_ov_tolerance_mv,
                "firmware_profile": args.firmware_profile,
                "min_held_seconds": args.min_held_seconds,
                "min_uplinks": args.min_uplinks,
                "max_heartbeat_gap_seconds": args.max_heartbeat_gap_seconds,
                "max_handoff_gap_seconds": args.max_handoff_gap_seconds,
                "scheduled_gap_seconds": [
                    args.scheduled_gap_min_seconds,
                    args.scheduled_gap_max_seconds,
                ],
            },
        }

    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        try:
            os.link(temporary, args.output)
        except FileExistsError as error:
            raise SystemExit(
                f"refusing to overwrite soak-summary evidence: {args.output}"
            ) from error
        finally:
            temporary.unlink(missing_ok=True)
    print(serialized, end="")
    if args.final and report["final_gate"]["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
