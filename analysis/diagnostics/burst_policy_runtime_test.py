#!/usr/bin/env python3
"""Execute production burst/chatter branches with host hardware boundaries.

Extracted unchanged: loop-top classification, spurious and optical early returns,
burst admission/cooldown, post-GNSS freefall handoff, burst exit/sleep selection,
atomic ISR/pending helpers, and LIS2DH12 acceleration-clear calculation. Link the
real region-age implementation. Controlled boundaries supply acceleration, time,
rail, joined/region state, and record quiescence/sleep requests.

Normal/burst sleep is observed only at initial budget selection. Subsequent
optical clamping, CTT/relay budget subtraction and radio quiescence are omitted;
selected budgets must not be interpreted as final sleep requests or timing.

The GPS/sensor/radio work between these branches is NOT executed: a work marker
only observes whether control reaches that boundary in burst or normal mode.
This is neither full-loop emulation, physical INT1/STOP1 validation, RF delivery,
nor an energy measurement. Config constants are production inputs; fixture
expectations are literal, independently counted sequences. Mutations alter only
temporary C++ compilation input and must compile and fail named assertions.
"""

from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def block(source: str, opening: str) -> str:
    if source.count(opening) != 1:
        raise AssertionError(f"production boundary is not unique: {opening}")
    start = source.index(opening)
    brace = source.index("{", start)
    depth = 0
    for end in range(brace, len(source)):
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
            if depth == 0:
                return source[start:end + 1]
    raise AssertionError(f"unterminated production boundary: {opening}")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise AssertionError(f"mutation boundary changed: {old}")
    return source.replace(old, new, 1)


