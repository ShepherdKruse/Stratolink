#!/usr/bin/env python3
"""Exercise post-poll fix admission against real driver code under ASan/UBSan.

Preserves all eleven behaviors from the shared admission experiment and adds external
ADC latency, interrupt and zero/fault cases. Five compiled mutants must fail
named behaviors before production passes. Only external boundaries are fake;
this neither bounds the pinned GNSS transport nor qualifies physical energy.
The shared experiment's ideal configuration packets and poll waits are adapted
to the supervised startup interface and deadline measured from function entry.
Use --mutation NAME to expose one expected RED run without editing production.
"""

import argparse
import hashlib

import gps_post_poll_admission_experiment as experiment


harness = experiment.harness

ADC_BOUNDARY = r"""
static uint32_t adc_delay_ms = 0u;
static bool adc_latches_mission = false, adc_returns_zero = false;
uint16_t power_adc_read_vSTOR_mv() {
    // Entry/model checks see the healthy rail. The hazard begins only once
    // the second external poll has delivered an advancing, usable PVT.
    if (polls_this_call >= 2u) {
        delay(adc_delay_ms);
        if (adc_latches_mission) mission_pending = true;
        if (adc_returns_zero) return 0u;
    }
    return rail_mv;
}
"""

ADC_CASES = r"""
    // Break caught: checking the deadline before a potentially slow ADC read.
    // Before ADC: 999 ms elapsed; after its 1 ms delay: exactly the deadline.
    reset_case(HEALTHY);
    second_poll_wait_ms = 786u; // 13 ms entry wake + 100 + 100 + 786 = 999.
    adc_delay_ms = 1u;
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("ADC consumes last millisecond so PVT cannot be published",
          rejected(returned, fix, 0u, 0u) && s_gps_diag.no_fresh_cycles == 1u,
          returned, fix);
    adc_delay_ms = 0u;

    // Break caught: checking mission authority only before sampling the rail.
    reset_case(HEALTHY);
    adc_latches_mission = true;
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("freefall arriving during ADC aborts instead of publishing PVT",
          rejected(returned, fix, 0u, 1u) && s_gps_diag.no_fresh_cycles == 0u,
          returned, fix);
    adc_latches_mission = false;

    // Break caught: accepting an ADC failure/sentinel as usable rail evidence.
    reset_case(HEALTHY);
    adc_returns_zero = true;
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("zero ADC result aborts and counts power not success",
          rejected(returned, fix, 1u, 0u) && s_gps_diag.no_fresh_cycles == 0u,
          returned, fix);
    adc_returns_zero = false;

"""

POWER_GUARD = """                        if (power_adc_read_vSTOR_mv() < (extended ? 4400u : GPS_ACQ_FLOOR_MV)) {
                            power_aborted = true;
                            break;
                        }
"""
MISSION_GUARD = """                        if (power_manager_freefall_pending()) {
                            mission_aborted = true;
                            break;
                        }
"""
DEADLINE_GUARD = """                        if (!acquisition_budget_available()) {
                            break;
                        }
"""
GUARDS = POWER_GUARD + MISSION_GUARD + DEADLINE_GUARD
RESPONSE_MISSION_GUARD = """            if (!power_aborted && power_manager_freefall_pending()) {
                mission_aborted = true;
            }
"""

