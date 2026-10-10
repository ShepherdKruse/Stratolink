#!/usr/bin/env python3
"""Screen GNSS shutdown recovery and terminal containment from flight source.

This is a conservative source-bound model, not a substitute for the final
supercapacitor / PPK2 capture. It uses the exact part's 0.8 F datasheet minimum,
counts configured waits and delays, and includes two RESET_N recovery paths.
The timing subtotal excludes transport and execution overhead; it is not a
complete wall-clock upper bound. A terminal PMREQ failure is modeled both as the former
awake-receiver hazard and as the new RESET_N-held posture. The latter remains
launch-blocking because its exact-assembly current has not been measured.
The legacy compatibility release subtotal does not describe supervised startup;
that path's timing and energy are outside this screen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "firmware/include/gps_backup_policy.h"
CONFIG = ROOT / "firmware/include/config.h"
GPS = ROOT / "firmware/src/gps_ublox.cpp"
MAIN = ROOT / "firmware/src/main.cpp"
GNSS_LIBRARY = ROOT / "firmware/.pio/libdeps/stratolink/SparkFun u-blox GNSS v3"
GNSS_CPP = GNSS_LIBRARY / "src/u-blox_GNSS.cpp"
GNSS_HEADER = GNSS_LIBRARY / "src/SparkFun_u-blox_GNSS_v3.h"

CAPACITANCE_F = 0.8
CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V = 3.32
OUTPUT_V = 3.3
GNSS_CURRENT_A = 0.030
# Existing flight model uses 5 mA for the active MCU. Double that allowance to
# cover control/I/O overhead during the exceptional recovery path.
ACTIVE_CONTROL_CURRENT_A = 0.010
CONVERSION_EFFICIENCY = 0.85
RESET_PULLUP_OHMS = 10_000.0
GNSS_INTERNAL_RESET_PULLUP_MIN_OHMS = 7_000.0
GNSS_INTERNAL_RESET_PULLUP_MAX_OHMS = 13_000.0


def define_u(text: str, name: str) -> int:
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(\d+)u?\b", text, re.M)
    if not match:
        raise AssertionError(f"missing integer define {name}")
    return int(match.group(1))


def cap_reserve_j(start_v: float) -> float:
    return 0.5 * CAPACITANCE_F * (
        start_v**2 - CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V**2
    )


def load_energy_j(duration_ms: int) -> float:
    current = GNSS_CURRENT_A + ACTIVE_CONTROL_CURRENT_A
    return OUTPUT_V * current * (duration_ms / 1000.0) / CONVERSION_EFFICIENCY


def sleep_load_energy_j(current_a: float, duration_s: int) -> float:
    return OUTPUT_V * current_a * duration_s / CONVERSION_EFFICIENCY


def begin_connection_attempts(cpp: str, header: str) -> int:
    """Bind the reviewed serial-begin -> init -> isConnected retry contract.

    Source hashes deliberately require re-review if this dependency behavior
    changes. Counting call sites alone would miss loops or changed wait args.
    Each reviewed serial isConnected call performs one getVal8(maxWait).
    """
    for source, start, end, expected in (
        (cpp, "bool DevUBLOXGNSS::init(", "// Allow the user to change I2C",
         "d606ebe2e437eb34208ecbc90bbb174bb47fd70e0df3289bdaab26880b15d7f1"),
        (cpp, "bool DevUBLOXGNSS::isConnected(",
         "// Enable or disable the printing of sent/response",
         "2ed74e62dbb3fe39df8e2196581043d18985ce7a65868e37baefe36864c1d955"),
        (header, "bool begin(Stream &serialPort,", "\nprivate:",
         "1d90b62b053b37f29033bd19f35e2236180e03829907e8437e3e60a9e5316713"),
    ):
        first = source.index(start)
        section = source[first:source.index(end, first)].strip()
        assert hashlib.sha256(section.encode()).hexdigest() == expected, (
            "review SparkFun serial begin retry/wait behavior before updating audit"
        )
    return 3


def shutdown_configuration_budget(policy: str, gps: str) -> int:
    """Bind frame completion and CFG calls to their reviewed shared deadline."""
    for start, end, expected in (
        ("static uint16_t gps_backup_config_remaining_ms(",
         "\nstatic bool gps_configure_backup_marker(",
         "6129345a06293bce40ee2861b03436d922fd309a5ede932cd53ccabf14a42f49"),
        ("static bool gps_configure_backup_marker(",
         "\ngps_quiescence_result_t gps_ublox_quiesce(",
         "f5839b0e146d8b4415d30c879270e52d6081c20999ee22a173e22fbaa6817d4f"),
    ):
        first = gps.index(start)
        section = gps[first:gps.index(end, first)].strip()
        assert hashlib.sha256(section.encode()).hexdigest() == expected, (
            "review GNSS shared configuration deadline before updating audit"
        )
    budget = define_u(policy, "GPS_BACKUP_CONFIG_BUDGET_MS")
    assert 0 < budget <= 65535
    assert "bool marker_armed = gps_configure_backup_marker();" in gps
    return budget


def shutdown_marker_combined_budget(policy: str, gps: str) -> int:
    """Bind the absolute deadline through discard, marker wait, and PMREQ."""
    for start, end, expected in (
        ("static bool gps_uart_discard_buffered_input(",
         "\nstatic bool gps_wait_for_nav_eoe_marker(",
         "921aa47877fd463f630eca9722bb921230ac661e91358cdc30932f499a90a633"),
        ("static bool gps_wait_for_nav_eoe_marker(",
         "\nstatic bool gps_uart_activity_seen(",
         "494a89a9d1d5594e759296fb5e2452b876932967f5063a1b86847826244f58c9"),
        ("        const uint32_t marker_deadline =",
         "            GPS_SERIAL.flush();",
         "f1f64e1a07dc7b1815740e963571aaf1eebd6f835414295c708e0a697f5ca297"),
    ):
        try:
            first = gps.index(start)
            last = gps.index(end, first) + (len(end) if end.endswith(";") else 0)
        except ValueError as exc:
            raise AssertionError(
                "review GNSS combined CFG/marker deadline before updating audit"
            ) from exc
        section = gps[first:last].strip()
        assert hashlib.sha256(section.encode()).hexdigest() == expected, (
            "review GNSS combined CFG/marker deadline before updating audit"
        )
    configuration_ms = define_u(policy, "GPS_BACKUP_CONFIG_BUDGET_MS")
    marker_ms = define_u(policy, "GPS_BACKUP_MARKER_WAIT_MS")
    combined_ms = configuration_ms + marker_ms
    assert 0 < configuration_ms < combined_ms <= 0x7FFFFFFF
    return combined_ms


def model_configuration_budget(config: str, gps: str) -> int:
    """Bind legacy public/shutdown model gates, not supervised startup or return time."""
    for start, end, expected in (
        ("static constexpr uint32_t GPS_MODEL_FIRST_SET_WAIT_MS =",
         "\nbool gps_ublox_set_airborne_4g(void)",
         "51a92cabfe3cc4203c8ee6156313a545c96013f475b315d7e46e6ec41543b55d"),
        ("bool gps_ublox_set_airborne_4g(void)",
         "\n/* Bounded recovery",
         "8d1eb854030b59be9c64f06268440f4db696c2033a73f6057b4474c1c41ecc71"),
    ):
        first = gps.index(start)
        section = gps[first:gps.index(end, first)].strip()
        assert hashlib.sha256(section.encode()).hexdigest() == expected, (
            "review GNSS shared model deadline before updating audit"
        )
    # The bound source derives its first SET cap from four configured slices
    # and its total shared gate from six; all later SET/read caps use one slice.
    wait_ms = define_u(config, "GPS_DYNMODEL_MAX_WAIT_MS")
    assert 0 < wait_ms <= 65535 // 6
    return 6 * wait_ms


def legacy_recovery_contract(gps: str) -> None:
    """Pin legacy reset/release waits and gates independently of startup helpers."""
    # The reset body is byte-identical to the reviewed pre-extension path.
    # Opt-in acquisition energy remains outside this shutdown-only screen.
    for signature, expected in (
        ("static bool gps_ublox_reset(void)",
         "32eb4c5a985c5c2be6328d73c8cb829219c3f809abe8003bf8157d57e4757b44"),
        ("gps_recovery_result_t gps_ublox_prepare_acquisition(void)",
         "7547e80363087fbe76ad78cac4808c3a2ac6762d563b67b736f4dbb932518625"),
    ):
        first = gps.index(signature)
        section = gps[first:gps.index("\n}\n", first) + 2]
        assert hashlib.sha256(section.encode()).hexdigest() == expected, (
            "review legacy GNSS reset/release waits and gates before updating audit"
        )


def build_audit() -> dict[str, object]:
    policy = POLICY.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    gps = GPS.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    assert "version=3.1.13\n" in (
        GNSS_LIBRARY / "library.properties"
    ).read_text(encoding="utf-8")
    assert "sparkfun/SparkFun u-blox GNSS v3@3.1.13" in (
        ROOT / "firmware/platformio.ini"
    ).read_text(encoding="utf-8")
    begin_attempts = begin_connection_attempts(
        GNSS_CPP.read_text(encoding="utf-8"),
        GNSS_HEADER.read_text(encoding="utf-8"),
    )

    attempts = define_u(policy, "GPS_BACKUP_MAX_ATTEMPTS")
    confirm_ms = define_u(policy, "GPS_BACKUP_CONFIRM_MS")
    reset_floor_mv = define_u(policy, "GPS_BACKUP_RESET_FLOOR_MV")
    acquisition_floor_mv = define_u(config, "GPS_ACQ_FLOOR_MV")
    dyn_wait_ms = define_u(config, "GPS_DYNMODEL_MAX_WAIT_MS")
    begin_wait_ms = define_u(config, "GPS_BEGIN_MAX_WAIT_MS")
    normal_sleep_s = max(
        define_u(config, name)
        for name in (
            "SLEEP_INTERVAL_FULL_SEC",
            "SLEEP_INTERVAL_REDUCED_SEC",
            "SLEEP_INTERVAL_NO_GPS_SEC",
            "SLEEP_INTERVAL_EMERGENCY_SEC",
        )
    )

    # Pin every structural input to the current implementation. If the source
    # changes, the audit fails instead of silently preserving an obsolete bound.
    configuration_budget_ms = shutdown_configuration_budget(policy, gps)
    combined_marker_budget_ms = shutdown_marker_combined_budget(policy, gps)
    dynamic_model_ms = model_configuration_budget(config, gps)
    # These legacy functions retain synchronous begin/model calls. Production
    # init/get_fix now use separate supervised helpers outside this screen.
    legacy_recovery_contract(gps)
    assert "delay(10);" in gps
    assert "!gps_backup_reset_allowed(power_adc_read_vSTOR_mv())" in gps
    assert "gps_quiescence_result_t gps_ublox_quiesce(void)" in gps
    assert "gps_assert_reset_hold();" in gps
    assert "return GPS_QUIESCENCE_RESET_HELD;" in gps
    assert "GPS_BACKUP_RETRY_SLEEP_MS" not in policy
    assert "GPS_BACKUP_RETRY_SLEEP_MS" not in main
    assert "if (!gps_quiesced && sleep_ms >" not in main
    assert re.search(
        r"if\s*\(!gps_attempted_this_cycle\)\s*\{\s*"
        r"gps_quiescence\s*=\s*gps_ublox_quiesce\(\);\s*\}",
        main,
    )
    assert "gps_ublox_sleep()" not in main
    assert "gps_ublox_assert_reset_early();" in main
    assert "!gps_attempted_this_cycle ||" not in main

    wake_settle_ms = 10
    reset_pulse_ms = 20
    reset_boot_ms = 1000
    # Current fallback performs set + readback. The macro-defined branch also
    # polls before setting. These counts describe possible operations, not
    # independent waits: both branches share the same gate, including pauses.
    model_body = gps.split("bool gps_ublox_set_airborne_4g(void) {", 1)[1]
    model_body = model_body.split("/* Bounded recovery", 1)[0]
    macro_body, fallback_body = model_body.split("#else", 1)
    fallback_body, shared_body = fallback_body.split("#endif", 1)
    operations = lambda body: len(re.findall(
        r"gnss\.(?:getDynamicModel|setDynamicModel)\(", body
    ))
    macro_operations = operations(macro_body) + operations(shared_body)
    fallback_operations = operations(fallback_body) + operations(shared_body)
    assert (macro_operations, fallback_operations) == (3, 2)

    confirmation_attempt_ms = (
        wake_settle_ms
        + combined_marker_budget_ms
        + confirm_ms
    )
    hardware_reset_ms = (
        reset_pulse_ms + reset_boot_ms
        + begin_attempts * begin_wait_ms + dynamic_model_ms
    )
    hardware_resets = attempts - 1
    full_recovery_ms = (
        attempts * confirmation_attempt_ms + hardware_resets * hardware_reset_ms
    )

    full_energy = load_energy_j(full_recovery_ms)
    low_rail_attempt_energy = load_energy_j(confirmation_attempt_ms)
    acquisition_reserve = cap_reserve_j(acquisition_floor_mv / 1000.0)
    reset_reserve = cap_reserve_j(reset_floor_mv / 1000.0)
    full_charge_reserve = cap_reserve_j(4.66)
    awake_sleep_energy = sleep_load_energy_j(GNSS_CURRENT_A, normal_sleep_s)
    board_reset_pullup_current_a = OUTPUT_V / RESET_PULLUP_OHMS
    reset_pullup_best_case_current_a = OUTPUT_V * (
        1.0 / RESET_PULLUP_OHMS
        + 1.0 / GNSS_INTERNAL_RESET_PULLUP_MAX_OHMS
    )
    reset_pullup_worst_case_current_a = OUTPUT_V * (
        1.0 / RESET_PULLUP_OHMS
        + 1.0 / GNSS_INTERNAL_RESET_PULLUP_MIN_OHMS
    )
    reset_pullup_best_case_energy = sleep_load_energy_j(
        reset_pullup_best_case_current_a, normal_sleep_s
    )
    reset_pullup_worst_case_energy = sleep_load_energy_j(
        reset_pullup_worst_case_current_a, normal_sleep_s
    )
    structural_gates = {
        "reset_floor_above_acquisition_floor": reset_floor_mv > acquisition_floor_mv,
        "one_low_rail_attempt_subtotal_fits_acquisition_reserve": (
            low_rail_attempt_energy < acquisition_reserve
        ),
        "full_recovery_subtotal_fits_reset_floor_reserve": full_energy < reset_reserve,
        "reset_gate_wired_before_hardware_reset": True,
        "normal_cycle_has_at_most_one_shutdown_recovery_call": True,
        "terminal_failure_has_no_cross_cycle_fast_retry": True,
        "terminal_failure_asserts_reset_hold": True,
        "legacy_compatibility_reset_hold_release_is_rail_gated": True,
    }
    if not all(structural_gates.values()):
        raise AssertionError(
            f"GNSS backup structural gate failed: {structural_gates}"
        )
    measurement_gates = {
        "reset_held_current_measured_on_exact_assembly": False,
        "reset_held_terminal_sleep_charge_positive": False,
        "complete_recovery_time_and_energy_qualified": False,
    }
    gates = {**structural_gates, **measurement_gates}

    return {
        "status": "BLOCKED_RESET_HELD_CURRENT_MEASUREMENT_REQUIRED",
        "scope": {
            "energy_screen": "legacy shutdown recovery and terminal containment",
            "release_subtotal_function": "gps_ublox_prepare_acquisition",
            "supervised_startup_included": False,
            "supervised_startup_time_bound_ms": None,
            "supervised_startup_energy_qualified": False,
        },
        "source": {
            "gps_backup_policy": str(POLICY.relative_to(ROOT)),
            "config": str(CONFIG.relative_to(ROOT)),
            "gps_implementation": str(GPS.relative_to(ROOT)),
            "gnss_library_implementation": str(GNSS_CPP.relative_to(ROOT)),
            "gnss_library_version": "3.1.13",
        },
        "timing_subtotal_ms": {
            "confirmation_attempt": confirmation_attempt_ms,
            "hardware_reset_and_reconfigure": hardware_reset_ms,
            "full_three_attempt_two_reset_path": full_recovery_ms,
            "low_rail_path_before_reset_suppression": confirmation_attempt_ms,
            "legacy_compatibility_reset_hold_release_and_uart_reinit": (
                reset_boot_ms + begin_attempts * begin_wait_ms
            ),
        },
        "timing_assumptions": {
            "begin_connection_attempts": begin_attempts,
            "shared_configuration_budget_ms": configuration_budget_ms,
            "configuration_subcap_ms": configuration_budget_ms,
            "combined_config_marker_deadline_ms": combined_marker_budget_ms,
            "model_operations_per_attempt": {
                "macro_defined_branch": macro_operations,
                "fallback_branch": fallback_operations,
            },
            "shared_model_budget_ms": dynamic_model_ms,
            "model_first_set_wait_cap_ms": 4 * dyn_wait_ms,
            "model_later_set_and_read_wait_cap_ms": dyn_wait_ms,
            "model_branch_subtotal_ms": {
                "macro_defined_branch": dynamic_model_ms,
                "fallback_branch": dynamic_model_ms,
            },
            "model_retry_pauses_within_shared_budget": True,
            "fallback_full_path_subtotal_ms": full_recovery_ms,
            "fallback_never_set_ack_subtotal_ms": dynamic_model_ms,
            # Historical comparator: three 300 ms SET timeouts + 20 ms pauses.
            "prior_fallback_never_set_ack_subtotal_ms": 960,
            "complete_wall_clock_upper_bound": False,
            "excluded": [
                "UART command transmission and flush duration outside response waits",
                "driver/parser/allocation/ADC/GPIO execution and polling-loop overshoot",
                "interrupt latency and other active control work",
            ],
        },
        "energy_model": {
            "basis": "legacy shutdown configured-wait/delay subtotal; transport/execution overhead not yet quantified",
            "capacitance_f": CAPACITANCE_F,
            "conservative_flight3_reported_plateau_floor_v": (
                CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V
            ),
            "output_v": OUTPUT_V,
            "gnss_current_ma": GNSS_CURRENT_A * 1000,
            "active_control_allowance_ma": ACTIVE_CONTROL_CURRENT_A * 1000,
            "conversion_efficiency": CONVERSION_EFFICIENCY,
            "acquisition_floor_v": acquisition_floor_mv / 1000.0,
            "reset_floor_v": reset_floor_mv / 1000.0,
            "acquisition_floor_reserve_j": round(acquisition_reserve, 6),
            "reset_floor_reserve_j": round(reset_reserve, 6),
            "one_low_rail_attempt_j": round(low_rail_attempt_energy, 6),
            "full_recovery_j": round(full_energy, 6),
            "reset_floor_margin_j": round(reset_reserve - full_energy, 6),
            "reset_floor_margin_percent_of_recovery": round(
                100.0 * (reset_reserve - full_energy) / full_energy, 3
            ),
            "normal_terminal_sleep_s": normal_sleep_s,
            "full_charge_to_reported_plateau_reserve_j": round(
                full_charge_reserve, 6
            ),
            "uncontained_awake_receiver": {
                "current_ma": GNSS_CURRENT_A * 1000,
                "sleep_energy_j": round(awake_sleep_energy, 6),
                "fraction_of_full_charge_reserve": round(
                    awake_sleep_energy / full_charge_reserve, 3
                ),
            },
            "reset_held_receiver": {
                "board_r18_pullup_ohms": int(RESET_PULLUP_OHMS),
                "max_m10s_internal_pullup_ohms_range": [
                    int(GNSS_INTERNAL_RESET_PULLUP_MIN_OHMS),
                    int(GNSS_INTERNAL_RESET_PULLUP_MAX_OHMS),
                ],
                "board_r18_only_current_ma": round(
                    board_reset_pullup_current_a * 1000, 6
                ),
                "parallel_pullups_best_case_current_ma": round(
                    reset_pullup_best_case_current_a * 1000, 6
                ),
                "parallel_pullups_worst_case_current_ma": round(
                    reset_pullup_worst_case_current_a * 1000, 6
                ),
                "parallel_pullups_best_case_sleep_energy_j": round(
                    reset_pullup_best_case_energy, 6
                ),
                "parallel_pullups_worst_case_sleep_energy_j": round(
                    reset_pullup_worst_case_energy, 6
                ),
                "parallel_pullups_best_case_fraction_of_full_charge_reserve": round(
                    reset_pullup_best_case_energy / full_charge_reserve, 3
                ),
                "parallel_pullups_worst_case_fraction_of_full_charge_reserve": round(
                    reset_pullup_worst_case_energy / full_charge_reserve, 3
                ),
                "receiver_reset_held_current_ma": None,
                "total_reset_held_sleep_energy_j": None,
                "measurement_qualified": False,
            },
        },
        "gates": gates,
        "structural_gates": structural_gates,
        "measurement_gates": measurement_gates,
        "limits": [
            "The 4300 ms legacy gps_ublox_prepare_acquisition release subtotal is not a supervised startup bound; production init/get_fix timing and energy are outside this screen.",
            "Configured waits/delays and conservative currents form an incomplete energy screen, not a complete worst-case timing or energy bound.",
            "The combined CFG/first-marker allowance is unchanged at 2000 ms, but fast-CFG missing-marker paths can observe the configured receiver up to roughly 1400 ms longer than the former fixed 500 ms window; unchanged aggregate arithmetic does not prove identical branch energy.",
            "The shutdown marker and discard loops reject expired reads, but synchronous library UART enqueue/flush and execution overhead remain outside the configured subtotal. The 350 ms silence observation does not independently prove physical standby or low current.",
            "The legacy public/shutdown shared model deadline gates success acceptance and starting further operations; it does not bound function return time because library UART enqueue and RX draining can overrun supplied waits.",
            f"The fallback never-ACK SET branch has a {dynamic_model_ms} ms configured subtotal, compared with the former 960 ms; aggregate maximum improvement does not imply improvement in every fault branch.",
            "The arithmetic reserve checks cover only the reported subtotal; passing them cannot qualify the excluded UART/execution overhead or a longer acquisition window.",
            "Final proof requires PPK2 phase-current and VSTOR sag capture with the exact flight supercapacitor installed, including measured capacitance and ESR.",
            "Terminal PMREQ failure now asserts and holds RESET_N instead of leaving the receiver awake; that is electrical containment, not an energy qualification.",
            "The board's 10 kOhm R18 and the MAX-M10S 7-13 kOhm internal RESET_N pullup are modeled in parallel; the receiver's remaining reset-held supply current is absent from qualified evidence and remains null rather than guessed.",
            "Persistent-failure survival requires exact-assembly RESET_N-held current plus VSTOR/capacitor behavior over the complete 1200 s cadence; the launch gate remains failed until that measurement is bound here.",
        ],
    }


def write_create_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise SystemExit(f"refusing to overwrite evidence: {path}") from exc
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = build_audit()
    payload = (json.dumps(audit, indent=2, sort_keys=True) + "\n").encode()
    if args.output:
        write_create_once(args.output, payload)
    else:
        print(payload.decode(), end="")


if __name__ == "__main__":
    main()
