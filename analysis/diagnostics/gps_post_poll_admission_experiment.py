#!/usr/bin/env python3
"""RED experiment for admitting a PVT after acquisition authority has expired.

The real driver, freshness/value gates and backup policy run under ASan/UBSan
using the existing acquisition harness. Only external GNSS, time/GPIO, ADC and
mission inputs are simulated. A successful PVT poll can consume scripted time
and change the external rail or pending interrupt before returning. These are
boundary fixtures, not a model or proof of the pinned library's UART/transaction
return bound, physical energy, or TTFF. Configuration replies are ideal
packet-shaped responses, validated by production but not the pinned parser.

This intentionally is not an automatically discovered *_test.py. It exits
nonzero while production accepts an otherwise usable PVT after its deadline,
rail floor, or mission authority changes. Production files are never modified.
"""

import hashlib

import gps_acquisition_runtime_test as harness


GNSS = r"""
enum AdmissionScenario { HEALTHY, LOW_RAIL, FREEFALL, NOFIX, FLOOR_RAIL };
inline AdmissionScenario scenario = HEALTHY;
inline uint32_t second_poll_wait_ms = 100u;
inline unsigned polls_this_call = 0u, total_polls = 0u, cached_getters = 0u;
inline uint16_t rail_mv = 4660u;
inline bool mission_pending = false, response_pending = false;
struct SFE_UBLOX_GNSS_SERIAL : IdealConfigPackets {
    Stream* stream = nullptr;
    FakePvtPacket storage{};
    FakePvtPacket* packetUBXNAVPVT = nullptr;
    bool begin(Stream& selected, uint16_t) { stream = &selected; return true; }
    bool sendCommand(ubxPacket* packet, uint16_t wait) { return sendConfig(stream, packet, wait); }
    bool setDynamicModel(dynModel, uint8_t, uint16_t) { return true; }
    uint8_t getDynamicModel(uint8_t, uint16_t) { return 8; }
    bool setVal8(uint32_t, uint8_t, uint8_t, uint16_t) { return true; }
    bool setVal16(uint32_t, uint16_t, uint8_t, uint16_t) { return true; }
    bool powerOffWithInterrupt(uint32_t, uint32_t, bool, uint16_t) { return true; }
    bool getPVT(uint16_t) {
        packetUBXNAVPVT = &storage;
        ++polls_this_call;
        ++total_polls;
        response_pending = true;
        const uint8_t prefix[] = {0xb5, 0x62, 0x01, 0x07, 0x00, 0x00};
        const uint8_t suffix[] = {0x08, 0x19};
        (void)stream->write(prefix, sizeof(prefix));
        (void)stream->write(suffix, sizeof(suffix));
        return false;
    }
    bool checkUblox(uint8_t cls, uint8_t id) {
        if (cls == UBX_CLASS_CFG) return configResponse(cls, id);
        if (!response_pending) return false;
        response_pending = false;
        delay(polls_this_call == 2u ? second_poll_wait_ms : 100u);
        if (polls_this_call == 2u) {
            if (scenario == LOW_RAIL) rail_mv = 3599u;
            if (scenario == FLOOR_RAIL) rail_mv = 3600u;
            if (scenario == FREEFALL) mission_pending = true;
        }
        storage.data.iTOW = 400000000u + total_polls * 1000u;
        storage.data.valid.all = 3u;
        storage.data.flags.all = scenario != NOFIX && polls_this_call >= 2u ? 1u : 0u;
        storage.data.numSV = 4u;
        storage.data.lat = 370000000;
        storage.data.lon = -1220000000;
        storage.data.height = 123000;
        storage.data.gSpeed = 1000;
        storage.data.headMot = 9000000;
        storage.moduleQueried.moduleQueried1.all = 1u;
        storage.moduleQueried.moduleQueried2.all = 1u;
        return true;
    }
    uint32_t getTimeOfWeek() { ++cached_getters; return 400000000u + total_polls * 1000u; }
    bool getDateValid() { ++cached_getters; return true; }
    bool getTimeValid() { ++cached_getters; return true; }
    bool getTimeFullyResolved() { ++cached_getters; return false; }
    bool getGnssFixOk() { ++cached_getters; return scenario != NOFIX && polls_this_call >= 2u; }
    uint8_t getSIV() { ++cached_getters; return 4u; }
    int32_t getLatitude() { ++cached_getters; return 370000000; }
    int32_t getLongitude() { ++cached_getters; return -1220000000; }
    int32_t getAltitude() { ++cached_getters; return 123000; }
    int32_t getGroundSpeed() { ++cached_getters; return 1000; }
    int32_t getHeading() { ++cached_getters; return 9000000; }
};
"""

