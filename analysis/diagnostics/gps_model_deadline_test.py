#!/usr/bin/env python3
"""Exercise the legacy public model-helper deadline with a simulated receiver.

The harness compiles gps_ublox.cpp and its real policy helpers under ASan/UBSan.
Only receiver responses, clock, GPIO, and rails are fake. This does not qualify
SparkFun parsing, UART timing, hardware, STOP, energy, or warm-fix performance.
The 1200 ms readiness profile is synthetic, not a measured universal boot delay.
Overrun profiles deliberately return after the requested external-call timeout
to test the application's acceptance deadline, not a library timeout guarantee.

Run with --output PATH to preserve stdout, stderr, and before/after source hashes
as a create-once, private evidence record. The process retains the test exit code.
Both enum-only and macro-defined AIRBORNE_4G compatibility branches run by default.
Every case calls gps_ublox_set_airborne_4g directly. Acquisition now uses separate
strict read-first startup supervision; gps_model_runtime_test.py and the pinned-
parser gps_startup_supervision_test.py cover that path. These legacy helper
deadlines must not be presented as acquisition-startup timing guarantees.
--mutation all checks that compiled guard regressions are rejected. Mutations
exist only in the temporary translation unit; production files are never edited.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import gps_model_runtime_test as base
from evidence_provenance import write_create_once


harness = base.harness
replace_once = base.replace_once
ROOT = Path(__file__).resolve().parents[2]

harness.GNSS = replace_once(
    harness.GNSS,
    "inline bool wrong_model_or_layer = false;",
    "inline bool wrong_model_or_layer = false;\n" + r"""
enum DeadlineProfile {
    FAST, STARTUP_1200, NEVER_RESPONDS, QUICK_FAILURE, WRONG_MODEL,
    SET_AT_DEADLINE, SET_AFTER_DEADLINE, READ_AT_DEADLINE,
    READ_AFTER_DEADLINE, PAUSE_AT_DEADLINE, FINAL_TIMELY_READ
};
inline DeadlineProfile deadline_profile = FAST;
inline bool gate_seen = false, timely_model_proof = false;
inline bool invalid_call_budget = false;
inline uint32_t gate_start = 0, readback_elapsed = UINT32_MAX;
inline unsigned seen_resets = 0, gate_sets = 0;
inline unsigned pvt_before_model_proof = 0, zero_wait_calls = 0;
inline uint32_t set_elapsed[12] = {}, set_waits[12] = {}, read_waits[12] = {};

