#!/usr/bin/env python3
"""Run the production GPS driver through the real SparkFun serial parser.

Configuration hardware returns ideal immediate, checksum-valid CFG replies;
shutdown commands are idealized so this test can isolate position transactions.
The production driver, bounded Stream adapter, SparkFun 3.1.13 configuration
and getPVT/checkUblox/SfeSerial parser, freshness and value policy are real.
The startup supervision suite separately exercises realistic CFG UART timing.
"""

from pathlib import Path
import os
import subprocess
import tempfile

import gps_poll_supervision_uart_timing_experiment as fixture


ROOT, LIB = fixture.ROOT, fixture.LIB
SOURCE = ROOT / "firmware/src/gps_ublox.cpp"

ARDUINO = fixture.ARDUINO.replace(
    "  virtual int read() { return -1; }\n",
    "  virtual int read() { return -1; }\n"
    "  virtual int peek() { return -1; }\n"
    "  virtual void flush() {}\n"
    "  virtual int availableForWrite() { return 0; }\n",
) + r"""
#include <climits>
#include <deque>
#include <vector>
inline bool reset_seen = false;
inline void digitalWrite(int, int level) { if (level == LOW) reset_seen = true; }
inline void pinMode(int, int) {}
#define INPUT 0
#define PA_0 0

class DriverSerial : public Stream {
public:
  std::deque<uint8_t> rx;
  std::vector<std::vector<uint8_t>> replies;
  std::vector<uint8_t> tx;
  std::vector<uint8_t> assembling;
  size_t reply_index = 0u, arrival_index = 0u, poll_bytes = 0u, polls = 0u, reads = 0u;
  bool response_active = false;
  uint64_t next_arrival_us = 0u;
  uint32_t service_us = 10u;
  int tx_space = 63, write_limit = INT_MAX;

  void begin(uint32_t) {}
  void service() {
    if (!response_active || reply_index >= replies.size()) return;
    const auto& reply = replies[reply_index];
    while (arrival_index < reply.size() &&
           next_arrival_us + uint64_t(arrival_index) * 1042u <= fixture_us) {
      rx.push_back(reply[arrival_index++]);
    }
  }
  int available() override { service(); return int(rx.size()); }
  int read() override {
    service();
    if (rx.empty()) return -1;
    uint8_t value = rx.front(); rx.pop_front(); ++reads; fixture_us += service_us;
    if (rx.empty() && reply_index < replies.size() &&
        arrival_index >= replies[reply_index].size()) {
      ++reply_index;
      arrival_index = reads = 0u;
      response_active = false;
    }
    return value;
  }
  int peek() override { service(); return rx.empty() ? -1 : rx.front(); }
  void flush() override {}
  int availableForWrite() override { return tx_space; }
  size_t write(uint8_t value) override { return write(&value, 1u); }
  size_t write(const uint8_t* data, size_t size) override {
    size_t accepted = size < size_t(write_limit) ? size : size_t(write_limit);
    tx.insert(tx.end(), data, data + accepted);
    write_limit -= int(accepted);
    for (size_t i = 0; i < accepted; ++i) {
      uint8_t byte = data[i];
      if (assembling.empty() && byte != 0xb5u) continue;
      assembling.push_back(byte);
      if (assembling.size() == 2u && byte != 0x62u) { assembling.clear(); continue; }
      if (assembling.size() < 6u) continue;
      size_t len = assembling[4] + 256u * assembling[5];
      if (assembling.size() != len + 8u) continue;
      if (assembling[2] == 6u && assembling[3] == 0x8bu && len == 8u) {
        std::vector<uint8_t> reply = {0xb5, 0x62, 6, 0x8b, 9, 0,
            1, 0, 0, 0, assembling[10], assembling[11], assembling[12], assembling[13],
            uint8_t(assembling[10] == 1u && assembling[12] == 0x73u ? 1u : 8u)};
        uint8_t a = 0u, b = 0u;
        for (size_t j = 2u; j < reply.size(); ++j) { a += reply[j]; b += a; }
        reply.push_back(a); reply.push_back(b);
        rx.insert(rx.end(), reply.begin(), reply.end());
      }
      assembling.clear();
    }
    if (accepted == 6u && data[0] == 0xb5u && data[1] == 0x62u &&
        data[2] == 0x01u && data[3] == 0x07u) {
      poll_bytes = 6u;
    } else if (poll_bytes == 6u && accepted == 2u) {
      ++polls; poll_bytes = 0u; rx.clear(); arrival_index = reads = 0u;
      response_active = true;
      next_arrival_us = fixture_us + 1042u;
    }
    return accepted;
  }
  void reset() {
    rx.clear(); replies.clear(); tx.clear(); assembling.clear();
    reply_index = arrival_index = poll_bytes = polls = reads = 0u;
    response_active = false; next_arrival_us = 0u; service_us = 10u;
    tx_space = 63; write_limit = INT_MAX;
  }
};
inline DriverSerial Serial1;
"""