# Exact text identifies the compile-time mutation site only. Assertions are
# on the real driver's returned fix, invalidation, counters and reset behavior.
MUTATIONS = {
    "missing_power_guard": (
        MISSION_GUARD + DEADLINE_GUARD,
        ("rail sag during valid poll aborts and counts power not success",
         "zero ADC result aborts and counts power not success"),
    ),
    "missing_mission_guard": (
        POWER_GUARD + DEADLINE_GUARD,
        ("freefall during valid poll aborts and counts mission not success",
         "freefall arriving during ADC aborts instead of publishing PVT"),
    ),
    "missing_deadline_guard": (
        POWER_GUARD + MISSION_GUARD,
        ("PVT returned after deadline is rejected and invalidated",
         "PVT returned exactly at deadline is rejected and invalidated",
         "PVT returned at wrapped deadline is rejected and invalidated"),
    ),
    "deadline_equality_accepted": (
        POWER_GUARD + MISSION_GUARD + DEADLINE_GUARD.replace(
            "!acquisition_budget_available()", "(int32_t)(deadline - (uint32_t)millis()) < 0"),
        ("PVT returned exactly at deadline is rejected and invalidated",
         "PVT returned at wrapped deadline is rejected and invalidated"),
    ),
    "deadline_before_adc": (
        DEADLINE_GUARD + POWER_GUARD + MISSION_GUARD,
        ("ADC consumes last millisecond so PVT cannot be published",),
    ),
}


def configure_harness() -> None:
    harness.GNSS = experiment.GNSS
    old_adc = "uint16_t power_adc_read_vSTOR_mv() { return rail_mv; }"
    summary = '    std::printf("SUMMARY: %u checks, %u failures; external-boundary model only'
    assert experiment.TEST.count(old_adc) == experiment.TEST.count(summary) == 1
    harness.TEST = experiment.TEST.replace(old_adc, ADC_BOUNDARY, 1).replace(
        summary, ADC_CASES + summary, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutation", choices=MUTATIONS)
    args = parser.parse_args()
    inputs = [harness.SOURCE, *(harness.ROOT / f"firmware/src/{name}.cpp"
              for name in ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
              harness.ROOT / "analysis/diagnostics/gps_post_poll_admission_experiment.py"]
    before = {path: path.read_bytes() for path in inputs}
    source = before[harness.SOURCE].decode("utf-8")
    assert source.count(GUARDS) == 1, "review changed admission mutation target"
    configure_harness()
    for name in (args.mutation,) if args.mutation else MUTATIONS:
        replacement, expected_failures = MUTATIONS[name]
        mutated = source.replace(GUARDS, replacement, 1)
        if name in ("missing_deadline_guard", "deadline_equality_accepted"):
            # Deadline admission is now redundant immediately after parsing,
            # after periodic ADC, and before publishing. Mutate the complete
            # post-parser admission failure mode, not just one redundant site.
            start = mutated.index("(void)gnss.checkUblox(UBX_CLASS_NAV, UBX_NAV_PVT);")
            end = mutated.index("        if (pvt_received) {", start)
            post_parser = mutated[start:end]
            boundary = "if (!acquisition_budget_available()) break;"
            assert boundary in post_parser
            mutated = mutated[:start] + post_parser.replace(boundary, "") + mutated[end:]
        if name == "missing_mission_guard":
            assert mutated.count(RESPONSE_MISSION_GUARD) == 1
            mutated = mutated.replace(RESPONSE_MISSION_GUARD, "", 1)
        result = harness.run(mutated, "")
        assert result.returncode == 1 and not result.stderr, result
        for behavior in expected_failures:
            assert f"[FAIL] {behavior}:" in result.stdout, result.stdout
        assert all(path.read_bytes() == payload for path, payload in before.items())
        if args.mutation:
            print(result.stdout, end="")
            raise SystemExit(result.returncode)
        print(f"PASS: compiled {name} mutant rejected by:")
        for behavior in expected_failures:
            print(f"  - {behavior}")

    result = harness.run(source, "")
    print(result.stdout, end="")
    assert result.returncode == 0 and not result.stderr, result
    assert result.stdout.count("[PASS]") == 14, result.stdout
    assert all(path.read_bytes() == payload for path, payload in before.items()), (
        "production input or shared admission experiment changed during test")
    print("PASS: 14 real-driver cases; 5 compiled behavioral mutants rejected; "
          "ASan/UBSan clean; production inputs and shared admission experiment unchanged during run")
    print("driver_sha256=" + hashlib.sha256(before[harness.SOURCE]).hexdigest())


if __name__ == "__main__":
    main()
