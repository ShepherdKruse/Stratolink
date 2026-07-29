#!/usr/bin/env python3
"""Prevent unguarded target access from returning to the post-soak runbook."""

from __future__ import annotations

from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RUNBOOK = HERE / "STRATOLINK2_POSTSOAK_HIL.md"
PRESERVE = HERE / "preserve_precursor.py"
FLASH = HERE / "flash_flight_candidate.py"


def command_blocks(markdown: str, command: str) -> list[str]:
    blocks = re.findall(r"```sh\n(.*?)```", markdown, flags=re.DOTALL)
    return [block for block in blocks if command in block]


def main() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    preserve_source = PRESERVE.read_text(encoding="utf-8")
    flash_source = FLASH.read_text(encoding="utf-8")
    assert "45 exact" not in text, "runbook retained a superseded HIL symbol count"
    assert "47 exact" not in text, "runbook retained the candidate-v9 HIL symbol count"
    assert "50 exact" not in text, "runbook retained a superseded symbol count"
    assert text.count("51 exact") == 2, (
        "runbook must bind both freeze and readback to 51 symbols"
    )
    assert "JLinkExe" not in text, "runbook contains direct J-Link execution"
    assert "jlink_reset.jlink" not in text, "runbook contains an unguarded reset"
    assert (
        "generated/jlink_bench_authorize_us.jlink" not in text
        and "generated/jlink_bench_clear_region_lease.jlink" not in text
    ), "runbook bypasses the allow-listed HIL action wrapper"

    reset_comparisons = command_blocks(text, "compare_flight_states.py")
    assert len(reset_comparisons) == 3
    assert all("--reset-manifest" in block for block in reset_comparisons), (
        "every reset transition must bind its create-once reset manifest"
    )

    reset_blocks = command_blocks(text, "reset_flight_candidate.py")
    assert len(reset_blocks) == 3
    for label in ("session", "downlink", "b2b"):
        matching = [block for block in reset_blocks if f"--label {label}" in block]
        assert len(matching) == 1
        assert "--check-only" in matching[0]

    action_blocks = command_blocks(text, "apply_flight_hil_action.py")
    assert len(action_blocks) == 3
    for action, expected_count in (
        ("authorize-us", 2),
        ("clear-region-lease", 1),
    ):
        matching = [
            block for block in action_blocks if f"--action {action}" in block
        ]
        assert len(matching) == expected_count
        assert all("--check-only" in block for block in matching)

    action_comparisons = command_blocks(text, "compare_hil_action_states.py")
    assert len(action_comparisons) == 3
    assert all("--action-manifest" in block for block in action_comparisons)

    corruption_blocks = command_blocks(text, "corrupt_tamp_session_hil.py")
    assert len(corruption_blocks) == 1
    assert "--check-only" in corruption_blocks[0]

    assert "Do not perform another direct J-Link read here" in text
    assert "stratolink2_soak_retry2_20260727_ttn.jsonl" in text
    assert "stratolink2_retry2_precollector_storage_20260727.json" in text
    assert "FCntUp 1" in text and "FCntUp 2" in text and "FCntUp 3" in text

    assert "path.resolve() == args.handoff_power.resolve()" in preserve_source
    assert "append_allowed=" in preserve_source, (
        "growing standby evidence is not preserved as an append-only prefix"
    )
    for gate in (
        "require_precursor_manifest(",
        "flash_unchanged_during_soak",
        "EXPECTED_PRE_RETRY_FLASH_SHA256",
        "FLASH_OPTR_IWDG_STOP",
        "verify_provenance(immutable_inputs)",
    ):
        assert gate in flash_source, f"flight flash gate lost precursor check: {gate}"

    preserve_blocks = command_blocks(text, "preserve_precursor.py")
    assert len(preserve_blocks) == 1
    assert preserve_blocks[0].count("preserve_precursor.py") == 2
    preserve_required = (
        "--prefix", "--summary", "--sensor-model", "--candidate-verification",
        "--handoff-power", "--primary-power", "--ttn", "--supabase",
        "--soak-plot", "--readiness-plot", "--candidate-elf",
        "--candidate-bin", "--pre-retry-flash",
    )
    assert all(
        all(argument in block for argument in preserve_required)
        for block in preserve_blocks
    ), "every precursor command must bind the complete retry evidence set"
    assert preserve_blocks[0].count("stratolink2_soak_retry2_20260727_final.json") == 2
    assert preserve_blocks[0].count("stratolink2_soak_retry2_20260727_handoff.jsonl") == 2
    assert preserve_blocks[0].count("stratolink2_soak_retry2_20260727_ttn.jsonl") == 2

    flash_blocks = command_blocks(text, "flash_flight_candidate.py")
    assert len(flash_blocks) == 1
    assert flash_blocks[0].count("flash_flight_candidate.py") == 2
    flash_required = (
        "--prefix", "--summary", "--sensor-model", "--candidate-verification",
        "--precursor-manifest", "--handoff-power",
    )
    assert all(argument in flash_blocks[0] for argument in flash_required)
    assert flash_blocks[0].count("stratolink2_soak_retry2_20260727_final.json") == 2
    assert flash_blocks[0].count("stratolink2_soak_retry2_20260727_handoff.jsonl") == 2

    meshtastic_blocks = command_blocks(text, "compare_operational_states.py")
    meshtastic_blocks = [
        block for block in meshtastic_blocks if "--scenario meshtastic" in block
    ]
    assert len(meshtastic_blocks) == 1
    assert meshtastic_blocks[0].count("--stimulus-evidence") == 5
    assert "--min-relay-canceled 1" in meshtastic_blocks[0]
    assert "--profile cancel" in text
    assert "--interval-seconds 0.1" in text

    supabase_blocks = command_blocks(text, "export_supabase_soak.py")
    assert len(supabase_blocks) == 1
    assert "--since 2026-07-27T10:37:56Z" in supabase_blocks[0]
    assert (
        "--through-ttn-log analysis/diagnostics/logs/"
        "stratolink2_soak_retry2_20260727_ttn.jsonl"
        in supabase_blocks[0]
    )
    assert "stratolink2_soak_retry2_20260727_supabase.json" in supabase_blocks[0]

    summary_blocks = command_blocks(text, "soak_summary.py")
    assert len(summary_blocks) == 1
    assert "--min-held-seconds 86400" in summary_blocks[0]
    assert "--expected-source-mv 4660" in summary_blocks[0]
    assert "--vbat-ov-mv 5363" in summary_blocks[0]
    assert "--vbat-ov-tolerance-mv 75" in summary_blocks[0]
    assert "stratolink2_soak_retry2_20260727_power.jsonl" in summary_blocks[0]
    assert "stratolink2_soak_retry2_20260727_handoff.jsonl" in summary_blocks[0]
    assert "stratolink2_soak_retry2_20260727_ttn.jsonl" in summary_blocks[0]

    sensor_model_blocks = command_blocks(text, "soak_sensor_model.py")
    assert len(sensor_model_blocks) == 1
    assert "--source-mv 4660" in sensor_model_blocks[0]
    assert "--vbat-ov-mv 5363" in sensor_model_blocks[0]
    assert "--vbat-ov-tolerance-mv 75" in sensor_model_blocks[0]
    assert "stratolink2_soak_retry2_20260727_ttn.jsonl" in sensor_model_blocks[0]

    charge_blocks = command_blocks(text, "supercap_charge_ceiling_audit.py")
    assert len(charge_blocks) == 1
    assert "--allow-blocked" in charge_blocks[0]
    assert "stratolink2_soak_retry2_20260727_ttn.jsonl" in charge_blocks[0]
    assert "stratolink2_soak_retry_20260725_ttn.jsonl" not in charge_blocks[0]
    assert "stratolink2_supercap_charge_ceiling_retry2_20260728.json" in charge_blocks[0]

    night_blocks = command_blocks(text, "supercap_night_reserve_audit.py")
    assert len(night_blocks) == 1
    assert "--allow-blocked" in night_blocks[0]
    assert "stratolink2_supercap_night_reserve_20260726.json" in night_blocks[0]

    gps_energy_blocks = command_blocks(text, "gps_backup_energy_audit.py")
    assert len(gps_energy_blocks) == 1
    assert "gps_backup_energy_audit_20260726_min_cap.json" in gps_energy_blocks[0]

    soak_plot_blocks = command_blocks(text, "plot_final_soak.py")
    assert len(soak_plot_blocks) == 1
    assert "stratolink2_final_soak_retry2_20260728.png" in soak_plot_blocks[0]
    assert "stratolink2_soak_retry2_20260727_final.json" in soak_plot_blocks[0]
    readiness_plot_blocks = command_blocks(text, "plot_launch_readiness.py")
    assert len(readiness_plot_blocks) == 1
    assert "stratolink2_launch_readiness_retry2_20260728.png" in readiness_plot_blocks[0]
    assert text.count("--soak-plot analysis/diagnostics/stratolink2_final_soak_retry2_20260728.png") == 2
    assert text.count("--readiness-plot analysis/diagnostics/stratolink2_launch_readiness_retry2_20260728.png") == 2

    identity_blocks = command_blocks(text, "draft_flight_candidate_identity.py")
    assert len(identity_blocks) == 1
    assert "set -euo pipefail" in identity_blocks[0]
    assert "git diff --check" in identity_blocks[0]
    assert "warning_compile.py --analyzer" in identity_blocks[0]
    assert "SKIP_STALE_CANDIDATE_VERIFICATION=1" in identity_blocks[0]
    assert "mktemp -d /private/tmp/stratolink-flight-v11-independent.XXXXXX" in identity_blocks[0]
    assert 'PLATFORMIO_BUILD_DIR="$stratolink_v11_build_dir"' in identity_blocks[0]
    assert "-e stratolink" in identity_blocks[0]
    assert "--independent-elf" in identity_blocks[0]
    assert "--independent-bin" in identity_blocks[0]
    assert "stratolink2_flight_candidate_identity_20260728_v11.json" in identity_blocks[0]
    assert "stratolink2_flight_candidate_dynamic_memory_20260728_v11.json" in identity_blocks[0]
    assert "stratolink2_flight_candidate_static_stack_20260728_v11.json" in identity_blocks[0]
    assert text.count("git diff --check") == 2

    verifier_blocks = command_blocks(text, "verify_flight_candidate.py")
    assert len(verifier_blocks) == 2
    assert verifier_blocks[0].count("verify_flight_candidate.py") == 1
    assert "--output" not in verifier_blocks[0]
    assert "--dynamic-memory-audit" in verifier_blocks[0]
    assert "--static-stack-audit" in verifier_blocks[0]
    assert verifier_blocks[1].count("verify_flight_candidate.py") == 1
    assert "--output" in verifier_blocks[1]
    assert "--dynamic-memory-audit" in verifier_blocks[1]
    assert "--static-stack-audit" in verifier_blocks[1]
    assert "stratolink2_flight_candidate_verification_20260728_v11.json" in text
    assert "stratolink2_flight_candidate_verification_20260726_v9.json" not in text
    print("PASS: post-soak runbook has no direct or unbound J-Link mutation")


if __name__ == "__main__":
    main()