inline void begin_gate() {
    if (!gate_seen || seen_resets != receiver_resets) {
        gate_seen = true;
        seen_resets = receiver_resets;
        gate_start = fake_millis;
        gate_sets = 0;
        timely_model_proof = false;
    }
}
inline void observe_call(uint16_t wait, uint32_t cap) {
    const uint32_t elapsed = fake_millis - gate_start;
    if (wait == 0u) ++zero_wait_calls;
    if (wait == 0u || wait > cap || elapsed >= 1800u ||
        (elapsed < 1800u && wait > 1800u - elapsed))
        invalid_call_budget = true;
}
""",
)
start = harness.GNSS.index("    bool setDynamicModel(")
end = harness.GNSS.index("    bool setVal8(", start)
harness.GNSS = replace_once(harness.GNSS, harness.GNSS[start:end], r"""
    bool setDynamicModel(dynModel model, uint8_t layer, uint16_t wait) {
        begin_gate();
        observe_call(wait, gate_sets == 0u ? 1200u : 300u);
        if (model_sets < 12u) {
            set_elapsed[model_sets] = fake_millis - gate_start;
            set_waits[model_sets] = wait;
        }
        ++model_sets;
        ++gate_sets;
        if (model != DYN_MODEL_AIRBORNE4g || layer != VAL_LAYER_RAM_BBR)
            wrong_model_or_layer = true;
        if (deadline_profile == SET_AT_DEADLINE) { delay(1800u); return true; }
        if (deadline_profile == SET_AFTER_DEADLINE) { delay(1801u); return true; }
        if (deadline_profile == PAUSE_AT_DEADLINE) { delay(1790u); return false; }
        if (deadline_profile == QUICK_FAILURE) { delay(1u); return false; }
        if (deadline_profile == NEVER_RESPONDS ||
            (deadline_profile == STARTUP_1200 && fake_millis - gate_start < 1200u) ||
            (deadline_profile == FINAL_TIMELY_READ && gate_sets == 1u)) {
            // Early startup SETs are discarded, even if readiness arrives later.
            delay(wait);
            return false;
        }
        const uint32_t latency = deadline_profile == STARTUP_1200 ? 145u :
            deadline_profile == FINAL_TIMELY_READ ? (gate_sets == 2u ? 280u : 100u) : 20u;
        if (wait < latency) { delay(wait); return false; }
        delay(latency);
        return true;
    }
    uint8_t getDynamicModel(uint8_t layer, uint16_t wait) {
        begin_gate();
        observe_call(wait, 300u);
        if (model_reads < 12u) read_waits[model_reads] = wait;
        ++model_reads;
        if (layer != VAL_LAYER_RAM) wrong_model_or_layer = true;
        if (deadline_profile == NEVER_RESPONDS ||
            (deadline_profile == STARTUP_1200 && fake_millis - gate_start < 1200u)) {
            delay(wait);
            return 255u;
        }
        const uint32_t latency = deadline_profile == STARTUP_1200 ? 58u :
            deadline_profile == READ_AT_DEADLINE ? (gate_sets == 0u ? 1800u : 1780u) :
            deadline_profile == READ_AFTER_DEADLINE ? (gate_sets == 0u ? 1801u : 1781u) :
            deadline_profile == FINAL_TIMELY_READ ? (gate_sets == 2u ? 100u : 79u) : 20u;
        const bool forced_overrun = deadline_profile == READ_AT_DEADLINE ||
            deadline_profile == READ_AFTER_DEADLINE;
        if (!forced_overrun && wait < latency) { delay(wait); return 255u; }
        delay(latency);
        const uint8_t model = deadline_profile == WRONG_MODEL ||
            (deadline_profile == FINAL_TIMELY_READ && gate_sets == 2u) ||
            (gate_sets == 0u && (deadline_profile == QUICK_FAILURE ||
             deadline_profile == SET_AT_DEADLINE || deadline_profile == SET_AFTER_DEADLINE ||
             deadline_profile == PAUSE_AT_DEADLINE)) ? 0u : 8u;
        readback_elapsed = fake_millis - gate_start;
        timely_model_proof = model == 8u && readback_elapsed < 1800u;
        return model;
    }
""")
harness.GNSS = replace_once(
    harness.GNSS,
    "++pvt_polls;",
    "++pvt_polls;\n"
    "        if (!timely_model_proof) ++pvt_before_model_proof;",
)

harness.TEST = harness.TEST[:harness.TEST.index("int main() {")] + r"""
static void deadline_case(DeadlineProfile selected, uint32_t start = 0u) {
    reset_case(GOOD, RESET_EPOCH);
    deadline_profile = selected;
    fake_millis = start;
    gate_seen = timely_model_proof = invalid_call_budget = false;
    gate_start = 0u;
    readback_elapsed = UINT32_MAX;
    seen_resets = gate_sets = zero_wait_calls = pvt_before_model_proof = 0u;
    for (unsigned i = 0; i < 12u; ++i)
        set_elapsed[i] = set_waits[i] = read_waits[i] = 0u;
}
static void deadline_check(const char* name, bool passed) {
    check(name, passed && !invalid_call_budget && zero_wait_calls == 0u &&
          pvt_before_model_proof == 0u);
    std::printf("  elapsed=%u readback=%u invalid_budget=%u zero_wait=%u premature_pvt=%u SET=",
        fake_millis - gate_start, readback_elapsed, invalid_call_budget,
        zero_wait_calls, pvt_before_model_proof);
    for (unsigned i = 0; i < model_sets && i < 12u; ++i)
        std::printf("%s%u/%u", i ? "," : "", set_elapsed[i], set_waits[i]);
    std::printf(" READ_wait=");
    for (unsigned i = 0; i < model_reads && i < 12u; ++i)
        std::printf("%s%u", i ? "," : "", read_waits[i]);
    std::printf("\n");
}
int main() {
#if defined(DYN_MODEL_AIRBORNE_4G)
    // This compatibility branch can prove an already-retained model by READ.
    deadline_case(FAST);
    const bool retained_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy read-first helper accepts timely retained model",
        retained_fix && model_sets == 0u && model_reads == 1u &&
        readback_elapsed == 20u && receiver_resets == 0u && pvt_polls == 0u);

    deadline_case(STARTUP_1200);
    const bool startup_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy read-first helper tolerates startup within shared deadline",
        startup_fix && receiver_resets == 0u && model_sets == 1u &&
        model_reads == 2u && readback_elapsed == 1578u && set_waits[0] == 1200u);

    // The pre-READ must spend the same budget as SET and subsequent READs.
    deadline_case(NEVER_RESPONDS);
    const bool silent_gate = gps_ublox_set_airborne_4g();
    deadline_check("read-first silence expires without any zero-wait SET",
        !silent_gate && fake_millis == 1800u && model_sets == 1u &&
        model_reads == 2u && set_waits[0] == 1200u && read_waits[1] == 280u);

    deadline_case(READ_AT_DEADLINE);
    const bool exact_pre_read = gps_ublox_set_airborne_4g();
    deadline_check("pre-READ model 8 at deadline is rejected without SET",
        !exact_pre_read && fake_millis == 1800u && model_sets == 0u && model_reads == 1u);

    deadline_case(READ_AFTER_DEADLINE);
    const bool late_pre_read = gps_ublox_set_airborne_4g();
    deadline_check("late pre-READ model 8 is rejected without SET",
        !late_pre_read && fake_millis == 1801u && model_sets == 0u && model_reads == 1u);

    deadline_case(NEVER_RESPONDS, UINT32_MAX - 600u);
    const bool wrapped_silence = gps_ublox_set_airborne_4g();
    deadline_check("read-first shared deadline survives millis wrap",
        !wrapped_silence && fake_millis == 1199u && model_sets == 1u && model_reads == 2u);

    deadline_case(READ_AFTER_DEADLINE);
    const bool late_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy late pre-READ never publishes model proof",
        !late_fix && receiver_resets == 0u && model_sets == 0u &&
        model_reads == 1u && pvt_polls == 0u && position_reads == 0u);

    deadline_case(WRONG_MODEL);
    const bool wrong_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy wrong pre-READ and post-SET models never publish proof",
        !wrong_fix && receiver_resets == 0u && model_sets == 3u &&
        model_reads == 6u && pvt_polls == 0u && position_reads == 0u);
