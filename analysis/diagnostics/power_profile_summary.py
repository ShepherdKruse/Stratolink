#!/usr/bin/env python3
"""Validate and plot create-once pre-supercap PPK2 current evidence."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import statistics

import matplotlib.pyplot as plt

from evidence_provenance import record, write_create_once
from preserve_precursor import sha256
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


EXPECTED_PROFILE_BIN_SHA256 = (
    "99959649faf9e2974fbaf711f957f7d90d357fdacd3adff57bd991840f1ac520"
)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object: {path}")
    return value


def tail_floor(value: dict, count: int) -> list[float]:
    bins = value.get("five_second_median_ua")
    if not isinstance(bins, list) or len(bins) < count:
        raise SystemExit("current evidence lacks required five-second bins")
    return [float(item) for item in bins[-count:]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--flight", type=Path, required=True)
    parser.add_argument("--profile-bin", type=Path, required=True)
    parser.add_argument("--profile-flash-raw", type=Path, required=True)
    parser.add_argument("--candidate-verification", type=Path, required=True)
    parser.add_argument("--restore-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot", type=Path, required=True)
    args = parser.parse_args()

    profile = load(args.profile)
    flight = load(args.flight)
    candidate = load(args.candidate_verification)
    restore = load(args.restore_manifest)
    transcript = args.profile_flash_raw.read_text(encoding="utf-8")
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    for label, value in (("profile", profile), ("flight", flight)):
        require(value.get("source_mv") == 4660, f"{label} source is not 4660 mV")
        require(value.get("frame_phase") == 0, f"{label} frame phase is not zero")
        fractions = value.get("phase_invalid_fraction", [])
        require(
            isinstance(fractions, list) and fractions and fractions[0] == 0.0,
            f"{label} selected frame phase has invalid range codes",
        )
    require(
        sha256(args.profile_bin) == EXPECTED_PROFILE_BIN_SHA256,
        "profile BIN hash changed",
    )
    require("Verify successful." in transcript, "profile flash was not verified")
    require(candidate.get("passed") is True, "candidate verification is not passing")
    require(
        candidate.get("candidate", {}).get("elf_sha256") == EXPECTED_ELF_SHA256
        and candidate.get("candidate", {}).get("bin_sha256") == EXPECTED_BIN_SHA256,
        "candidate hashes changed",
    )
    require(
        restore.get("reserved_devnonce_pages_preserved") is True
        and restore.get("candidate", {}).get("elf_sha256") == EXPECTED_ELF_SHA256
        and restore.get("candidate", {}).get("bin_sha256") == EXPECTED_BIN_SHA256,
        "post-profile exact-flight restore is not passing",
    )

    profile_floor = tail_floor(profile, 8)
    flight_floor = tail_floor(flight, 5)
    for label, values in (("profile", profile_floor), ("flight", flight_floor)):
        require(max(values) <= 10.0, f"{label} STOP1 median exceeds 10 uA")
        require(max(values) - min(values) <= 0.5, f"{label} STOP1 floor is unstable")
    require(
        sum(value > 20_000 for value in profile["five_second_median_ua"][:12]) >= 10,
        "profile trace lacks the active mission phase",
    )
    require(
        sum(value > 20_000 for value in flight["five_second_median_ua"][:7]) >= 6,
        "flight trace lacks the active GNSS phase",
    )

    profile_median = statistics.median(profile_floor)
    flight_median = statistics.median(flight_floor)
    report = {
        "schema": "stratolink.pre_supercap_power_profile.v1",
        "passed": not failures,
        "failures": failures,
        "source_mv": 4660,
        "stop1": {
            "profile_tail_bins": profile_floor,
            "profile_median_ua": round(profile_median, 3),
            "flight_tail_bins": flight_floor,
            "flight_median_ua": round(flight_median, 3),
            "absolute_difference_ua": round(abs(profile_median - flight_median), 3),
            "gate_max_bin_ua": 10.0,
            "gate_max_spread_ua": 0.5,
        },
        "active_phase": {
            "profile_first_60s_bins_ua": profile["five_second_median_ua"][:12],
            "flight_pre_stop_bins_ua": flight["five_second_median_ua"][:7],
        },
        "decoder_scope": {
            "profile_rejected_fraction": profile.get("artifact_fraction"),
            "flight_rejected_fraction": flight.get("artifact_fraction"),
            "selected_phase_invalid_fraction": 0.0,
            "whole_cycle_mean_qualified": False,
            "note": (
                "Range-transition outliers make the whole-cycle mean unusable; "
                "five-second medians and the stable low-current tail are qualified."
            ),
        },
        "scope": {
            "proves": [
                "flight-representative profile reaches a stable STOP1 floor",
                "the restored exact v15 flight BIN independently reaches the same floor",
                "the exact v15 flight image and DevNonce journal were restored afterward",
            ],
            "does_not_prove": [
                "fitted-supercapacitor reserve or darkness endurance",
                "cold-temperature current or capacitance",
                "whole-cycle energy from this range-switching capture",
                "active-solar harvester noise or reserve behavior",
            ],
        },
        "provenance": {
            "profile": record(args.profile),
            "flight": record(args.flight),
            "profile_bin": record(args.profile_bin),
            "profile_flash_raw": record(args.profile_flash_raw),
            "candidate_verification": record(args.candidate_verification),
            "restore_manifest": record(args.restore_manifest),
        },
    }
    if failures:
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit("power profile failed; refusing final evidence")

    fig, axis = plt.subplots(figsize=(10.5, 5.4))
    for label, value, color in (
        ("flight-representative profile", profile, "#1f6f78"),
        ("exact v15 flight continuation", flight, "#e67e22"),
    ):
        bins = value["five_second_median_ua"]
        axis.plot(
            [(index + 0.5) * 5 for index in range(len(bins))],
            bins,
            marker="o",
            markersize=3.5,
            linewidth=1.8,
            color=color,
            label=label,
        )
    axis.axhline(10, color="#8e44ad", linestyle="--", linewidth=1.2, label="10 µA gate")
    axis.set_yscale("log")
    axis.set_xlabel("Seconds from capture start")
    axis.set_ylabel("Five-second median current (µA, log scale)")
    axis.set_title("StratoLink-2 pre-supercap current qualification")
    axis.grid(True, which="both", alpha=0.22)
    axis.legend(loc="best")
    fig.text(
        0.01,
        0.01,
        "4660 mV PPK2 source · panels covered · whole-cycle mean excluded due range-transition artifacts",
        fontsize=8.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    rendered = BytesIO()
    fig.savefig(rendered, format="png", dpi=180)
    plt.close(fig)

    write_create_once(
        args.output,
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(),
    )
    write_create_once(args.plot, rendered.getvalue())
    print(json.dumps({"passed": True, "output": str(args.output), "plot": str(args.plot)}))


if __name__ == "__main__":
    main()
