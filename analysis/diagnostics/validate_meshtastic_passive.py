#!/usr/bin/env python3
"""Validate and bind privacy-safe passive Meshtastic RF evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from decode_flight_state import atomic_json
from evidence_provenance import record as provenance_record
from meshtastic_passive_monitor import (
    MAX_FUTURE_RADIO_SKEW_SECONDS,
    MAX_LIVE_RADIO_AGE_SECONDS,
)


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSONL row at line {number}")
        rows.append(value)
    if not rows:
        raise ValueError("passive Meshtastic evidence is empty")
    return rows


def validate(
    rows: list[dict], *, minimum_live_rf: int, minimum_elapsed_seconds: float
) -> dict:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    starts = [
        (index, row) for index, row in enumerate(rows)
        if row.get("event") == "meshtastic_passive_monitor_start"
    ]
    ends = [
        (index, row) for index, row in enumerate(rows)
        if row.get("event") == "meshtastic_passive_monitor_end"
    ]
    packets = [
        row for row in rows if row.get("event") == "meshtastic_packet_metadata"
    ]
    live = [
        row for row in packets
        if row.get("classification") in ("live_rf", "local_origin_rf_echo")
    ]
    echoes = [
        row for row in live
        if row.get("classification") == "local_origin_rf_echo"
    ]
    cached = [
        row for row in packets if row.get("classification") == "cached_history"
    ]
    live_sources = {
        row["source_opaque"] for row in live if row.get("source_opaque")
    }

    require(len(starts) == 1, "expected exactly one passive-monitor start")
    require(len(ends) == 1, "expected exactly one passive-monitor end")
    if len(starts) == len(ends) == 1:
        require(starts[0][0] < ends[0][0], "monitor end preceded its start")
        start = starts[0][1]
        end = ends[0][1]
    else:
        start, end = {}, {}

    require(start.get("region") == "US", "peer region was not US")
    require(
        start.get("modem_preset") == "LONG_FAST",
        "peer modem preset was not LONG_FAST",
    )
    require(start.get("use_preset") is True, "peer preset mode was disabled")
    require(
        start.get("live_radio_age_window_seconds")
        == [-MAX_FUTURE_RADIO_SKEW_SECONDS, MAX_LIVE_RADIO_AGE_SECONDS],
        "monitor did not record the pinned live-RF age window",
    )
    elapsed = end.get("elapsed_seconds")
    require(
        isinstance(elapsed, (int, float))
        and elapsed >= minimum_elapsed_seconds,
        "passive RF observation was too short or incomplete",
    )
    require(end.get("packet_count") == len(packets), "packet count mismatch")
    require(
        end.get("live_rf_packet_count") == len(live),
        "live RF count mismatch",
    )
    require(
        end.get("local_origin_rf_echo_count") == len(echoes),
        "local-origin echo count mismatch",
    )
    require(
        end.get("live_rf_opaque_source_count") == len(live_sources),
        "opaque live-source count mismatch",
    )
    require(len(live) >= minimum_live_rf, "too few verified live RF packets")

    for index, row in enumerate(live):
        prefix = f"live[{index}]"
        require(
            isinstance(row.get("rx_rssi_dbm"), (int, float)),
            f"{prefix} lacks RSSI",
        )
        require(
            isinstance(row.get("rx_snr_db"), (int, float)),
            f"{prefix} lacks SNR",
        )
        require(row.get("via_mqtt") is False, f"{prefix} arrived via MQTT")
        age = row.get("radio_age_seconds")
        require(
            isinstance(age, (int, float))
            and -MAX_FUTURE_RADIO_SKEW_SECONDS
            <= age <= MAX_LIVE_RADIO_AGE_SECONDS,
            f"{prefix} is cached or has implausible receive time",
        )

    return {
        "passed": not failures,
        "failures": failures,
        "scope": (
            "proves current nearby Meshtastic LongFast RF stimulus only; "
            "does not prove StratoLink receive, relay, CAD, or PHY restore"
        ),
        "observed": {
            "elapsed_seconds": elapsed,
            "metadata_packets": len(packets),
            "verified_live_rf_packets": len(live),
            "verified_local_origin_echoes": len(echoes),
            "verified_opaque_sources": len(live_sources),
            "cached_history_packets_excluded": len(cached),
        },
        "expected": {
            "minimum_elapsed_seconds": minimum_elapsed_seconds,
            "minimum_live_rf_packets": minimum_live_rf,
            "region": "US",
            "modem_preset": "LONG_FAST",
            "radio_age_seconds": [
                -MAX_FUTURE_RADIO_SKEW_SECONDS,
                MAX_LIVE_RADIO_AGE_SECONDS,
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--minimum-live-rf", type=int, default=1)
    parser.add_argument("--minimum-elapsed-seconds", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.minimum_live_rf <= 1000000:
        parser.error("--minimum-live-rf must be between 0 and 1000000")
    if not 5 <= args.minimum_elapsed_seconds <= 3600:
        parser.error("--minimum-elapsed-seconds must be between 5 and 3600")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite passive RF validation: {args.output}")
    try:
        result = validate(
            load_rows(args.log),
            minimum_live_rf=args.minimum_live_rf,
            minimum_elapsed_seconds=args.minimum_elapsed_seconds,
        )
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    result["provenance"] = {
        "passive_log": provenance_record(args.log),
        "monitor": provenance_record(
            Path(__file__).with_name("meshtastic_passive_monitor.py")
        ),
        "validator": provenance_record(Path(__file__)),
    }
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