TEST = r"""
#include <cstdio>
#include "gps_ublox.cpp"

uint16_t power_adc_read_vSTOR_mv() { return rail_mv; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return mission_pending; }

static unsigned failures = 0u, checks = 0u;
static void check(const char* name, bool ok, bool returned,
                  const gps_fix_t& fix) {
    ++checks;
    std::printf("[%s] %s: returned=%u valid=%u cachevalid=%u sat=%u "
                "accepted=%u power=%u mission=%u nofresh=%u resets=%u "
                "edges=%u tick=%u rail=%u pending=%u\n",
        ok ? "PASS" : "FAIL", name, unsigned(returned), unsigned(fix.valid),
        unsigned(last_fix.valid), unsigned(fix.satellites),
        s_gps_diag.accepted_fixes, s_gps_diag.power_aborts,
        s_gps_diag.mission_aborts, s_gps_diag.no_fresh_cycles,
        s_gps_diag.hardware_resets, reset_edges, fake_millis,
        unsigned(rail_mv), unsigned(mission_pending));
    if (!ok) ++failures;
}
static void reset_case(AdmissionScenario selected, uint32_t start = 0u) {
    scenario = selected;
    fake_millis = start;
    second_poll_wait_ms = 100u;
    polls_this_call = total_polls = cached_getters = reset_edges = 0u;
    rail_mv = 4660u;
    mission_pending = false;
    response_pending = false;
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0u;
    gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
    s_gps_diag.hardware_resets = s_gps_diag.accepted_fixes = 0u;
    s_gps_diag.power_aborts = s_gps_diag.mission_aborts = 0u;
    s_gps_diag.no_fresh_cycles = s_gps_diag.rejected_value_fixes = 0u;
    s_gps_diag.dyn_model_terminal_failures = 0u;
    last_fix = {};
    (void)gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);
}
static gps_fix_t previously_valid() {
    gps_fix_t fix{};
    fix.valid = true;
    fix.satellites = 8u;
    last_fix = fix;
    return fix;
}
static bool no_reset() {
    return s_gps_diag.hardware_resets == 0u && reset_edges == 0u;
}
static bool expected_position(const gps_fix_t& fix) {
    return fix.valid && fix.lat_e7 == 370000000 && fix.lon_e7 == -1220000000 &&
        fix.altitude_m == 123 && fix.speed_cm_s == 100u &&
        fix.heading_cd == 9000u && fix.satellites == 4u;
}
static bool accepted_control(bool returned, const gps_fix_t& fix) {
    return returned && expected_position(fix) && last_fix.valid &&
        s_gps_diag.accepted_fixes == 1u && s_gps_diag.power_aborts == 0u &&
        s_gps_diag.mission_aborts == 0u && s_gps_diag.no_fresh_cycles == 0u &&
        cached_getters == 0u && no_reset();
}
static bool rejected(bool returned, const gps_fix_t& fix,
                     unsigned powers, unsigned missions) {
    return !returned && !fix.valid && fix.satellites == 0u && !last_fix.valid &&
        s_gps_diag.accepted_fixes == 0u && s_gps_diag.power_aborts == powers &&
        s_gps_diag.mission_aborts == missions && cached_getters == 0u && no_reset();
}
int main() {
    // The first response anchors real freshness; the next advances and has a
    // valid position. The deadline now starts at acquisition entry, including
    // the 13 ms supervised wake. Ideal packet configuration adds no fake time.
    reset_case(HEALTHY);
    gps_fix_t fix = previously_valid();
    bool returned = gps_ublox_get_fix(&fix, 1000u);
    check("timely healthy advancing PVT is accepted",
          accepted_control(returned, fix), returned, fix);

    reset_case(HEALTHY);
    second_poll_wait_ms = 786u; // 13 wake + 100 first + 100 loop + 786 = 999 ms.
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("one millisecond before deadline remains admissible",
          accepted_control(returned, fix) && fake_millis == 999u, returned, fix);

    reset_case(HEALTHY, UINT32_MAX - 250u);
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("timely PVT across millis wrap remains admissible",
          accepted_control(returned, fix), returned, fix);

    reset_case(FLOOR_RAIL);
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("rail exactly at acquisition floor remains admissible",
          accepted_control(returned, fix), returned, fix);

    // A return at the deadline is too late: the driver's existing loop uses
    // strict positive remaining time. These wait fixtures also cross wrap.
    for (unsigned variant = 0u; variant < 3u; ++variant) {
        reset_case(HEALTHY, variant == 2u ? UINT32_MAX - 500u : 0u);
        second_poll_wait_ms = variant == 0u ? 788u : 787u;
        fix = previously_valid();
        returned = gps_ublox_get_fix(&fix, 1000u);
        const char* name = variant == 0u
            ? "PVT returned after deadline is rejected and invalidated"
            : variant == 1u
            ? "PVT returned exactly at deadline is rejected and invalidated"
            : "PVT returned at wrapped deadline is rejected and invalidated";
        check(name, rejected(returned, fix, 0u, 0u), returned, fix);
    }

    // Changes occur inside the successful external poll, not before entry.
    // The rail case is before the next 1 Hz sample: admission needs current
    // authority even when the periodic maintenance sample is not due yet.
    reset_case(LOW_RAIL);
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("rail sag during valid poll aborts and counts power not success",
          rejected(returned, fix, 1u, 0u) && s_gps_diag.no_fresh_cycles == 0u,
          returned, fix);

    reset_case(FREEFALL);
    fix = previously_valid();
    returned = gps_ublox_get_fix(&fix, 1000u);
    check("freefall during valid poll aborts and counts mission not success",
          rejected(returned, fix, 0u, 1u) && s_gps_diag.no_fresh_cycles == 0u,
          returned, fix);

    // Repeat beyond the real reset-ladder threshold. Keep real freshness and
    // globally advancing iTOW between calls; only each external poll schedule
    // restarts. Late responsive PVT is not proof of a silent/frozen receiver.
    reset_case(HEALTHY);
    second_poll_wait_ms = 788u;
    bool all_rejected = true;
    const unsigned cycles = GPS_STALE_RECOVERY_CYCLES + 2u;
    for (unsigned cycle = 0u; cycle < cycles; ++cycle) {
        polls_this_call = 0u;
        fix = previously_valid();
        returned = gps_ublox_get_fix(&fix, 1000u);
        if (!rejected(returned, fix, 0u, 0u)) all_rejected = false;
    }
    check("repeated late responsive PVT stays invalid without reset escalation",
          all_rejected && no_reset() && consecutive_no_fresh == 0u &&
          s_gps_diag.no_fresh_cycles == cycles, returned, fix);

    reset_case(NOFIX);
    all_rejected = true;
    for (unsigned cycle = 0u; cycle < cycles; ++cycle) {
        polls_this_call = 0u;
        fix = previously_valid();
        returned = gps_ublox_get_fix(&fix, 6000u);
        if (!rejected(returned, fix, 0u, 0u)) all_rejected = false;
    }
    check("ordinary advancing no-fix remains invalid without reset escalation",
          all_rejected && no_reset() && consecutive_no_fresh == 0u &&
          s_gps_diag.no_fresh_cycles == cycles, returned, fix);

    std::printf("SUMMARY: %u checks, %u failures; external-boundary model only\n",
                checks, failures);
    return failures == 0u ? 0 : 1;
}
"""


def main() -> None:
    inputs = [harness.SOURCE, *(harness.ROOT / f"firmware/src/{name}.cpp"
              for name in ("gps_freshness", "gps_pvt_validation", "gps_backup_policy"))]
    before = {path: path.read_bytes() for path in inputs}
    harness.GNSS = GNSS
    harness.TEST = TEST
    result = harness.run(before[harness.SOURCE].decode("utf-8"), "")
    print(result.stdout, end="")
    print(result.stderr, end="")
    assert all(path.read_bytes() == payload for path, payload in before.items()), (
        "production input changed during experiment")
    for path, payload in before.items():
        print(f"UNCHANGED {path.relative_to(harness.ROOT)} "
              f"sha256={hashlib.sha256(payload).hexdigest()}")
    assert not result.stderr, "unexpected runtime/sanitizer diagnostic, not assertion RED"
    assert result.returncode in (0, 1), "unexpected experiment execution failure"
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
