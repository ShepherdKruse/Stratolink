#!/usr/bin/env python3
"""Verify dry-run-by-default and explicit TTN PING queue behavior."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import ttn_downlink_test


VALUES = {
    "TTN_APP_ID": "test-app",
    "TTN_APP_KEY": "redacted",
    "TTN_BASE_URL": "https://example.invalid",
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-downlink-queue-") as raw:
        root = Path(raw)
        dry_output = root / "dry.json"
        with (
            patch.object(ttn_downlink_test, "load_values", return_value=VALUES),
            patch.object(
                ttn_downlink_test,
                "request_json",
                return_value=(200, {"downlinks": []}),
            ) as request,
            patch.object(
                sys,
                "argv",
                [
                    "ttn_downlink_test.py",
                    "--seq",
                    "42",
                    "--output",
                    str(dry_output),
                ],
            ),
        ):
            ttn_downlink_test.main()
        assert request.call_count == 1
        dry = json.loads(dry_output.read_text(encoding="utf-8"))
        assert dry["event"] == "ping_queue_dry_run"
        assert dry["queue_http_status"] is None

        queue_output = root / "queued.json"
        with (
            patch.object(ttn_downlink_test, "load_values", return_value=VALUES),
            patch.object(
                ttn_downlink_test,
                "request_json",
                side_effect=[
                    (200, {"downlinks": []}),
                    (204, {}),
                ],
            ) as request,
            patch.object(
                sys,
                "argv",
                [
                    "ttn_downlink_test.py",
                    "--seq",
                    "43",
                    "--queue",
                    "--output",
                    str(queue_output),
                ],
            ),
        ):
            ttn_downlink_test.main()
        assert request.call_count == 2
        queued = json.loads(queue_output.read_text(encoding="utf-8"))
        assert queued["event"] == "ping_queued"
        assert queued["queue_http_status"] == 204
        assert queued["target_balloon_id"] == 2
        assert queued["application_payload_bytes"] == 4

        relay_output = root / "relay.json"
        with (
            patch.object(ttn_downlink_test, "load_values", return_value=VALUES),
            patch.object(
                ttn_downlink_test,
                "request_json",
                side_effect=[
                    (200, {"downlinks": []}),
                    (204, {}),
                ],
            ) as request,
            patch.object(
                sys,
                "argv",
                [
                    "ttn_downlink_test.py",
                    "--seq",
                    "44",
                    "--relay",
                    "off",
                    "--queue",
                    "--output",
                    str(relay_output),
                ],
            ),
        ):
            ttn_downlink_test.main()
        assert request.call_count == 2
        relay = json.loads(relay_output.read_text(encoding="utf-8"))
        assert relay["event"] == "relay_queued"
        assert relay["opcode"] == "RELAY"
        assert relay["relay_requested"] == "off"
        assert relay["application_payload_bytes"] == 5

        with (
            patch.object(ttn_downlink_test, "load_values", return_value=VALUES),
            patch.object(
                ttn_downlink_test,
                "request_json",
                return_value=(200, {"downlinks": [{"f_port": 10}]}),
            ),
            patch.object(
                sys,
                "argv",
                ["ttn_downlink_test.py", "--seq", "44", "--queue"],
            ),
        ):
            try:
                ttn_downlink_test.main()
            except SystemExit as error:
                assert "already has 1 queued" in str(error)
            else:
                raise AssertionError("queue mutation accepted a preexisting downlink")

        with (
            patch.object(ttn_downlink_test, "load_values", return_value=VALUES),
            patch.object(
                ttn_downlink_test,
                "request_json",
                return_value=(200, {"downlinks": []}),
            ),
            patch.object(
                sys,
                "argv",
                [
                    "ttn_downlink_test.py",
                    "--seq",
                    "45",
                    "--output",
                    str(dry_output),
                ],
            ),
        ):
            try:
                ttn_downlink_test.main()
            except SystemExit as error:
                assert "refusing to overwrite" in str(error)
            else:
                raise AssertionError("queue evidence was overwritten")

        with patch.object(
            sys,
            "argv",
            [
                "ttn_downlink_test.py",
                "--device",
                "stratolink-3",
                "--seq",
                "46",
                "--queue",
            ],
        ):
            try:
                ttn_downlink_test.main()
            except SystemExit as error:
                assert error.code == 2
            else:
                raise AssertionError("board-2 PING accepted a different TTN device")

    print("PASS: TTN PING/relay commands are dry-run by default and evidence is create-once")


if __name__ == "__main__":
    main()
