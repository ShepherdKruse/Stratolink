#!/usr/bin/env python3
"""Compare exact-candidate state captures across controlled operational HIL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compare_flight_states import load_capture
from decode_flight_state import atomic_json
from evidence_provenance import record as provenance_record
from evidence_provenance import verify_all as verify_provenance


SCENARIOS = (
    "meshtastic",
    "ctt",
    "tmp117",
    "acoustic-quiet",
    "acoustic-stimulus",
    "freefall-short",
    "gps",
    "gps-cold-start",
    "downlink-replay",
    "downlink-accept",
)
RELAY_COUNTERS = (
    "rx_count",
    "forwarded",
    "deduplicated",
    "hop_zero_drop",
    "airtime_cap_skip",
    "rx_arm_failures",
    "queued",
    "pending_duplicate",
    "directed_next_hop_skip",
    "queue_full",
    "invalid_header",
    "cad_busy",
    "cad_error",
    "tx_error",
    "window_boundary_skip",
)
CTT_COUNTERS = (
    "frames_rx",
    "crc_failures",
    "tags_seen",
    "windows",
    "rx_arm_failures",
    "pending_drop",
)
TMP117_COUNTERS = (
    "direct_reads",
    "fallback_reads",
    "rejected_poweron_sentinels",
)
ACOUSTIC_COUNTERS = (
    "attempts",
    "captures",
    "capture_failures",
    "events",
)
GPS_COUNTERS = (
    "begin_failures",
    "dynamic_model_failures",
    "backup_failures",
    "hardware_resets",
    "accepted_fixes",
    "power_aborts",
    "mission_aborts",
    "no_fresh_cycles",
    "backup_confirmations",
    "backup_terminal_failures",
    "rejected_value_fixes",
)
MESHTASTIC_EVIDENCE_PROFILES = {
    "check", "relay", "cancel", "hop-zero", "directed"
}


def load_meshtastic_evidence(paths: list[Path]) -> tuple[list[dict], dict]:
    evidence: list[dict] = []
    provenance: dict = {}
    profiles: set[str] = set()
    for index, path in enumerate(paths):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            verify_provenance(value.get("provenance"))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise SystemExit(
                f"invalid Meshtastic stimulus evidence {path}: {error}"
            ) from error
        if value.get("passed") is not True:
            raise SystemExit(f"Meshtastic stimulus evidence did not pass: {path}")
        profile = value.get("profile")
        if profile not in MESHTASTIC_EVIDENCE_PROFILES:
            raise SystemExit(
                f"unknown Meshtastic stimulus evidence profile in {path}"
            )
        if profile in profiles:
            raise SystemExit(
                f"duplicate Meshtastic stimulus evidence profile: {profile}"
            )
        profiles.add(profile)
        evidence.append(value)
        provenance[f"meshtastic_stimulus_{index}_{profile}"] = provenance_record(
            path
        )
    missing = MESHTASTIC_EVIDENCE_PROFILES - profiles
    if missing:
        raise SystemExit(
            "missing Meshtastic stimulus evidence profiles: "
            + ", ".join(sorted(missing))
        )
    return evidence, provenance


def provenance_inputs(
    before: Path,
    before_manifest: Path,
    after: Path,
    after_manifest: Path,
) -> dict:
    return {
        "before": provenance_record(before),
        "before_manifest": provenance_record(before_manifest),
        "after": provenance_record(after),
        "after_manifest": provenance_record(after_manifest),
        "comparator": provenance_record(Path(__file__)),
    }


def counter_deltas(
    before: dict,
    after: dict,
    names: tuple[str, ...],
    failures: list[str],
    label: str,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for name in names:
        old = before.get(name)
        new = after.get(name)
        if (
            not isinstance(old, int)
            or isinstance(old, bool)
            or not isinstance(new, int)
            or isinstance(new, bool)
        ):
            failures.append(f"{label}.{name} is missing or non-integer")
            continue
        if new < old:
            failures.append(f"{label}.{name} regressed")
            continue
        result[name] = new - old
    return result


def compare(
    before: dict,
    after: dict,
    scenario: str,
    expected_fcnt_up_advance: int,
    *,
    min_relay_rx: int = 1,
    min_relay_queued: int = 1,
    min_relay_forwarded: int = 1,
    min_relay_deduplicated: int = 0,
    min_relay_canceled: int = 0,
    min_relay_cad_busy: int = 0,
    min_relay_hop_zero_drop: int = 0,
    min_relay_directed_drop: int = 0,
    min_ctt_frames: int = 1,
    min_ctt_tags: int = 1,
    min_tmp117_direct: int = 1,
    min_gps_fixes: int = 1,
    min_gps_hardware_resets: int = 0,
    expected_fcnt_up_after: int | None = None,
    expected_command_sequence_after: int | None = None,
) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")

    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    bh, ah = before["health"], after["health"]
    bt, at = before["tamp"], after["tamp"]
    require(
        ah["boot"]["count"] == bh["boot"]["count"],
        "MCU rebooted during the operational HIL interval",
    )
    if scenario == "gps-cold-start":
        require(
            not bh["region_lease"]["known"],
            "cold-start pre-state was already region-authorized",
        )
        require(
            not bh["last_gps_fix"]["valid"],
            "cold-start pre-state already contained a valid GPS fix",
        )
        require(
            ah["session"]["joined"] and ah["session"]["region"] == "US915",
            "cold-start did not end in a joined US915 session",
        )
        require(
            at["session"]["valid"]
            and at["session"]["region_id"] == 0
            and at["session"]["network_key_present"]
            and at["session"]["application_key_present"],
            "cold-start did not persist a valid US915 session",
        )
        require(
            ah["session"]["next_fcnt_up"] == at["session"]["next_fcnt_up"],
            "post-cold-start RAM/TAMP FCntUp disagreement",
        )
        require(
            expected_fcnt_up_after is not None
            and ah["session"]["next_fcnt_up"] == expected_fcnt_up_after,
            "post-cold-start FCntUp did not equal the independently observed value",
        )
        require(
            ah["region_lease"]["known"] and at["region_lease"]["valid"],
            "cold-start did not persist fresh region authorization",
        )
    else:
        require(
            ah["session"]["joined"] and bh["session"]["joined"],
            "joined session was not present on both sides of HIL",
        )
        require(
            ah["session"]["region"] == bh["session"]["region"] == "US915",
            "RAM region changed or was not US915",
        )
        require(
            at["session"]["dev_addr"] == bt["session"]["dev_addr"],
            "DevAddr changed during operational HIL",
        )
        require(
            ah["session"]["next_fcnt_up"]
            == bh["session"]["next_fcnt_up"] + expected_fcnt_up_advance,
            "FCntUp did not advance by the controlled amount",
        )
        require(
            ah["session"]["next_fcnt_up"] == at["session"]["next_fcnt_up"]
            and bh["session"]["next_fcnt_up"] == bt["session"]["next_fcnt_up"],
            "RAM/TAMP FCntUp disagreement",
        )
        require(
            ah["region_lease"]["known"] and at["region_lease"]["valid"],
            "region authorization was lost during operational HIL",
        )

    radio_deltas = counter_deltas(
        bh["radio_diag"],
        ah["radio_diag"],
        (
            "begin_failures",
            "config_failures",
            "restore_attempts",
            "restore_recovered",
            "sleep_failures",
            "allocation_failures",
        ),
        failures,
        "radio_diag",
    )
    require(
        radio_deltas.get("begin_failures") == 0
        and radio_deltas.get("config_failures") == 0
        and radio_deltas.get("sleep_failures") == 0
        and radio_deltas.get("allocation_failures") == 0,
        "radio allocation/begin/config/sleep failure counter advanced",
    )
    require(
        radio_deltas.get("restore_attempts")
        == radio_deltas.get("restore_recovered"),
        "radio restore attempt was not fully recovered",
    )

    observed: dict[str, object] = {
        "boot_count_before": bh["boot"]["count"],
        "boot_count_after": ah["boot"]["count"],
        "fcnt_up_before": bh["session"]["next_fcnt_up"],
        "fcnt_up_after": ah["session"]["next_fcnt_up"],
        "radio_deltas": radio_deltas,
    }

    if scenario == "meshtastic":
        deltas = counter_deltas(
            bh["meshtastic_relay"],
            ah["meshtastic_relay"],
            RELAY_COUNTERS,
            failures,
            "meshtastic_relay",
        )
        require(deltas.get("rx_count", -1) >= min_relay_rx,
                "too few Meshtastic frames received")
        require(deltas.get("queued", -1) >= min_relay_queued,
                "too few Meshtastic frames entered delayed contention")
        require(deltas.get("forwarded", -1) >= min_relay_forwarded,
                "too few Meshtastic frames were forwarded")
        require(deltas.get("deduplicated", -1) >= min_relay_deduplicated,
                "Meshtastic dedup stimulus was not observed")
        require(deltas.get("pending_duplicate", -1) >= min_relay_canceled,
                "Meshtastic pending-relay cancellation was not observed")
        require(deltas.get("cad_busy", -1) >= min_relay_cad_busy,
                "Meshtastic CAD-busy stimulus was not observed")
        require(deltas.get("hop_zero_drop", -1) >= min_relay_hop_zero_drop,
                "Meshtastic hop-zero reject stimulus was not observed")
        require(
            deltas.get("directed_next_hop_skip", -1)
            >= min_relay_directed_drop,
            "Meshtastic directed-next-hop reject stimulus was not observed",
        )
        for name in (
            "airtime_cap_skip",
            "rx_arm_failures",
            "queue_full",
            "invalid_header",
            "cad_error",
            "tx_error",
            "window_boundary_skip",
        ):
            require(deltas.get(name) == 0, f"unexpected relay {name} advance")
        observed["meshtastic_relay_deltas"] = deltas

    elif scenario in ("downlink-replay", "downlink-accept"):
        bc, ac = bh["command"], ah["command"]
        bd, ad = bh["downlink"], ah["downlink"]
        command_deltas = counter_deltas(
            bc,
            ac,
            ("rx_count", "command_count", "sequence_persist_failures"),
            failures,
            "command",
        )
        downlink_deltas = counter_deltas(
            bd,
            ad,
            ("calls", "rx1_armed", "rx2_armed", "irq_count", "frame_count"),
            failures,
            "downlink",
        )
        require(
            ah["session"]["next_fcnt_down"]
            == bh["session"]["next_fcnt_down"] + 1,
            "FCntDown did not advance exactly once",
        )
        require(
            ah["session"]["next_fcnt_down"]
            == at["session"]["next_fcnt_down"]
            and bh["session"]["next_fcnt_down"]
            == bt["session"]["next_fcnt_down"],
            "RAM/TAMP FCntDown disagreement",
        )
        require(command_deltas.get("rx_count") == 1,
                "command parser did not receive exactly one frame")
        require(command_deltas.get("sequence_persist_failures") == 0,
                "command sequence persistence failed")
        require(downlink_deltas.get("calls") == 1,
                "Class-A receiver did not run exactly once")
        require(downlink_deltas.get("irq_count") == 1,
                "downlink did not produce exactly one radio IRQ")
        require(downlink_deltas.get("frame_count") == 1,
                "downlink frame count did not advance exactly once")
        require(
            downlink_deltas.get("rx1_armed", -1)
            + downlink_deltas.get("rx2_armed", -1) in (1, 2),
            "Class-A receiver armed an impossible number of windows",
        )
        require(ad["last_window"] in (1, 2),
                "accepted downlink did not identify RX1 or RX2")
        require(ad["last_reject"] == 0,
                "downlink frame was rejected")
        require(ad["last_length"] >= 17,
                "downlink frame was shorter than command minimum")
        require((ad["last_mhdr"] & 0xE0) == 0x60,
                "downlink MHDR was not unconfirmed data-down")
        require(
            (
                ad["last_window"] == 1
                and ad["last_rx1_start_state"] == 0
            )
            or (
                ad["last_window"] == 2
                and ad["last_rx2_start_state"] == 0
            ),
            "successful downlink window was not armed cleanly",
        )
        require(ac["last_fport"] == 10 and ac["last_length"] == 4,
                "command parser did not see the exact PING shape")
        require(
            expected_command_sequence_after is not None
            and ac["last_sequence"] == expected_command_sequence_after
            and at["command_sequence"]["valid"]
            and at["command_sequence"]["last_applied"]
            == expected_command_sequence_after,
            "post-downlink command sequence did not equal expected value",
        )
        require(
            ac.get("ack_valid")
            and ac.get("ack_sequence") == expected_command_sequence_after
            and ac.get("relay_enabled")
            == at["command_sequence"].get("relay_enabled"),
            "post-downlink RAM ACK/state did not match retained command state",
        )
        require(
            bt["command_sequence"]["valid"]
            and bc["last_sequence"]
            == bt["command_sequence"]["last_applied"]
            and bc.get("relay_enabled")
            == bt["command_sequence"].get("relay_enabled"),
            "pre-downlink RAM/TAMP command state disagreement",
        )
        require(
            ac.get("relay_enabled") == bc.get("relay_enabled")
            == at["command_sequence"].get("relay_enabled"),
            "PING changed or desynchronized retained relay state",
        )
        if scenario == "downlink-replay":
            require(command_deltas.get("command_count") == 0,
                    "same-sequence replay was applied")
            require(
                expected_command_sequence_after
                == bc["last_sequence"]
                == ac["last_sequence"],
                "same-sequence replay changed application sequence",
            )
        else:
            sequence_delta = (
                ac["last_sequence"] - bc["last_sequence"]
            ) & 0xFF
            require(command_deltas.get("command_count") == 1,
                    "newer command was not applied exactly once")
            require(1 <= sequence_delta <= 127,
                    "accepted application sequence was not monotonically newer")
            require(ac["last_opcode"] == 0,
                    "accepted command was not harmless PING")
        observed["command_deltas"] = command_deltas
        observed["downlink_deltas"] = downlink_deltas
        observed["command_sequence_before"] = bc["last_sequence"]
        observed["command_sequence_after"] = ac["last_sequence"]
        observed["fcnt_down_before"] = bh["session"]["next_fcnt_down"]
        observed["fcnt_down_after"] = ah["session"]["next_fcnt_down"]

    elif scenario == "freefall-short":
        bb, ab = bh["burst"], ah["burst"]
        bf, af = bh["freefall_guard"], ah["freefall_guard"]
        require(
            not bb["active"] and bb["cycles"] == 0 and bb["cooldown"] == 0,
            "freefall pre-state was not cleanly armed",
        )
        require(
            not ab["active"] and ab["cycles"] == 1 and ab["cooldown"] == 0,
            "short freefall did not enter once and clear normally",
        )
        require(
            not bf["suppression_latched"]
            and not af["suppression_latched"]
            and bf["spurious_wake_streak"] == 0
            and af["spurious_wake_streak"] == 0,
            "short freefall was misclassified as chatter",
        )
        require(
            not bf["wake_pending"] and not af["wake_pending"],
            "freefall wake flag was not consumed",
        )
        observed["burst_before"] = bb
        observed["burst_after"] = ab
        observed["freefall_guard_before"] = bf
        observed["freefall_guard_after"] = af

    elif scenario == "ctt":
        deltas = counter_deltas(
            bh["ctt"], ah["ctt"], CTT_COUNTERS, failures, "ctt"
        )
        require(deltas.get("frames_rx", -1) >= min_ctt_frames,
                "too few valid CTT frames received")
        require(deltas.get("tags_seen", -1) >= min_ctt_tags,
                "too few CTT tags were queued")
        require(deltas.get("windows", -1) >= 1,
                "CTT listening window did not run")
        for name in ("crc_failures", "rx_arm_failures", "pending_drop"):
            require(deltas.get(name) == 0, f"unexpected CTT {name} advance")
        observed["ctt_deltas"] = deltas

    elif scenario == "tmp117":
        deltas = counter_deltas(
            bh["tmp117_sampling"],
            ah["tmp117_sampling"],
            TMP117_COUNTERS,
            failures,
            "tmp117_sampling",
        )
        recovery = counter_deltas(
            bh["sensor_recovery"],
            ah["sensor_recovery"],
            ("tmp117_reinit_attempts",),
            failures,
            "sensor_recovery",
        )
        require(deltas.get("direct_reads", -1) >= min_tmp117_direct,
                "TMP117 direct-read counter did not advance")
        require(deltas.get("fallback_reads") == 0,
                "TMP117 fallback counter advanced")
        require(deltas.get("rejected_poweron_sentinels") == 0,
                "TMP117 power-on sentinel was observed")
        require(recovery.get("tmp117_reinit_attempts") == 0,
                "TMP117 required reinitialization during the interval")
        observed["tmp117_sampling_deltas"] = deltas
        observed["sensor_recovery_deltas"] = recovery

    elif scenario in ("acoustic-quiet", "acoustic-stimulus"):
        deltas = counter_deltas(
            bh["acoustic_diag"],
            ah["acoustic_diag"],
            ACOUSTIC_COUNTERS,
            failures,
            "acoustic_diag",
        )
        require(deltas.get("attempts", 0) >= 1,
                "acoustic detector did not run")
        require(deltas.get("captures") == deltas.get("attempts"),
                "not every acoustic attempt completed")
        require(deltas.get("capture_failures") == 0,
                "acoustic capture failure counter advanced")
        variance = ah["acoustic_diag"].get("last_variance_x16")
        floor = ah["acoustic_diag"].get("noise_floor_x16")
        require(
            isinstance(variance, int) and not isinstance(variance, bool)
            and isinstance(floor, int) and not isinstance(floor, bool)
            and floor >= 1,
            "acoustic variance/floor diagnostics are invalid",
        )
        if scenario == "acoustic-quiet":
            require(deltas.get("events") == 0,
                    "quiet acoustic interval produced an event")
            require(
                isinstance(variance, int) and isinstance(floor, int)
                and variance <= floor * 16,
                "quiet capture ended above the event threshold",
            )
        else:
            require(deltas.get("events", 0) >= 1,
                    "controlled acoustic stimulus produced no event")
            require(
                isinstance(variance, int) and isinstance(floor, int)
                and variance > floor * 16,
                "stimulus capture did not end above the event threshold",
            )
        observed["acoustic_deltas"] = deltas
        observed["acoustic_after"] = ah["acoustic_diag"]

    elif scenario in ("gps", "gps-cold-start"):
        deltas = counter_deltas(
            bh["gps_diag"],
            ah["gps_diag"],
            GPS_COUNTERS,
            failures,
            "gps_diag",
        )
        require(deltas.get("accepted_fixes", -1) >= min_gps_fixes,
                "too few fresh GPS fixes were accepted")
        require(
            deltas.get("hardware_resets", -1) >= min_gps_hardware_resets,
            "GPS PA0 reset stimulus was not observed",
        )
        require(
            deltas.get("backup_confirmations", -1) >= 1,
            "GPS backup entry was not independently confirmed",
        )
        for name in (
            "begin_failures",
            "dynamic_model_failures",
            "backup_failures",
            "power_aborts",
            "mission_aborts",
            "backup_terminal_failures",
            "rejected_value_fixes",
        ):
            require(deltas.get(name) == 0, f"unexpected GPS {name} advance")
        fix = ah["last_gps_fix"]
        require(
            fix["valid"]
            and fix["satellites"] >= 4
            and -900000000 <= fix["lat_e7"] <= 900000000
            and -1800000000 <= fix["lon_e7"] <= 1800000000
            and not (fix["lat_e7"] == 0 and fix["lon_e7"] == 0),
            "post-stimulus RAM does not contain a plausible fresh GPS fix",
        )
        observed["gps_deltas"] = deltas
        observed["last_gps_fix_after"] = fix

    return {
        "scenario": scenario,
        "expected_fcnt_up_advance": (
            None if scenario == "gps-cold-start"
            else expected_fcnt_up_advance
        ),
        "expected_fcnt_up_after": expected_fcnt_up_after,
        "expected_command_sequence_after": expected_command_sequence_after,
        "passed": not failures,
        "failures": failures,
        "observed": observed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--before-manifest", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--after-manifest", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--expect-fcnt-up-advance", type=int, default=1)
    parser.add_argument("--min-relay-rx", type=int, default=1)
    parser.add_argument("--min-relay-queued", type=int, default=1)
    parser.add_argument("--min-relay-forwarded", type=int, default=1)
    parser.add_argument("--min-relay-deduplicated", type=int, default=0)
    parser.add_argument("--min-relay-canceled", type=int, default=0)
    parser.add_argument("--min-relay-cad-busy", type=int, default=0)
    parser.add_argument("--min-relay-hop-zero-drop", type=int, default=0)
    parser.add_argument("--min-relay-directed-drop", type=int, default=0)
    parser.add_argument("--min-ctt-frames", type=int, default=1)
    parser.add_argument("--min-ctt-tags", type=int, default=1)
    parser.add_argument("--min-tmp117-direct", type=int, default=1)
    parser.add_argument("--min-gps-fixes", type=int, default=1)
    parser.add_argument("--min-gps-hardware-resets", type=int, default=0)
    parser.add_argument("--expect-fcnt-up-after", type=int)
    parser.add_argument("--expect-command-sequence-after", type=int)
    parser.add_argument(
        "--stimulus-evidence",
        type=Path,
        action="append",
        default=[],
        help=(
            "passing validate_meshtastic_hil output; Meshtastic requires one "
            "each for check, relay, cancel, hop-zero, and directed"
        ),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    nonnegative = (
        args.expect_fcnt_up_advance,
        args.min_relay_rx,
        args.min_relay_queued,
        args.min_relay_forwarded,
        args.min_relay_deduplicated,
        args.min_relay_canceled,
        args.min_relay_cad_busy,
        args.min_relay_hop_zero_drop,
        args.min_relay_directed_drop,
        args.min_ctt_frames,
        args.min_ctt_tags,
        args.min_tmp117_direct,
        args.min_gps_fixes,
        args.min_gps_hardware_resets,
    )
    if any(value < 0 or value > 65535 for value in nonnegative):
        parser.error("expected/minimum counts must be between 0 and 65535")
    if args.scenario == "gps-cold-start":
        if (
            args.expect_fcnt_up_after is None
            or not 0 <= args.expect_fcnt_up_after <= 0xFFFFFFFF
        ):
            parser.error(
                "gps-cold-start requires --expect-fcnt-up-after "
                "between 0 and 4294967295"
            )
    elif args.expect_fcnt_up_after is not None:
        parser.error("--expect-fcnt-up-after is only valid for gps-cold-start")
    if args.scenario in ("downlink-replay", "downlink-accept"):
        if (
            args.expect_command_sequence_after is None
            or not 0 <= args.expect_command_sequence_after <= 255
        ):
            parser.error(
                f"{args.scenario} requires --expect-command-sequence-after 0..255"
            )
    elif args.expect_command_sequence_after is not None:
        parser.error(
            "--expect-command-sequence-after is only valid for downlink scenarios"
        )
    if args.scenario == "meshtastic":
        if not args.stimulus_evidence:
            parser.error(
                "meshtastic requires five --stimulus-evidence artifacts"
            )
    elif args.stimulus_evidence:
        parser.error(
            "--stimulus-evidence is only valid for the meshtastic scenario"
        )
    if args.output and args.output.exists():
        raise SystemExit(
            f"refusing to overwrite operational comparison evidence: {args.output}"
        )

    meshtastic_evidence: list[dict] = []
    meshtastic_provenance: dict = {}
    if args.scenario == "meshtastic":
        meshtastic_evidence, meshtastic_provenance = load_meshtastic_evidence(
            args.stimulus_evidence
        )

    before_profile = (
        "cold-fail-closed"
        if args.scenario == "gps-cold-start"
        else "joined-us"
    )
    before = load_capture(
        args.before,
        args.before_manifest,
        expected_profile=before_profile,
    )
    after = load_capture(
        args.after,
        args.after_manifest,
        expected_profile="joined-us",
    )
    result = compare(
        before,
        after,
        args.scenario,
        args.expect_fcnt_up_advance,
        min_relay_rx=args.min_relay_rx,
        min_relay_queued=args.min_relay_queued,
        min_relay_forwarded=args.min_relay_forwarded,
        min_relay_deduplicated=args.min_relay_deduplicated,
        min_relay_canceled=args.min_relay_canceled,
        min_relay_cad_busy=args.min_relay_cad_busy,
        min_relay_hop_zero_drop=args.min_relay_hop_zero_drop,
        min_relay_directed_drop=args.min_relay_directed_drop,
        min_ctt_frames=args.min_ctt_frames,
        min_ctt_tags=args.min_ctt_tags,
        min_tmp117_direct=args.min_tmp117_direct,
        min_gps_fixes=args.min_gps_fixes,
        min_gps_hardware_resets=args.min_gps_hardware_resets,
        expected_fcnt_up_after=args.expect_fcnt_up_after,
        expected_command_sequence_after=args.expect_command_sequence_after,
    )
    result["provenance"] = provenance_inputs(
        args.before,
        args.before_manifest,
        args.after,
        args.after_manifest,
    )
    result["provenance"].update(meshtastic_provenance)
    if meshtastic_evidence:
        result["stimulus_evidence"] = [
            {
                "profile": value["profile"],
                "observed": value.get("observed"),
                "expected": value.get("expected"),
            }
            for value in meshtastic_evidence
        ]
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
