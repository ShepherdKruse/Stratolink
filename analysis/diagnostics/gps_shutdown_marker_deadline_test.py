#!/usr/bin/env python3
"""Run real gps_ublox_quiesce against a shared CFG/first-EOE deadline contract.

The entire current production GPS driver, its bounded stream and real marker,
freshness and value policies are compiled unchanged. The external GNSS facade
scripts CFG latency, parser-preflight completion, byte-arrival intervals,
per-read service time, finite noise, PMREQ acceptance and rail readings. It
intentionally does NOT execute SparkFun, real UART serialization, target
interrupts or physical standby/current. Integer byte spacing and read costs
are deliberate stress inputs, not measured UART/MCU timing. Noise has a finite
2500-byte limit, so even an unbounded production drain terminates in the test.

Named breaks: resetting the marker allowance after CFG, allowing the CFG phase
past 1500 ms, restarting the 2000 ms combined allowance after preflight, or
rejecting a valid first EOE which fits the combined allowance. Expected values
are literal elapsed-time/counter contracts, not calculated by production helpers.
The 650 ms marker latency is a diagnostic case, not a measured receiver bound.

This new regression is expected RED until the independently owned production
change shares unused CFG time with first-marker observation. It makes no
production edits and does not relax the separate 350 ms confirmation policy.
"""

from pathlib import Path
import hashlib
import argparse
import os
import subprocess
import tempfile

from gps_shutdown_ack_timing_experiment import ARDUINO as ACK_ARDUINO
from gps_time_domain_integration_test import GNSS as BASE_GNSS


ROOT = Path(__file__).resolve().parents[2]
STREAM = "class Stream" + ACK_ARDUINO.split("class Stream", 1)[1].split(
    "struct FakeSerial", 1)[0]

ARDUINO = r"""
#pragma once
#include <cstddef>
#include <cstdint>
inline uint32_t fake_millis = 0;
inline uint32_t millis() { return fake_millis; }
inline void delay(uint32_t ms) { fake_millis += ms; }
constexpr int LOW = 0, INPUT = 0, OUTPUT = 1, PA_0 = 0;
inline uint16_t rail_mv = 4399;
inline uint32_t config_cost_ms = 100, marker_after_ack_ms = 100;
inline uint32_t preflight_ready_ms = 0, next_marker_ms = 0;
inline uint32_t first_config_ms = 0, final_ack_ms = 0, pmreq_ms = 0;
inline unsigned configured = 0, marker_offset = 0, setter_calls = 0, pmreq_calls = 0;
inline bool no_marker = false, corrupt_marker = false, continued_uart = false;
inline bool standby_requested = false, waits_positive = true;
inline bool final_ack_seen = false;
inline uint32_t byte_spacing_ms = 0, read_cost_ms = 0;
inline uint32_t noise_ready_ms = 0, noise_after_ack_ms = 0;
inline uint32_t last_marker_complete_ms = 0;
inline unsigned noise_remaining = 0, noise_reads = 0, marker_reads = 0, complete_markers = 0;
inline constexpr uint8_t marker[] = {0xb5,0x62,1,0x61,4,0,0,0,0,0,0x66,0xc7};
inline void digitalWrite(int, int) {}
inline void pinMode(int, int mode) {
    if (mode == OUTPUT) {
        configured = marker_offset = 0;
        standby_requested = false;
    }
}
""" + STREAM + r"""
struct FakeSerial : Stream {
    void begin(uint32_t) {}
    int available() override {
        if (configured != 31u || (standby_requested && !continued_uart)) return 0;
        if (noise_remaining && int32_t(fake_millis - noise_ready_ms) >= 0) return 1;
        if (no_marker || int32_t(fake_millis -
                (next_marker_ms + marker_offset * byte_spacing_ms)) < 0) return 0;
        return byte_spacing_ms ? 1 : int(sizeof(marker) - marker_offset);
    }
    int read() override {
        if (available() == 0) return -1;
        if (noise_remaining && int32_t(fake_millis - noise_ready_ms) >= 0) {
            --noise_remaining; ++noise_reads;
            delay(read_cost_ms);
            return 0; // Finite non-UBX traffic keeps available() positive.
        }
        uint8_t value = marker[marker_offset++];
        ++marker_reads;
        delay(read_cost_ms);
        if (marker_offset == sizeof(marker)) {
            ++complete_markers;
            last_marker_complete_ms = fake_millis;
            marker_offset = 0;
            next_marker_ms = fake_millis + 100u;
            if (corrupt_marker) value ^= 1u;
        }
        return value;
    }
};
inline FakeSerial Serial1;
"""

