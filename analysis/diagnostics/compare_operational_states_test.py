#!/usr/bin/env python3
"""Synthetic operational-state delta regressions."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile

from compare_operational_states import (
    compare,
    load_meshtastic_evidence,
    provenance_inputs,
)
from evidence_provenance import record
from evidence_provenance import verify_all as verify_provenance


def fixture() -> dict:
    relay = {
        "rx_count": 10,
        "forwarded": 5,
        "deduplicated": 2,
        "hop_zero_drop": 1,
        "airtime_cap_skip": 0,
        "rx_arm_failures": 0,
        "queued": 7,
        "pending_duplicate": 1,
        "directed_next_hop_skip": 1,
        "queue_full": 0,
        "invalid_header": 0,
        "cad_busy": 2,
        "cad_error": 0,
        "tx_error": 0,
        "window_boundary_skip": 0,
    }
    return {
        "health": {
            "boot": {"count": 9},
            "session": {
                "joined": True,
                "region": "US915",
                "next_fcnt_up": 40,
                "next_fcnt_down": 7,
            },
            "region_lease": {"known": True},
            "burst": {"active": False, "cycles": 0, "cooldown": 0},
            "freefall_guard": {
                "spurious_wake_streak": 0,
                "suppression_clean_wakes": 0,
                "suppression_latched": False,
                "wake_pending": False,
            },
            "radio_diag": {
                "begin_failures": 0,
                "config_failures": 0,
                "restore_attempts": 0,
                "restore_recovered": 0,
                "sleep_failures": 0,
                "allocation_failures": 0,
            },
            "command": {
                "rx_count": 0,
                "command_count": 0,
                "last_opcode": 0,
                "last_sequence": 42,
                "last_fport": 0,
                "last_length": 0,
                "sequence_persist_failures": 0,
                "ack_valid": True,
                "ack_sequence": 42,
                "relay_enabled": True,
            },
            "downlink": {
                "calls": 0,
                "rx1_armed": 0,
                "rx2_armed": 0,
                "irq_count": 0,
                "frame_count": 0,
                "last_rx1_start_state": 0,
                "last_rx2_start_state": 0,
                "last_window": 0,
                "last_length": 0,
                "last_mhdr": 0,
                "last_reject": 0,
            },
            "meshtastic_relay": relay,
            "ctt": {
                "frames_rx": 3,
                "crc_failures": 0,
                "tags_seen": 3,
                "windows": 8,
                "rx_arm_failures": 0,
                "pending_drop": 0,
            },
            "tmp117_sampling": {
                "direct_reads": 20,
                "fallback_reads": 0,
                "rejected_poweron_sentinels": 0,
            },
            "acoustic_diag": {
                "attempts": 20,
                "captures": 20,
                "capture_failures": 0,
                "events": 0,
                "last_variance_x16": 40,
                "noise_floor_x16": 10,
            },
            "sensor_recovery": {"tmp117_reinit_attempts": 0},
            "gps_diag": {
                "begin_failures": 0,
                "dynamic_model_failures": 0,
                "backup_failures": 0,
                "hardware_resets": 0,
                "accepted_fixes": 4,
                "power_aborts": 0,
                "mission_aborts": 0,
                "no_fresh_cycles": 1,
                "backup_confirmations": 4,
                "backup_terminal_failures": 0,
                "rejected_value_fixes": 0,
            },
            "last_gps_fix": {
                "valid": False,
                "satellites": 0,
                "lat_e7": 0,
                "lon_e7": 0,
            },
        },
        "tamp": {
            "session": {
                "dev_addr": "260CACD0",
                "next_fcnt_up": 40,
                "next_fcnt_down": 7,
            },
            "region_lease": {"valid": True},
            "command_sequence": {
                "valid": True,
                "last_applied": 42,
                "relay_enabled": True,
            },
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="stratolink-operational-provenance-"
    ) as raw:
        root = Path(raw)
        paths = [root / name for name in ("before", "before_manifest", "after", "after_manifest")]
        for index, path in enumerate(paths):
            path.write_text(f"evidence-{index}\n", encoding="utf-8")
        provenance = provenance_inputs(*paths)
        verify_provenance(provenance)
        paths[0].write_text("mutated\n", encoding="utf-8")
        try:
            verify_provenance(provenance)
        except ValueError:
            pass
        else:
            raise AssertionError("operational provenance accepted mutated input")

        source = root / "stimulus-source"
        source.write_text("bound stimulus\n", encoding="utf-8")
        stimulus_paths: list[Path] = []
        for profile in ("check", "relay", "cancel", "hop-zero", "directed"):
            path = root / f"{profile}.json"
            path.write_text(
                json.dumps(
                    {
                        "profile": profile,
                        "passed": True,
                        "provenance": {"stimulus": record(source)},
                    }
                ),
                encoding="utf-8",
            )
            stimulus_paths.append(path)
        evidence, bound = load_meshtastic_evidence(stimulus_paths)
        assert {value["profile"] for value in evidence} == {
            "check", "relay", "cancel", "hop-zero", "directed"
        }
        verify_provenance(bound)
        try:
            load_meshtastic_evidence(stimulus_paths[:-1])
        except SystemExit as error:
            assert "missing" in str(error)
        else:
            raise AssertionError("operational gate accepted missing RF profile")
        source.write_text("mutated stimulus\n", encoding="utf-8")
        try:
            load_meshtastic_evidence(stimulus_paths)
        except SystemExit as error:
            assert "invalid" in str(error)
        else:
            raise AssertionError("operational gate accepted mutated RF evidence")

    before = fixture()

    mesh_after = deepcopy(before)
    mesh_after["health"]["session"]["next_fcnt_up"] += 1
    mesh_after["tamp"]["session"]["next_fcnt_up"] += 1
    mesh_after["health"]["meshtastic_relay"]["rx_count"] += 3
    mesh_after["health"]["meshtastic_relay"]["queued"] += 2
    mesh_after["health"]["meshtastic_relay"]["forwarded"] += 1
    mesh_after["health"]["meshtastic_relay"]["deduplicated"] += 1
    mesh_after["health"]["meshtastic_relay"]["pending_duplicate"] += 1
    mesh_after["health"]["meshtastic_relay"]["cad_busy"] += 1
    mesh = compare(
        before,
        mesh_after,
        "meshtastic",
        1,
        min_relay_deduplicated=1,
        min_relay_canceled=1,
        min_relay_cad_busy=1,
    )
    assert mesh["passed"], mesh

    mesh_uncanceled = deepcopy(mesh_after)
    mesh_uncanceled["health"]["meshtastic_relay"]["pending_duplicate"] -= 1
    failed_cancel = compare(
        before,
        mesh_uncanceled,
        "meshtastic",
        1,
        min_relay_canceled=1,
    )
    assert not failed_cancel["passed"]
    assert (
        "Meshtastic pending-relay cancellation was not observed"
        in failed_cancel["failures"]
    )

    mesh_bad = deepcopy(mesh_after)
    mesh_bad["health"]["meshtastic_relay"]["tx_error"] += 1
    failed_mesh = compare(before, mesh_bad, "meshtastic", 1)
    assert not failed_mesh["passed"]
    assert "unexpected relay tx_error advance" in failed_mesh["failures"]

    ctt_after = deepcopy(before)
    ctt_after["health"]["session"]["next_fcnt_up"] += 1
    ctt_after["tamp"]["session"]["next_fcnt_up"] += 1
    ctt_after["health"]["ctt"]["frames_rx"] += 1
    ctt_after["health"]["ctt"]["tags_seen"] += 1
    ctt_after["health"]["ctt"]["windows"] += 1
    ctt = compare(before, ctt_after, "ctt", 1)
    assert ctt["passed"], ctt

    tmp_after = deepcopy(before)
    tmp_after["health"]["session"]["next_fcnt_up"] += 1
    tmp_after["tamp"]["session"]["next_fcnt_up"] += 1
    tmp_after["health"]["tmp117_sampling"]["direct_reads"] += 1
    tmp = compare(before, tmp_after, "tmp117", 1)
    assert tmp["passed"], tmp

    tmp_bad = deepcopy(tmp_after)
    tmp_bad["health"]["tmp117_sampling"]["fallback_reads"] += 1
    failed_tmp = compare(before, tmp_bad, "tmp117", 1)
    assert not failed_tmp["passed"]
    assert "TMP117 fallback counter advanced" in failed_tmp["failures"]

    quiet_after = deepcopy(before)
    quiet_after["health"]["session"]["next_fcnt_up"] += 1
    quiet_after["tamp"]["session"]["next_fcnt_up"] += 1
    quiet_after["health"]["acoustic_diag"].update(
        {"attempts": 21, "captures": 21, "last_variance_x16": 80}
    )
    quiet = compare(before, quiet_after, "acoustic-quiet", 1)
    assert quiet["passed"], quiet

    noisy_quiet = deepcopy(quiet_after)
    noisy_quiet["health"]["acoustic_diag"].update(
        {"events": 1, "last_variance_x16": 161}
    )
    failed_quiet = compare(before, noisy_quiet, "acoustic-quiet", 1)
    assert not failed_quiet["passed"]
    assert "quiet acoustic interval produced an event" in failed_quiet["failures"]

    stimulus_after = deepcopy(quiet_after)
    stimulus_after["health"]["acoustic_diag"].update(
        {"events": 1, "last_variance_x16": 161}
    )
    stimulus = compare(before, stimulus_after, "acoustic-stimulus", 1)
    assert stimulus["passed"], stimulus

    failed_stimulus_state = deepcopy(stimulus_after)
    failed_stimulus_state["health"]["acoustic_diag"]["capture_failures"] = 1
    failed_stimulus = compare(
        before, failed_stimulus_state, "acoustic-stimulus", 1
    )
    assert not failed_stimulus["passed"]
    assert (
        "acoustic capture failure counter advanced"
        in failed_stimulus["failures"]
    )

    freefall_after = deepcopy(before)
    freefall_after["health"]["session"]["next_fcnt_up"] += 1
    freefall_after["tamp"]["session"]["next_fcnt_up"] += 1
    freefall_after["health"]["burst"]["cycles"] = 1
    freefall = compare(
        before,
        freefall_after,
        "freefall-short",
        1,
    )
    assert freefall["passed"], freefall

    chatter_after = deepcopy(freefall_after)
    chatter_after["health"]["freefall_guard"]["spurious_wake_streak"] = 1
    chatter = compare(
        before,
        chatter_after,
        "freefall-short",
        1,
    )
    assert not chatter["passed"]
    assert "short freefall was misclassified as chatter" in chatter["failures"]

    replay_after = deepcopy(before)
    replay_after["health"]["session"]["next_fcnt_up"] += 1
    replay_after["tamp"]["session"]["next_fcnt_up"] += 1
    replay_after["health"]["session"]["next_fcnt_down"] += 1
    replay_after["tamp"]["session"]["next_fcnt_down"] += 1
    replay_after["health"]["command"].update(
        {"rx_count": 1, "last_fport": 10, "last_length": 4}
    )
    replay_after["health"]["downlink"].update(
        {
            "calls": 1,
            "rx1_armed": 1,
            "irq_count": 1,
            "frame_count": 1,
            "last_window": 1,
            "last_length": 17,
            "last_mhdr": 0x60,
            "last_reject": 0,
        }
    )
    replay = compare(
        before,
        replay_after,
        "downlink-replay",
        1,
        expected_command_sequence_after=42,
    )
    assert replay["passed"], replay

    replay_applied = deepcopy(replay_after)
    replay_applied["health"]["command"]["command_count"] = 1
    failed_replay = compare(
        before,
        replay_applied,
        "downlink-replay",
        1,
        expected_command_sequence_after=42,
    )
    assert not failed_replay["passed"]
    assert "same-sequence replay was applied" in failed_replay["failures"]

    accept_after = deepcopy(replay_after)
    accept_after["health"]["command"].update(
        {
            "command_count": 1,
            "last_opcode": 0,
            "last_sequence": 43,
            "ack_sequence": 43,
        }
    )
    accept_after["tamp"]["command_sequence"]["last_applied"] = 43
    accepted = compare(
        before,
        accept_after,
        "downlink-accept",
        1,
        expected_command_sequence_after=43,
    )
    assert accepted["passed"], accepted

    gps_after = deepcopy(before)
    gps_after["health"]["session"]["next_fcnt_up"] += 1
    gps_after["tamp"]["session"]["next_fcnt_up"] += 1
    gps_after["health"]["gps_diag"]["accepted_fixes"] += 1
    gps_after["health"]["gps_diag"]["hardware_resets"] += 1
    gps_after["health"]["gps_diag"]["backup_confirmations"] += 1
    gps_after["health"]["last_gps_fix"] = {
        "valid": True,
        "satellites": 8,
        "lat_e7": 475000000,
        "lon_e7": -1223000000,
    }
    gps = compare(
        before,
        gps_after,
        "gps",
        1,
        min_gps_hardware_resets=1,
    )
    assert gps["passed"], gps

    gps_bad = deepcopy(gps_after)
    gps_bad["health"]["gps_diag"]["backup_failures"] += 1
    failed_gps = compare(before, gps_bad, "gps", 1)
    assert not failed_gps["passed"]
    assert "unexpected GPS backup_failures advance" in failed_gps["failures"]

    gps_terminal = deepcopy(gps_after)
    gps_terminal["health"]["gps_diag"]["backup_terminal_failures"] += 1
    failed_terminal = compare(before, gps_terminal, "gps", 1)
    assert not failed_terminal["passed"]
    assert (
        "unexpected GPS backup_terminal_failures advance"
        in failed_terminal["failures"]
    )

    cold_before = deepcopy(before)
    cold_before["health"]["session"]["joined"] = False
    cold_before["health"]["region_lease"]["known"] = False
    cold_before["tamp"]["region_lease"]["valid"] = False

    cold_after = deepcopy(gps_after)
    cold_after["health"]["session"]["next_fcnt_up"] = 1
    cold_after["tamp"]["session"].update({
        "valid": True,
        "region_id": 0,
        "network_key_present": True,
        "application_key_present": True,
        "next_fcnt_up": 1,
    })
    cold_after["health"]["gps_diag"]["hardware_resets"] = 0
    cold = compare(
        cold_before,
        cold_after,
        "gps-cold-start",
        0,
        expected_fcnt_up_after=1,
    )
    assert cold["passed"], cold

    cold_pre_authorized = deepcopy(cold_before)
    cold_pre_authorized["health"]["region_lease"]["known"] = True
    failed_cold = compare(
        cold_pre_authorized,
        cold_after,
        "gps-cold-start",
        0,
        expected_fcnt_up_after=1,
    )
    assert not failed_cold["passed"]
    assert (
        "cold-start pre-state was already region-authorized"
        in failed_cold["failures"]
    )

    cold_bad_fcnt = compare(
        cold_before,
        cold_after,
        "gps-cold-start",
        0,
        expected_fcnt_up_after=2,
    )
    assert not cold_bad_fcnt["passed"]
    assert (
        "post-cold-start FCntUp did not equal the independently observed value"
        in cold_bad_fcnt["failures"]
    )

    reset = deepcopy(mesh_after)
    reset["health"]["boot"]["count"] += 1
    reset_result = compare(before, reset, "meshtastic", 1)
    assert not reset_result["passed"]
    assert "MCU rebooted during the operational HIL interval" in reset_result["failures"]

    print(
        "PASS: Meshtastic, downlink replay/accept, CTT, TMP117, freefall, "
        "acoustic quiet/stimulus, GPS, and cold-start operational gates"
    )


if __name__ == "__main__":
    main()
