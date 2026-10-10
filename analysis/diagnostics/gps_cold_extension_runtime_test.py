#!/usr/bin/env python3
"""Execute opt-in cold extension contract against the actual production driver.

This reuses the hash-bound boot-94 scalar PVT fixture and ideal packet-shaped
configuration facade. It does not model the SparkFun parser, UART timing,
standby, or physical reserve. Only clock/GPIO/GNSS/ADC/mission boundaries are
fake; acquisition, freshness, value validation and recovery remain production.
The two-argument compatibility adapter permits a behavioral RED on the old
driver rather than a missing-signature compiler failure. Each scenario runs in
a fresh process so production boot state is not manufactured by the fixture.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

import gps_acquisition_runtime_test as base


ARDUINO = base.ARDUINO.replace(
    "struct FakeSerial : Stream {",
    "inline uint32_t tx_block_at = UINT32_MAX;\n"
    "struct FakeSerial : Stream {\n"
    "    int availableForWrite() override { return fake_millis >= tx_block_at ? 0 : 63; }",
)
GNSS = base.GNSS.replace(
    "inline Frame current{};",
    "inline Frame current{};\n"
    "inline uint32_t silence_at=UINT32_MAX, silence_until=0u;\n"
    "inline uint32_t stall_at=UINT32_MAX, last_poll_at=0u;\n"
    "inline uint32_t validity_change_at=UINT32_MAX;\n"
    "inline uint32_t time_only_change_at=UINT32_MAX;\n"
    "inline uint32_t quality_oscillate_at=UINT32_MAX, quality_regress_at=UINT32_MAX;\n"
    "inline uint32_t reacquire_fix_after=UINT32_MAX;\n"
    "inline uint32_t reacquire_previous_epoch=UINT32_MAX, reacquire_first_fix_epoch=UINT32_MAX;\n"
    "inline uint32_t reacquire_fresh_epoch=UINT32_MAX, reacquire_fresh_sample_ms=UINT32_MAX;\n"
    "inline uint32_t reply_pause_from=UINT32_MAX, reply_pause_until=0u;\n"
    "inline uint32_t parser_delay_at=UINT32_MAX, parser_cost=0u;\n"
    "inline bool model_fail_until_reset=false;",
).replace(
    "if (scenario == SILENT) return false;",
    "if (scenario == SILENT || fake_millis >= silence_at || fake_millis < silence_until) return false;",
).replace(
    "(fake_millis / 1000u) * 1000u",
    "((fake_millis < stall_at ? fake_millis : stall_at) / 1000u) * 1000u",
).replace(
    "if (scenario == PROVISIONAL) current.valid = 0u;",
    "if (scenario == PROVISIONAL) current.valid = 0u;\n"
    "        if (validity_change_at != UINT32_MAX) {\n"
    "            current.valid = fake_millis < validity_change_at ? 0u : 3u;\n"
    "            current.itow = fake_millis < validity_change_at ? (fake_millis/1000u)*1000u :\n"
    "                348000000u + ((fake_millis-validity_change_at)/1000u)*1000u;\n"
    "        }\n"
    "        if (time_only_change_at != UINT32_MAX) {\n"
    "            const uint32_t epoch_ms = fake_millis < stall_at ? fake_millis : stall_at;\n"
    "            current.valid = fake_millis < time_only_change_at ? 0u :\n"
    "                (fake_millis < validity_change_at ? 2u : 3u);\n"
    "            current.itow = epoch_ms < time_only_change_at ? (epoch_ms/1000u)*1000u :\n"
    "                349899000u + ((epoch_ms-time_only_change_at)/1000u)*1000u;\n"
    "            current.fix_type=3u; current.flags=1u; current.satellites=4u;\n"
    "            if (fake_millis >= quality_oscillate_at)\n"
    "                current.valid = ((fake_millis-quality_oscillate_at)/500u)%2u ? 0u : 2u;\n"
    "            if (quality_regress_at != UINT32_MAX) {\n"
    "                current.valid = fake_millis < quality_regress_at ? 3u : 2u;\n"
    "                if (fake_millis < quality_regress_at) current.flags=0u;\n"
    "            }\n"
    "        }",
).replace(
    "if (scenario == CACHED || scenario == IMPOSSIBLE_VALUE) {",
    "if (reacquire_fix_after != UINT32_MAX &&\n"
    "            fake_millis-origin >= reacquire_fix_after) {\n"
    "            current.fix_type=3u; current.flags=1u; current.satellites=4u;\n"
    "        }\n"
    "        if (scenario == CACHED || scenario == IMPOSSIBLE_VALUE) {",
).replace(
    "packetUBXNAVPVT = &storage;",
    "last_poll_at = fake_millis; packetUBXNAVPVT = &storage;",
).replace(
    "if (cls == UBX_CLASS_CFG) return configResponse(cls, id);",
    "if (cls == UBX_CLASS_CFG) return model_fail_until_reset && reset_edges == 0u ? false : configResponse(cls, id);",
).replace(
    "if (!emitPVT()) return false;",
    "if (fake_millis >= reply_pause_from && fake_millis < reply_pause_until) return false;\n"
    "        if (fake_millis >= parser_delay_at) { fake_millis += parser_cost; parser_delay_at=UINT32_MAX; }\n"
    "        if (!emitPVT()) return false;",
).replace(
    "storage.data.iTOW = current.itow;",
    "if (reacquire_fix_after != UINT32_MAX) {\n"
    "            if ((current.valid&3u)==3u && (current.flags&1u)!=0u) {\n"
    "                if (reacquire_first_fix_epoch==UINT32_MAX) reacquire_first_fix_epoch=current.itow;\n"
    "                if (reacquire_previous_epoch!=UINT32_MAX && current.itow!=reacquire_previous_epoch &&\n"
    "                    reacquire_fresh_sample_ms==UINT32_MAX) {\n"
    "                    reacquire_fresh_epoch=current.itow; reacquire_fresh_sample_ms=fake_millis;\n"
    "                }\n"
    "            }\n"
    "            reacquire_previous_epoch=current.itow;\n"
    "        }\n"
    "        storage.data.iTOW = current.itow;",
)

PRELUDE = base.TEST.split("int main() {", 1)[0].replace(
    '#include <initializer_list>', '#include <initializer_list>\n#include <type_traits>\n#include <cstring>',
).replace(
    "uint16_t power_adc_read_vSTOR_mv() { return 4660u; }",
    "uint16_t rail_before=4660u, rail_after=4660u;\n"
    "uint32_t rail_change_at=UINT32_MAX, mission_at=UINT32_MAX, first_adc_cost=0u;\n"
    "uint32_t adc_delay_at=UINT32_MAX, adc_cost=0u;\n"
    "uint16_t power_adc_read_vSTOR_mv() {\n"
    "    fake_millis += first_adc_cost; first_adc_cost=0u;\n"
    "    if (fake_millis >= adc_delay_at) { fake_millis += adc_cost; adc_delay_at=UINT32_MAX; }\n"
    "    return fake_millis >= rail_change_at ? rail_after : rail_before;\n"
    "}",
).replace(
    "bool power_manager_freefall_pending() { return false; }",
    "bool power_manager_freefall_pending() { return fake_millis >= mission_at; }",
)
TEST = PRELUDE + r'''
template<class Function>
bool acquire(Function function, gps_fix_t* fix, uint32_t budget, bool permit) {
    if constexpr (std::is_invocable_r_v<bool,Function,gps_fix_t*,uint32_t,bool>)
        return function(fix,budget,permit);
    else {
        (void)permit;
        return function(fix,budget);
    }
}
static bool attempt(gps_fix_t& fix,uint32_t budget=30000u,bool permit=true) {
    return acquire(&gps_ublox_get_fix,&fix,budget,permit);
}
static bool invalid(const gps_fix_t& fix) {
    return !fix.valid && fix.satellites==0u && !last_fix.valid;
}
static bool bounded_since(uint32_t start,uint32_t budget) {
    return fake_millis-start>=budget && fake_millis-start<=budget+100u &&
        last_poll_at-start<budget;
}
int main(int argc,char** argv) {
    if(argc!=2) return 2;
    const char* name=argv[1]; gps_fix_t fix=previously_valid();
    reset_case(COLD);
    if(!strcmp(name,"cold-capture")) {
        check(name,attempt(fix) && expected_position(fix) && no_reset() &&
            fake_millis>=159052u && fake_millis<159200u);
    } else if(!strcmp(name,"default-optout")) {
        check(name,!gps_ublox_get_fix(&fix,30000u) && invalid(fix) && bounded_since(0u,30000u));
    } else if(!strcmp(name,"explicit-optout")) {
        check(name,!attempt(fix,30000u,false) && invalid(fix) && bounded_since(0u,30000u));
    } else if(!strcmp(name,"burst-never-extends")) {
        check(name,!attempt(fix,10000u,true) && invalid(fix) && bounded_since(0u,10000u));
    } else if(!strcmp(name,"warm-after-cold")) {
        bool cold=attempt(fix); scenario=WARM; origin=fake_millis;
        bool warm=attempt(fix);
        check(name,cold && warm && expected_position(fix) && no_reset() &&
            fake_millis-origin>=14731u && fake_millis-origin<14900u);
    } else if(!strcmp(name,"ordinary-fix-does-not-starve-reacquisition")) {
        scenario=WARM; bool fixed=attempt(fix);
        scenario=ADVANCING_NOFIX; origin=fake_millis;
        bool again=attempt(fix);
        check(name,fixed && !again && invalid(fix) && bounded_since(origin,180000u) && no_reset());
    } else if(!strcmp(name,"accepted-fix-then-late-45s-reacquisition")) {
        scenario=WARM; bool fixed=attempt(fix);
        scenario=ADVANCING_NOFIX; origin=fake_millis; reacquire_fix_after=45000u;
        bool again=attempt(fix);
        // The fix flag first changes inside an already-observed 1 Hz epoch.
        // Publish only on the next real external epoch, not phase_start+45s.
        check(name,fixed && again && expected_position(fix) &&
            fake_millis-origin>=45000u && fake_millis-origin<180000u &&
            reacquire_fresh_sample_ms!=UINT32_MAX && fake_millis==reacquire_fresh_sample_ms &&
            reacquire_fresh_epoch==reacquire_first_fix_epoch+1000u &&
            s_gps_diag.accepted_fixes==2u && no_reset());
    } else if(!strcmp(name,"accepted-fix-then-repeated-nofix-extensions")) {
        scenario=WARM; bool fixed=attempt(fix); bool all_bounded=true;
        scenario=ADVANCING_NOFIX;
        for(unsigned cycle=0u; cycle<3u; ++cycle) {
            origin=fake_millis;
            bool again=attempt(fix);
            all_bounded=all_bounded && !again && invalid(fix) && bounded_since(origin,180000u);
        }
        check(name,fixed && all_bounded && s_gps_diag.accepted_fixes==1u &&
            s_gps_diag.no_fresh_cycles==3u && no_reset());
    } else if(!strcmp(name,"accepted-fix-reacquisition-still-needs-admission-rail")) {
        scenario=WARM; bool fixed=attempt(fix);
        scenario=ADVANCING_NOFIX; origin=fake_millis; rail_before=4499u;
        bool again=attempt(fix);
        check(name,fixed && !again && invalid(fix) && bounded_since(origin,30000u) && no_reset());
    } else if(!strcmp(name,"reset-followed-by-bounded-reacquisition")) {
        scenario=WARM; bool fixed=attempt(fix);
        GpsStartupContext reset{fake_millis+5000u}; bool reset_ok=gps_startup_reset(reset);
        scenario=COLD; origin=fake_millis;
        check(name,fixed && reset_ok && attempt(fix) && expected_position(fix) &&
            fake_millis-origin>=159052u && fake_millis-origin<159200u && s_gps_diag.hardware_resets==1u);
    } else if(!strcmp(name,"failed-extension-can-retry-next-window")) {
        scenario=ADVANCING_NOFIX; bool first=attempt(fix);
        bool first_bound=bounded_since(0u,180000u); origin=fake_millis;
        bool second=attempt(fix);
        check(name,!first && !second && first_bound && bounded_since(origin,180000u) && invalid(fix) && no_reset());
    } else if(!strcmp(name,"repeat-needs-fresh-admission")) {
        scenario=ADVANCING_NOFIX; (void)attempt(fix);
        bool first_bound=bounded_since(0u,180000u); origin=fake_millis;
        rail_before=4499u; bool second=attempt(fix);
        check(name,first_bound && !second && bounded_since(origin,30000u) && invalid(fix) && no_reset());
    } else if(!strcmp(name,"low-rail-defers-not-consumes")) {
        rail_before=4499u; bool denied=attempt(fix); bool first_bound=bounded_since(0u,30000u);
        rail_before=4500u; origin=fake_millis;
        check(name,!denied && first_bound && attempt(fix) && expected_position(fix) &&
            fake_millis-origin>=159052u && fake_millis-origin<159200u && no_reset());
    } else if(!strcmp(name,"admission-4500")) {
        rail_before=4500u;
        check(name,attempt(fix) && expected_position(fix) && fake_millis>=159052u && no_reset());
    } else if(!strcmp(name,"admission-4499")) {
        rail_before=4499u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && no_reset());
    } else if(!strcmp(name,"admission-uses-current-rail")) {
        rail_change_at=29900u; rail_after=4499u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && no_reset());
    } else if(!strcmp(name,"continuation-4400")) {
        scenario=ADVANCING_NOFIX; rail_change_at=60000u; rail_after=4400u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,180000u) && no_reset());
    } else if(!strcmp(name,"continuation-4399")) {
        scenario=ADVANCING_NOFIX; rail_change_at=60000u; rail_after=4399u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=60000u &&
            fake_millis<=61005u && s_gps_diag.power_aborts==1u && no_reset());
    } else if(!strcmp(name,"mission-abort")) {
        scenario=PROVISIONAL; mission_at=60000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=60000u &&
            fake_millis<=60105u && s_gps_diag.mission_aborts==1u && no_reset());
    } else if(!strcmp(name,"transport-abort")) {
        scenario=PROVISIONAL; tx_block_at=60000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=60000u && fake_millis<=60105u && no_reset());
    } else if(!strcmp(name,"provisional-progress-extends")) {
        scenario=PROVISIONAL;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,180000u) && no_reset());
    } else if(!strcmp(name,"provisional-stall-denies")) {
        scenario=PROVISIONAL; stall_at=5000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u));
    } else if(!strcmp(name,"time-domain-transition-reanchors")) {
        scenario=PROVISIONAL; validity_change_at=28000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,180000u) && no_reset());
    } else if(!strcmp(name,"time-domain-transition-needs-second-epoch")) {
        scenario=PROVISIONAL; validity_change_at=29900u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && no_reset());
    } else if(!strcmp(name,"time-only-domain-progress-extends-without-publication")) {
        scenario=PROVISIONAL; time_only_change_at=10000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,180000u) && no_reset());
    } else if(!strcmp(name,"time-only-domain-then-date-needs-fresh-epoch")) {
        scenario=PROVISIONAL; time_only_change_at=10000u; validity_change_at=34000u;
        check(name,attempt(fix) && expected_position(fix) && fake_millis>=35000u &&
            fake_millis<=35100u && no_reset());
    } else if(!strcmp(name,"time-only-domain-frozen-jump-denies")) {
        scenario=PROVISIONAL; time_only_change_at=10000u; stall_at=10000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && no_reset());
    } else if(!strcmp(name,"time-only-domain-needs-second-epoch-before-admission")) {
        scenario=PROVISIONAL; time_only_change_at=29900u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && no_reset());
    } else if(!strcmp(name,"time-only-frozen-after-admission-aborts")) {
        scenario=PROVISIONAL; time_only_change_at=10000u; stall_at=60000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=63000u &&
            fake_millis<=63100u && no_reset());
    } else if(!strcmp(name,"time-quality-oscillation-does-not-refresh-progress-age")) {
        scenario=PROVISIONAL; time_only_change_at=10000u; stall_at=60000u;
        quality_oscillate_at=60000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=63000u &&
            fake_millis<=63100u && no_reset());
    } else if(!strcmp(name,"date-quality-regression-never-publishes-time-only-fix")) {
        scenario=PROVISIONAL; time_only_change_at=0u; quality_regress_at=34000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,180000u) && no_reset());
    } else if(!strcmp(name,"provisional-stall-aborts-extension")) {
        scenario=PROVISIONAL; stall_at=60000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=60000u && fake_millis<=64200u);
    } else if(!strcmp(name,"parser-crosses-progress-grace")) {
        scenario=ADVANCING_NOFIX; reply_pause_from=60100u; reply_pause_until=63010u;
        parser_delay_at=63010u; parser_cost=5u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=63010u &&
            fake_millis<=63020u && no_reset());
    } else if(!strcmp(name,"response-adc-crosses-progress-grace")) {
        scenario=ADVANCING_NOFIX; reply_pause_from=60100u; reply_pause_until=61113u;
        adc_delay_at=61113u; adc_cost=3000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=64113u &&
            fake_millis<=64120u && no_reset());
    } else if(!strcmp(name,"admission-adc-crosses-hard-deadline")) {
        scenario=ADVANCING_NOFIX; adc_delay_at=30000u; adc_cost=150000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=180000u &&
            fake_millis<=180100u && last_poll_at<30000u && no_reset());
    } else if(!strcmp(name,"extended-adc-crosses-hard-deadline")) {
        scenario=ADVANCING_NOFIX; adc_delay_at=179900u; adc_cost=150u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=180000u &&
            fake_millis<=180100u && last_poll_at<179900u && no_reset());
    } else if(!strcmp(name,"mission-arrives-during-admission-adc")) {
        scenario=ADVANCING_NOFIX; adc_delay_at=30000u; adc_cost=150u; mission_at=30100u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=30100u &&
            fake_millis<=30200u && s_gps_diag.mission_aborts==1u && last_poll_at<30000u && no_reset());
    } else if(!strcmp(name,"admission-adc-crosses-progress-grace")) {
        scenario=ADVANCING_NOFIX; adc_delay_at=30000u; adc_cost=3000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=33000u &&
            fake_millis<=33100u && last_poll_at<30000u && no_reset());
    } else if(!strcmp(name,"silence-aborts-extension")) {
        scenario=PROVISIONAL; silence_at=60000u;
        check(name,!attempt(fix) && invalid(fix) && fake_millis>=60000u && fake_millis<=66200u);
    } else if(!strcmp(name,"inline-reset-disqualifies-call")) {
        scenario=PROVISIONAL; silence_until=7000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && s_gps_diag.hardware_resets==1u);
    } else if(!strcmp(name,"model-recovery-disqualifies-call")) {
        scenario=PROVISIONAL; model_fail_until_reset=true;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,30000u) && s_gps_diag.hardware_resets==1u);
    } else if(!strcmp(name,"startup-time-included")) {
        scenario=ADVANCING_NOFIX; first_adc_cost=2000u;
        check(name,!attempt(fix) && invalid(fix) && bounded_since(0u,180000u) && no_reset());
    } else if(!strcmp(name,"millis-wrap")) {
        fake_millis=origin=UINT32_MAX-10000u;
        bool accepted=attempt(fix);
        check(name,accepted && expected_position(fix) && fake_millis-origin>=159052u &&
            fake_millis-origin<159200u && no_reset());
    } else return 2;
    return failures ? 1 : 0;
}
'''

CASES = (
    "cold-capture", "default-optout", "explicit-optout", "burst-never-extends",
    "warm-after-cold", "ordinary-fix-does-not-starve-reacquisition",
    "accepted-fix-then-late-45s-reacquisition", "accepted-fix-then-repeated-nofix-extensions",
    "accepted-fix-reacquisition-still-needs-admission-rail", "reset-followed-by-bounded-reacquisition",
    "failed-extension-can-retry-next-window", "repeat-needs-fresh-admission",
    "low-rail-defers-not-consumes", "admission-4500", "admission-4499",
    "admission-uses-current-rail", "continuation-4400", "continuation-4399",
    "mission-abort", "transport-abort", "provisional-progress-extends",
    "provisional-stall-denies", "time-domain-transition-reanchors",
    "time-domain-transition-needs-second-epoch",
    "time-only-domain-progress-extends-without-publication",
    "time-only-domain-then-date-needs-fresh-epoch", "time-only-domain-frozen-jump-denies",
    "time-only-domain-needs-second-epoch-before-admission",
    "time-only-frozen-after-admission-aborts",
    "time-quality-oscillation-does-not-refresh-progress-age",
    "date-quality-regression-never-publishes-time-only-fix",
    "provisional-stall-aborts-extension",
    "parser-crosses-progress-grace",
    "response-adc-crosses-progress-grace", "admission-adc-crosses-hard-deadline",
    "extended-adc-crosses-hard-deadline", "mission-arrives-during-admission-adc",
    "admission-adc-crosses-progress-grace",
    "silence-aborts-extension", "inline-reset-disqualifies-call",
    "model-recovery-disqualifies-call", "startup-time-included", "millis-wrap",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-source", type=Path, default=base.SOURCE)
    args = parser.parse_args()
    original = args.driver_source.read_text()
    with tempfile.TemporaryDirectory(prefix="gps-cold-extension-test-") as tmp:
        directory = Path(tmp)
        (directory / "Arduino.h").write_text(ARDUINO)
        (directory / "SparkFun_u-blox_GNSS_v3.h").write_text(
            base.GNSS_PREFIX + GNSS.replace("@CAPTURE_FRAMES@", base.capture_frames()))
        (directory / "gps_ublox.cpp").write_text(original)
        (directory / "test.cpp").write_text(TEST)
        binary = directory / "test"
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
            "-Werror", "-fsanitize=address,undefined", "-I", str(directory),
            "-I", str(base.ROOT / "firmware/include"), "-I", str(base.ROOT / "firmware/src"),
            str(directory / "test.cpp"), *(str(base.ROOT / f"firmware/src/{name}.cpp")
                for name in ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
            "-o", str(binary)], check=True, timeout=60)
        failures = 0
        for case in CASES:
            result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=20)
            print(result.stdout, end="")
            assert result.returncode in (0, 1) and not result.stderr, result
            failures += result.returncode != 0
        assert args.driver_source.read_text() == original
        print(f"Cold-extension actual-driver cases={len(CASES)} failures={failures}; facade timing, not physical energy proof")
        raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
