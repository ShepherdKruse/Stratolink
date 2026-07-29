#!/usr/bin/env python3
"""Compare create-once flight-state captures across one controlled reset."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from decode_flight_state import atomic_json
from evidence_provenance import record as provenance_record
from flash_flight_candidate import verify_file_record
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


SCENARIOS = ("session-reset", "downlink-reset", "b2b-reset")


def provenance_inputs(
    before: Path,
    before_manifest: Path,
    reset_manifest: Path,
    after: Path,
    after_manifest: Path,
) -> dict:
    return {
        "before": provenance_record(before),
        "before_manifest": provenance_record(before_manifest),
        "reset_manifest": provenance_record(reset_manifest),
        "after": provenance_record(after),
        "after_manifest": provenance_record(after_manifest),
        "comparator": provenance_record(Path(__file__)),
    }


def load_capture(
    decoded_path: Path,
    manifest_path: Path,
    expected_profile: str = "joined-us",
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("passed") is not True:
        raise SystemExit(f"state capture is not passing: {manifest_path}")
    record = manifest.get("decoded_redacted_state")
    if not isinstance(record, dict):
        raise SystemExit(f"decoded-state evidence is missing: {manifest_path}")
    recorded_path = verify_file_record(record)
    if recorded_path.resolve() != decoded_path.resolve():
        raise SystemExit(
            f"manifest does not identify requested decoded state: {decoded_path}"
        )
    value = json.loads(decoded_path.read_text(encoding="utf-8"))
    if (
        value.get("manifest_elf_sha256") != EXPECTED_ELF_SHA256
        or value.get("profile_gate", {}).get("passed") is not True
        or value.get("profile_gate", {}).get("profile") != expected_profile
    ):
        raise SystemExit(
            "decoded state is not a passing "
            f"{expected_profile} candidate: {decoded_path}"
        )
    return value


def parse_created_utc(value: object, path: Path) -> datetime:
    if not isinstance(value, str):
        raise SystemExit(f"missing evidence creation time: {path}")
    try:
        created = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SystemExit(f"invalid evidence creation time: {path}") from error
    if created.tzinfo is None:
        raise SystemExit(f"evidence creation time is not timezone-aware: {path}")
    return created


def load_reset(
    reset_path: Path,
    before_manifest_path: Path,
    after_manifest_path: Path,
) -> dict:
    reset = json.loads(reset_path.read_text(encoding="utf-8"))
    before_manifest = json.loads(before_manifest_path.read_text(encoding="utf-8"))
    after_manifest = json.loads(after_manifest_path.read_text(encoding="utf-8"))
    if (
        reset.get("passed") is not True
        or reset.get("reset_issued") is not True
        or reset.get("target", {}).get("jlink_serial") != "802007563"
        or reset.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or reset.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit(f"exact-candidate reset evidence is not passing: {reset_path}")
    for side in ("ppk2_before", "ppk2_after"):
        ppk2 = reset.get("target", {}).get(side, {})
        if ppk2.get("source_mv") != 4660 or ppk2.get("max_reconnects") != 0:
            raise SystemExit(f"reset lacks healthy PPK2 evidence: {reset_path}")
    for group_name in ("gate_inputs", "reset_evidence"):
        records = reset.get(group_name)
        if not isinstance(records, dict) or not records:
            raise SystemExit(
                f"reset {group_name.replace('_', ' ')} are missing: {reset_path}"
            )
        for record in records.values():
            if not isinstance(record, dict):
                raise SystemExit(f"reset evidence record is malformed: {reset_path}")
            verify_file_record(record)
    before_created = parse_created_utc(
        before_manifest.get("created_utc"),
        before_manifest_path,
    )
    reset_created = parse_created_utc(reset.get("created_utc"), reset_path)
    after_created = parse_created_utc(
        after_manifest.get("created_utc"),
        after_manifest_path,
    )
    if not before_created < reset_created < after_created:
        raise SystemExit(
            "reset evidence is not temporally bracketed by the requested "
            "state captures"
        )
    return reset


def compare(
    before: dict,
    after: dict,
    scenario: str,
    expected_fcnt_up_advance: int,
) -> dict:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    bh, ah = before["health"], after["health"]
    bt, at = before["tamp"], after["tamp"]
    require(
        ah["boot"]["count"] == bh["boot"]["count"] + 1,
        "retained boot count did not advance exactly once",
    )
    require(
        at["boot"]["count"] == bt["boot"]["count"] + 1,
        "TAMP boot count did not advance exactly once",
    )
    require(
        ah["session"]["joined"] and bh["session"]["joined"],
        "joined session was not present on both sides of reset",
    )
    require(
        ah["session"]["region"] == bh["session"]["region"] == "US915",
        "RAM region changed across reset",
    )
    require(
        at["session"]["region"] == bt["session"]["region"] == "US915",
        "retained region changed across reset",
    )
    require(
        at["session"]["dev_addr"] == bt["session"]["dev_addr"],
        "DevAddr changed across reset (possible rejoin)",
    )
    require(
        at["session"]["network_key_present"]
        and at["session"]["application_key_present"]
        and bt["session"]["network_key_present"]
        and bt["session"]["application_key_present"],
        "retained session key presence was lost",
    )
    require(
        ah["session"]["next_fcnt_up"] == at["session"]["next_fcnt_up"]
        and bh["session"]["next_fcnt_up"] == bt["session"]["next_fcnt_up"],
        "RAM/TAMP FCntUp disagreement",
    )
    require(
        ah["session"]["next_fcnt_down"] == at["session"]["next_fcnt_down"]
        and bh["session"]["next_fcnt_down"] == bt["session"]["next_fcnt_down"],
        "RAM/TAMP FCntDown disagreement",
    )
    require(
        ah["session"]["next_fcnt_up"]
        == bh["session"]["next_fcnt_up"] + expected_fcnt_up_advance,
        "FCntUp did not advance by the controlled amount",
    )
    require(
        ah["session"]["next_fcnt_down"] == bh["session"]["next_fcnt_down"],
        "FCntDown changed during the reset-only interval",
    )
    require(
        ah["region_lease"]["known"] and at["region_lease"]["valid"],
        "restored region lease is invalid",
    )
    require(
        ah["region_lease"]["age_seconds"]
        == at["region_lease"]["age_seconds"],
        "restored RAM/TAMP lease ages disagree",
    )

    if scenario == "session-reset":
        require(
            expected_fcnt_up_advance >= 1,
            "session-reset must include at least one post-reset uplink",
        )
        require(
            ah["session"]["next_fcnt_up"] > bh["session"]["next_fcnt_up"],
            "post-reset uplink did not reserve a fresh FCntUp",
        )
    elif scenario == "downlink-reset":
        require(
            expected_fcnt_up_advance == 0,
            "downlink-reset must be captured before another uplink",
        )
        require(
            bh["command"]["command_count"] >= 1
            and bh["command"]["last_fport"] == 10,
            "pre-reset capture lacks an accepted fPort-10 command",
        )
        require(
            bh["downlink"]["frame_count"] >= 1
            and bh["downlink"]["irq_count"] >= 1
            and bh["downlink"]["last_window"] in (1, 2)
            and bh["downlink"]["last_reject"] == 0,
            "pre-reset capture lacks a successful RX1/RX2 downlink",
        )
        require(
            bh["session"]["next_fcnt_down"] >= 1,
            "pre-reset FCntDown was not consumed",
        )
        require(
            bh["command"]["sequence_persist_failures"] == 0,
            "pre-reset command sequence reservation failed",
        )
        require(
            bt["command_sequence"]["valid"]
            and bt["command_sequence"]["last_applied"]
            == bh["command"]["last_sequence"]
            and bt["command_sequence"].get("relay_enabled")
            == bh["command"].get("relay_enabled"),
            "pre-reset RAM/TAMP command state disagreement",
        )
        require(
            at["command_sequence"]["valid"]
            and at["command_sequence"]["last_applied"]
            == bt["command_sequence"]["last_applied"]
            and at["command_sequence"].get("relay_enabled")
            == bt["command_sequence"].get("relay_enabled"),
            "retained command state changed across reset",
        )
        require(
            ah["command"]["rx_count"] == 0
            and ah["command"]["command_count"] == 0
            and ah["downlink"]["frame_count"] == 0
            and ah["command"]["last_sequence"]
            == at["command_sequence"]["last_applied"]
            and ah["command"].get("ack_valid")
            and ah["command"].get("ack_sequence")
            == at["command_sequence"]["last_applied"]
            and ah["command"].get("relay_enabled")
            == at["command_sequence"].get("relay_enabled")
            and ah["command"]["sequence_persist_failures"] == 0,
            "volatile downlink diagnostics did not reset",
        )
    elif scenario == "b2b-reset":
        require(
            expected_fcnt_up_advance == 0,
            "b2b-reset must be captured before another uplink",
        )
        require(
            bt["b2b_origin_id"]["valid"] and at["b2b_origin_id"]["valid"],
            "retained B2B origin ID is invalid",
        )
        require(
            at["b2b_origin_id"]["next_id"] == bt["b2b_origin_id"]["next_id"],
            "retained B2B next ID changed across reset",
        )
        require(
            ah["b2b_queues"]["origin_id_ready"],
            "post-reset RAM did not restore the B2B origin ID",
        )
    else:
        raise ValueError(f"unknown scenario: {scenario}")

    return {
        "scenario": scenario,
        "expected_fcnt_up_advance": expected_fcnt_up_advance,
        "passed": not failures,
        "failures": failures,
        "observed": {
            "boot_count_before": bh["boot"]["count"],
            "boot_count_after": ah["boot"]["count"],
            "fcnt_up_before": bh["session"]["next_fcnt_up"],
            "fcnt_up_after": ah["session"]["next_fcnt_up"],
            "fcnt_down_before": bh["session"]["next_fcnt_down"],
            "fcnt_down_after": ah["session"]["next_fcnt_down"],
            "b2b_next_id_before": bt["b2b_origin_id"]["next_id"],
            "b2b_next_id_after": at["b2b_origin_id"]["next_id"],
            "command_sequence_before": bt["command_sequence"]["last_applied"],
            "command_sequence_after": at["command_sequence"]["last_applied"],
            "relay_enabled_before": bt["command_sequence"].get("relay_enabled"),
            "relay_enabled_after": at["command_sequence"].get("relay_enabled"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--before-manifest", type=Path, required=True)
    parser.add_argument("--reset-manifest", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--after-manifest", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--expect-fcnt-up-advance", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    expected = (
        args.expect_fcnt_up_advance
        if args.expect_fcnt_up_advance is not None
        else 1 if args.scenario == "session-reset" else 0
    )
    if expected < 0 or expected > 16:
        parser.error("--expect-fcnt-up-advance must be between 0 and 16")
    if args.output and args.output.exists():
        raise SystemExit(f"refusing to overwrite comparison evidence: {args.output}")

    before = load_capture(args.before, args.before_manifest)
    reset = load_reset(
        args.reset_manifest,
        args.before_manifest,
        args.after_manifest,
    )
    after = load_capture(args.after, args.after_manifest)
    result = compare(before, after, args.scenario, expected)
    result["reset"] = {
        "label": reset["label"],
        "created_utc": reset["created_utc"],
        "jlink_serial": reset["target"]["jlink_serial"],
    }
    result["provenance"] = provenance_inputs(
        args.before,
        args.before_manifest,
        args.reset_manifest,
        args.after,
        args.after_manifest,
    )
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
