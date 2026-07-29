#!/usr/bin/env python3
"""Validate privacy-safe Meshtastic RF stimulus evidence byte-for-byte."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from decode_flight_state import atomic_json
from evidence_provenance import record as provenance_record
from evidence_provenance import verify_all as verify_provenance


PROFILES = ("check", "relay", "cancel", "hop-zero", "directed")
MAX_VERIFIED_RADIO_AGE_SECONDS = 30.0
MAX_VERIFIED_FUTURE_SKEW_SECONDS = 5.0


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSONL row at line {number}")
        rows.append(value)
    if not rows:
        raise ValueError("Meshtastic evidence log is empty")
    return rows


def validate(
    rows: list[dict],
    manifest: dict,
    *,
    profile: str,
    payload_bytes: int,
    repeats: int,
    interval_seconds: float,
    hop_limit: int,
    observe_seconds: float,
    min_echoes: int,
) -> dict:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    starts = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("event") == "meshtastic_hil_stimulus_start"
    ]
    actions = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("event") in (
            "meshtastic_hil_stimulus_transmitted",
            "meshtastic_hil_stimulus_check_only",
        )
    ]
    ends = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("event") == "meshtastic_hil_stimulus_end"
    ]
    metadata = [
        row for row in rows if row.get("event") == "meshtastic_packet_metadata"
    ]
    echoes = [
        row for row in metadata
        if row.get("classification") == "local_origin_rf_echo"
    ]
    require(len(starts) == 1, "expected exactly one stimulus start event")
    require(len(actions) == 1, "expected exactly one stimulus action event")
    require(len(ends) == 1, "expected exactly one stimulus end event")
    if len(starts) == len(actions) == len(ends) == 1:
        require(
            starts[0][0] < actions[0][0] < ends[0][0],
            "stimulus events are out of order",
        )
        start = starts[0][1]
        action = actions[0][1]
        end = ends[0][1]
    else:
        start, action, end = {}, {}, {}

    transmitted = profile != "check"
    directed = profile == "directed"
    require(start.get("region") == "US", "peer region was not US")
    require(
        start.get("modem_preset") == "LONG_FAST",
        "peer modem preset was not LONG_FAST",
    )
    require(start.get("use_preset") is True, "peer preset mode was disabled")
    require(start.get("tx_enabled") is True, "peer transmitter was disabled")
    require(start.get("config_ok") is True, "peer configuration did not pass")
    require(
        start.get("transmit_requested") is transmitted,
        "transmit mode does not match the validation profile",
    )
    require(
        action.get("event")
        == (
            "meshtastic_hil_stimulus_transmitted"
            if transmitted
            else "meshtastic_hil_stimulus_check_only"
        ),
        "stimulus action does not match the validation profile",
    )
    require(action.get("application") == "PRIVATE_APP", "wrong application port")
    require(action.get("channel_index") == 0, "wrong channel index")
    require(action.get("payload_bytes") == payload_bytes, "wrong payload length")
    require(
        action.get("repeats_same_packet_id") == repeats,
        "wrong same-ID repeat count",
    )
    require(
        action.get("interval_seconds") == interval_seconds,
        "wrong repeat interval",
    )
    require(action.get("hop_limit") == hop_limit, "wrong initial hop limit")
    require(
        action.get("directed_next_hop_nonzero") is directed,
        "directed-next-hop mode does not match profile",
    )
    require(action.get("want_ack") is False, "stimulus unexpectedly requested ACK")
    require(end.get("completed") is True, "stimulus did not complete")
    require(end.get("packet_count") == len(metadata), "packet count mismatch")
    require(
        end.get("local_origin_rf_echo_count") == len(echoes),
        "local-origin echo count mismatch",
    )
    require(len(echoes) >= min_echoes, "too few verified local-origin RF echoes")

    if profile == "relay":
        require(hop_limit > 0, "relay profile requires a positive hop limit")
        require(not directed, "relay profile cannot be directed")
        require(min_echoes >= 1, "relay profile must require at least one echo")
        for index, echo in enumerate(echoes):
            prefix = f"echo[{index}]"
            require(echo.get("portnum") == "PRIVATE_APP",
                    f"{prefix} has wrong application port")
            require(echo.get("payload_bytes") == payload_bytes,
                    f"{prefix} has wrong payload length")
            require(echo.get("channel_index") == 0,
                    f"{prefix} has wrong channel")
            require(isinstance(echo.get("rx_rssi_dbm"), (int, float)),
                    f"{prefix} lacks RSSI")
            require(isinstance(echo.get("rx_snr_db"), (int, float)),
                    f"{prefix} lacks SNR")
            radio_age = echo.get("radio_age_seconds")
            require(isinstance(radio_age, (int, float)),
                    f"{prefix} lacks receive-age evidence")
            if isinstance(radio_age, (int, float)):
                require(
                    -MAX_VERIFIED_FUTURE_SKEW_SECONDS
                    <= radio_age <= MAX_VERIFIED_RADIO_AGE_SECONDS,
                    f"{prefix} is cached or has implausible clock skew",
                )
            require(echo.get("hop_start") == hop_limit,
                    f"{prefix} has wrong hop_start")
            require(echo.get("hop_limit") == hop_limit - 1,
                    f"{prefix} was not decremented exactly once")
            require(echo.get("next_hop") == 0,
                    f"{prefix} retained next_hop")
            require(echo.get("relay_node") == 0,
                    f"{prefix} retained relay_node")
            require(echo.get("via_mqtt") is False,
                    f"{prefix} arrived via MQTT")
    elif profile == "cancel":
        require(hop_limit > 0, "cancel profile requires a positive hop limit")
        require(not directed, "cancel profile cannot be directed")
        require(repeats >= 2, "cancel profile requires exact-ID repetition")
        require(
            interval_seconds == 0.1,
            "cancel profile requires the pinned 0.1-second repeat interval",
        )
        require(min_echoes == 0, "cancel profile cannot require RF echoes")
        require(
            len(echoes) == 0,
            "cancel profile unexpectedly produced a forwarded RF echo",
        )
    elif profile == "hop-zero":
        require(hop_limit == 0, "hop-zero profile requires hop limit zero")
        require(not directed, "hop-zero profile cannot be directed")
    elif profile == "directed":
        require(hop_limit > 0, "directed profile requires a positive hop limit")
    elif profile == "check":
        require(min_echoes == 0, "check profile cannot require RF echoes")

    params = manifest.get("parameters", {})
    counts = manifest.get("counts", {})
    require(manifest.get("passed") is True, "stimulus manifest did not pass")
    require(manifest.get("completed") is True, "manifest says incomplete")
    require(manifest.get("config_ok") is True, "manifest configuration failed")
    require(manifest.get("transmitted") is transmitted,
            "manifest transmit mode mismatch")
    require(params.get("payload_bytes") == payload_bytes,
            "manifest payload length mismatch")
    require(params.get("repeats") == repeats,
            "manifest repeat count mismatch")
    require(params.get("interval_seconds") == interval_seconds,
            "manifest interval mismatch")
    require(params.get("hop_limit") == hop_limit,
            "manifest hop limit mismatch")
    require(params.get("directed_next_hop_nonzero") is directed,
            "manifest directed mode mismatch")
    require(params.get("observe_seconds") == observe_seconds,
            "manifest observation interval mismatch")
    require(counts.get("packet_count") == len(metadata),
            "manifest packet count mismatch")
    require(counts.get("local_origin_rf_echo_count") == len(echoes),
            "manifest echo count mismatch")

    return {
        "profile": profile,
        "passed": not failures,
        "failures": failures,
        "observed": {
            "metadata_events": len(metadata),
            "verified_local_origin_rf_echoes": len(echoes),
        },
        "expected": {
            "payload_bytes": payload_bytes,
            "repeats": repeats,
            "interval_seconds": interval_seconds,
            "hop_limit": hop_limit,
            "directed_next_hop_nonzero": directed,
            "observe_seconds": observe_seconds,
            "minimum_echoes": min_echoes,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--payload-bytes", type=int, default=180)
    parser.add_argument("--repeats", type=int, required=True)
    parser.add_argument("--interval-seconds", type=float, default=0.8)
    parser.add_argument("--hop-limit", type=int, required=True)
    parser.add_argument("--observe-seconds", type=float, required=True)
    parser.add_argument("--min-echoes", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite Meshtastic validation: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        verify_provenance(manifest.get("provenance"))
    except ValueError as error:
        raise SystemExit(f"stimulus provenance failed: {error}") from error
    if (
        manifest.get("provenance", {}).get("evidence_log")
        != provenance_record(args.log)
    ):
        raise SystemExit(
            "stimulus manifest does not bind the requested evidence log"
        )
    result = validate(
        load_rows(args.log),
        manifest,
        profile=args.profile,
        payload_bytes=args.payload_bytes,
        repeats=args.repeats,
        interval_seconds=args.interval_seconds,
        hop_limit=args.hop_limit,
        observe_seconds=args.observe_seconds,
        min_echoes=args.min_echoes,
    )
    result["provenance"] = {
        "stimulus_log": provenance_record(args.log),
        "stimulus_manifest": provenance_record(args.manifest),
        "validator": provenance_record(Path(__file__)),
    }
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
