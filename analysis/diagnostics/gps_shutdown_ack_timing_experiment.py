#!/usr/bin/env python3
"""Deliberately red, manually invoked shutdown ACK-timing regression.

Compile the real gps_ublox.cpp, freshness/value gates, and standby policy with
the existing time-domain harness's GNSS facade. Only external GNSS responses,
UART bytes, time, and rail readings are simulated. The 401 ms fixture comes
from stratolink1_upstairs_cfg_wait1200_v2_capture_20261006.json; it is an observed
latency, not a proposed production timeout or a claimed receiver upper bound.

This does not execute SparkFun's parser/serial implementation or qualify energy,
physical standby, actual EOE cadence, or debugger-free ACK latency. It exercises
the production driver's response to that transport outcome. No production code
is modified. This filename intentionally does not match the diagnostic runner's
*_test.py glob. Run directly; the delayed-ACK assertion must remain visibly red
until a production remedy is separately selected and implemented.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from gps_time_domain_integration_test import GNSS as BASE_GNSS


ROOT = Path(__file__).resolve().parents[2]

ARDUINO = r"""
#pragma once
#include <cstddef>
#include <cstdint>
inline uint32_t fake_millis = 0;
inline uint32_t millis() { return fake_millis; }
inline void delay(uint32_t ms) { fake_millis += ms; }
constexpr int LOW = 0, INPUT = 0, OUTPUT = 1, PA_0 = 0;
enum ShutdownFixture { PROMPT_ACK, DELAYED_ACK, NO_ACK, NACK,
                       NO_EOE, CONTINUED_TRAFFIC, LOW_RAIL_NO_ACK };
