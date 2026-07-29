#!/usr/bin/env python3
"""Regression-test the overnight soak gate with synthetic, secret-free logs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from backend_ingest_summary import expected_from_ttn
from soak_summary import US915_FSB2_FREQUENCIES_HZ


HERE = Path(__file__).resolve().parent
SOURCE_MV = 4660


def iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds")


def fixture() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    power = [
        {
            "utc": iso(start),
            "event": "ppk2_power_on",
            "source_mv": SOURCE_MV,
        }
    ]
    for held_seconds in range(30, 57571, 30):
        power.append(
            {
                "utc": iso(start + timedelta(seconds=held_seconds)),
                "event": "ppk2_power_heartbeat",
                "held_seconds": held_seconds,
                "source_mv": SOURCE_MV,
                "reconnects": 0,
            }
        )
    power.append(
        {
            "utc": iso(start + timedelta(seconds=57590)),
            "event": "ppk2_power_heartbeat",
            "held_seconds": 57590,
            "source_mv": SOURCE_MV,
            "reconnects": 0,
        }
    )
    power.append(
        {
            "utc": iso(start + timedelta(seconds=57600)),
            "event": "ppk2_power_hold_end",
            "held_seconds": 57600,
            "source_mv": SOURCE_MV,
            "reconnects": 0,
        }
    )

    handoff_start = start + timedelta(seconds=57600.5)
    handoff = [
        {
            "utc": iso(handoff_start),
            "event": "ppk2_power_on",
            "source_mv": SOURCE_MV,
            "reconnects": 0,
        },
        {
            "utc": iso(handoff_start + timedelta(seconds=30)),
            "event": "ppk2_power_heartbeat",
            "held_seconds": 30,
            "source_mv": SOURCE_MV,
            "reconnects": 0,
        },
    ]

    ttn = [
        {
            "utc": iso(start + timedelta(seconds=60)),
            "event": "mqtt_connected",
            "device_id": "stratolink-2",
        }
    ]
    supabase: list[dict] = []
    for index in range(40):
        received = start + timedelta(seconds=300 + index * 1255)
        telemetry = {
            "solar_mv": 500,
            "vstor_mv": 4620,
            "temperature_deci_c": 250,
            "pressure_deci_hpa": 10130,
            "lat_e7": 0,
            "lon_e7": 0,
            "altitude_m": 0,
            "speed_cm_s": 0,
            "heading_cdeg": 0,
            "satellites": 0,
            "accel_x_cms2": 0,
            "accel_y_cms2": 0,
            "accel_z_cms2": 981,
            "uv_index": 0,
            "ambient_lux": 500,
            "acoustic_event": 0,
        }
        uplink = {
            "utc": iso(received),
            "received_at": iso(received),
            "event": "ttn_uplink",
            "device_id": "stratolink-2",
            "f_cnt": 14 + index,
            "f_port": 1,
            "payload_len": 35,
            "frequency_hz": US915_FSB2_FREQUENCIES_HZ[index % 8],
            "gateway_id": "test-gateway",
            "rssi_dbm": -70,
            "snr_db": 10,
            "spreading_factor": 9,
            "bandwidth_hz": 125000,
            "telemetry": telemetry,
        }
        ttn.append(uplink)
        downstream = expected_from_ttn(uplink)
        downstream["time"] = iso(received + timedelta(milliseconds=200))
        supabase.append(downstream)
    return power, handoff, ttn, supabase


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_case(
    root: Path,
    name: str,
    power: list[dict],
    handoff: list[dict],
    ttn: list[dict],
    supabase: list[dict],
) -> subprocess.CompletedProcess[str]:
    case = root / name
    case.mkdir()
    power_path = case / "power.jsonl"
    handoff_path = case / "handoff.jsonl"
    ttn_path = case / "ttn.jsonl"
    supabase_path = case / "supabase.json"
    output_path = case / "summary.json"
    write_jsonl(power_path, power)
    write_jsonl(handoff_path, handoff)
    write_jsonl(ttn_path, ttn)
    supabase_path.write_text(json.dumps(supabase), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(HERE / "soak_summary.py"),
            "--final",
            "--power",
            str(power_path),
            "--handoff-power",
            str(handoff_path),
            "--ttn",
            str(ttn_path),
            "--supabase",
            str(supabase_path),
            "--output",
            str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    power, handoff, ttn, supabase = fixture()
    with tempfile.TemporaryDirectory(prefix="stratolink-soak-test-") as temporary:
        root = Path(temporary)
        collision_output = root / "preserved-summary.json"
        collision_output.write_text("preserved\n", encoding="utf-8")
        collision = subprocess.run(
            [
                sys.executable,
                str(HERE / "soak_summary.py"),
                "--power", str(root / "missing.jsonl"),
                "--output", str(collision_output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite soak-summary evidence" in collision.stderr
        assert collision_output.read_text(encoding="utf-8") == "preserved\n"

        passing = run_case(root, "passing", power, handoff, ttn, supabase)
        assert passing.returncode == 0, passing.stdout + passing.stderr
        assert '"passed": true' in passing.stdout
        passing_report = json.loads(passing.stdout)
        assert passing_report["qualification_scope"]["firmware_profile"] == "relay_soak"
        assert any(
            "STOP1" in value
            for value in passing_report["qualification_scope"]["does_not_prove"]
        )

        protobuf_zero = deepcopy(ttn)
        protobuf_uplinks = [
            row for row in protobuf_zero if row.get("event") == "ttn_uplink"
        ]
        for counter, row in enumerate(protobuf_uplinks):
            row["f_cnt"] = None if counter == 0 else counter
        protobuf_supabase = [expected_from_ttn(row) for row in protobuf_uplinks]
        for row, original in zip(protobuf_supabase, supabase):
            row["time"] = original["time"]
        protobuf_zero_result = run_case(
            root,
            "protobuf-zero",
            power,
            handoff,
            protobuf_zero,
            protobuf_supabase,
        )
        assert protobuf_zero_result.returncode == 0, (
            protobuf_zero_result.stdout + protobuf_zero_result.stderr
        )
        protobuf_report = json.loads(protobuf_zero_result.stdout)
        assert protobuf_report["uplinks"]["f_cnt_first"] == 0
        assert protobuf_report["uplinks"]["f_cnt_last"] == 39

        partial_power = root / "partial-power.jsonl"
        partial_ttn = root / "partial-ttn.jsonl"
        write_jsonl(partial_power, power[:-1])
        write_jsonl(partial_ttn, ttn)
        partial = subprocess.run(
            [
                sys.executable,
                str(HERE / "soak_summary.py"),
                "--power", str(partial_power),
                "--ttn", str(partial_ttn),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert partial.returncode == 0, partial.stdout + partial.stderr
        partial_report = json.loads(partial.stdout)
        assert partial_report["backend"] is None
        assert partial_report["handoff"]["power_on_events"] == 0
        assert partial_report["provenance"]["handoff_power"] is None
        assert partial_report["provenance"]["supabase"] is None

        missing_explicit_final = subprocess.run(
            [
                sys.executable,
                str(HERE / "soak_summary.py"),
                "--power", str(partial_power),
                "--ttn", str(partial_ttn),
                "--final",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert missing_explicit_final.returncode != 0
        assert "requires explicit --handoff-power and --supabase" in (
            missing_explicit_final.stderr
        )

        solar_charge = deepcopy(ttn)
        solar_charge[1]["telemetry"]["vstor_mv"] = 5396
        solar_supabase = [
            expected_from_ttn(row)
            for row in solar_charge
            if row.get("event") == "ttn_uplink"
        ]
        for row, original in zip(solar_supabase, supabase):
            row["time"] = original["time"]
        solar_result = run_case(
            root, "solar-charge", power, handoff, solar_charge, solar_supabase
        )
        assert solar_result.returncode == 0, solar_result.stdout + solar_result.stderr

        overvoltage = deepcopy(solar_charge)
        overvoltage[1]["telemetry"]["vstor_mv"] = 5439
        overvoltage_supabase = [
            expected_from_ttn(row)
            for row in overvoltage
            if row.get("event") == "ttn_uplink"
        ]
        for row, original in zip(overvoltage_supabase, supabase):
            row["time"] = original["time"]
        overvoltage_result = run_case(
            root,
            "overvoltage",
            power,
            handoff,
            overvoltage,
            overvoltage_supabase,
        )
        assert overvoltage_result.returncode != 0
        assert "harvester ceiling" in overvoltage_result.stdout

        source_loss = deepcopy(ttn)
        source_loss[1]["telemetry"]["vstor_mv"] = 4559
        source_loss_supabase = [
            expected_from_ttn(row)
            for row in source_loss
            if row.get("event") == "ttn_uplink"
        ]
        for row, original in zip(source_loss_supabase, supabase):
            row["time"] = original["time"]
        source_loss_result = run_case(
            root,
            "source-loss",
            power,
            handoff,
            source_loss,
            source_loss_supabase,
        )
        assert source_loss_result.returncode != 0
        assert "source floor" in source_loss_result.stdout

        short = deepcopy(power)
        short[-1]["held_seconds"] = 57599
        short_result = run_case(root, "short", short, handoff, ttn, supabase)
        assert short_result.returncode != 0
        assert "terminal hold duration is missing or too short" in short_result.stdout

        terminal_gap = [
            row for row in power
            if row.get("event") != "ppk2_power_heartbeat"
            or int(row.get("held_seconds", 0)) <= 57500
        ]
        gap_result = run_case(
            root,
            "terminal-gap",
            terminal_gap,
            handoff,
            ttn,
            supabase,
        )
        assert gap_result.returncode != 0
        assert "final assertion-to-hold_end gap" in gap_result.stdout

        wrong_source = deepcopy(power)
        wrong_source[10]["source_mv"] = SOURCE_MV - 1
        wrong_source_result = run_case(
            root, "wrong-source", wrong_source, handoff, ttn, supabase
        )
        assert wrong_source_result.returncode != 0
        assert "PPK2 source changed" in wrong_source_result.stdout

        reconnected = deepcopy(power)
        reconnected[20]["reconnects"] = 1
        reconnect_result = run_case(
            root, "reconnect", reconnected, handoff, ttn, supabase
        )
        assert reconnect_result.returncode != 0
        assert "PPK2 reconnected" in reconnect_result.stdout

        delayed_handoff = deepcopy(handoff)
        hold_end_time = datetime.fromisoformat(power[-1]["utc"])
        delayed_handoff[0]["utc"] = iso(hold_end_time + timedelta(seconds=2.001))
        delayed_handoff[1]["utc"] = iso(hold_end_time + timedelta(seconds=32.001))
        delayed_result = run_case(
            root, "delayed-handoff", power, delayed_handoff, ttn, supabase
        )
        assert delayed_result.returncode != 0
        assert "PPK2 handoff exceeded" in delayed_result.stdout

        counter_gap = deepcopy(ttn)
        uplink_indices = [
            index
            for index, row in enumerate(counter_gap)
            if row.get("event") == "ttn_uplink"
        ]
        counter_gap[uplink_indices[20]]["f_cnt"] += 1
        counter_result = run_case(
            root, "counter-gap", power, handoff, counter_gap, supabase
        )
        assert counter_result.returncode != 0
        assert "fCnt gap or duplicate" in counter_result.stdout

        out_of_order = deepcopy(ttn)
        uplink_indices = [
            index
            for index, row in enumerate(out_of_order)
            if row.get("event") == "ttn_uplink"
        ]
        first = uplink_indices[10]
        second = uplink_indices[11]
        out_of_order[first]["utc"], out_of_order[second]["utc"] = (
            out_of_order[second]["utc"],
            out_of_order[first]["utc"],
        )
        order_result = run_case(
            root, "out-of-order", power, handoff, out_of_order, supabase
        )
        assert order_result.returncode != 0
        assert "uplink timestamps are not strictly increasing" in order_result.stdout

        missing_downstream = run_case(
            root, "missing-downstream", power, handoff, ttn, supabase[:-1]
        )
        assert missing_downstream.returncode != 0
        assert "TTN and Supabase final row counts differ" in missing_downstream.stdout

        altered_supabase = deepcopy(supabase)
        altered_supabase[0]["temperature"] += 1
        altered_result = run_case(
            root, "altered-downstream", power, handoff, ttn, altered_supabase
        )
        assert altered_result.returncode != 0
        assert "decoded fields differ" in altered_result.stdout

        disconnected = deepcopy(ttn)
        disconnected.append(
            {
                "utc": iso(hold_end_time),
                "event": "mqtt_disconnected",
                "reason_code": 1,
            }
        )
        disconnect_result = run_case(
            root, "mqtt-disconnect", power, handoff, disconnected, supabase
        )
        assert disconnect_result.returncode != 0
        assert "TTN MQTT monitor disconnected" in disconnect_result.stdout

        bad_gps = deepcopy(ttn)
        bad_gps[uplink_indices[5]]["telemetry"]["satellites"] = 3
        gps_result = run_case(
            root, "bad-gps", power, handoff, bad_gps, supabase
        )
        assert gps_result.returncode != 0
        assert "GPS fields contain an inconsistent" in gps_result.stdout

        unavailable_sensor = deepcopy(ttn)
        unavailable_sensor[uplink_indices[6]]["telemetry"][
            "temperature_deci_c"
        ] = None
        unavailable_supabase = [
            expected_from_ttn(row)
            for row in unavailable_sensor
            if row.get("event") == "ttn_uplink"
        ]
        for row, original in zip(unavailable_supabase, supabase):
            row["time"] = original["time"]
        unavailable_result = run_case(
            root,
            "unavailable-sensor",
            power,
            handoff,
            unavailable_sensor,
            unavailable_supabase,
        )
        assert unavailable_result.returncode != 0
        assert "reported an unavailable sensor" in unavailable_result.stdout

    print(
        "PASS: soak duration/power/handoff/counter/backend/monitor/GPS gates "
        "reject adversarial evidence"
    )


if __name__ == "__main__":
    main()
