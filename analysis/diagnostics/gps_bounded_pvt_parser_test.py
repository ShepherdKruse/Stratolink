#!/usr/bin/env python3
"""Exercise the bounded GPS Stream adapter with the real SparkFun parser."""

import os
from pathlib import Path
import subprocess
import tempfile

import gps_poll_supervision_uart_timing_experiment as fixture


ROOT, LIB = fixture.ROOT, fixture.LIB
ARDUINO = fixture.ARDUINO.replace(
    "  virtual int read() { return -1; }\n",
    "  virtual int read() { return -1; }\n"
    "  virtual int peek() { return -1; }\n"
    "  virtual void flush() {}\n"
    "  virtual int availableForWrite() { return 0; }\n",
)

HARNESS = r"""
#include <climits>
#include <cstdint>
#include <deque>
#include <iostream>
#include <string>
#include <vector>
#include "u-blox_GNSS.h"
#include "gps_bounded_stream.h"

class PeripheralStream : public Stream {
public:
  std::deque<uint8_t> rx;
  std::vector<uint8_t> arrivals, tx;
  size_t next_arrival = 0u, reads = 0u;
  uint64_t next_arrival_us = 0u;
  uint32_t arrival_period_us = 1042u, service_us = 10u;
  int tx_space = 63, write_limit = INT_MAX;

  void service() {
    while (next_arrival < arrivals.size() && next_arrival_us <= fixture_us) {
      rx.push_back(arrivals[next_arrival++]);
      next_arrival_us += arrival_period_us;
    }
  }
  int available() override { service(); return int(rx.size()); }
  int read() override {
    service();
    if (rx.empty()) return -1;
    uint8_t value = rx.front();
    rx.pop_front();
    ++reads;
    fixture_us += service_us;
    return value;
  }
  int peek() override { service(); return rx.empty() ? -1 : rx.front(); }
  void flush() override {}
  int availableForWrite() override { return tx_space; }
  size_t write(uint8_t value) override { return write(&value, 1u); }
  size_t write(const uint8_t *data, size_t size) override {
    const size_t accepted = size < size_t(write_limit) ? size : size_t(write_limit);
    tx.insert(tx.end(), data, data + accepted);
    write_limit -= int(accepted);
    return accepted;
  }
};

class Parser : public DevUBLOXGNSS {
public:
  explicit Parser(SparkFun_UBLOX_GNSS::SfeSerial& bus) {
    _commType = COMM_TYPE_SERIAL;
    setCommunicationBus(bus);
    setPacketCfgPayloadSize(256);
  }
};

static std::vector<uint8_t> pvt(uint32_t itow, bool good_crc = true) {
  std::vector<uint8_t> bytes = {0xb5, 0x62, 0x01, 0x07, 0x5c, 0x00};
  std::vector<uint8_t> payload(92u, 0u);
  payload[0] = uint8_t(itow); payload[1] = uint8_t(itow >> 8);
  payload[2] = uint8_t(itow >> 16); payload[3] = uint8_t(itow >> 24);
  payload[4] = 0xea; payload[5] = 0x07; payload[6] = 10; payload[7] = 6;
  payload[11] = 3; payload[20] = 3; payload[21] = 1; payload[23] = 5;
  payload[24] = 0x00; payload[25] = 0x78; payload[26] = 0x7c; payload[27] = 0xb7;
  payload[28] = 0x80; payload[29] = 0xc0; payload[30] = 0x0d; payload[31] = 0x16;
  payload[36] = 0x78; payload[37] = 0xe0; payload[38] = 0x01;
  payload[60] = 0xe8; payload[61] = 0x03;
  payload[64] = 0x40; payload[65] = 0x54; payload[66] = 0x89;
  bytes.insert(bytes.end(), payload.begin(), payload.end());
  uint8_t a = 0, b = 0;
  for (size_t i = 2; i < bytes.size(); ++i) { a += bytes[i]; b += a; }
  bytes.push_back(a); bytes.push_back(good_crc ? b : uint8_t(b ^ 0xffu));
  return bytes;
}

struct Result {
  bool tx_ok = false, got = false;
  uint32_t itow = 0u, max_slice_ms = 0u, elapsed_ms = 0u;
  size_t polls = 0u;
};

static Result run(PeripheralStream& raw, uint32_t wait_ms = 1100u) {
  SparkFun_UBLOX_GNSS::SfeSerial bus;
  GpsBoundedStream bounded(raw);
  Parser parser(bus);
  bus.init(bounded);
  Result result;
  const uint32_t started = uint32_t(millis());
  bounded.begin_position_phase();
  if (bounded.begin_poll_write(8u)) {
    ++result.polls;
    (void)parser.getPVT(0u);
    result.tx_ok = bounded.finish_poll_write();
  }
  if (parser.packetUBXNAVPVT != nullptr) {
    parser.packetUBXNAVPVT->moduleQueried.moduleQueried1.all = 0u;
    parser.packetUBXNAVPVT->moduleQueried.moduleQueried2.all = 0u;
  }
  while (result.tx_ok && uint32_t(millis()) - started < wait_ms) {
    const uint32_t slice_started = uint32_t(millis());
    bounded.begin_read_slice(5u, 16u);
    (void)parser.checkUblox(UBX_CLASS_NAV, UBX_NAV_PVT);
    bounded.finish_read_slice();
    const uint32_t slice_ms = uint32_t(millis()) - slice_started;
    if (slice_ms > result.max_slice_ms) result.max_slice_ms = slice_ms;
    if (parser.packetUBXNAVPVT != nullptr &&
        parser.packetUBXNAVPVT->moduleQueried.moduleQueried1.bits.all) {
      const UBX_NAV_PVT_data_t snapshot = parser.packetUBXNAVPVT->data;
      parser.packetUBXNAVPVT->moduleQueried.moduleQueried1.all = 0u;
      parser.packetUBXNAVPVT->moduleQueried.moduleQueried2.all = 0u;
      result.got = true;
      result.itow = snapshot.iTOW;
      break;
    }
    delay(1u);
  }
  bounded.end_position_phase();
  result.elapsed_ms = uint32_t(millis()) - started;
  return result;
}

static unsigned failures = 0u;
static void check(const char *name, bool ok) {
  std::cout << (ok ? "[PASS] " : "[FAIL] ") << name << "\n";
  if (!ok) ++failures;
}

int main() {
  const std::vector<uint8_t> good = pvt(123456000u);
  PeripheralStream split;
  split.arrivals = good;
  split.next_arrival_us = 9u * 1042u;
  Result result = run(split);
  const std::vector<uint8_t> expected_poll =
      {0xb5, 0x62, 0x01, 0x07, 0x00, 0x00, 0x08, 0x19};
  check("split frame survives bounded parser slices",
        result.tx_ok && result.got && result.itow == 123456000u &&
        result.polls == 1u && split.tx == expected_poll &&
        result.elapsed_ms >= 112u);

  fixture_us = 0u;
  PeripheralStream crc;
  crc.arrivals = pvt(111000u, false);
  const std::string nmea = "$GPGGA,123519,4807.038,N,01131.000,E,1,08*00\r\n";
  crc.arrivals.insert(crc.arrivals.end(), nmea.begin(), nmea.end());
  crc.arrivals.insert(crc.arrivals.end(), good.begin(), good.end());
  crc.next_arrival_us = 9u * 1042u;
  result = run(crc);
  check("bad CRC and interleaved NMEA cannot hide following PVT",
        result.tx_ok && result.got && result.itow == 123456000u);

  fixture_us = 0u;
  PeripheralStream truncated;
  truncated.arrivals.assign(good.begin(), good.begin() + 55);
  truncated.next_arrival_us = 9u * 1042u;
  result = run(truncated, 250u);
  check("truncated frame remains incomplete", result.tx_ok && !result.got);

  fixture_us = 0u;
  PeripheralStream silent;
  result = run(silent, 250u);
  check("silence remains bounded", result.tx_ok && !result.got &&
        result.elapsed_ms >= 250u && result.elapsed_ms <= 251u);

  fixture_us = 0u;
  PeripheralStream slow;
  slow.arrivals = good;
  slow.next_arrival_us = 9u * 1042u;
  slow.service_us = 2000u;
  result = run(slow);
  check("slow RX service yields between finite slices",
        result.tx_ok && result.got && result.max_slice_ms <= 6u);

  fixture_us = 0u;
  PeripheralStream stalled;
  stalled.tx_space = 7;
  result = run(stalled);
  check("insufficient TX ring rejects poll without writing",
        !result.tx_ok && stalled.tx.empty() && result.polls == 0u);

  fixture_us = 0u;
  PeripheralStream partial;
  partial.write_limit = 6;
  result = run(partial);
  check("partial accepted TX rejects transaction",
        !result.tx_ok && partial.tx.size() == 6u && result.polls == 1u);

  fixture_us = uint64_t(UINT32_MAX - 20u) * 1000u;
  PeripheralStream wrap;
  wrap.arrivals = good;
  wrap.next_arrival_us = fixture_us + 9u * 1042u;
  result = run(wrap);
  check("slice and response clocks survive millis wrap",
        result.tx_ok && result.got && result.itow == 123456000u);

  PeripheralStream passthrough;
  passthrough.rx.push_back(0x42u);
  GpsBoundedStream transparent(passthrough);
  check("non-position mode is transparent",
        transparent.available() == 1 && transparent.read() == 0x42 &&
        transparent.write(uint8_t(0x24u)) == 1u);
  return failures == 0u ? 0 : 1;
}
"""


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-bounded-pvt-") as name:
        build = Path(name)
        for filename, content in (("Arduino.h", ARDUINO), ("Wire.h", fixture.WIRE),
                                  ("SPI.h", fixture.SPI), ("test.cpp", HARNESS)):
            (build / filename).write_text(content, encoding="utf-8")
        binary = build / "test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++17",
            "-Wno-vla-cxx-extension",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            "-I", str(build), "-I", str(ROOT / "firmware/include"), "-I", str(LIB),
            str(LIB / "u-blox_GNSS.cpp"), str(LIB / "sfe_bus.cpp"),
            str(build / "test.cpp"), "-o", str(binary),
        ], check=True, timeout=60)
        result = subprocess.run(
            [str(binary)], text=True, capture_output=True, timeout=10,
            env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1"),
        )
    print(result.stdout, end="")
    print(result.stderr, end="")
    assert result.returncode == 0 and not result.stderr, result
    assert result.stdout.count("[PASS]") == 9, result.stdout
    print("PASS: bounded adapter with real SparkFun parser; ASan/UBSan clean")


if __name__ == "__main__":
    main()