def harness() -> str:
    main = (ROOT / "firmware/src/main.cpp").read_text()
    power = (ROOT / "firmware/src/power_manager.cpp").read_text()
    accel = (ROOT / "firmware/src/sensor_lis2dh12.cpp").read_text()
    # Keep the contiguous early-return/entry sequence, including optical policy.
    early = main[main.index("    bool freefall_wake ="):
                 main.index("    telemetry_input_t ti;", main.index("    bool freefall_wake ="))]
    handoff = block(main, "if (power_manager_freefall_pending()) {")
    end = main[main.index("    if (burst_mode) {"):
               main.index("    /* Account both active work", main.index("    if (burst_mode) {"))]
    atomic = "\n".join(block(power, name) for name in (
        "static void freefall_wake_callback(void)",
        "bool power_manager_did_wake_from_freefall(void)",
        "bool power_manager_freefall_pending(void)",
        "void power_manager_suppress_freefall_wake(bool on)",
    ))
    clear = "\n".join(block(accel, name) for name in (
        "bool sensor_lis2dh12_get_freefall_cleared(bool* cleared)",
        "bool sensor_lis2dh12_is_freefall_cleared(void)",
    ))
    return r'''
#include "config.h"
#include "gps_backup_policy.h"
#include "lis2dh12_conversion.h"
#include "optical_fault_policy.h"
#include "power_adc.h"
#include "region_manager.h"
#include <cstdio>
#include <cstdint>
#include <vector>

enum class Accel { Low, Cleared, Unavailable };
static Accel sample = Accel::Low;
static bool inject_during_sample;
static volatile bool s_burst_wake, s_ff_suppressed;
static volatile uint32_t s_burst_wake_generation;
static bool burst_mode, region_known = true, joined = true;
static uint16_t burst_cycles;
static uint8_t burst_cooldown, spurious_ff_streak, ff_suppress_clean;
static bool s_optical_quiescence_fault, optical_clear;
static uint8_t s_optical_quiet_retries;
static uint16_t rail_mv = 4660;
static uint32_t now_ms, region_fix_age_sec, persisted_age;
static unsigned acquisition_boundaries, work_boundaries, burst_work_boundaries;
static unsigned gps_quiesces, radio_sleeps, saves;
static std::vector<uint32_t> sleep_requests;
static std::vector<uint32_t> selected_sleep_budgets;
static unsigned checks, failures;
static const char* scenario;
static void freefall_wake_callback(void);

// Hardware sample boundary: actual clear magnitude/math and fail-open decision
// stay in the extracted production functions below.
static bool sensor_lis2dh12_read_accel_cm_s2(int16_t* x, int16_t* y, int16_t* z) {
    if (inject_during_sample) {
        inject_during_sample = false;
        freefall_wake_callback();
    }
    if (sample == Accel::Unavailable) return false;
    *x = *y = 0;
    *z = sample == Accel::Cleared ? 981 : 0;
    return true;
}
''' + clear + "\n" + atomic + r'''
static uint32_t millis() { return now_ms; }
bool lorawan_joined() { return joined; }
uint16_t power_adc_read_vSTOR_mv() { return rail_mv; }
power_tier_t power_adc_get_tier() { return POWER_TIER_FULL; }
uint32_t power_adc_get_sleep_interval_sec(power_tier_t) { return 1200; }
static void gps_ublox_quiesce() { ++gps_quiesces; }
void lorawan_sleep() { ++radio_sleeps; }
static void sensors_recover_i2c_bus() {}
static bool sensor_ltr390_quiesce() { return optical_clear; }
static void persist_region_lease_if_trusted() { persisted_age = region_fix_age_sec; ++saves; }
static void power_manager_sleep_ms(uint32_t duration) { sleep_requests.push_back(duration); }

struct Cycle {
    bool edge = false;
    Accel at_entry = Accel::Low, at_exit = Accel::Low;
    bool edge_after_acquisition = false, gps_attempted = true;
    uint16_t exit_rail = 4660;
    bool exit_joined = true, exit_region = true;
};
static void cycle(Cycle in = {}) {
    sample = in.at_entry;
    if (in.edge) freefall_wake_callback();
    const uint32_t cycle_started_ms = millis();
''' + early + r'''
    // Omitted real GPS/region segment boundary. The caller provides the resulting
    // state; no simulated acceptance is asserted as a production GNSS result.
    ++acquisition_boundaries;
    const bool gps_attempted_this_cycle = in.gps_attempted;
    now_ms += 1500;
    if (gps_attempted_this_cycle) gps_ublox_quiesce();
    region_known = in.exit_region;
    if (in.edge_after_acquisition) freefall_wake_callback();
''' + handoff + r'''
    ++work_boundaries;
    if (burst_mode) ++burst_work_boundaries;
    sample = in.at_exit;
    rail_mv = in.exit_rail;
    joined = in.exit_joined;
''' + end + r'''
    // Observation only: later production optical/CTT/relay/radio work is omitted.
    selected_sleep_budgets.push_back(sleep_ms);
}
static void expect(bool ok, const char* contract) {
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL %s: %s\n", scenario, contract); }
}
static void reset(const char* name) {
    scenario = name;
    sample = Accel::Low; inject_during_sample = false;
    s_burst_wake = s_ff_suppressed = false; s_burst_wake_generation = 0;
    burst_mode = false; region_known = joined = true; burst_cycles = 0;
    burst_cooldown = spurious_ff_streak = ff_suppress_clean = 0;
    s_optical_quiescence_fault = optical_clear = false; s_optical_quiet_retries = 0;
    rail_mv = 4660; now_ms = region_fix_age_sec = persisted_age = 0;
    acquisition_boundaries = work_boundaries = burst_work_boundaries = 0;
    gps_quiesces = radio_sleeps = saves = 0; sleep_requests.clear(); selected_sleep_budgets.clear();
}
static Cycle edge(Accel at_entry = Accel::Low, Accel at_exit = Accel::Low) {
    Cycle in; in.edge = true; in.at_entry = at_entry; in.at_exit = at_exit; return in;
}
static void capped_bout(Accel value) {
    cycle(edge(value, value));
    for (unsigned i = 1; i < 6; ++i) {
        Cycle in; in.at_entry = in.at_exit = value; cycle(in);
    }
}

int main() {
    // Break: lost/inverted cap condition, cycle reset each wake, wrong sleep.
    reset("continuous low-g cap");
    cycle(edge());
    for (unsigned i = 1; i < 6; ++i) cycle();
    expect(work_boundaries == 6 && burst_work_boundaries == 6 &&
           !burst_mode && burst_cycles == 6 && burst_cooldown == 3,
           "six completed burst cycles exit into cooldown");
    expect(selected_sleep_budgets == std::vector<uint32_t>({10000,10000,10000,10000,10000,1200000}),
           "sixth cycle selects normal initial sleep budget");
    for (unsigned i = 0; i < 4; ++i) cycle(edge());
    expect(burst_work_boundaries == 6 && burst_cooldown == 3,
           "persistent events cannot reopen capped bout");

    // Break: decrementing cooldown despite a new low-g event, or early rearm.
    reset("consecutive clean cooldown"); capped_bout(Accel::Low);
    cycle(); expect(burst_cooldown == 2, "first quiet wake decrements cooldown");
    cycle(edge()); expect(burst_cooldown == 3, "new event restarts entire cooldown");
    cycle(); cycle();
    expect(burst_work_boundaries == 6 && burst_cooldown == 1,
           "two quiet wakes are insufficient to rearm");
    cycle(); expect(!burst_mode && burst_cooldown == 0, "third quiet wake rearms without burst");
    cycle(edge()); expect(burst_work_boundaries == 7 && burst_cycles == 1 && burst_mode,
                          "new event after three quiet wakes enters fresh bout");

    // Break: dropped early return, wrong backoff, latch at wrong event boundary.
    reset("spurious chatter probation");
    cycle(edge(Accel::Cleared)); cycle(edge(Accel::Cleared));
    expect(!s_ff_suppressed && spurious_ff_streak == 2,
           "two spurious events do not latch suppression");
    cycle(edge(Accel::Cleared));
    expect(s_ff_suppressed && spurious_ff_streak == 3 && ff_suppress_clean == 0,
           "third spurious event latches suppression");
    expect(acquisition_boundaries == 0 && work_boundaries == 0 && !burst_mode &&
           gps_quiesces == 3 && radio_sleeps == 3 &&
           sleep_requests == std::vector<uint32_t>({60000,60000,60000}),
           "spurious returns cannot reach acquisition or work");
    for (unsigned i = 0; i < 15; ++i) cycle();
    expect(s_ff_suppressed && ff_suppress_clean == 15,
           "fifteen quiet cycles retain suppression");
    cycle(); expect(!s_ff_suppressed && spurious_ff_streak == 0,
                    "sixteenth quiet cycle rearms suppression");

    reset("sub-latch streak reset");
    cycle(edge(Accel::Cleared)); cycle(edge(Accel::Cleared)); cycle();
    cycle(edge(Accel::Cleared));
    expect(!s_ff_suppressed && spurious_ff_streak == 1,
           "quiet cycle breaks consecutive spurious streak");
    spurious_ff_streak = 255; cycle(edge(Accel::Cleared));
    expect(s_ff_suppressed && spurious_ff_streak == 255,
           "spurious streak saturates without reopening wake policy");

    // Real pending path must swallow a confirmed noisy edge but preserve a new
    // edge racing the I2C classification, then expose low-g/unknown immediately.
    reset("suppressed pending handoff");
    s_ff_suppressed = true; sample = Accel::Cleared; freefall_wake_callback();
    expect(!power_manager_freefall_pending() && !s_burst_wake && s_ff_suppressed,
           "confirmed noise is swallowed while suppression remains");
    freefall_wake_callback(); inject_during_sample = true;
    expect(!power_manager_freefall_pending() && s_burst_wake,
           "edge arriving during sensor read remains pending");
    sample = Accel::Low;
    expect(power_manager_freefall_pending() && !s_ff_suppressed && s_burst_wake,
           "real low-g overrides suppression without consuming edge");
    cycle(); expect(burst_mode && !s_burst_wake && burst_work_boundaries == 1,
                    "loop consumes preserved edge and enters burst");

    // Break: treating an unavailable sample as cleared or hiding it in latch.
    reset("unavailable acceleration bounded");
    s_ff_suppressed = true; spurious_ff_streak = 3;
    sample = Accel::Unavailable; freefall_wake_callback();
    expect(power_manager_freefall_pending(), "unavailable sample stays recovery-worthy");
    Cycle missing; missing.at_entry = missing.at_exit = Accel::Unavailable;
    cycle(missing);
    expect(burst_mode && !s_ff_suppressed && spurious_ff_streak == 0,
           "unavailable sample enters bounded burst and clears chatter latch");
    for (unsigned i = 1; i < 6; ++i) cycle(missing);
    expect(burst_work_boundaries == 6 && !burst_mode && burst_cooldown == 3,
           "unavailable sample cannot bypass six-cycle cap");

    // Characterization, not a proposed global airtime guarantee: short separate
    // unloads each clear naturally and therefore never enter capped cooldown.
    reset("repeated transient unloads");
    for (unsigned i = 0; i < 8; ++i) cycle(edge(Accel::Low, Accel::Cleared));
    expect(burst_work_boundaries == 8 && !burst_mode && burst_cycles == 1 && burst_cooldown == 0,
           "eight distinct cleared unloads remain eight independent bursts");
    expect(selected_sleep_budgets == std::vector<uint32_t>(8, 1200000),
           "cleared unload selects normal initial sleep budget");

    // Admission/exit depend on fresh live prerequisites, not stale initial tier.
    for (unsigned reason = 0; reason < 3; ++reason) {
        reset("unusable entry prerequisites");
        if (reason == 0) joined = false;
        if (reason == 1) region_known = false;
        if (reason == 2) rail_mv = 3599;
        cycle(edge()); expect(burst_work_boundaries == 0 && !burst_mode,
                              "no rapid mode without session region and GPS rail");
    }
    for (unsigned reason = 0; reason < 3; ++reason) {
        reset("lost exit prerequisites"); Cycle in = edge();
        if (reason == 0) in.exit_joined = false;
        if (reason == 1) in.exit_region = false;
        if (reason == 2) in.exit_rail = 3599;
        cycle(in); expect(burst_work_boundaries == 1 && !burst_mode &&
                          selected_sleep_budgets == std::vector<uint32_t>({1200000}),
                          "lost session region or rail selects normal initial budget");
    }
    reset("exact GPS rail floor"); rail_mv = 3600;
    Cycle at_floor = edge(); at_floor.exit_rail = 3600; cycle(at_floor);
    expect(burst_work_boundaries == 1, "exact GPS floor permits burst admission");
    expect(burst_mode && selected_sleep_budgets == std::vector<uint32_t>({10000}),
           "exact GPS floor retains rapid initial budget");

    // Break: consuming pending in abort, skipping its return, double quiescing
    // GPS, or resetting/debiting a partially completed active burst.
    for (bool attempted : {false, true}) {
        reset("mid-acquisition abort handoff");
        Cycle interrupted; interrupted.edge_after_acquisition = true;
        interrupted.gps_attempted = attempted; cycle(interrupted);
        expect(s_burst_wake && acquisition_boundaries == 1 && work_boundaries == 0 &&
               burst_cycles == 0 && sleep_requests.empty() && selected_sleep_budgets.empty() && gps_quiesces == 1 &&
               radio_sleeps == 1 && saves == 1 && persisted_age == 2,
               "abort preserves pending state and skips work and sleep");
        cycle(); expect(burst_mode && burst_cycles == 1 && burst_work_boundaries == 1 &&
                        !s_burst_wake,
                        "next iteration consumes abort handoff into burst");
    }
    reset("partial burst abort handoff"); cycle(edge()); cycle();
    Cycle interrupted; interrupted.edge_after_acquisition = true; cycle(interrupted);
    expect(burst_mode && burst_cycles == 2 && burst_work_boundaries == 2 && s_burst_wake,
           "aborted burst retains already-completed cycle count");
    cycle(); expect(burst_cycles == 3 && burst_work_boundaries == 3,
                    "pending handoff continues existing bout without resetting cap");

    reset("optical recovery overlap");
    s_optical_quiescence_fault = true; cycle();
    expect(work_boundaries == 0 && s_optical_quiet_retries == 1,
           "ordinary optical fault returns before work");
    cycle(edge()); expect(burst_work_boundaries == 1 && s_optical_quiet_retries == 1,
                          "pending freefall bypasses unrelated optical fast return");

    std::printf("%u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
'''


