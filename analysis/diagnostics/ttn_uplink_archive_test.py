#!/usr/bin/env python3
"""Deterministic, network-free tests for raw TTN uplink archiving."""

from __future__ import annotations

import base64
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import ttn_uplink_archive as archive_tool

from evidence_provenance import write_create_once
from ttn_uplink_archive import (
    ARCHIVE_SCHEMA,
    assert_no_credentials,
    build_archive,
    build_report,
    canonical_bytes,
)


def sample(counter: int = 8, *, device: str = "stratolink-1") -> dict:
    payload = bytearray(40)
    payload[12:14] = (215).to_bytes(2, "big", signed=True)
    payload[14:16] = (10132).to_bytes(2, "big")
    payload[16:18] = (12).to_bytes(2, "big")
    payload[18:20] = (4660).to_bytes(2, "big")
    payload[25:27] = (10).to_bytes(2, "big", signed=True)
    payload[27:29] = (20).to_bytes(2, "big", signed=True)
    payload[29:31] = (980).to_bytes(2, "big", signed=True)
    payload[32:34] = (3).to_bytes(2, "big")
    payload[34] = 0x80
    payload[35] = 8
    payload[36:38] = (0x9100).to_bytes(2, "big")
    payload[38] = 1
    payload[39] = 0x80
    return {
        "end_device_ids": {
            "device_id": device,
            "application_ids": {"application_id": "stratolink"},
            "dev_addr": "260CACD0",
        },
        "received_at": f"2026-08-31T06:{counter:02d}:00.000000000Z",
        "uplink_message": {
            "session_key_id": "opaque-session-id",
            "f_cnt": counter,
            "f_port": 1,
            "frm_payload": base64.b64encode(payload).decode("ascii"),
            "received_at": f"2026-08-31T06:{counter:02d}:00Z",
            "settings": {
                "frequency": "904100000",
                "data_rate": {"lora": {
                    "spreading_factor": 9,
                    "bandwidth": 125000,
                }},
            },
            "rx_metadata": [{
                "gateway_ids": {"gateway_id": "onethreenine"},
                "rssi": -55,
                "snr": 10.5,
            }],
        },
    }


