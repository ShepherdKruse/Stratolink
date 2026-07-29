#!/usr/bin/env python3
"""Prove the firmware-visible transition around one guarded HIL mutation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compare_flight_states import load_capture, parse_created_utc
from decode_flight_state import atomic_json
from evidence_provenance import record as provenance_record
from flash_flight_candidate import verify_file_record
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


SCENARIOS = ("authorize-us", "clear-region-lease")
PROFILES = {
    "authorize-us": ("cold-fail-closed", "authorized-us"),
    "clear-region-lease": ("joined-us", "cold-fail-closed"),
}


def load_action(
    path: Path,
    scenario: str,
    before: Path,
    before_manifest: Path,
    after_manifest: Path,
) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("passed") is not True
        or value.get("action_issued") is not True
        or value.get("action") != scenario
        or value.get("target", {}).get("jlink_serial") != "802007563"
        or value.get("candidate", {}).get("elf_sha256") != EXPECTED_ELF_SHA256
        or value.get("candidate", {}).get("bin_sha256") != EXPECTED_BIN_SHA256
    ):
        raise SystemExit(f"exact-candidate HIL action is not passing: {path}")
    expected_reset = scenario == "clear-region-lease"
    if value.get("reset_issued") is not expected_reset:
        raise SystemExit(f"HIL action reset semantics are incorrect: {path}")
    for side in ("ppk2_before", "ppk2_after"):
        ppk2 = value.get("target", {}).get(side, {})
        if ppk2.get("source_mv") != 4660 or ppk2.get("max_reconnects") != 0:
            raise SystemExit(f"HIL action lacks healthy PPK2 evidence: {path}")
    before_records = value.get("before_evidence", {})
    state_record = before_records.get("state")
    manifest_record = before_records.get("manifest")
    if not isinstance(state_record, dict) or not isinstance(manifest_record, dict):
        raise SystemExit(f"HIL action lacks before-state evidence: {path}")
    if verify_file_record(state_record).resolve() != before.resolve():
        raise SystemExit("HIL action does not identify the requested before state")
    if verify_file_record(manifest_record).resolve() != before_manifest.resolve():
        raise SystemExit("HIL action does not identify the requested before manifest")
    for group_name in ("gate_inputs", "action_evidence"):
        records = value.get(group_name)
        if not isinstance(records, dict) or not records:
            raise SystemExit(f"HIL action {group_name} are missing: {path}")
        for record in records.values():
            if not isinstance(record, dict):
                raise SystemExit(f"HIL action evidence is malformed: {path}")
            verify_file_record(record)
    before_value = json.loads(before_manifest.read_text(encoding="utf-8"))
    after_value = json.loads(after_manifest.read_text(encoding="utf-8"))
    before_created = parse_created_utc(
        before_value.get("created_utc"),
        before_manifest,
    )
    action_created = parse_created_utc(value.get("created_utc"), path)
    after_created = parse_created_utc(
        after_value.get("created_utc"),
        after_manifest,
    )
    if not before_created < action_created < after_created:
        raise SystemExit(
            "HIL action is not temporally bracketed by the requested states"
        )
    return value


def compare(before: dict, after: dict, scenario: str) -> dict:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    bh, ah = before["health"], after["health"]
    bt, at = before["tamp"], after["tamp"]
    require(
        bh["session"]["region_id"] == ah["session"]["region_id"] == 0,
        "RAM region was not US915 on both sides of the action",
    )
    if scenario == "authorize-us":
        require(
            ah["boot"]["count"] == bh["boot"]["count"],
            "authorize-US action unexpectedly reset the MCU",
        )
        require(
            at["boot"]["count"] == bt["boot"]["count"],
            "authorize-US action unexpectedly changed retained boot count",
        )
        require(
            not bh["region_lease"]["known"],
            "authorize-US pre-state was already authorized",
        )
        require(
            ah["region_lease"]["known"] and at["region_lease"]["valid"],
            "authorize-US action did not establish a valid lease",
        )
        require(
            ah["region_lease"].get("trusted_provenance") in (None, True),
            "authorize-US action did not establish trusted lease provenance",
        )
        require(
            ah["region_lease"]["age_seconds"]
            == at["region_lease"]["age_seconds"],
            "authorize-US RAM/TAMP lease ages disagree",
        )
    elif scenario == "clear-region-lease":
        require(
            ah["boot"]["count"] == bh["boot"]["count"] + 1,
            "lease cleanup did not reset the MCU exactly once",
        )
        require(
            at["boot"]["count"] == bt["boot"]["count"] + 1,
            "lease cleanup did not advance retained boot count exactly once",
        )
        require(
            bh["region_lease"]["known"] and bt["region_lease"]["valid"],
            "lease-cleanup pre-state was not authorized",
        )
        require(
            not ah["region_lease"]["known"],
            "lease cleanup left RAM region authorized",
        )
        require(
            ah["region_lease"].get("trusted_provenance") in (None, False),
            "lease cleanup left RAM lease provenance trusted",
        )
        require(
            not at["region_lease"]["valid"],
            "lease cleanup left a valid retained lease",
        )
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    return {
        "scenario": scenario,
        "passed": not failures,
        "failures": failures,
        "observed": {
            "boot_count_before": bh["boot"]["count"],
            "boot_count_after": ah["boot"]["count"],
            "region_known_before": bh["region_lease"]["known"],
            "region_known_after": ah["region_lease"]["known"],
            "retained_lease_valid_before": bt["region_lease"]["valid"],
            "retained_lease_valid_after": at["region_lease"]["valid"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--before-manifest", type=Path, required=True)
    parser.add_argument("--action-manifest", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--after-manifest", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise SystemExit(f"refusing to overwrite action comparison: {args.output}")

    before_profile, after_profile = PROFILES[args.scenario]
    before = load_capture(
        args.before,
        args.before_manifest,
        expected_profile=before_profile,
    )
    action = load_action(
        args.action_manifest,
        args.scenario,
        args.before,
        args.before_manifest,
        args.after_manifest,
    )
    after = load_capture(
        args.after,
        args.after_manifest,
        expected_profile=after_profile,
    )
    result = compare(before, after, args.scenario)
    result["action"] = {
        "label": action["label"],
        "created_utc": action["created_utc"],
        "jlink_serial": action["target"]["jlink_serial"],
    }
    result["provenance"] = {
        "before": provenance_record(args.before),
        "before_manifest": provenance_record(args.before_manifest),
        "action_manifest": provenance_record(args.action_manifest),
        "after": provenance_record(args.after),
        "after_manifest": provenance_record(args.after_manifest),
        "comparator": provenance_record(Path(__file__)),
    }
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
