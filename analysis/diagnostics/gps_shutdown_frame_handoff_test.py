#!/usr/bin/env python3
"""Real-driver regression for preserving a pending frame before shutdown CFG.

Named breaks: reusing packetCfg before completing PVT; discarding into a binary
payload containing D3; issuing CFG after a truncated frame uses the deadline;
leaking bounded-stream mode; renewing the shared deadline; accepting bad ACKs.
The production GPS source, bounded stream, and pinned SparkFun parser/setters
run unchanged. Only UART/clock/pins/rail are external simulations. ACKs follow
decoded, checksum-validated outgoing CFG packets at 9600/8N1 through a 63-byte
RX ring. Each case runs in a new process. This does not establish standby/EOE
cadence, target timing, or an exact physical interruption offset.
"""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

import gps_poll_supervision_uart_timing_experiment as fixture

ROOT, LIB = fixture.ROOT, fixture.LIB
CAPTURE_FIXTURE = Path(__file__).with_name("fixtures") / "gps_shutdown_frame_handoff.hex.txt"
# Exact bytes from stream 2 offsets [4001, 4537) of the 2026-10-07 22:46
# capture analysis JSON, SHA-256 b2aba99f664623a510310e4693a2de95f3bbd899a6ae08c6fea450319a4688cc.
# The ignored capture log is provenance only; running this test does not read it.
CAPTURE_BYTES_SHA256 = "470f5317accf43e066329f09bbaf7cbb998c77011b9102a13e1ae84754f12962"

ARDUINO = fixture.ARDUINO.replace(
    "  virtual int read() { return -1; }\n",
    "  virtual int read() { return -1; }\n"
    "  virtual int peek() { return -1; }\n"
    "  virtual void flush() {}\n"
    "  virtual int availableForWrite() { return 0; }\n",
) + r'''
#include <deque>
#include <vector>
#include <string>
#define INPUT 0
#define PA_0 0
inline unsigned reset_edges = 0;
inline void digitalWrite(int, int level) { if (level == LOW) ++reset_edges; }
inline void pinMode(int, int) {}
inline std::string scenario;

class HandoffSerial : public Stream {
public:
  std::deque<std::pair<uint64_t, uint8_t>> wire;
  std::deque<uint8_t> rx;
  std::vector<uint8_t> assembling, tx;
  unsigned configs = 0, polls = 0, invalid_requests = 0, dropped = 0;
  size_t reads = 0, max_buffered = 0;
  uint64_t tx_end = 0, first_cfg_us = 0;
  size_t first_cfg_reads = 0;
  uint32_t ack_delay_us = 0;
  bool corrupt_ack = false;
  void begin(uint32_t) {}
  void service() {
    while (!wire.empty() && wire.front().first <= fixture_us) {
      if (rx.size() < 63u) rx.push_back(wire.front().second); else ++dropped;
      wire.pop_front();
      max_buffered = std::max(max_buffered, rx.size());
    }
  }
  void schedule(const std::vector<uint8_t>& bytes, uint64_t first_us) {
    uint64_t next = first_us;
    if (!wire.empty() && wire.back().first >= next) next = wire.back().first + 1042u;
    for (auto byte : bytes) { wire.push_back({next, byte}); next += 1042u; }
  }
  int available() override { service(); return int(rx.size()); }
  int read() override {
    service(); if (rx.empty()) return -1;
    uint8_t byte = rx.front(); rx.pop_front(); ++reads; fixture_us += 10u;
    return byte;
  }
  int peek() override { service(); return rx.empty() ? -1 : rx.front(); }
  int availableForWrite() override {
    uint64_t queued = tx_end > fixture_us ? (tx_end - fixture_us + 1041u) / 1042u : 0u;
    return queued < 63u ? int(63u - queued) : 0;
  }
  void flush() override { if (fixture_us < tx_end) fixture_us = tx_end; service(); }
  size_t write(uint8_t value) override { return write(&value, 1u); }
  size_t write(const uint8_t* data, size_t size) override {
    for (size_t i = 0; i < size; ++i) {
      if (availableForWrite() == 0) { fixture_us = tx_end - 62u * 1042u; service(); }
      tx_end = std::max(tx_end, fixture_us) + 1042u;
      uint8_t byte = data[i]; tx.push_back(byte);
      if (assembling.empty() && byte != 0xb5u) continue;
      assembling.push_back(byte);
      if (assembling.size() == 2u && byte != 0x62u) { assembling.clear(); continue; }
      if (assembling.size() < 6u) continue;
      size_t len = assembling[4] + 256u * assembling[5];
      if (assembling.size() != len + 8u) continue;
      auto request = assembling; assembling.clear();
      uint8_t a = 0, b = 0;
      for (size_t j = 2; j < request.size() - 2; ++j) { a += request[j]; b += a; }
      if (request[request.size() - 2] != a || request.back() != b) { ++invalid_requests; continue; }
      if (request[2] == 1u && request[3] == 7u && len == 0u) { ++polls; continue; }
      if (request[2] != 6u || request[3] != 0x8au) { ++invalid_requests; continue; }
      static const uint32_t keys[] = {0x10740001u, 0x10740002u, 0x30210001u, 0x30210002u, 0x20910160u};
      static const uint16_t values[] = {1u, 0u, 100u, 1u, 1u};
      static const uint8_t lengths[] = {9u, 9u, 10u, 10u, 9u};
      if (configs == 0u) { first_cfg_us = fixture_us; first_cfg_reads = reads; }
      const unsigned slot = configs++;
      if (slot >= 5u || len != lengths[slot] || request[6] != 0u || request[7] != 1u ||
          request[8] != 0u || request[9] != 0u) { ++invalid_requests; continue; }
      uint32_t key = uint32_t(request[10]) | uint32_t(request[11]) << 8 |
          uint32_t(request[12]) << 16 | uint32_t(request[13]) << 24;
      uint16_t value = request[14] | (len == 10u ? uint16_t(request[15]) << 8 : 0u);
      if (key != keys[slot] || value != values[slot]) { ++invalid_requests; continue; }
      // Hand-checked ACK-ACK for CFG-VALSET. Only a decoded valid request
      // can schedule it, after its final transmitted byte reaches the device.
      std::vector<uint8_t> ack = {0xb5,0x62,5,1,2,0,6,0x8a,0x98,0xc1};
      if (corrupt_ack) ack.back() ^= 1u;
      schedule(ack, tx_end + ack_delay_us + 1042u);
    }
    return size;
  }
};
inline HandoffSerial Serial1;
'''