inline ShutdownFixture shutdown_fixture = PROMPT_ACK;
inline uint16_t rail_mv = 4660;
inline unsigned receiver_resets = 0;
inline unsigned configured = 0;
inline bool standby_requested = false;
inline uint32_t next_marker_ms = 0;
inline unsigned marker_offset = 0;
// Hand-checked UBX-NAV-EOE: iTOW=0, Fletcher checksum 66 c7.
inline constexpr uint8_t marker[] = {
    0xb5, 0x62, 0x01, 0x61, 0x04, 0x00, 0, 0, 0, 0, 0x66, 0xc7
};
inline void digitalWrite(int, int) {}
inline void pinMode(int, int mode) {
    if (mode == OUTPUT) {
        ++receiver_resets;
        configured = 0;
        standby_requested = false;
        marker_offset = 0;
    }
}
class Stream {
public:
    virtual ~Stream() = default;
    virtual int available() { return 0; }
    virtual int availableForWrite() { return 63; }
    virtual int read() { return -1; }
    virtual int peek() { return -1; }
    virtual void flush() {}
    virtual size_t write(uint8_t) { return 1u; }
    virtual size_t write(const uint8_t* data, size_t size) {
        size_t accepted = 0u;
        while (accepted < size && write(data[accepted]) == 1u) ++accepted;
        return accepted;
    }
    size_t readBytes(uint8_t* data, size_t size) {
        size_t accepted = 0u;
        while (accepted < size) {
            int value = read();
            if (value < 0) break;
            data[accepted++] = (uint8_t)value;
        }
        return accepted;
    }
};
struct FakeSerial : Stream {
    void begin(uint32_t) {}
    int available() {
        if (configured != 31u || shutdown_fixture == NO_EOE ||
            (standby_requested && shutdown_fixture != CONTINUED_TRAFFIC) ||
            fake_millis < next_marker_ms) return 0;
        return static_cast<int>(sizeof(marker) - marker_offset);
    }
    int read() {
        if (!available()) return -1;
        uint8_t byte = marker[marker_offset++];
        if (marker_offset == sizeof(marker)) {
            marker_offset = 0;
            next_marker_ms = fake_millis + 100u;
        }
        return byte;
    }
};
inline FakeSerial Serial1;
"""

# Reuse the already exercised PVT facade so each shutdown follows acceptance
# through the real driver, rather than manufacturing an accepted-fix counter.
GNSS = BASE_GNSS.replace(
    "struct SFE_UBLOX_GNSS_SERIAL : IdealConfigPackets {",
    "struct PVTFixtureGNSS : IdealConfigPackets {"
) + r"""
struct SFE_UBLOX_GNSS_SERIAL : PVTFixtureGNSS {
    bool configure(uint32_t key, uint16_t value, uint8_t layer,
                   uint16_t max_wait) {
        if (layer != VAL_LAYER_RAM) return false;
        unsigned bit = 0;
        if (key == UBLOX_CFG_UART1OUTPROT_UBX && value == 1) bit = 1;
        if (key == UBLOX_CFG_UART1OUTPROT_NMEA && value == 0) bit = 2;
        if (key == UBLOX_CFG_RATE_MEAS && value == 100) bit = 4;
        if (key == UBLOX_CFG_RATE_NAV && value == 1) bit = 8;
        if (key == UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1 && value == 1) bit = 16;
        if (!bit) return false;
        uint32_t ack_latency = 20u;
        if (key == UBLOX_CFG_UART1OUTPROT_UBX) {
            if (shutdown_fixture == NO_ACK ||
                shutdown_fixture == LOW_RAIL_NO_ACK) {
                delay(max_wait);
                return false;
            }
            if (shutdown_fixture == NACK) {
                delay(max_wait < 20u ? max_wait : 20u);
                return false;
            }
            // A reset returns the fixture to the prompt-response condition
            // seen on the physical capture's second attempt. A late ACK does
            // not count as success when the caller's wait has already expired.
            if (shutdown_fixture == DELAYED_ACK && receiver_resets == 0u)
                ack_latency = 401u;
        }
        delay(max_wait < ack_latency ? max_wait : ack_latency);
        if (max_wait <= ack_latency) return false;
        configured |= bit;
        if (configured == 31u) next_marker_ms = fake_millis + 100u;
        return true;
    }
    bool setVal8(uint32_t key, uint8_t value, uint8_t layer, uint16_t wait) {
        return configure(key, value, layer, wait);
    }
    bool setVal16(uint32_t key, uint16_t value, uint8_t layer, uint16_t wait) {
        return configure(key, value, layer, wait);
    }
    bool powerOffWithInterrupt(uint32_t duration, uint32_t wake,
                               bool force, uint16_t wait) {
        if (duration != 0 || wake != VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX ||
            !force || wait != 0) return false;
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

static int failures = 0;
static void run_case(const char* name, ShutdownFixture selected,
                     gps_quiescence_result_t expected,
                     unsigned expected_resets, unsigned expected_failures) {
    shutdown_fixture = selected;
    scenario = COLD_LATE_WEEK;
    fake_millis = 0;
    rail_mv = selected == LOW_RAIL_NO_ACK ? 4399u : 4660u;
    receiver_resets = configured = marker_offset = 0;
    standby_requested = false;
    next_marker_ms = 0;
    position_reads = 0;
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
    auto* diagnostics = reinterpret_cast<volatile unsigned char*>(&s_gps_diag);
    for (unsigned i = 0; i < sizeof(s_gps_diag); ++i) diagnostics[i] = 0;
    last_fix = {};
    gnss.stream = &gps_gnss_stream;
    gps_fix_t fix{};
    bool accepted = gps_ublox_get_fix(&fix, 10000u) && fix.valid &&
                    s_gps_diag.accepted_fixes == 1u;
    if (!accepted) {
        std::printf("[FAIL] %s: accepted-fix fixture did not qualify\n", name);
        ++failures;
        return;
    }
    const auto result = gps_ublox_quiesce();
    const bool confirmed = expected == GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY;
    bool passed = result == expected &&
        s_gps_diag.hardware_resets == expected_resets &&
        s_gps_diag.backup_failures == expected_failures &&
        s_gps_diag.backup_confirmations == (confirmed ? 1u : 0u) &&
        s_gps_diag.backup_terminal_failures == (confirmed ? 0u : 1u) &&
        s_gps_diag.reset_hold_entries == (confirmed ? 0u : 1u) &&
        gps_ublox_current_quiescence() == expected;
    std::printf("[%s] %s: result=%u resets=%u backup_failures=%u "
                "confirmations=%u terminal=%u; want result=%u resets=%u "
                "backup_failures=%u\n", passed ? "PASS" : "FAIL", name,
                static_cast<unsigned>(result),
                static_cast<unsigned>(s_gps_diag.hardware_resets),
                static_cast<unsigned>(s_gps_diag.backup_failures),
                static_cast<unsigned>(s_gps_diag.backup_confirmations),
                static_cast<unsigned>(s_gps_diag.backup_terminal_failures),
                static_cast<unsigned>(expected), expected_resets, expected_failures);
    if (!passed) ++failures;
}
int main() {
    run_case("prompt ACK preserves acquired state", PROMPT_ACK,
             GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY, 0, 0);
    run_case("no ACK cannot prove standby", NO_ACK,
             GPS_QUIESCENCE_RESET_HELD, 2, 3);
    run_case("NACK cannot prove standby", NACK,
             GPS_QUIESCENCE_RESET_HELD, 2, 3);
    run_case("ACK without EOE cannot prove standby", NO_EOE,
             GPS_QUIESCENCE_RESET_HELD, 2, 3);
    run_case("continued UART cannot prove standby", CONTINUED_TRAFFIC,
             GPS_QUIESCENCE_RESET_HELD, 2, 3);
    run_case("low rail suppresses recovery resets", LOW_RAIL_NO_ACK,
             GPS_QUIESCENCE_RESET_HELD, 0, 1);
    run_case("401ms ACK reaches standby without RESET_N", DELAYED_ACK,
             GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY, 0, 0);
    std::printf("Shutdown ACK timing experiment: %d failing case(s)\n", failures);
    return failures ? 1 : 0;
}
"""


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="stratolink-shutdown-ack-") as name:
        directory = Path(name)
        (directory / "Arduino.h").write_text(ARDUINO, encoding="utf-8")
        (directory / "SparkFun_u-blox_GNSS_v3.h").write_text(GNSS, encoding="utf-8")
        source = directory / "experiment.cpp"
        source.write_text(TEST, encoding="utf-8")
        binary = directory / "experiment"
        subprocess.run(
            [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
             "-Werror", "-fsanitize=address,undefined", "-g",
             "-I", str(directory), "-I", str(ROOT / "firmware/include"),
             "-I", str(ROOT / "firmware/src"), str(source),
             str(ROOT / "firmware/src/gps_freshness.cpp"),
             str(ROOT / "firmware/src/gps_pvt_validation.cpp"),
             str(ROOT / "firmware/src/gps_backup_policy.cpp"),
             "-o", str(binary)], check=True, timeout=60,
        )
        environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                           UBSAN_OPTIONS="halt_on_error=1")
        return subprocess.run([str(binary)], env=environment,
                              timeout=30, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