GNSS = BASE_GNSS.replace(
    "struct SFE_UBLOX_GNSS_SERIAL : IdealConfigPackets {",
    "struct TimingFixtureGNSS : IdealConfigPackets {",
) + r"""
struct SFE_UBLOX_GNSS_SERIAL : TimingFixtureGNSS {
    bool checkUblox(uint8_t cls, uint8_t id) {
        if (cls == 0u && id == 0u) {
            if (int32_t(fake_millis - preflight_ready_ms) >= 0)
                currentSentence = SFE_UBLOX_SENTENCE_TYPE_NONE;
            return true;
        }
        return TimingFixtureGNSS::checkUblox(cls, id);
    }
    bool configure(uint32_t key, uint16_t value, uint8_t layer, uint16_t wait) {
        if (layer != VAL_LAYER_RAM) return false;
        unsigned bit = 0;
        if (key == UBLOX_CFG_UART1OUTPROT_UBX && value == 1u) bit = 1u;
        if (key == UBLOX_CFG_UART1OUTPROT_NMEA && value == 0u) bit = 2u;
        if (key == UBLOX_CFG_RATE_MEAS && value == 100u) bit = 4u;
        if (key == UBLOX_CFG_RATE_NAV && value == 1u) bit = 8u;
        if (key == UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1 && value == 1u) bit = 16u;
        if (!bit) return false;
        ++setter_calls;
        if (bit == 1u) first_config_ms = fake_millis;
        waits_positive = waits_positive && wait != 0u;
        const uint32_t latency = config_cost_ms / 5u +
            (bit == 16u ? config_cost_ms % 5u : 0u);
        delay(wait < latency ? wait : latency);
        if (wait < latency) return false;
        configured |= bit;
        if (configured == 31u) {
            final_ack_seen = true;
            final_ack_ms = fake_millis;
            next_marker_ms = fake_millis + marker_after_ack_ms;
            noise_ready_ms = fake_millis + noise_after_ack_ms;
        }
        return true;
    }
    bool setVal8(uint32_t key, uint8_t value, uint8_t layer, uint16_t wait) {
        return configure(key, value, layer, wait);
    }
    bool setVal16(uint32_t key, uint16_t value, uint8_t layer, uint16_t wait) {
        return configure(key, value, layer, wait);
    }
    bool powerOffWithInterrupt(uint32_t duration, uint32_t wake, bool force, uint16_t wait) {
        if (duration != 0u || wake != VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX || !force || wait != 0u)
            return false;
        ++pmreq_calls;
        pmreq_ms = fake_millis;
        standby_requested = true;
        return true;
    }
};
"""