TEST = r'''
#include <cstdio>
#include <cstdlib>
#include "gps_ublox.cpp"
#include "captured_bytes.h"
uint16_t power_adc_read_vSTOR_mv() { return 4660u; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }

int main(int argc, char** argv) {
  if (argc != 3) return 2;
  scenario = argv[1]; const unsigned prefix = unsigned(std::stoul(argv[2]));
  if (prefix > 100u) return 2;
  gps_gnss_stream.begin_position_phase();
  (void)gnss.begin(gps_gnss_stream, 0u);
  gps_gnss_stream.end_position_phase();
  Serial1 = HandoffSerial{};
  if (scenario == "wrap") fixture_us = uint64_t(UINT32_MAX - 50u) * 1000u;
  gps_gnss_stream.begin_position_phase();
  if (!gps_gnss_stream.begin_poll_write(8u)) return 2;
  (void)gnss.getPVT(0u);
  if (!gps_gnss_stream.finish_poll_write() || Serial1.polls != 1u) return 2;
  std::vector<uint8_t> pvt(captured, captured + 100u);
  if (scenario == "adversarial") {
    pvt[30] = 0xd3u; pvt[31] = 3u; pvt[32] = 0xffu; pvt[33] = 0u;
    pvt[98] = 0xe6u; pvt[99] = 0x55u; // Independently checked new checksum.
  }
  Serial1.schedule(std::vector<uint8_t>(pvt.begin(), pvt.begin() + prefix), Serial1.tx_end + 1042u);
  while (Serial1.reads < prefix) {
    gps_gnss_stream.begin_read_slice(5u, 1u);
    (void)gnss.checkUblox(1u, 7u);
    gps_gnss_stream.finish_read_slice();
    fixture_us += 100u;
  }
  gps_gnss_stream.end_position_phase();
  std::vector<uint8_t> remainder(pvt.begin() + prefix, pvt.end());
  // Start on a millisecond boundary so deadline-edge expectations do not
  // depend on a fractional-millisecond residue from seeding the prefix.
  const uint64_t start_us = ((fixture_us + 12000u + 999u) / 1000u) * 1000u;
  if (scenario == "shared" || scenario == "edge") {
    const uint64_t completion_us = start_us + (scenario == "shared" ? 1100000u : 1500000u);
    Serial1.schedule(remainder, completion_us - uint64_t(remainder.size() - 1u) * 1042u);
    if (scenario == "shared") Serial1.ack_delay_us = 600000u;
  } else if (scenario != "truncated") {
    remainder.insert(remainder.end(), captured + 100u, captured + 526u);
    Serial1.schedule(remainder, std::max(Serial1.tx_end, fixture_us) + 1042u);
  }
  Serial1.corrupt_ack = scenario == "bad_ack";
  // Model the existing wake/settle gap before the configuration entry.
  fixture_us = start_us;
  Serial1.service();
  const bool ok = gps_configure_backup_marker();
  const uint64_t elapsed_us = fixture_us - start_us;
  // Consumer-visible cleanup: ordinary unbounded UART writes must work again.
  const bool mode_clean = gps_gnss_stream.write(uint8_t(0xffu)) == 1u;
  const bool common = mode_clean && Serial1.invalid_requests == 0u &&
      Serial1.dropped == 0u && reset_edges == 0u;
  bool behavior;
  if (scenario == "truncated" || scenario == "edge") {
    behavior = !ok && Serial1.configs == 0u && elapsed_us >= 1500000u && elapsed_us <= 1501000u;
  } else if (scenario == "shared") {
    behavior = !ok && Serial1.configs == 1u && Serial1.first_cfg_reads == 100u &&
        Serial1.first_cfg_us - start_us >= 1100000u &&
        elapsed_us >= 1500000u && elapsed_us <= 1501000u;
  } else if (scenario == "bad_ack") {
    behavior = !ok && Serial1.configs == 1u && elapsed_us >= 1500000u && elapsed_us <= 1501000u;
  } else {
    // Only an already-idle prefix0 may start CFG before any PVT is consumed.
    behavior = ok && Serial1.configs == 5u && elapsed_us < 1500000u &&
        (prefix == 0u || Serial1.first_cfg_reads == 100u);
  }
  const bool good = common && behavior;
  std::printf("[%s] %s:%u ok=%u cfg=%u elapsed_us=%llu clean=%u invalid=%u drops=%u maxrx=%zu first_cfg_reads=%zu\n",
      good ? "PASS" : "FAIL", scenario.c_str(), prefix, ok, Serial1.configs,
      (unsigned long long)elapsed_us, mode_clean, Serial1.invalid_requests, Serial1.dropped,
      Serial1.max_buffered, Serial1.first_cfg_reads);
  return good ? 0 : 1;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="scenario:prefix, e.g. captured:4")
    args = parser.parse_args()
    cases = args.case or [f"{scenario}:{prefix}" for scenario in ("captured", "adversarial")
                         for prefix in range(101)] + ["truncated:17", "shared:17", "edge:17",
                                                     "wrap:4", "bad_ack:4"]
    allowed = {"captured", "adversarial", "truncated", "shared", "edge", "wrap", "bad_ack"}
    for case in cases:
        scenario, prefix = case.split(":")
        if scenario not in allowed or not 0 <= int(prefix) <= 100:
            parser.error(f"invalid case: {case}")
        if scenario in {"truncated", "shared", "edge"} and not 1 <= int(prefix) <= 99:
            parser.error(f"case needs an incomplete PVT prefix: {case}")
    wire = bytes.fromhex("".join(line.partition("#")[0]
                                  for line in CAPTURE_FIXTURE.read_text().splitlines()))
    assert len(wire) == 536 and hashlib.sha256(wire).hexdigest() == CAPTURE_BYTES_SHA256
    failures = []
    with tempfile.TemporaryDirectory(prefix="gps-shutdown-frame-handoff-") as name:
        build = Path(name)
        for filename, contents in (("Arduino.h", ARDUINO), ("Wire.h", fixture.WIRE),
                                   ("SPI.h", fixture.SPI), ("test.cpp", TEST),
                                   ("captured_bytes.h", "constexpr uint8_t captured[] = {" +
                                    ",".join(str(value) for value in wire) + "};\n")):
            (build / filename).write_text(contents)
        binary = build / "test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++17", "-Wno-vla-cxx-extension",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
            "-I", str(build), "-I", str(ROOT / "firmware/include"),
            "-I", str(ROOT / "firmware/src"), "-I", str(LIB),
            str(LIB / "u-blox_GNSS.cpp"), str(LIB / "sfe_bus.cpp"), str(build / "test.cpp"),
            *(str(ROOT / f"firmware/src/{part}.cpp") for part in
              ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
            "-o", str(binary)], check=True, timeout=60)
        for case in cases:
            scenario, prefix = case.split(":")
            result = subprocess.run([str(binary), scenario, prefix], capture_output=True, text=True,
                                    timeout=20, env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                                         UBSAN_OPTIONS="halt_on_error=1"))
            print(result.stdout, end="")
            print(result.stderr, end="")
            if result.returncode or result.stderr:
                failures.append(case)
    if failures:
        print(f"FAIL: {len(failures)}/{len(cases)} real-driver handoff cases: {failures}")
        return 1
    print(f"PASS: {len(cases)} real-driver frame handoffs; real bounded stream/parser/setters; ASan/UBSan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