def forensic_cases() -> None:
    # Break caught: malformed payloads must not prevent raw preservation, or
    # disappear from analysis while surrounding frames imply continuity.
    good = sample(8)
    bad_primary = sample(9)
    payload = bytearray(base64.b64decode(bad_primary["uplink_message"]["frm_payload"]))
    payload[34] = 15
    bad_primary["uplink_message"]["frm_payload"] = base64.b64encode(payload).decode()
    bad_base64 = sample(10)
    bad_base64["uplink_message"]["frm_payload"] = "%%%not-base64%%%"
    unknown_port = sample(11)
    unknown_port["uplink_message"]["f_port"] = 99
    invalid_time = sample(12)
    invalid_time["uplink_message"]["received_at"] = None
    bad_length = sample(13)
    bad_length["uplink_message"].update(f_port=11, frm_payload=base64.b64encode(bytes(16)).decode())
    bad_port_type = sample(14)
    bad_port_type["uplink_message"]["f_port"] = {"malformed": True}
    last = sample(15)
    payload = bytearray(base64.b64decode(last["uplink_message"]["frm_payload"]))
    payload[35] = 9  # An opaque failed row must also break boot continuity.
    last["uplink_message"]["frm_payload"] = base64.b64encode(payload).decode()
    rows = [good, bad_primary, bad_base64, unknown_port, invalid_time, bad_length, bad_port_type, last]
    frozen = build_archive(rows, "stratolink-1", "2026-08-31T05:00:00Z", 1000)
    assert frozen["schema"] == ARCHIVE_SCHEMA
    assert frozen["records"] == rows and frozen["record_count"] == 8
    report = build_report(canonical_bytes(frozen), "stratolink-1", "forensic.json")
    assert report["schema"] == "stratolink.ttn_uplink_offline_report.v2"
    assert report["normalization_complete"] is False
    assert report["normalization_success_count"] == 2
    assert report["normalization_failure_count"] == 6
    assert len(report["records"]) == len(rows)
    assert [r["raw_record"] for r in report["records"]] == rows
    assert all(r["normalization_errors"] for r in report["records"][1:-1])
    assert report["counter_transitions"] == []
    assert report["counter_gaps"] == []
    assert report["boot_transitions"] == []
    assert report["interval_seconds"] == []
    assert len(report["session_observations"]) == 2

    # Neither a delayed Storage envelope nor an unknown inner time may move an
    # error past its capture-order neighbors and reconnect their continuity.
    delayed = [sample(8), sample(9), sample(10)]
    delayed[1]["received_at"] = "2026-08-31T06:20:00Z"
    delayed[1]["uplink_message"]["received_at"] = None
    delayed[2]["uplink_message"]["received_at"] = "2026-08-31T06:07:00Z"
    delayed_archive = build_archive(delayed, "stratolink-1", "2026-08-31T05:00:00Z", 1000)
    delayed_report = build_report(canonical_bytes(delayed_archive), "stratolink-1", "delayed.json")
    assert [row["f_cnt"] for row in delayed_report["records"]] == [8, 9, 10]
    assert delayed_report["interval_seconds"] == delayed_report["counter_transitions"] == []
    assert len(delayed_report["session_observations"]) == 2
    assert delayed_report["first_received_at"] == "2026-08-31T06:07:00Z"
    assert delayed_report["last_received_at"] == "2026-08-31T06:08:00Z"

    # Endpoint counters describe the same event-ordered rows as timestamp
    # bounds, even when a failed row separates reversed capture-order frames.
    reversed_report = build_report(canonical_bytes([sample(10), invalid_time, sample(8)]),
                                   "stratolink-1", "reversed-endpoints.json")
    assert reversed_report["first_received_at"] == "2026-08-31T06:08:00Z"
    assert reversed_report["last_received_at"] == "2026-08-31T06:10:00Z"
    assert reversed_report["first_f_cnt"] == 8
    assert reversed_report["last_f_cnt"] == 10
    assert not reversed_report["normalization_complete"]
    assert reversed_report["counter_transitions"] == []

    # Storage can already deliver outer-time order with an earlier RF packet
    # last. Any failed row therefore makes the whole window's continuity unknown.
    late_bad = sample(9)
    late_bad["received_at"] = "2026-08-31T06:20:00Z"
    late_bad["uplink_message"]["frm_payload"] = "%%%not-base64%%%"
    tail_delivery = [sample(8), sample(10), late_bad]
    tail_report = build_report(canonical_bytes(tail_delivery), "stratolink-1", "late-tail.json")
    assert tail_report["interval_seconds"] == [], "late failed FC9 must not imply uninterrupted FC8-to-10 cadence"
    for field in ("counter_transitions", "counter_gaps", "counter_non_increasing",
                  "session_transitions", "dev_addr_transitions", "boot_transitions"):
        assert tail_report[field] == [], field
    assert [row["raw_record"] for row in tail_report["records"]] == tail_delivery
    assert tail_report["normalization_success_count"] == 2 and tail_report["normalization_failure_count"] == 1
    assert [row["record_count"] for row in tail_report["session_observations"]] == [1, 1]
    assert "unavailable" in tail_report["continuity_scope"] and "incomplete window" in tail_report["continuity_scope"]
    assert tail_report["first_received_at"] == "2026-08-31T06:08:00Z"
    assert tail_report["last_received_at"] == "2026-08-31T06:10:00Z"
    # Also suppress a reset-like tuple, not only monotonically increasing FCnt.
    reset_row = sample(7)
    reset_row["received_at"] = reset_row["uplink_message"]["received_at"] = "2026-08-31T06:10:00Z"
    reset_row["end_device_ids"]["dev_addr"] = "260CACD1"
    reset_row["uplink_message"]["session_key_id"] = "different-session-id"
    reset_payload = bytearray(base64.b64decode(reset_row["uplink_message"]["frm_payload"]))
    reset_payload[35] = 9
    reset_row["uplink_message"]["frm_payload"] = base64.b64encode(reset_payload).decode()
    reset_report = build_report(canonical_bytes([sample(8), reset_row, late_bad]), "stratolink-1", "late-reset.json")
    for field in ("interval_seconds", "counter_transitions", "counter_gaps", "counter_non_increasing",
                  "session_transitions", "dev_addr_transitions", "boot_transitions"):
        assert reset_report[field] == [], field

    noninteger_port = sample(8)
    noninteger_port["uplink_message"]["f_port"] = 1.0
    port_report = build_report(canonical_bytes([noninteger_port]), "stratolink-1", "port.json")
    assert not port_report["normalization_complete"]
    assert port_report["records"][0]["raw_record"] == noninteger_port

    all_bad = build_report(canonical_bytes(rows[1:-1]), "stratolink-1", "all-bad.json")
    assert not all_bad["normalization_complete"]
    assert all_bad["normalization_success_count"] == 0
    assert all_bad["normalization_failure_count"] == 6
    assert all_bad["first_received_at"] is None and all_bad["first_f_cnt"] is None
    assert all_bad["session_observations"] == []
    assert all_bad["records"][0]["raw_record"] == bad_primary

    auxiliary = sample(8)
    auxiliary["uplink_message"].update(f_port=11,
        frm_payload=base64.b64encode(bytes.fromhex("435402000000000100000000ffce010005")).decode())
    aux = build_report(canonical_bytes([auxiliary]), "stratolink-1", "aux-only.json")
    assert aux["normalization_complete"]
    assert aux["primary_record_count"] == 0 and aux["auxiliary_record_count"] == 1
    assert aux["boot_observation_count"] == 0 and aux["boot_transitions"] == []
    assert aux["records"][0]["payload_decode_status"] == "deferred"
    assert aux["records"][0]["telemetry"] is None
    assert "analysis_complete" not in aux
    deferred_b2b = sample(9)
    # Length alone does not establish B2B magic/version/content validity.
    deferred_b2b["uplink_message"].update(f_port=12, frm_payload=base64.b64encode(bytes(9)).decode())
    aux = build_report(canonical_bytes([auxiliary, deferred_b2b]), "stratolink-1", "aux-both.json")
    assert aux["normalization_complete"] and aux["auxiliary_record_count"] == 2
    assert aux["primary_record_count"] == aux["boot_observation_count"] == 0
    assert all(row["payload_decode_status"] == "deferred" for row in aux["records"])

    # Existing v1 archive rows may omit application IDs and FCnt's default0.
    legacy = sample(0)
    del legacy["end_device_ids"]["application_ids"]
    del legacy["uplink_message"]["f_cnt"]
    old = {"schema": ARCHIVE_SCHEMA, "record_count": 1, "records": [legacy],
           "records_sha256": hashlib.sha256(canonical_bytes([legacy])).hexdigest()}
    old_report = build_report(canonical_bytes(old), "stratolink-1", "old-v1.json")
    assert old_report["normalization_complete"] and old_report["first_f_cnt"] == 0
    assert old_report["records"][0]["raw_record"] == legacy

    invalid_envelopes = []
    for key, value in (("f_cnt", True), ("f_cnt", -1), ("frm_payload", None)):
        row = deepcopy(good)
        row["uplink_message"][key] = value
        invalid_envelopes.append(row)
    for change in ("time", "address", "application", "credential"):
        row = deepcopy(good)
        if change == "time": row["received_at"] = "invalid"
        elif change == "address": row["end_device_ids"]["dev_addr"] = "bad"
        elif change == "application": row["end_device_ids"]["application_ids"]["application_id"] = "wrong-app"
        else: row["uplink_message"]["api_key"] = "PRIVATE_SENTINEL"
        invalid_envelopes.append(row)
    for row in invalid_envelopes:
        try:
            build_archive([row], "stratolink-1", "2026-08-31T05:00:00Z", 1000)
        except ValueError as error:
            assert "PRIVATE_SENTINEL" not in str(error)
        else:
            raise AssertionError("unsafe raw transport envelope was archived")

    with tempfile.TemporaryDirectory(prefix="ttn-forensic-cli-") as directory:
        raw = Path(directory) / "raw.json"
        output = Path(directory) / "report.json"
        # A real online CLI capture succeeds despite semantic errors; only the
        # external transport and credential source are replaced for this test.
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["archive", "--after", "2026-08-31T05:00:00Z", "--output", str(raw)]), \
                patch.object(archive_tool, "load_values", return_value={"TTN_NA_API_KEY": "PRIVATE_SENTINEL"}), \
                patch.object(archive_tool, "fetch_storage", return_value=rows), \
                redirect_stdout(stdout):
            archive_tool.main()
        assert json.loads(raw.read_text())["records"] == rows
        assert "PRIVATE_SENTINEL" not in raw.read_text() + stdout.getvalue()
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["archive", "--input", str(raw), "--output", str(output)]), \
                patch.object(archive_tool, "load_values", side_effect=AssertionError("offline loaded credentials")), \
                patch.object(archive_tool, "fetch_storage", side_effect=AssertionError("offline made request")), \
                redirect_stdout(stdout):
            try:
                archive_tool.main()
            except SystemExit as error:
                assert error.code == 1
            else:
                raise AssertionError("incomplete report returned success exit status")
        saved = json.loads(output.read_text())
        assert saved["record_count"] == 8 and not saved["normalization_complete"]
        assert json.loads(stdout.getvalue())["normalization_complete"] is False


