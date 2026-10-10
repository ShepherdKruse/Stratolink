#!/usr/bin/env python3
"""Regression checks for the GNSS backup energy source-bound model."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


SCRIPT = Path(__file__).with_name("gps_backup_energy_audit.py")
SPEC = importlib.util.spec_from_file_location("gps_backup_energy_audit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> None:
    gps = MODULE.GPS.read_text(encoding="utf-8")
    MODULE.legacy_recovery_contract(gps)
    audit = MODULE.build_audit()
    # SparkFun 3.1.13 serial begin() can exhaust THREE connection polls.
    # Counting only one understates reset release by 2200 ms.
    assert audit["timing_subtotal_ms"]["legacy_compatibility_reset_hold_release_and_uart_reinit"] == 4300, (
        "legacy compatibility release must include the 1000 ms boot delay and all three "
        "1100 ms connection attempts"
    )
    assert audit["timing_subtotal_ms"] == {
        "confirmation_attempt": 2360,
        "hardware_reset_and_reconfigure": 6120,
        "full_three_attempt_two_reset_path": 19320,
        "low_rail_path_before_reset_suppression": 2360,
        "legacy_compatibility_reset_hold_release_and_uart_reinit": 4300,
    }
    assert audit["scope"] == {
        "energy_screen": "legacy shutdown recovery and terminal containment",
        "release_subtotal_function": "gps_ublox_prepare_acquisition",
        "supervised_startup_included": False,
        "supervised_startup_time_bound_ms": None,
        "supervised_startup_energy_qualified": False,
    }
    assert any("4300" in limit and "supervised startup" in limit
               for limit in audit["limits"])
    assert audit["timing_assumptions"]["begin_connection_attempts"] == 3
    assert audit["timing_assumptions"]["shared_configuration_budget_ms"] == 1500
    assert audit["timing_assumptions"]["configuration_subcap_ms"] == 1500
    assert audit["timing_assumptions"]["combined_config_marker_deadline_ms"] == 2000
    assert audit["timing_assumptions"]["model_operations_per_attempt"] == {
        "macro_defined_branch": 3,
        "fallback_branch": 2,
    }
    assert audit["timing_assumptions"]["shared_model_budget_ms"] == 1800
    assert audit["timing_assumptions"]["model_first_set_wait_cap_ms"] == 1200
    assert audit["timing_assumptions"]["model_later_set_and_read_wait_cap_ms"] == 300
    assert audit["timing_assumptions"]["model_branch_subtotal_ms"] == {
        "macro_defined_branch": 1800,
        "fallback_branch": 1800,
    }
    assert audit["timing_assumptions"]["model_retry_pauses_within_shared_budget"] is True
    assert audit["timing_assumptions"]["fallback_full_path_subtotal_ms"] == 19320
    assert audit["timing_assumptions"]["fallback_never_set_ack_subtotal_ms"] == 1800
    assert audit["timing_assumptions"]["prior_fallback_never_set_ack_subtotal_ms"] == 960
    assert audit["timing_assumptions"]["complete_wall_clock_upper_bound"] is False
    assert audit["status"] == "BLOCKED_RESET_HELD_CURRENT_MEASUREMENT_REQUIRED"
    assert all(audit["structural_gates"].values())
    assert audit["measurement_gates"] == {
        "reset_held_current_measured_on_exact_assembly": False,
        "reset_held_terminal_sleep_charge_positive": False,
        "complete_recovery_time_and_energy_qualified": False,
    }
    assert not all(audit["gates"].values())
    energy = audit["energy_model"]
    assert energy["capacitance_f"] == 0.8
    assert energy["acquisition_floor_v"] == 3.6
    assert energy["reset_floor_v"] == 4.4
    assert energy["acquisition_floor_reserve_j"] == 0.77504
    assert energy["reset_floor_reserve_j"] == 3.33504
    assert energy["full_recovery_j"] == 3.000282
    assert energy["reset_floor_margin_j"] == 0.334758
    assert energy["reset_floor_margin_percent_of_recovery"] == 11.158
    assert "terminal_retry_sleep_s" not in energy
    assert audit["gates"]["terminal_failure_has_no_cross_cycle_fast_retry"] is True
    assert audit["gates"]["terminal_failure_asserts_reset_hold"] is True
    assert audit["gates"]["legacy_compatibility_reset_hold_release_is_rail_gated"] is True
    assert energy["normal_terminal_sleep_s"] == 1200
    assert energy["full_charge_to_reported_plateau_reserve_j"] == 4.27728
    awake = energy["uncontained_awake_receiver"]
    assert 139.76 < awake["sleep_energy_j"] < 139.77
    assert awake["fraction_of_full_charge_reserve"] > 32.0
    held = energy["reset_held_receiver"]
    assert held["board_r18_pullup_ohms"] == 10000
    assert held["max_m10s_internal_pullup_ohms_range"] == [7000, 13000]
    assert held["board_r18_only_current_ma"] == 0.33
    assert 0.583 < held["parallel_pullups_best_case_current_ma"] < 0.585
    assert 0.800 < held["parallel_pullups_worst_case_current_ma"] < 0.802
    assert 2.71 < held["parallel_pullups_best_case_sleep_energy_j"] < 2.73
    assert 3.72 < held["parallel_pullups_worst_case_sleep_energy_j"] < 3.74
    assert (
        held["parallel_pullups_best_case_fraction_of_full_charge_reserve"]
        > 0.63
    )
    assert (
        held["parallel_pullups_worst_case_fraction_of_full_charge_reserve"]
        > 0.87
    )
    assert held["receiver_reset_held_current_ma"] is None
    assert held["total_reset_held_sleep_energy_j"] is None
    assert held["measurement_qualified"] is False

    # A changed retry count or wait argument must invalidate the reviewed
    # dependency contract instead of continuing to publish a stale subtotal.
    cpp = MODULE.GNSS_CPP.read_text(encoding="utf-8")
    header = MODULE.GNSS_HEADER.read_text(encoding="utf-8")
    assert MODULE.begin_connection_attempts(cpp, header) == 3
    for changed_cpp in (
        cpp.replace("bool connected = isConnected(maxWait);",
                    "bool connected = isConnected(maxWait);\n"
                    "  connected = isConnected(maxWait);", 1),
        cpp.replace("bool connected = isConnected(maxWait);",
                    "bool connected = isConnected(2 * maxWait);", 1),
    ):
        try:
            MODULE.begin_connection_attempts(changed_cpp, header)
        except AssertionError as exc:
            assert "review" in str(exc)
        else:
            raise AssertionError("changed library retry behavior was not rejected")

    gps = MODULE.GPS.read_text(encoding="utf-8")
    policy = MODULE.POLICY.read_text(encoding="utf-8")
    config = MODULE.CONFIG.read_text(encoding="utf-8")
    # New startup can add/remove begin calls without changing the legacy screen.
    MODULE.legacy_recovery_contract(gps + "\ngnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);\n")
    for signature in ("static bool gps_ublox_reset(void)",
                      "gps_recovery_result_t gps_ublox_prepare_acquisition(void)"):
        start = gps.index(signature)
        end = gps.index("\n}\n", start) + 2
        body = gps[start:end]
        mutations = [
            ("delay(1000);", "delay(2000);"),
            ("gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS)",
             "gnss.begin(gps_gnss_stream, 2 * GPS_BEGIN_MAX_WAIT_MS)"),
        ]
        if "prepare_acquisition" in signature:
            mutations.append(("!gps_backup_containment_release_allowed(power_adc_read_vSTOR_mv())",
                              "false"))
        else:
            mutations.append(("delay(20);", "delay(40);"))
        for old, new in mutations:
            assert old in body
            changed = gps[:start] + body.replace(old, new, 1) + gps[end:]
            try:
                MODULE.legacy_recovery_contract(changed)
            except AssertionError as exc:
                assert "review" in str(exc)
            else:
                raise AssertionError("changed legacy recovery behavior was not rejected")
    assert MODULE.model_configuration_budget(config, gps) == 1800
    model_start = gps.index("static constexpr uint32_t GPS_MODEL_FIRST_SET_WAIT_MS =")
    model_end = gps.index("\n/* Bounded recovery", model_start)
    model = gps[model_start:model_end]
    for old, new in (
        ("6u * GPS_DYNMODEL_MAX_WAIT_MS", "7u * GPS_DYNMODEL_MAX_WAIT_MS"),
        ("deadline - (uint32_t)millis()", "deadline"),
        ("attempt < 3", "attempt < 4"),
        ("wait_ms != 0 && gnss.setDynamicModel", "gnss.setDynamicModel"),
        ("gps_model_remaining_ms(deadline, 1u) != 0", "true"),
        ("delay(wait_ms);", "delay(20);"),
    ):
        # Change every matching final check so both preprocessor branches are
        # covered; the hash contract must reject even a one-call bypass.
        changed_model = model.replace(old, new)
        assert changed_model != model
        changed_gps = gps[:model_start] + changed_model + gps[model_end:]
        try:
            MODULE.model_configuration_budget(config, changed_gps)
        except AssertionError as exc:
            assert "review" in str(exc)
        else:
            raise AssertionError("changed model deadline behavior was not rejected")

    assert MODULE.shutdown_configuration_budget(policy, gps) == 1500
    # Scope these mutations to shutdown: the model helper also subtracts millis.
    shutdown_start = gps.index("static uint16_t gps_backup_config_remaining_ms(")
    shutdown = gps[shutdown_start:]
    for changed_shutdown in (
        shutdown.replace("deadline - (uint32_t)millis()", "deadline", 1),
        shutdown.replace("gps_backup_config_remaining_ms(deadline) != 0;",
                         "true;", 1),
    ):
        assert changed_shutdown != shutdown
        changed_gps = gps[:shutdown_start] + changed_shutdown
        try:
            MODULE.shutdown_configuration_budget(policy, changed_gps)
        except AssertionError as exc:
            assert "review" in str(exc)
        else:
            raise AssertionError("changed shutdown deadline behavior was not rejected")

    assert MODULE.shutdown_marker_combined_budget(policy, gps) == 2000
    discard_start = gps.index("static bool gps_uart_discard_buffered_input(")
    marker_wait_start = gps.index("static bool gps_wait_for_nav_eoe_marker(")
    discard = gps[discard_start:marker_wait_start]
    marker_wait_end = gps.index("\nstatic bool gps_uart_activity_seen(", marker_wait_start)
    marker_wait = gps[marker_wait_start:marker_wait_end]
    quiesce_start = gps.index("gps_quiescence_result_t gps_ublox_quiesce(void)")
    quiesce = gps[quiesce_start:]
    marker_mutations = (
        gps[:marker_wait_start]
        + marker_wait.replace(
            "static bool gps_wait_for_nav_eoe_marker(uint32_t deadline)",
            "static bool gps_wait_for_nav_eoe_marker(uint32_t window_ms)",
            1,
        ).replace(
            "uint32_t last_kick = millis();",
            "uint32_t deadline = millis() + window_ms;\n    uint32_t last_kick = millis();",
            1,
        )
        + gps[marker_wait_end:],
        gps[:discard_start]
        + discard.replace(
            "static bool gps_uart_discard_buffered_input(uint32_t deadline)",
            "static bool gps_uart_discard_buffered_input(uint32_t window_ms)",
            1,
        ).replace(
            "while (GPS_SERIAL.available() > 0)",
            "uint32_t deadline = millis() + window_ms;\n    "
            "while (GPS_SERIAL.available() > 0)",
            1,
        )
        + gps[marker_wait_start:],
        gps[:discard_start]
        + discard.replace(
            "if ((int32_t)(deadline - (uint32_t)millis()) <= 0) return false;",
            "",
            1,
        )
        + gps[marker_wait_start:],
        gps[:discard_start]
        + discard.replace(
            "return (int32_t)(deadline - (uint32_t)millis()) > 0;",
            "return true;",
            1,
        )
        + gps[marker_wait_start:],
        gps[:quiesce_start]
        + quiesce.replace(
            "const uint32_t marker_deadline = (uint32_t)millis() +\n"
            "            GPS_BACKUP_CONFIG_BUDGET_MS + GPS_BACKUP_MARKER_WAIT_MS;\n"
            "        bool marker_armed = gps_configure_backup_marker();",
            "bool marker_armed = gps_configure_backup_marker();\n"
            "        const uint32_t marker_deadline = (uint32_t)millis() +\n"
            "            GPS_BACKUP_CONFIG_BUDGET_MS + GPS_BACKUP_MARKER_WAIT_MS;",
            1,
        ),
        gps[:quiesce_start]
        + quiesce.replace(
            "GPS_BACKUP_CONFIG_BUDGET_MS + GPS_BACKUP_MARKER_WAIT_MS;",
            "GPS_BACKUP_CONFIG_BUDGET_MS + GPS_BACKUP_MARKER_WAIT_MS + 1u;",
            1,
        ),
        gps[:quiesce_start]
        + quiesce.replace(
            "gps_wait_for_nav_eoe_marker(marker_deadline)",
            "gps_wait_for_nav_eoe_marker((uint32_t)millis() + GPS_BACKUP_MARKER_WAIT_MS)",
            1,
        ),
        gps[:quiesce_start]
        + quiesce.replace(
            "marker_armed = gps_uart_discard_buffered_input(marker_deadline) &&\n"
            "                gps_wait_for_nav_eoe_marker(marker_deadline);",
            "marker_armed = gps_wait_for_nav_eoe_marker(marker_deadline);",
            1,
        ),
        gps[:quiesce_start]
        + quiesce.replace(
            "marker_armed = gps_uart_discard_buffered_input(marker_deadline);",
            "(void)gps_uart_discard_buffered_input(marker_deadline);",
            1,
        ),
        gps[:marker_wait_start]
        + marker_wait.replace(
            "if ((int32_t)(deadline - (uint32_t)millis()) <= 0) return false;",
            "",
            1,
        )
        + gps[marker_wait_end:],
        gps[:marker_wait_start]
        + marker_wait.replace(
            "if ((int32_t)(deadline - (uint32_t)millis()) <= 0) return false;",
            "",
            2,
        )
        + gps[marker_wait_end:],
    )
    for changed_gps in marker_mutations:
        assert changed_gps != gps
        try:
            MODULE.shutdown_marker_combined_budget(policy, changed_gps)
        except AssertionError as exc:
            assert "review" in str(exc)
        else:
            raise AssertionError("changed combined marker deadline was not rejected")

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "audit.json"
        MODULE.write_create_once(output, b"first\n")
        assert output.read_bytes() == b"first\n"
        try:
            MODULE.write_create_once(output, b"second\n")
        except SystemExit:
            pass
        else:
            raise AssertionError("evidence overwrite was not rejected")
        assert output.read_bytes() == b"first\n"

    print(
        "PASS: GNSS backup subtotals include pinned-library retries; incomplete "
        "path timing and unmeasured RESET_N-held current still block launch"
    )


if __name__ == "__main__":
    main()