WRAPPER = r"""
class TestGNSS : public GpsGnss {
public:
    bool begin(Stream& stream, uint16_t) {
        (void)SFE_UBLOX_GNSS_SERIAL::begin(stream, 0u, true);
        return true;
    }
    bool setDynamicModel(dynModel, uint8_t, uint16_t) { return true; }
    uint8_t getDynamicModel(uint8_t, uint16_t) { return 8u; }
    bool setVal8(uint32_t, uint8_t, uint8_t, uint16_t) { return true; }
    bool setVal16(uint32_t, uint16_t, uint8_t, uint16_t) { return true; }
    bool powerOffWithInterrupt(uint32_t, uint32_t, bool, uint16_t) { return true; }
};
static TestGNSS gnss;
"""

TEST = r"""
#include <climits>
#include <cstdio>
#include <string>
#include <vector>
#include "gps_ublox.cpp"

uint16_t rail_mv = 4660u;
bool mission_pending = false;
bool mission_during_response = false, drop_rail_after_reset = false;
uint16_t power_adc_read_vSTOR_mv() {
  return drop_rail_after_reset && reset_seen ? 3300u : rail_mv;
}
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() {
  return mission_pending || (mission_during_response && fixture_us >= 20000u);
}

static std::vector<uint8_t> pvt(uint32_t itow, bool good_crc = true) {
  std::vector<uint8_t> bytes = {0xb5, 0x62, 0x01, 0x07, 0x5c, 0x00};
  std::vector<uint8_t> payload(92u, 0u);
  payload[0] = uint8_t(itow); payload[1] = uint8_t(itow >> 8);
  payload[2] = uint8_t(itow >> 16); payload[3] = uint8_t(itow >> 24);
  payload[4] = 0xea; payload[5] = 0x07; payload[6] = 10; payload[7] = 6;
  payload[11] = 3; payload[20] = 3; payload[21] = 1; payload[23] = 5;
  int32_t lon = -1220000000, lat = 370000000, height = 123000;
  int32_t speed = 1000, heading = 9000000;
  std::memcpy(payload.data() + 24, &lon, 4); std::memcpy(payload.data() + 28, &lat, 4);
  int32_t hmsl = 456000;
  std::memcpy(payload.data() + 32, &height, 4); std::memcpy(payload.data() + 36, &hmsl, 4);
  std::memcpy(payload.data() + 60, &speed, 4);
  std::memcpy(payload.data() + 64, &heading, 4);
  bytes.insert(bytes.end(), payload.begin(), payload.end());
  uint8_t a = 0u, b = 0u;
  for (size_t i = 2; i < bytes.size(); ++i) { a += bytes[i]; b += a; }
  bytes.push_back(a); bytes.push_back(good_crc ? b : uint8_t(b ^ 0xffu));
  return bytes;
}

static unsigned failures = 0u;
static void check(const char* name, bool ok) {
  std::printf("[%s] %s: ms=%lu polls=%zu tx=%zu valid=%u lat=%ld alt=%ld sat=%u "
              "reset=%lu resetseen=%u power=%lu mission=%lu nofresh=%u accepted=%lu\n",
              ok ? "PASS" : "FAIL", name, millis(), Serial1.polls, Serial1.tx.size(),
              unsigned(last_fix.valid), long(last_fix.lat_e7), long(last_fix.altitude_m),
              unsigned(last_fix.satellites), (unsigned long)s_gps_diag.hardware_resets,
              unsigned(reset_seen),
              (unsigned long)s_gps_diag.power_aborts,
              (unsigned long)s_gps_diag.mission_aborts, unsigned(consecutive_no_fresh),
              (unsigned long)s_gps_diag.accepted_fixes);
  if (!ok) ++failures;
}
static void reset_case() {
  fixture_us = 0u; Serial1.reset(); rail_mv = 4660u; mission_pending = false;
  mission_during_response = drop_rail_after_reset = reset_seen = false;
  gps_freshness_reset(&pvt_freshness); consecutive_no_fresh = 0u;
  gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
  s_gps_diag.hardware_resets = s_gps_diag.accepted_fixes = 0u;
  s_gps_diag.power_aborts = s_gps_diag.mission_aborts = 0u;
  s_gps_diag.no_fresh_cycles = 0u;
  last_fix = {}; (void)gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);
  Serial1.reset(); fixture_us = 0u;
}
int main() {
  reset_case();
  Serial1.replies = {pvt(123456000u), pvt(123457000u)};
  gps_fix_t fix{};
  bool ok = gps_ublox_get_fix(&fix, 3000u);
  check("real driver accepts advancing split NAV-PVT through real parser",
        ok && fix.valid && fix.lat_e7 == 370000000 && fix.lon_e7 == -1220000000 &&
        fix.altitude_m == 123 && fix.speed_cm_s == 100u &&
        fix.heading_cd == 9000u && fix.satellites == 5u &&
        Serial1.polls == 2u && Serial1.tx.size() == 34u);

  reset_case();
  std::vector<uint8_t> mixed = pvt(111000u, false);
  const std::string nmea = "$GPGGA,123519,4807.038,N,01131.000,E,1,08*00\r\n";
  mixed.insert(mixed.end(), nmea.begin(), nmea.end());
  auto good = pvt(200000u); mixed.insert(mixed.end(), good.begin(), good.end());
  Serial1.replies = {mixed, pvt(201000u)};
  check("CRC-bad and interleaved NMEA cannot bypass real driver freshness",
        gps_ublox_get_fix(&fix, 3000u) && fix.valid && Serial1.polls == 2u);

  reset_case();
  Serial1.tx_space = 7;
  fix.valid = true; fix.satellites = 8u;
  check("full TX-ring preflight aborts without entering wedge ladder",
        !gps_ublox_get_fix(&fix, 1000u) && !fix.valid && Serial1.polls == 0u &&
        s_gps_diag.hardware_resets == 0u && consecutive_no_fresh == 0u);

  reset_case();
  Serial1.write_limit = 6;
  check("partial TX aborts without parsing or wedge classification",
        !gps_ublox_get_fix(&fix, 1000u) && Serial1.tx.size() == 6u &&
        s_gps_diag.hardware_resets == 0u && consecutive_no_fresh == 0u);

  reset_case();
  Serial1.replies = {pvt(300000u)};
  mission_during_response = true;
  check("mid-response mission authority loss aborts before snapshot publication",
        !gps_ublox_get_fix(&fix, 1000u) && !fix.valid &&
        s_gps_diag.mission_aborts == 1u && s_gps_diag.accepted_fixes == 0u);

  reset_case();
  drop_rail_after_reset = true;
  check("authority loss during inline reset cannot start a subsequent poll",
        !gps_ublox_get_fix(&fix, 10000u) && !fix.valid && reset_seen &&
        Serial1.polls == 5u && s_gps_diag.hardware_resets == 1u &&
        s_gps_diag.power_aborts == 1u);
  return failures == 0u ? 0 : 1;
}
"""


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    declaration = "static GpsGnss gnss;"
    assert source.count(declaration) == 1
    source = source.replace(declaration, WRAPPER, 1)
    with tempfile.TemporaryDirectory(prefix="stratolink-driver-real-parser-") as name:
        build = Path(name)
        for filename, content in (("Arduino.h", ARDUINO), ("Wire.h", fixture.WIRE),
                                  ("SPI.h", fixture.SPI), ("gps_ublox.cpp", source),
                                  ("test.cpp", TEST)):
            (build / filename).write_text(content, encoding="utf-8")
        binary = build / "test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++17", "-Wno-vla-cxx-extension",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
            "-I", str(build), "-I", str(ROOT / "firmware/include"),
            "-I", str(ROOT / "firmware/src"), "-I", str(LIB),
            str(LIB / "u-blox_GNSS.cpp"), str(LIB / "sfe_bus.cpp"), str(build / "test.cpp"),
            *(str(ROOT / f"firmware/src/{name}.cpp") for name in
              ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
            "-o", str(binary),
        ], check=True, timeout=60)
        result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=20,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                         UBSAN_OPTIONS="halt_on_error=1"))
    print(result.stdout, end="")
    print(result.stderr, end="")
    assert result.returncode == 0 and not result.stderr, result
    assert result.stdout.count("[PASS]") == 6
    assert SOURCE.read_text(encoding="utf-8") == source.replace(WRAPPER, declaration, 1)
    print("PASS: production driver + adapter + real SparkFun parser/SfeSerial; ASan/UBSan clean")


if __name__ == "__main__":
    main()