TEST = r"""
#include <cstdio>
#include "gps_ublox.cpp"

uint16_t power_adc_read_vSTOR_mv() { return rail_mv; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }

struct Case {
    const char* name;
    uint32_t start, cfg_ms, eoe_ms, preflight_ms;
    bool missing, corrupt, traffic, confirmed;
    uint32_t max_elapsed_ms;
    uint32_t spacing_ms = 0, service_ms = 0;
    unsigned noise_bytes = 0;
    uint32_t noise_delay_ms = 0;
    unsigned max_noise_reads = 0;
};

static unsigned failures = 0u;
static void run(const Case& c) {
    fake_millis = c.start;
    rail_mv = 4399u; // Isolate one attempt; actual production rail gate blocks cold recovery.
    config_cost_ms = c.cfg_ms; marker_after_ack_ms = c.eoe_ms;
    configured = marker_offset = setter_calls = pmreq_calls = 0u;
    first_config_ms = final_ack_ms = pmreq_ms = 0u;
    no_marker = c.missing; corrupt_marker = c.corrupt; continued_uart = c.traffic;
    standby_requested = false; waits_positive = true; final_ack_seen = false;
    byte_spacing_ms = c.spacing_ms; read_cost_ms = c.service_ms;
    noise_remaining = c.noise_bytes; noise_after_ack_ms = c.noise_delay_ms;
    noise_reads = marker_reads = complete_markers = 0u;
    last_marker_complete_ms = noise_ready_ms = 0u;
    preflight_ready_ms = c.start + 10u + c.preflight_ms;
    gnss.currentSentence = c.preflight_ms ? 1u : SFE_UBLOX_SENTENCE_TYPE_NONE;
    gnss.stream = &gps_gnss_stream;
    gps_gnss_stream.end_position_phase();
    gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
    auto* diagnostics = reinterpret_cast<volatile unsigned char*>(&s_gps_diag);
    for (size_t i = 0; i < sizeof(s_gps_diag); ++i) diagnostics[i] = 0u;
    last_fix = {};
    const auto result = gps_ublox_quiesce();
    const uint32_t elapsed = fake_millis - c.start;
    // Literal 10 ms UART wake settle is outside the original 1500+500 allowance.
    const uint32_t before_pmreq = pmreq_ms - (c.start + 10u);
    const bool pmreq_bounded = pmreq_calls == 0u || before_pmreq < 2000u;
    const bool confirmed = result == GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY;
    bool good = confirmed == c.confirmed && elapsed <= c.max_elapsed_ms && pmreq_bounded &&
        waits_positive && s_gps_diag.hardware_resets == 0u &&
        gps_ublox_current_quiescence() == result;
    if (c.noise_bytes) good = good && noise_reads <= c.max_noise_reads;
    if (pmreq_calls) good = good && complete_markers > 0u &&
        uint32_t(last_marker_complete_ms - (c.start + 10u)) < 2000u;
    if (c.confirmed) {
        good = good && pmreq_calls == 1u && setter_calls == 5u &&
            s_gps_diag.backup_confirmations == 1u && s_gps_diag.backup_failures == 0u &&
            s_gps_diag.reset_hold_entries == 0u && s_gps_diag.backup_terminal_failures == 0u;
    } else {
        good = good && result == GPS_QUIESCENCE_RESET_HELD &&
            s_gps_diag.backup_confirmations == 0u && s_gps_diag.backup_failures == 1u &&
            s_gps_diag.reset_hold_entries == 1u && s_gps_diag.backup_terminal_failures == 1u &&
            (c.traffic ? pmreq_calls == 1u : pmreq_calls == 0u);
    }
    std::printf("[%s] %s: result=%u elapsed=%u pmreq=%u pre_pmreq=%u setters=%u "
                "cfg_ack_seen=%u cfg_ack_elapsed=%u backup_failures=%u resets=%u held=%u "
                "marker_reads=%u completed=%u completion_elapsed=%u noise_reads=%u\n",
                good ? "PASS" : "FAIL", c.name, unsigned(result), elapsed,
                pmreq_calls, pmreq_calls ? before_pmreq : 0u, setter_calls,
                unsigned(final_ack_seen), final_ack_seen ? uint32_t(final_ack_ms - (c.start + 10u)) : 0u,
                unsigned(s_gps_diag.backup_failures),
                unsigned(s_gps_diag.hardware_resets), unsigned(s_gps_diag.reset_hold_entries),
                marker_reads, complete_markers,
                complete_markers ? uint32_t(last_marker_complete_ms - (c.start + 10u)) : 0u,
                noise_reads);
    if (!good) ++failures;
}

int main() {
    const Case cases[] = {
        {"prompt marker remains successful", 0,100,100,0, false,false,false,true, 560},
        {"unused CFG budget admits EOE 650 ms after ACK", 0,100,650,0, false,false,false,true, 1110},
        {"marker immediately before combined deadline", 0,100,1899,0, false,false,false,true, 2359},
        {"marker at combined deadline is too late", 0,100,1900,0, false,false,false,false, 2010},
        {"late marker cannot extend combined budget", 0,100,2100,0, false,false,false,false, 2010},
        {"no marker fails closed within combined budget", 0,100,0,0, true,false,false,false, 2010},
        {"bad checksum cannot prove a marker", 0,100,100,0, false,true,false,false, 2010},
        {"1499 ms CFG retains only 501 ms for EOE", 0,1499,500,0, false,false,false,true, 2359},
        {"1499 ms CFG cannot grant another full window", 0,1499,600,0, false,false,false,false, 2010},
        {"CFG reaching 1500 ms is rejected", 0,1500,1,0, false,false,false,false, 1510},
        {"CFG exceeding 1500 ms is rejected", 0,1650,1,0, false,false,false,false, 1510},
        {"preflight time belongs to combined budget", 0,100,1600,400, false,false,false,false, 2010},
        {"preflight and delayed marker fit shared allowance", 0,100,650,400, false,false,false,true, 1511},
        {"preflight cannot consume marker budget for CFG", 0,100,1,1800, false,false,false,false, 1510},
        {"delayed marker works across millis wrap", UINT32_MAX-400u,100,650,0, false,false,false,true, 1110},
        {"missing marker remains bounded across wrap", UINT32_MAX-400u,100,0,0, true,false,false,false, 2010},
        {"continued UART cannot confirm standby", 0,100,100,0, false,false,true,false, 560},
        {"paced frame completing before deadline succeeds", 0,1499,488,0,
            false,false,false,true, 2359, 1,1},
        {"checksum read completing exactly at deadline is rejected", 0,1499,489,0,
            false,false,false,false, 2010, 1,1},
        {"read service cannot complete a frame after deadline", 0,1499,499,0,
            false,false,false,false, 2010, 1,1},
        {"two ms read crossing deadline is rejected", 0,1499,498,0,
            false,false,false,false, 2012, 1,2},
        {"split arrivals finishing after deadline are rejected", 0,1499,495,0,
            false,false,false,false, 2010, 1,0},
        {"checksum deadline applies across millis wrap", UINT32_MAX-400u,1499,489,0,
            false,false,false,false, 2010, 1,1},
        {"continuous noise in marker wait is deadline bounded", 0,100,0,0,
            true,false,false,false, 2011, 0,1,2500,1,1900},
        {"buffered noise in initial discard is deadline bounded", 0,100,0,0,
            true,false,false,false, 2011, 0,1,2500,0,1900},
    };
    for (const auto& c : cases) run(c);
    std::printf("Shutdown marker deadline: %u failing case(s)\n", failures);
    return failures ? 1 : 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-source", type=Path,
                        default=ROOT / "firmware/src/gps_ublox.cpp",
                        help="read-only alternate driver, for replaying a frozen pre-fix source")
    args = parser.parse_args()
    driver_source = args.driver_source.resolve()
    driver_text = driver_source.read_text()
    inputs = [driver_source,
              ROOT / "firmware/include/gps_backup_policy.h",
              ROOT / "firmware/src/gps_backup_policy.cpp"]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    with tempfile.TemporaryDirectory(prefix="stratolink-marker-deadline-") as temporary:
        build = Path(temporary)
        for name, contents in (("Arduino.h", ARDUINO), ("SparkFun_u-blox_GNSS_v3.h", GNSS),
                               ("test.cpp", TEST), ("gps_ublox.cpp", driver_text)):
            (build / name).write_text(contents)
        binary = build / "test"
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=address,undefined", "-g", "-I", str(build),
                        "-I", str(ROOT / "firmware/include"), "-I", str(ROOT / "firmware/src"),
                        str(build / "test.cpp"), *(str(ROOT / f"firmware/src/{name}.cpp")
                        for name in ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
                        "-o", str(binary)], check=True, timeout=60)
        result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                         UBSAN_OPTIONS="halt_on_error=1"))
        print(result.stdout, end="")
        print(result.stderr, end="")
        assert not result.stderr, "sanitizer/runtime errors are not an assertion RED"
    assert before == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    print("Production inputs unchanged:", before)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
