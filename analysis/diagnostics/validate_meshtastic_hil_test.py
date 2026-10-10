#!/usr/bin/env python3
"""Adversarial tests for Meshtastic stimulus evidence validation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

from evidence_provenance import record
from validate_meshtastic_hil import validate


ROOT = Path(__file__).resolve().parent
VALIDATOR = ROOT / "validate_meshtastic_hil.py"


def rows(hop_limit: int = 3, echoed_hop_limit: int = 2) -> list[dict]:
    return [
        {
            "event": "meshtastic_hil_stimulus_start",
            "region": "US",
            "modem_preset": "LONG_FAST",
            "use_preset": True,
            "tx_enabled": True,
            "transmit_requested": True,
            "observe_seconds": 180.0,
            "config_ok": True,
        },
        {
            "event": "meshtastic_hil_stimulus_transmitted",
            "application": "PRIVATE_APP",
            "channel_index": 0,
            "payload_bytes": 180,
            "repeats_same_packet_id": 10,
            "interval_seconds": 0.8,
            "hop_limit": hop_limit,
            "directed_next_hop_nonzero": False,
            "want_ack": False,
        },
        {
            "event": "meshtastic_packet_metadata",
            "classification": "local_origin_rf_echo",
            "portnum": "PRIVATE_APP",
            "payload_bytes": 180,
            "channel_index": 0,
            "rx_rssi_dbm": -91,
            "rx_snr_db": 4.5,
            "radio_age_seconds": 0.5,
            "hop_start": hop_limit,
            "hop_limit": echoed_hop_limit,
            "next_hop": 0,
            "relay_node": 0,
            "via_mqtt": False,
        },
        {
            "event": "meshtastic_hil_stimulus_end",
            "completed": True,
            "packet_count": 1,
            "live_rf_packet_count": 1,
            "local_origin_rf_echo_count": 1,
        },
    ]


def manifest(log: Path) -> dict:
    return {
        "passed": True,
        "completed": True,
        "config_ok": True,
        "transmitted": True,
        "parameters": {
            "payload_bytes": 180,
            "repeats": 10,
            "interval_seconds": 0.8,
            "hop_limit": 3,
            "directed_next_hop_nonzero": False,
            "observe_seconds": 180.0,
        },
        "counts": {
            "packet_count": 1,
            "live_rf_packet_count": 1,
            "local_origin_rf_echo_count": 1,
        },
        "provenance": {
            "evidence_log": record(log),
            "stimulus_tool": record(ROOT / "meshtastic_hil_stimulus.py"),
            "packet_sanitizer": record(ROOT / "meshtastic_passive_monitor.py"),
        },
    }


def main() -> None:
    good_rows = rows()
    with tempfile.TemporaryDirectory(prefix="stratolink-mesh-validate-") as raw:
        directory = Path(raw)
        log = directory / "stimulus.jsonl"
        manifest_path = directory / "manifest.json"
        output = directory / "validation.json"
        log.write_text(
            "".join(json.dumps(row) + "\n" for row in good_rows),
            encoding="utf-8",
        )
        value = manifest(log)
        manifest_path.write_text(json.dumps(value), encoding="utf-8")

        result = validate(
            good_rows,
            value,
            profile="relay",
            payload_bytes=180,
            repeats=10,
            interval_seconds=0.8,
            hop_limit=3,
            observe_seconds=180.0,
            min_echoes=1,
        )
        assert result["passed"], result

        wrong_hop = validate(
            rows(echoed_hop_limit=3),
            value,
            profile="relay",
            payload_bytes=180,
            repeats=10,
            interval_seconds=0.8,
            hop_limit=3,
            observe_seconds=180.0,
            min_echoes=1,
        )
        assert not wrong_hop["passed"]

        stale_rows = rows()
        stale_rows[2]["radio_age_seconds"] = 3600.0
        stale_echo = validate(
            stale_rows,
            value,
            profile="relay",
            payload_bytes=180,
            repeats=10,
            interval_seconds=0.8,
            hop_limit=3,
            observe_seconds=180.0,
            min_echoes=1,
        )
        assert not stale_echo["passed"]
        assert any("cached" in failure for failure in stale_echo["failures"])

        cancel_rows = rows()
        cancel_rows[1]["interval_seconds"] = 0.1
        cancel_rows.pop(2)
        cancel_rows[-1].update(
            {
                "packet_count": 0,
                "live_rf_packet_count": 0,
                "local_origin_rf_echo_count": 0,
            }
        )
        cancel_manifest = manifest(log)
        cancel_manifest["parameters"]["interval_seconds"] = 0.1
        cancel_manifest["counts"].update(
            {
                "packet_count": 0,
                "live_rf_packet_count": 0,
                "local_origin_rf_echo_count": 0,
            }
        )
        canceled = validate(
            cancel_rows,
            cancel_manifest,
            profile="cancel",
            payload_bytes=180,
            repeats=10,
            interval_seconds=0.1,
            hop_limit=3,
            observe_seconds=180.0,
            min_echoes=0,
        )
        assert canceled["passed"], canceled

        cancel_echo = rows()
        cancel_echo[1]["interval_seconds"] = 0.1
        leaked_cancel = validate(
            cancel_echo,
            cancel_manifest,
            profile="cancel",
            payload_bytes=180,
            repeats=10,
            interval_seconds=0.1,
            hop_limit=3,
            observe_seconds=180.0,
            min_echoes=0,
        )
        assert not leaked_cancel["passed"]
        assert any("forwarded RF echo" in value
                   for value in leaked_cancel["failures"])

        command = [
            sys.executable,
            str(VALIDATOR),
            "--log",
            str(log),
            "--manifest",
            str(manifest_path),
            "--profile",
            "relay",
            "--repeats",
            "10",
            "--hop-limit",
            "3",
            "--observe-seconds",
            "180",
            "--min-echoes",
            "1",
            "--output",
            str(output),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        assert json.loads(output.read_text())["passed"] is True

        collision = subprocess.run(command, text=True, capture_output=True)
        assert collision.returncode != 0
        assert "refusing to overwrite" in collision.stderr

        other_log = directory / "other.jsonl"
        other_log.write_text(log.read_text(), encoding="utf-8")
        unbound = subprocess.run(
            [
                *command[:2],
                "--log",
                str(other_log),
                *command[4:-2],
                "--output",
                str(directory / "unbound.json"),
            ],
            text=True,
            capture_output=True,
        )
        assert unbound.returncode != 0
        assert "does not bind" in unbound.stderr

    print("PASS: Meshtastic RF evidence validation rejects false relay proof")


if __name__ == "__main__":
    main()
