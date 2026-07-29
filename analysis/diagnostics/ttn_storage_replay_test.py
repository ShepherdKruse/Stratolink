#!/usr/bin/env python3
"""Host-only tests for fail-closed TTN Storage reconciliation."""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

import ttn_storage_replay as replay
from ttn_storage_replay import (
    parse_storage_stream,
    require_safe_webhook_url,
    select_device_records,
    validate_record,
)


def record(
    *,
    device_id: str = "stratolink-2",
    dev_addr: str = "260CACD0",
    received_at: str = "2026-07-25T00:51:52.030951598Z",
    frame_counter: int = 5,
    f_port: int = 1,
    payload: bytes = bytes(35),
) -> dict:
    return {
        "end_device_ids": {
            "device_id": device_id,
            "dev_addr": dev_addr,
        },
        "received_at": received_at,
        "uplink_message": {
            "f_cnt": frame_counter,
            "f_port": f_port,
            "frm_payload": base64.b64encode(payload).decode(),
        },
    }


class StorageReplayTests(unittest.TestCase):
    def test_sse_and_ndjson_are_accepted(self) -> None:
        body = (
            b"event: message\n"
            b'data: {"result":{"end_device_ids":{"device_id":"a"}}}\n\n'
            b'{"result":{"end_device_ids":{"device_id":"b"}}}\n'
        )
        rows = parse_storage_stream(body)
        self.assertEqual(
            [row["end_device_ids"]["device_id"] for row in rows],
            ["a", "b"],
        )

    def test_current_manual_session_shape_is_valid(self) -> None:
        self.assertEqual(
            validate_record(record()),
            (
                "stratolink-2",
                "2026-07-25T00:51:52.030951598Z",
                5,
                1,
            ),
        )
        self.assertEqual(validate_record(record(payload=bytes(40)))[3], 1)

        first = record(frame_counter=0)
        del first["uplink_message"]["f_cnt"]
        self.assertEqual(validate_record(first)[2], 0)

    def test_selection_filters_other_devices_and_orders_time(self) -> None:
        later = record(
            received_at="2026-07-25T01:00:00Z",
            frame_counter=6,
        )
        earlier = record(
            received_at="2026-07-25T00:00:00Z",
            frame_counter=4,
        )
        other = record(device_id="stratolink-3")
        selected, skipped = select_device_records(
            [later, other, earlier],
            "stratolink-2",
        )
        self.assertEqual(skipped, 1)
        self.assertEqual(
            [row["uplink_message"]["f_cnt"] for row in selected],
            [4, 6],
        )

    def test_target_record_errors_fail_closed(self) -> None:
        invalid = [
            record(dev_addr="bad"),
            record(received_at="not-a-time"),
            record(received_at="2026-07-25T00:00:00"),
            record(frame_counter=-1),
            record(f_port=10),
            record(payload=b"short"),
            record(f_port=11, payload=bytes(16)),
            record(f_port=12, payload=bytes(54)),
        ]
        for row in invalid:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    validate_record(row)

        explicit_null = record()
        explicit_null["uplink_message"]["f_cnt"] = None
        with self.assertRaises(ValueError):
            validate_record(explicit_null)

    def test_webhook_url_restrictions(self) -> None:
        self.assertEqual(
            require_safe_webhook_url(
                "https://stratolink.org/api/ttn-webhook"
            ),
            "https://stratolink.org/api/ttn-webhook",
        )
        self.assertEqual(
            require_safe_webhook_url(
                "http://127.0.0.1:3000/api/ttn-webhook/"
            ),
            "http://127.0.0.1:3000/api/ttn-webhook",
        )
        for url in (
            "http://stratolink.org/api/ttn-webhook",
            "file:///tmp/webhook",
            "https://stratolink.org/api/ttn-webhook?unsafe=1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    require_safe_webhook_url(url)

    def test_hardened_auth_probe_requires_401(self) -> None:
        with patch.object(replay, "request_bytes", return_value=(401, b"{}")):
            replay.prove_hardened_auth(
                "https://stratolink.org/api/ttn-webhook"
            )
        with patch.object(replay, "request_bytes", return_value=(400, b"{}")):
            with self.assertRaises(SystemExit):
                replay.prove_hardened_auth(
                    "https://stratolink.org/api/ttn-webhook"
                )

    def test_replay_counts_success_and_duplicate(self) -> None:
        responses = [
            (200, json.dumps({"success": True}).encode()),
            (
                200,
                json.dumps({"success": True, "duplicate": True}).encode(),
            ),
        ]
        records = [
            record(frame_counter=5),
            record(
                received_at="2026-07-25T01:00:00Z",
                frame_counter=6,
            ),
        ]
        with patch.object(replay, "request_bytes", side_effect=responses):
            self.assertEqual(
                replay.replay_records(
                    records,
                    "https://stratolink.org/api/ttn-webhook",
                    "x" * 32,
                ),
                (1, 1),
            )

        with patch.object(
            replay,
            "request_bytes",
            return_value=(500, b'{"error":"redacted"}'),
        ):
            with self.assertRaises(SystemExit):
                replay.replay_records(
                    records,
                    "https://stratolink.org/api/ttn-webhook",
                    "x" * 32,
                )


if __name__ == "__main__":
    unittest.main()
