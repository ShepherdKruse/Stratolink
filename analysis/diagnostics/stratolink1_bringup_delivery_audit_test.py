#!/usr/bin/env python3
"""Focused regression for Board1 delivery/parity evidence."""

from copy import deepcopy

from stratolink1_bringup_delivery_audit import evaluate


UPLINK = {
    "event": "ttn_uplink",
    "device_id": "stratolink-1",
    "received_at": "2026-08-31T03:33:43.903198675Z",
    "f_cnt": 0,
    "f_port": 1,
    "payload_len": 40,
    "rssi_dbm": -43,
    "snr_db": 11.5,
    "frequency_hz": "904100000",
    "spreading_factor": 9,
    "bandwidth_hz": 125000,
    "telemetry": {
        "temperature_deci_c": 225,
        "pressure_deci_hpa": 10127,
        "solar_mv": 1026,
        "vstor_mv": 4660,
        "speed_cm_s": 0,
        "heading_cdeg": 0,
        "satellites": 0,
        "accel_x_cms2": 78,
        "accel_y_cms2": 109,
        "accel_z_cms2": 1019,
        "uv_index": 0,
        "ambient_lux": 511,
        "acoustic_event": 0,
        "telemetry_version": 3,
        "power_tier": 0,
        "reset_cause": 4,
        "boot_count": 1,
        "gps_fix_age_min": None,
        "server_proof_count_mod8": 2,
        "server_qualified_miss_streak": 0,
        "server_recovery_parity": 1,
        "command_ack_seq": None,
        "relay_enabled": False,
        "relay_fwd_delta": 0,
        "ctt_tags_delta": 0,
    },
}
STORAGE = {
    "passed": True,
    "selected_rows": 1,
    "first_f_cnt": 0,
    "first_received_at": "2026-08-31T03:33:44.115251023Z",
}
ROW = {
    "device_id": "stratolink-1",
    "time": "2026-08-31T03:33:44.115251+00:00",
    "lat": None,
    "lon": None,
    "altitude_m": None,
    "temperature": 22.5,
    "pressure": 1012.7,
    "solar_voltage": 1.026,
    "battery_voltage": 4.66,
    "rssi": -43,
    "snr": 11.5,
    "gps_speed": 0,
    "gps_heading": 0,
    "gps_satellites": 0,
    "mems_accel_x": 0.78,
    "mems_accel_y": 1.09,
    "mems_accel_z": 10.19,
    "uv_index": 0,
    "ambient_lux": 511,
    "acoustic_event": 0,
    "telemetry_version": 3,
    "power_tier": 0,
    "reset_cause": 4,
    "boot_count": 1,
    "gps_fix_age_min": None,
    "server_proof_count_mod8": 2,
    "server_qualified_miss_streak": 0,
    "server_recovery_parity": 1,
    "command_ack_seq": None,
    "relay_enabled": False,
    "relay_fwd_delta": 0,
    "ctt_tags_delta": 0,
    "lora_sf": 9,
    "lora_bw": 125000,
    "frequency_hz": 904100000,
}


def run(row):
    return evaluate(
        [UPLINK], STORAGE, [row],
        device_id="stratolink-1",
        after="2026-08-31T03:33:00Z",
        until="2026-08-31T03:34:30Z",
    )


def main() -> None:
    assert run(ROW)["passed"] is True

    # The same one-packet audit must bind a later control-ACK uplink without
    # weakening its exact FCnt identity gate.
    later_uplink = deepcopy(UPLINK)
    later_uplink["f_cnt"] = 2
    later_uplink["telemetry"]["command_ack_seq"] = 1
    later_storage = deepcopy(STORAGE)
    later_storage["first_f_cnt"] = 2
    later_row = deepcopy(ROW)
    later_row["command_ack_seq"] = 1
    later = evaluate(
        [later_uplink], later_storage, [later_row],
        device_id="stratolink-1",
        after="2026-08-31T03:33:00Z",
        until="2026-08-31T03:34:30Z",
        expected_f_cnt=2,
        expected_command_ack=1,
    )
    assert later["passed"] is True
    assert later["command_ack_seq"] == 1

    wrong_ack = evaluate(
        [later_uplink], later_storage, [later_row],
        device_id="stratolink-1",
        after="2026-08-31T03:33:00Z",
        until="2026-08-31T03:34:30Z",
        expected_f_cnt=2,
        expected_command_ack=2,
    )
    assert wrong_ack["passed"] is False
    assert any("durable command ACK sequence 2" in failure
               for failure in wrong_ack["failures"])

    broken = deepcopy(ROW)
    broken["acoustic_event"] = None
    report = run(broken)
    assert report["passed"] is False
    assert report["delivery_layers_present"] is True
    assert report["transport_passed"] is True
    assert report["exact_payload_parity"] is False
    assert report["field_mismatches"] == [
        {"field": "acoustic_event", "mqtt": 0, "supabase": None}
    ]

    stale_proof = deepcopy(ROW)
    stale_proof["server_proof_count_mod8"] = 1
    proof_report = run(stale_proof)
    assert proof_report["exact_payload_parity"] is False
    assert proof_report["field_mismatches"] == [{
        "field": "server_proof_count_mod8", "mqtt": 2, "supabase": 1,
    }]

    stale_v2 = deepcopy(UPLINK)
    stale_v2["telemetry"]["telemetry_version"] = 2
    v2_report = evaluate(
        [stale_v2], STORAGE, [ROW],
        device_id="stratolink-1",
        after="2026-08-31T03:33:00Z",
        until="2026-08-31T03:34:30Z",
    )
    assert "MQTT payload is not the current telemetry-v3 contract" in (
        v2_report["failures"]
    )
    print("PASS: Board1 delivery audit separates live transport from payload parity")


if __name__ == "__main__":
    main()
