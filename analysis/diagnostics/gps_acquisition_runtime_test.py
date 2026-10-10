#!/usr/bin/env python3
"""Characterize real acquisition policy using the boot-94 PVT observations.

The checked-in, scalar-only fixture supplies MCU-elapsed PVT transitions from
the frozen capture, not UART packets or
uninstrumented TTFF. Between observations the external double returns the most
recent snapshot (explicit polls may repeat an epoch). Position fields absent
from the capture are synthetic. Configuration responses are ideal packet-shaped
VALGET/ACK replies checked by production, not the pinned parser; this does not replay
the measured 1776 ms model transaction, shutdown, sleep, RF, or physical energy.

Only GNSS, clock/GPIO and ADC/mission boundaries are fake. The driver, freshness,
PVT value gate and backup policy are compiled from production under ASan/UBSan.
Compiled mutants must fail behavioral assertions before the real source passes.
--mutation NAME exposes one expected RED run; no production files are edited.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import gps_time_domain_integration_test as base


ROOT = base.ROOT
FIXTURE = ROOT / "analysis/diagnostics/fixtures/gps_acquisition_boot94_pvt.json"
FIXTURE_SHA256 = "d576e5a852dd94ca8c1295dc11ccb4230b39937b9acb88cf9143475110ea30d3"
CAPTURE_SHA256 = "fe4986cd82d2384da08dc187c3c2e148da8641cdb8e3ddc17f3ec0bcb119c622"
SOURCE = ROOT / "firmware/src/gps_ublox.cpp"


def capture_frames() -> str:
    payload = FIXTURE.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    fixture = json.loads(payload)
    assert fixture["source_capture_sha256"] == CAPTURE_SHA256
    frames = [[tuple(row) for row in fixture[key]]
              for key in ("cold_frames", "warm_frames")]
    # Literal, independently reviewed landmarks bind the characterization to
    # this evidence; they are not expectations calculated by production helpers.
    assert [len(rows) for rows in frames] == [199, 17]
    for row in (
        (541, 3000, 240, 0, 0, 0),
        (39765, 195140113, 242, 0, 0, 0),
        (49412, 195152000, 243, 0, 0, 0),
        (158350, 195288000, 243, 3, 0, 4),
        (159052, 195289000, 243, 3, 1, 4),
    ):
        assert row in frames[0]
    assert frames[1][0] == (2089, 195334000, 243, 0, 0, 0)
    assert frames[1][-2:] == [
        (13928, 195349000, 243, 3, 0, 4),
        (14731, 195350000, 243, 3, 1, 4),
    ]
    arrays = []
    for name, rows in zip(("cold_frames", "warm_frames"), frames):
        assert all(a[0] < b[0] for a, b in zip(rows, rows[1:]))
        values = ",\n".join("    {" + ", ".join(f"{v}u" for v in row) + "}"
                            for row in rows)
        arrays.append(f"inline const Frame {name}[] = {{\n{values}\n}};")
    return "\n".join(arrays)


ARDUINO = base.ARDUINO.replace(
    "inline void digitalWrite(int, int) {}",
    "inline unsigned reset_edges = 0;\n"
    "inline bool reset_low = false;\n"
    "inline void digitalWrite(int, int level) {\n"
    "    if (level == 0 && !reset_low) ++reset_edges;\n"
    "    reset_low = level == 0;\n"
    "}",
).replace(
    "inline void pinMode(int, int) {}",
    "inline void pinMode(int, int mode) { if (mode == 0) reset_low = false; }",
)
GNSS_PREFIX = base.GNSS.split("enum Scenario {", 1)[0].replace(
    "DYN_MODEL_AIRBORNE_4G", "DYN_MODEL_AIRBORNE4g")
GNSS = r"""
struct Frame {
    uint32_t elapsed, itow;
    uint8_t valid, fix_type, flags, satellites;
};
@CAPTURE_FRAMES@
enum Scenario { COLD, WARM, ADVANCING_NOFIX, PROVISIONAL, SILENT, CACHED,
                IMPOSSIBLE_VALUE };