def main() -> None:
    forensic_cases()
    # Break caught: known Board1 regional devices must not be queried from the
    # US application or archived with false source provenance. Exercise the CLI
    # with only the external Storage transport and key loader replaced.
    regional_targets = (
        ("stratolink-1-eu", "eu1.cloud.thethings.network", "eu-stratolink", "EU_TEST_KEY"),
        ("stratolink-1-as", "eu1.cloud.thethings.network", "as-stratolink", "AS_TEST_KEY"),
        ("stratolink-1-au", "nam1.cloud.thethings.network", "stratolink", "NA_TEST_KEY"),
        ("stratolink-1", "nam1.cloud.thethings.network", "stratolink", "NA_TEST_KEY"),
        ("stratolink-2", "nam1.cloud.thethings.network", "stratolink", "NA_TEST_KEY"),
    )
    keys = {"TTN_NA_API_KEY": "NA_TEST_KEY", "TTN_EU_API_KEY": "EU_TEST_KEY",
            "TTN_AS_API_KEY": "AS_TEST_KEY"}
    with tempfile.TemporaryDirectory(prefix="ttn-archive-regions-") as directory:
        for device, host, app, key in regional_targets:
            row = sample(device=device)
            row["end_device_ids"]["application_ids"]["application_id"] = app
            output = Path(directory) / f"{device}.json"
            stdout = io.StringIO()
            with patch.object(sys, "argv", ["archive", "--device", device,
                    "--after", "2026-08-31T05:00:00Z", "--output", str(output)]), \
                    patch.object(archive_tool, "load_values", return_value=keys), \
                    patch.object(archive_tool, "fetch_storage", return_value=[row]) as fetch, \
                    redirect_stdout(stdout):
                archive_tool.main()
            fetch.assert_called_once_with(host, app, key, "2026-08-31T05:00:00Z", 1000)
            saved = json.loads(output.read_text())
            assert saved["source"]["cluster"] == host
            assert saved["source"]["application_id"] == app
            assert saved["records"] == [row]
            for secret in keys.values():
                assert secret not in output.read_text() and secret not in stdout.getvalue()
            # Offline replay must neither load local credentials nor contact TTN.
            with patch.object(sys, "argv", ["archive", "--device", device,
                    "--input", str(output), "--output", str(output.with_suffix(".offline.json"))]), \
                    patch.object(archive_tool, "load_values", side_effect=AssertionError("offline loaded keys")), \
                    patch.object(archive_tool, "fetch_storage", side_effect=AssertionError("offline used network")), \
                    redirect_stdout(io.StringIO()):
                archive_tool.main()

        # A missing regional key must not silently fall back to the NA key.
        missing_output = Path(directory) / "missing-eu-key.json"
        with patch.object(sys, "argv", ["archive", "--device", "stratolink-1-eu",
                "--after", "2026-08-31T05:00:00Z", "--output", str(missing_output)]), \
                patch.object(archive_tool, "load_values", return_value={"TTN_NA_API_KEY": "NA_TEST_KEY"}), \
                patch.object(archive_tool, "fetch_storage") as fetch:
            try:
                archive_tool.main()
            except SystemExit as error:
                assert str(error) == "missing local TTN_EU_API_KEY"
            else:
                raise AssertionError("missing regional credential was accepted")
            fetch.assert_not_called()
        assert not missing_output.exists()

    fixed = "2026-08-31T06:00:00.000+00:00"
    row = sample()
    archive = build_archive([row], "stratolink-1", "2026-08-31T05:00:00Z", 10,
                            created_utc=fixed)
    assert archive["schema"] == ARCHIVE_SCHEMA
    assert archive["records"][0]["uplink_message"]["frm_payload"] == row["uplink_message"]["frm_payload"]
    assert archive["records_sha256"] == hashlib.sha256(
        canonical_bytes(archive["records"])
    ).hexdigest()

    report = build_report(canonical_bytes(archive), "stratolink-1", "archive.json",
                          created_utc=fixed)
    normalized = report["records"][0]
    assert normalized["f_cnt"] == 8
    assert normalized["session_key_id"] == "opaque-session-id"
    assert normalized["settings"]["frequency"] == "904100000"
    assert normalized["rx_metadata"][0]["rssi"] == -55
    assert normalized["telemetry"]["telemetry_version"] == 3
    assert normalized["telemetry"]["server_proof_count_mod8"] == 1
    assert normalized["telemetry"]["boot_count"] == 8
    assert normalized["event_received_at"] == row["uplink_message"]["received_at"]
    assert normalized["storage_received_at"] == row["received_at"]

    truncated = dict(archive)
    truncated["records"] = []
    try:
        build_report(canonical_bytes(truncated), "stratolink-1", "truncated.json",
                     created_utc=fixed)
    except ValueError as error:
        assert "count mismatch" in str(error)
    else:
        raise AssertionError("truncated archive was accepted")

    tampered = json.loads(json.dumps(archive))
    tampered["records"][0]["uplink_message"]["f_cnt"] = 9
    try:
        build_report(canonical_bytes(tampered), "stratolink-1", "tampered.json",
                     created_utc=fixed)
    except ValueError as error:
        assert "digest mismatch" in str(error)
    else:
        raise AssertionError("digest-tampered archive was accepted")

    wrapper = {
        "collector_utc": "2026-08-31T06:08:00.250Z",
        "topic": "v3/stratolink@ttn/devices/stratolink-1/up",
        "body": json.dumps(row, separators=(",", ":")),
    }
    wrapped = build_report(canonical_bytes(wrapper), "stratolink-1", "mqtt.jsonl",
                           created_utc=fixed)
    assert wrapped["records"][0]["capture"]["collector_utc"].endswith("Z")
    assert build_report(
        canonical_bytes(row), "stratolink-1", "webhook.json", created_utc=fixed
    )["record_count"] == 1

    first_manual = sample(8)
    second_manual = sample(9)
    del first_manual["uplink_message"]["session_key_id"]
    del second_manual["uplink_message"]["session_key_id"]
    manual = build_report(
        canonical_bytes([first_manual, second_manual]),
        "stratolink-1", "manual.json", created_utc=fixed,
    )
    assert manual["interval_seconds"] == [60.0]
    assert manual["counter_transitions"][0]["delta"] == 1
    assert manual["session_observations"] == [{
        "session_key_id": None,
        "dev_addr": "260CACD0",
        "identity_basis": "dev_addr_fallback",
        "first_f_cnt": 8,
        "last_f_cnt": 9,
        "record_count": 2,
    }]

    # Auxiliary packets contain no primary boot counter. They must not invent
    # transitions to/from None or conceal a real boot change across the gap.
    auxiliary = sample(9)
    auxiliary["uplink_message"]["f_port"] = 11
    auxiliary["uplink_message"]["frm_payload"] = base64.b64encode(bytes(17)).decode("ascii")
    mixed_rows = [sample(8), auxiliary, sample(10)]
    mixed_report = build_report(canonical_bytes(mixed_rows), "stratolink-1", "mixed.json")
    assert mixed_report["boot_transitions"] == [], "auxiliary packets are not reboots"
    rebooted = bytearray(base64.b64decode(mixed_rows[-1]["uplink_message"]["frm_payload"]))
    rebooted[35] = 9
    mixed_rows[-1]["uplink_message"]["frm_payload"] = base64.b64encode(rebooted).decode("ascii")
    mixed_report = build_report(canonical_bytes(mixed_rows), "stratolink-1", "mixed-reset.json")
    assert mixed_report["boot_transitions"] == [{"at_f_cnt": 10, "from": 8, "to": 9}]

    ndjson = canonical_bytes(first_manual) + canonical_bytes(second_manual)
    assert build_report(
        ndjson, "stratolink-1", "mqtt.ndjson", created_utc=fixed
    )["record_count"] == 2

    sse = b"event: message\n" + b"data: " + canonical_bytes({"result": row}) + b"\n"
    assert build_report(sse, "stratolink-1", "storage.sse",
                        created_utc=fixed)["record_count"] == 1

    for secret_shape in ({"api_key": "secret"}, {"apiKey": "secret"}):
        try:
            assert_no_credentials(secret_shape)
        except ValueError:
            pass
        else:
            raise AssertionError("credential-bearing input was accepted")

    other_only = canonical_bytes([sample(device="some-other-device")])
    try:
        build_report(other_only, "stratolink-1", "other.json", created_utc=fixed)
    except ValueError as error:
        assert "no valid" in str(error)
    else:
        raise AssertionError("other-device-only input was accepted")

    duplicate = canonical_bytes([row, row])
    try:
        build_report(duplicate, "stratolink-1", "duplicate.json", created_utc=fixed)
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate delivery identity was accepted")

    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "evidence.json"
        write_create_once(path, b"one\n")
        try:
            write_create_once(path, b"two\n")
        except FileExistsError:
            pass
        else:
            raise AssertionError("create-once collision was overwritten")

    print("PASS: raw archive and fully offline normalization are fail-closed")


if __name__ == "__main__":
    main()