#else

    // A gratuitous readiness sleep would regress this prompt, verified fix.
    deadline_case(FAST);
    const bool fast_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy healthy model helper verifies promptly",
        fast_fix && receiver_resets == 0u && model_sets == 1u &&
        model_reads == 1u && readback_elapsed == 40u && pvt_polls == 0u);

    // Three short SET waits reproduce the unnecessary cold-reset defect.
    deadline_case(STARTUP_1200);
    const bool startup_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy startup-ready model helper proves model at 1423 ms",
        startup_fix && receiver_resets == 0u &&
        s_gps_diag.hardware_resets == 0u && s_gps_diag.accepted_fixes == 0u &&
        model_sets == 2u && model_reads == 1u && readback_elapsed == 1423u &&
        set_elapsed[1] == 1220u && set_waits[0] == 1200u && pvt_polls == 0u);

    // A renewed budget per attempt or a final unconditional pause exceeds 1800.
    deadline_case(NEVER_RESPONDS);
    const bool silent_gate = gps_ublox_set_airborne_4g();
    deadline_check("silent gate uses one 1800 ms budget and no readback",
        !silent_gate && model_sets == 3u && model_reads == 0u &&
        fake_millis == 1800u && set_waits[0] == 1200u &&
        set_waits[1] == 300u && set_waits[2] == 260u);

    // A deadline-only loop must not turn cheap failures into unlimited retries.
    deadline_case(QUICK_FAILURE);
    const bool quick_gate = gps_ublox_set_airborne_4g();
    deadline_check("fast SET failures stop after three attempts",
        !quick_gate && model_sets == 3u && model_reads == 0u && fake_millis < 1800u);

    // Accepting an ACK at/after expiration would wrongly launch a READ.
    deadline_case(SET_AT_DEADLINE);
    const bool exact_set = gps_ublox_set_airborne_4g();
    deadline_check("SET ACK exactly at deadline suppresses readback",
        !exact_set && model_sets == 1u && model_reads == 0u && fake_millis == 1800u);

    deadline_case(SET_AFTER_DEADLINE);
    const bool late_set = gps_ublox_set_airborne_4g();
    deadline_check("late SET ACK suppresses readback and further attempts",
        !late_set && model_sets == 1u && model_reads == 0u && fake_millis == 1801u);

    // Returning model 8 is insufficient if the proof arrived too late.
    deadline_case(READ_AT_DEADLINE);
    const bool exact_read = gps_ublox_set_airborne_4g();
    deadline_check("model 8 exactly at deadline is rejected",
        !exact_read && model_sets == 1u && model_reads == 1u && fake_millis == 1800u);

    deadline_case(READ_AFTER_DEADLINE);
    const bool late_read = gps_ublox_set_airborne_4g();
    deadline_check("late model 8 is rejected without additional attempts",
        !late_read && model_sets == 1u && model_reads == 1u && fake_millis == 1801u);

    // A fixed 20 ms retry pause would run ten milliseconds past the deadline.
    deadline_case(PAUSE_AT_DEADLINE);
    const bool pause_gate = gps_ublox_set_airborne_4g();
    deadline_check("retry pause cannot extend deadline or permit another SET",
        !pause_gate && model_sets == 1u && model_reads == 0u && fake_millis <= 1800u);

    // The final SET and READ must receive only their remaining shared budget.
    deadline_case(FINAL_TIMELY_READ);
    const bool final_gate = gps_ublox_set_airborne_4g();
    deadline_check("final timely model proof clamps both SET and READ waits",
        final_gate && model_sets == 3u && model_reads == 2u &&
        fake_millis == 1799u && set_waits[2] == 180u && read_waits[1] == 80u);

    // Absolute timestamp comparisons break this gate across millis wrap.
    deadline_case(STARTUP_1200, UINT32_MAX - 600u);
    const bool wrapped_startup = gps_ublox_set_airborne_4g();
    deadline_check("startup model proof remains timely across millis wrap",
        wrapped_startup && model_sets == 2u && model_reads == 1u &&
        readback_elapsed == 1423u && fake_millis == 822u);

    deadline_case(NEVER_RESPONDS, UINT32_MAX - 600u);
    const bool wrapped_silence = gps_ublox_set_airborne_4g();
    deadline_check("silent gate still expires across millis wrap",
        !wrapped_silence && model_sets == 3u && model_reads == 0u &&
        fake_millis == 1199u);

    // This public helper must report failure without issuing any PVT request.
    deadline_case(NEVER_RESPONDS);
    const bool silent_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy permanent silence fails proof without PVT",
        !silent_fix && receiver_resets == 0u &&
        model_sets == 3u && model_reads == 0u && pvt_polls == 0u && position_reads == 0u);

    deadline_case(READ_AFTER_DEADLINE);
    const bool late_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy late model proof is rejected without reset or PVT",
        !late_fix && receiver_resets == 0u && model_sets == 1u &&
        model_reads == 1u && pvt_polls == 0u && position_reads == 0u);

    deadline_case(WRONG_MODEL);
    const bool wrong_fix = gps_ublox_set_airborne_4g();
    deadline_check("legacy wrong model readback cannot publish proof",
        !wrong_fix && receiver_resets == 0u && model_sets == 3u &&
        model_reads == 3u && pvt_polls == 0u && position_reads == 0u);