inline Scenario scenario = COLD;
inline uint32_t origin = 0, position_reads = 0;
inline Frame current{};
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
    bool emitPVT() {
        if (scenario == SILENT) return false;
        if (scenario == COLD || scenario == WARM) {
            const Frame* rows = scenario == COLD ? cold_frames : warm_frames;
            const unsigned count = scenario == COLD
                ? sizeof(cold_frames) / sizeof(Frame)
                : sizeof(warm_frames) / sizeof(Frame);
            uint32_t elapsed = fake_millis - origin;
            if (elapsed < rows[0].elapsed) return false;
            unsigned index = 0;
            while (index + 1u < count && rows[index + 1u].elapsed <= elapsed)
                ++index;
            current = rows[index];
            return true;
        }
        current = {0u, 400000000u + (fake_millis / 1000u) * 1000u,
                   3u, 0u, 0u, 0u};
        if (scenario == PROVISIONAL) current.valid = 0u;
        if (scenario == CACHED || scenario == IMPOSSIBLE_VALUE) {
            current.fix_type = 3u;
            current.flags = 1u;
            current.satellites = 4u;
        }
        if (scenario == CACHED) current.itow = 195289000u;
        return true;
    }
    bool getPVT(uint16_t) {
        packetUBXNAVPVT = &storage;
        const uint8_t prefix[] = {0xb5, 0x62, 0x01, 0x07, 0x00, 0x00};
        const uint8_t suffix[] = {0x08, 0x19};
        (void)stream->write(prefix, sizeof(prefix));
        (void)stream->write(suffix, sizeof(suffix));
        return false;
    }
    uint32_t getTimeOfWeek() { return current.itow; }
    bool getDateValid() { return (current.valid & 1u) != 0u; }
    bool getTimeValid() { return (current.valid & 2u) != 0u; }
    bool getTimeFullyResolved() { return (current.valid & 4u) != 0u; }
    uint8_t getFixType() { return current.fix_type; }
    bool getGnssFixOk() { return (current.flags & 1u) != 0u; }
    uint8_t getSIV() { return current.satellites; }
    int32_t getLatitude() { ++position_reads; return 370000000; }
    int32_t getLongitude() { ++position_reads; return -1220000000; }
    int32_t getAltitude() {
        ++position_reads;
        return scenario == IMPOSSIBLE_VALUE ? 60000001 : 123000;
    }
    int32_t getGroundSpeed() { ++position_reads; return 1000; }
    int32_t getHeading() { ++position_reads; return 9000000; }
    bool checkUblox(uint8_t cls, uint8_t id) {
        if (cls == UBX_CLASS_CFG) return configResponse(cls, id);
        if (!emitPVT()) return false;
        storage.data.iTOW = current.itow;
        storage.data.valid.all = current.valid;
        storage.data.flags.all = current.flags;
        storage.data.numSV = current.satellites;
        storage.data.lat = 370000000;
        storage.data.lon = -1220000000;
        storage.data.height = scenario == IMPOSSIBLE_VALUE ? 60000001 : 123000;
        storage.data.gSpeed = 1000;
        storage.data.headMot = 9000000;
        storage.moduleQueried.moduleQueried1.all = 1u;
        storage.moduleQueried.moduleQueried2.all = 1u;
        return true;
    }
};
"""

TEST = r"""
#include <cstdio>
#include <initializer_list>
#include "gps_ublox.cpp"

uint16_t power_adc_read_vSTOR_mv() { return 4660u; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }

static unsigned failures = 0;
static void check(const char* name, bool ok) {
    std::printf("[%s] %s: tick=%u accepted=%u nofresh=%u resets=%u edges=%u\n",
        ok ? "PASS" : "FAIL", name, fake_millis, s_gps_diag.accepted_fixes,
        s_gps_diag.no_fresh_cycles, s_gps_diag.hardware_resets, reset_edges);
    if (!ok) ++failures;
}
static void reset_case(Scenario selected) {
    scenario = selected;
    fake_millis = origin = position_reads = reset_edges = 0u;
    current = {};
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0u;
    gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
    s_gps_diag.hardware_resets = s_gps_diag.accepted_fixes = 0u;
    s_gps_diag.no_fresh_cycles = s_gps_diag.rejected_value_fixes = 0u;
    s_gps_diag.power_aborts = s_gps_diag.dyn_model_terminal_failures = 0u;
    last_fix = {};
    (void)gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);
}
static gps_fix_t previously_valid() {
    gps_fix_t fix{};
    fix.valid = true;
    fix.satellites = 8u;
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
int main() {
    // Break caught: treat an ordinary no-fix/provisional receiver as wedged.
    reset_case(COLD);
    gps_fix_t fix = previously_valid();
    check("cold trace exceeds 30s policy without resetting healthy acquisition",
        !gps_ublox_get_fix(&fix, 30000u) && !fix.valid && fix.satellites == 0u &&
        !last_fix.valid && s_gps_diag.accepted_fixes == 0u &&
        s_gps_diag.no_fresh_cycles == 1u && no_reset() && position_reads == 0u &&
        fake_millis >= 30000u && fake_millis < 31000u);

    // 158.5s lies after the observed 3D/4-satellite row but before fixOK.
    reset_case(COLD);
    fix = previously_valid();
    check("3D with four satellites but fixOK false remains unusable",
        !gps_ublox_get_fix(&fix, 158500u) && !fix.valid &&
        fix.satellites == 0u && s_gps_diag.accepted_fixes == 0u &&
        position_reads == 0u && no_reset() && fake_millis < 159052u);

    // Break caught: provisional UTC poisons the anchor or no-fix causes reset.
    reset_case(COLD);
    check("600s diagnostic ceiling accepts cold trace only after fixOK",
        gps_ublox_get_fix(&fix, 600000u) && expected_position(fix) &&
        s_gps_diag.accepted_fixes == 1u && s_gps_diag.no_fresh_cycles == 0u &&
        no_reset() && fake_millis >= 159052u && fake_millis < 159200u);

    // Preserve the accepted epoch/cache from the prior real-driver call.
    // Only the external PVT stream changes; this does NOT test actual standby.
    scenario = WARM;
    origin = fake_millis;
    check("captured warm PVT stream is accepted inside a 30s window",
        gps_ublox_get_fix(&fix, 30000u) && expected_position(fix) &&
        s_gps_diag.accepted_fixes == 2u && no_reset() &&
        fake_millis - origin >= 14731u && fake_millis - origin < 14900u);

    // Break caught: UART responses are confused with position-fix success.
    for (Scenario healthy : {ADVANCING_NOFIX, PROVISIONAL}) {
        reset_case(healthy);
        bool all_invalid = true;
        for (unsigned cycle = 0; cycle < GPS_STALE_RECOVERY_CYCLES + 2u; ++cycle) {
            fix = previously_valid();
            if (gps_ublox_get_fix(&fix, 30000u) || fix.valid || fix.satellites)
                all_invalid = false;
        }
        check(healthy == PROVISIONAL
                  ? "responding provisional UTC never triggers either reset ladder"
                  : "advancing qualified no-fix never triggers either reset ladder",
            all_invalid && no_reset() && consecutive_no_fresh == 0u &&
            s_gps_diag.accepted_fixes == 0u && position_reads == 0u &&
            s_gps_diag.no_fresh_cycles == GPS_STALE_RECOVERY_CYCLES + 2u);
    }

    // An unanchored receiver must exercise silence recovery independently of
    // the three-second frozen-epoch branch used by a retained anchor.
    reset_case(SILENT);
    fix = previously_valid();
    check("unanchored silence still triggers one bounded recovery",
        !gps_ublox_get_fix(&fix, 10000u) && !fix.valid && fix.satellites == 0u &&
        s_gps_diag.accepted_fixes == 0u && s_gps_diag.no_fresh_cycles == 1u &&
        s_gps_diag.hardware_resets == 1u && reset_edges == 1u &&
        position_reads == 0u && fake_millis >= 10000u && fake_millis < 12000u);

    // Break caught: silent cached getters leak a previous successful position.
    reset_case(COLD);
    (void)gps_ublox_get_fix(&fix, 600000u);
    scenario = SILENT;
    origin = fake_millis;
    position_reads = 0u;
    check("silence invalidates a prior fix and recovers once per window",
        !gps_ublox_get_fix(&fix, 10000u) && !fix.valid && fix.satellites == 0u &&
        !last_fix.valid && s_gps_diag.accepted_fixes == 1u &&
        s_gps_diag.hardware_resets == 1u && reset_edges == 1u &&
        position_reads == 0u && fake_millis - origin < 12000u);

    // Break caught: bypass freshness, accepting repeated qualified coordinates.
    reset_case(COLD);
    (void)gps_ublox_get_fix(&fix, 600000u);
    scenario = CACHED;
    origin = fake_millis;
    position_reads = 0u;
    check("frozen cached fix cannot be accepted and recovers only once",
        !gps_ublox_get_fix(&fix, 10000u) && !fix.valid && fix.satellites == 0u &&
        !last_fix.valid && s_gps_diag.accepted_fixes == 1u &&
        s_gps_diag.hardware_resets == 1u && reset_edges == 1u &&
        position_reads == 0u && fake_millis - origin < 12000u);

    reset_case(IMPOSSIBLE_VALUE);
    check("advancing fresh fix still crosses the real numeric value gate",
        !gps_ublox_get_fix(&fix, 6000u) && !fix.valid &&
        s_gps_diag.accepted_fixes == 0u && s_gps_diag.rejected_value_fixes > 0u &&
        no_reset());
    return failures ? 1 : 0;
}
"""

MUTATIONS = {
    "reset-healthy": (
        "gps_recovery_due(epoch_anchor_available, now,",
        "gps_recovery_due(epoch_anchor_available || module_responded, now,",
        "responding provisional UTC never triggers either reset ladder",
    ),
    "bypass-freshness": (
        "&pvt_freshness, itow, last_pvt_time_valid)) {",
        "&pvt_freshness, itow, last_pvt_time_valid) || true) {",
        "frozen cached fix cannot be accepted and recovers only once",
    ),
    "bypass-fixok": (
        "if (pvt_packet.flags.bits.gnssFixOK && siv >= 4) {",
        "if ((pvt_packet.flags.bits.gnssFixOK || true) && siv >= 4) {",
        "3D with four satellites but fixOK false remains unusable",
    ),
    "silence-requires-anchor": (
        "last_epoch_progress_ms, last_pvt_ms)) {",
        "last_epoch_progress_ms, last_pvt_ms) && epoch_anchor_available) {",
        "unanchored silence still triggers one bounded recovery",
    ),
}


def run(source: str, frames: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="stratolink-gps-acquisition-") as tmp:
        directory = Path(tmp)
        (directory / "Arduino.h").write_text(ARDUINO, encoding="utf-8")
        (directory / "SparkFun_u-blox_GNSS_v3.h").write_text(
            GNSS_PREFIX + GNSS.replace("@CAPTURE_FRAMES@", frames), encoding="utf-8")
        (directory / "gps_ublox.cpp").write_text(source, encoding="utf-8")
        (directory / "test.cpp").write_text(TEST, encoding="utf-8")
        binary = directory / "test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
            "-Werror", "-fsanitize=address,undefined", "-g",
            "-I", str(directory), "-I", str(ROOT / "firmware/include"),
            "-I", str(ROOT / "firmware/src"), str(directory / "test.cpp"),
            *(str(ROOT / f"firmware/src/{name}.cpp") for name in (
                "gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
            "-o", str(binary),
        ], check=True, timeout=60)
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutation", choices=MUTATIONS)
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8")
    frames = capture_frames()
    for name in (args.mutation,) if args.mutation else MUTATIONS:
        old, new, expected_failure = MUTATIONS[name]
        assert source.count(old) == 1, f"review changed mutation target: {name}"
        result = run(source.replace(old, new, 1), frames)
        if args.mutation:
            print(result.stdout, end="")
            print(result.stderr, end="")
            raise SystemExit(result.returncode)
        assert result.returncode == 1 and not result.stderr, result
        assert f"[FAIL] {expected_failure}:" in result.stdout, result.stdout
        print(f"PASS: compiled {name} mutant rejected by {expected_failure}")
    result = run(source, frames)
    print(result.stdout, end="")
    assert result.returncode == 0 and not result.stderr, result
    assert result.stdout.count("[PASS]") == 10
    assert SOURCE.read_text(encoding="utf-8") == source
    print("PASS: 10 real-driver acquisition cases; 4 compiled mutants rejected; "
          "capture-bound characterization, not timing/energy/flight qualification")


if __name__ == "__main__":
    main()