def main() -> None:
    source = harness()
    # Named production breaks are fixed before running any baseline. Run RED
    # mutants first, then unchanged GREEN; neither rewrites firmware files.
    mutants = [
        ("cap inverted", "burst_cycles >= BURST_MAX_CYCLES", "burst_cycles > BURST_MAX_CYCLES",
         "six completed burst cycles exit into cooldown"),
        ("cooldown ignores renewed event",
         "burst_cooldown = freefall_wake ? BURST_COOLDOWN_CYCLES : (uint8_t)(burst_cooldown - 1);",
         "burst_cooldown = (uint8_t)(burst_cooldown - 1);",
         "new event restarts entire cooldown"),
        ("third spurious event ignored", "if (spurious_ff_streak >= 3) {\n            power_manager",
         "if (spurious_ff_streak > 3) {\n            power_manager",
         "third spurious event latches suppression"),
        ("premature chatter rearm", "if (++ff_suppress_clean >= 16)", "if (++ff_suppress_clean >= 15)",
         "fifteen quiet cycles retain suppression"),
        ("spurious acquisition leakage", "        return;\n    }\n\n    /* A successful LTR390",
         "        /* lost early return */\n    }\n\n    /* A successful LTR390",
         "spurious returns cannot reach acquisition or work"),
        ("unavailable sample clears recovery", "return lis2dh12_freefall_is_cleared(sample_ok, cleared);",
         "return !sample_ok || lis2dh12_freefall_is_cleared(sample_ok, cleared);",
         "unavailable sample enters bounded burst and clears chatter latch"),
        ("natural clear wrongly forces cooldown",
         "/* Normal exit: payload reached terminal velocity / landed (~1g). */\n            burst_mode = false;",
         "/* Normal exit: payload reached terminal velocity / landed (~1g). */\n            burst_mode = false; burst_cooldown = BURST_COOLDOWN_CYCLES;",
         "eight distinct cleared unloads remain eight independent bursts"),
        ("lost sensor-racing edge", "generation_after != generation_before", "generation_after == generation_before",
         "edge arriving during sensor read remains pending"),
        ("abort consumes pending event", "if (power_manager_freefall_pending()) {",
         "if (power_manager_did_wake_from_freefall()) {",
         "abort preserves pending state and skips work and sleep"),
        ("partial bout restarted", "freefall_wake && !burst_mode &&", "freefall_wake &&",
         "pending handoff continues existing bout without resetting cap"),
        ("entry rail gate bypass", "power_adc_read_vSTOR_mv() >= GPS_ACQ_FLOOR_MV",
         "power_adc_read_vSTOR_mv() > 0u", "no rapid mode without session region and GPS rail"),
        ("exit rail gate bypass", "power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV",
         "power_adc_read_vSTOR_mv() < 1u", "lost session region or rail selects normal initial budget"),
        ("entry rail equality rejected", "power_adc_read_vSTOR_mv() >= GPS_ACQ_FLOOR_MV",
         "power_adc_read_vSTOR_mv() > GPS_ACQ_FLOOR_MV", "exact GPS floor permits burst admission"),
        ("exit rail equality rejected", "power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV",
         "power_adc_read_vSTOR_mv() <= GPS_ACQ_FLOOR_MV", "exact GPS floor retains rapid initial budget"),
    ]
    flags = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-I", str(ROOT / "firmware/include")]
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1")
    with tempfile.TemporaryDirectory(prefix="stratolink-burst-policy-") as temp:
        binary = str(Path(temp) / "burst_policy")

        def run(code: str) -> subprocess.CompletedProcess:
            compiled = subprocess.run(flags + ["-x", "c++", "-", str(ROOT / "firmware/src/region_manager.cpp"),
                                               "-o", binary], input=code, text=True, capture_output=True)
            if compiled.returncode:
                raise AssertionError(f"harness failed to compile:\n{compiled.stdout}{compiled.stderr}")
            return subprocess.run([binary], text=True, capture_output=True, env=env, check=False)

        for name, old, new, assertion in mutants:
            result = run(replace_once(source, old, new))
            if result.returncode != 1 or assertion not in result.stdout or result.stderr:
                raise AssertionError(f"mutation {name} missed its behavioral contract:\n{result.stdout}{result.stderr}")
            print(f"RED: {name}: {assertion}", flush=True)
        baseline = run(source)
        print(baseline.stdout, end="", flush=True)
        if baseline.returncode or baseline.stderr:
            raise AssertionError(f"unchanged production failed:\n{baseline.stdout}{baseline.stderr}")
    print(f"PASS: actual burst/chatter branches and {len(mutants)} compiled behavioral mutations")


if __name__ == "__main__":
    main()