#endif
    return failures ? 1 : 0;
}
"""


MUTATIONS = {
    "first-set-too-short": (
        "4u * GPS_DYNMODEL_MAX_WAIT_MS;", "1u * GPS_DYNMODEL_MAX_WAIT_MS;"),
    "set-zero-wait-guard-removed": (
        "const bool set_ok = wait_ms != 0 && gnss.setDynamicModel(",
        "const bool set_ok = gnss.setDynamicModel("),
    "read-zero-wait-guard-removed": (
        "if (set_ok && wait_ms != 0 &&", "if (set_ok &&"),
    "post-read-acceptance-guard-removed": (
        "if (set_ok && wait_ms != 0 &&\n"
        "            gnss.getDynamicModel(VAL_LAYER_RAM, wait_ms) == expected &&\n"
        "            gps_model_remaining_ms(deadline, 1u) != 0)",
        "if (set_ok && wait_ms != 0 &&\n"
        "            gnss.getDynamicModel(VAL_LAYER_RAM, wait_ms) == expected)"),
    "pre-read-acceptance-guard-removed": (
        "if (wait_ms != 0 &&\n"
        "            gnss.getDynamicModel(VAL_LAYER_RAM, wait_ms) == expected &&\n"
        "            gps_model_remaining_ms(deadline, 1u) != 0)",
        "if (wait_ms != 0 &&\n"
        "            gnss.getDynamicModel(VAL_LAYER_RAM, wait_ms) == expected)"),
    "remaining-wait-clamp-removed": (
        "return (uint32_t)remaining < cap_ms ? (uint16_t)remaining : cap_ms;",
        "return cap_ms;"),
    "retry-pause-clamp-removed": ("        delay(wait_ms);", "        delay(20u);"),
    "fourth-attempt-allowed": (
        "for (uint8_t attempt = 0; attempt < 3; ++attempt)",
        "for (uint8_t attempt = 0; attempt < 4; ++attempt)"),
}


def source_snapshot(driver_source=None):
    files = [Path(__file__).resolve(), Path(base.__file__).resolve(),
             Path(harness.__file__).resolve()]
    files += [ROOT / "firmware/src" / name for name in (
        "gps_ublox.cpp", "gps_freshness.cpp", "gps_pvt_validation.cpp", "gps_backup_policy.cpp")]
    files += sorted((ROOT / "firmware/include").glob("*.h"))
    if driver_source is not None:
        files.append(driver_source.resolve())
    return {str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}


def run_branches(branch, driver_source=None, mutation=None):
    original_gnss = harness.GNSS
    original_test = harness.TEST
    if driver_source is not None or mutation is not None:
        source_path = driver_source or ROOT / "firmware/src/gps_ublox.cpp"
        source = source_path.read_text(encoding="utf-8")
        if mutation is not None:
            source = replace_once(source, *MUTATIONS[mutation])
        harness.TEST = replace_once(harness.TEST, '#include "gps_ublox.cpp"', source)
    failures = 0
    for spelling in ("enum", "macro") if branch == "both" else (branch,):
        harness.GNSS = original_gnss
        if spelling == "macro":
            harness.GNSS += "\n#define DYN_MODEL_AIRBORNE_4G DYN_MODEL_AIRBORNE4g\n"
        print(f"BRANCH {spelling}: real driver with external receiver/time fixture", flush=True)
        try:
            harness.main()
        except subprocess.CalledProcessError as error:
            failures += 1
            print(f"BRANCH {spelling}: exit {error.returncode}", flush=True)
    harness.GNSS = original_gnss
    harness.TEST = original_test
    return 1 if failures else 0


def run_mutations(branch):
    unexpected = 0
    for mutation in MUTATIONS:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--branch", branch,
             "--mutation", mutation], text=True, capture_output=True,
            env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1"))
        killed = result.returncode == 1 and "[FAIL]" in result.stdout and not result.stderr
        print(f"MUTATION {mutation}: {'KILLED' if killed else 'UNEXPECTED'}", flush=True)
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", file=sys.stderr, flush=True)
        unexpected += not killed
    print(f"MUTATION_SUMMARY count={len(MUTATIONS)} unexpected={unexpected}", flush=True)
    return 1 if unexpected else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--branch", choices=("both", "enum", "macro"), default="both")
    parser.add_argument("--driver-source", type=Path,
                        help="compile a preserved source baseline without changing production")
    parser.add_argument("--mutation", choices=("all", *MUTATIONS))
    args = parser.parse_args()
    if args.driver_source is not None and args.mutation is not None:
        parser.error("baseline replay and mutations are separate experiments")
    if args.output is None:
        if args.mutation == "all":
            raise SystemExit(run_mutations(args.branch))
        raise SystemExit(run_branches(args.branch, args.driver_source, args.mutation))
    if args.output.exists():
        raise FileExistsError("refusing to overwrite deadline-test evidence")
    before = source_snapshot(args.driver_source)
    command = [sys.executable, str(Path(__file__).resolve()), "--branch", args.branch]
    if args.driver_source is not None:
        command += ["--driver-source", str(args.driver_source.resolve())]
    if args.mutation is not None:
        command += ["--mutation", args.mutation]
    result = subprocess.run(command, text=True, capture_output=True,
                            env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                     UBSAN_OPTIONS="halt_on_error=1"))
    after = source_snapshot(args.driver_source)
    report = {
        "schema": "stratolink.gps_model_deadline.runtime.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "real application source; fake external receiver/time/rail; not hardware qualification",
        "mutation": args.mutation,
        "command": command, "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
        "before_sha256": before, "after_sha256": after,
        "source_unchanged_during_run": before == after,
    }
    write_create_once(args.output, (json.dumps(report, indent=2) + "\n").encode())
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    print(json.dumps({"report": str(args.output.resolve()),
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "mode": oct(args.output.stat().st_mode & 0o777),
                      "source_unchanged_during_run": before == after}))
    if before != after:
        raise AssertionError("source changed while capturing evidence")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
