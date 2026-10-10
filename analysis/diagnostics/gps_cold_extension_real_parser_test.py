#!/usr/bin/env python3
"""Cold-extension behavior through the actual driver and SparkFun 3.1.13 parser.

Only the external clock/GPIO/rail and UART peripheral are scripted. PVT frames
are generated dynamically, checksummed, and delivered at 1042 us/byte (9600
baud, 8N1) through a 63-byte RX ring and the real getPVT/checkUblox/SfeSerial
path. Epochs advance at 1 Hz, not once per poll. CFG replies and configuration
recovery setters are idealized using gps_driver_real_parser_integration_test;
this is not a startup-configuration timing or physical-energy qualification.

Each case runs in a new process. --driver-source can replay a frozen pre-change
driver through its two-argument API, producing behavioral RED rather than a
missing-symbol error. Production inputs are hashed before and after each run.

The partial-time cases synthesize the low valid-bit transition observed in
stratolink1_b68_cold_firstcycle_20261008_v1_analysis.json (SHA256
69a72b2dae3e67e02e8b0b941ed227063cbbe2655a0b3111c25ccb742ff696f5):
provisional iTOW then validTime-only iTOW 349899000. The later date-valid fix is
a declared synthetic continuation, not an observed RF/GNSS capture result.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import gps_driver_real_parser_integration_test as base


ROOT, LIB = base.ROOT, base.LIB
SOURCE = ROOT / "firmware/src/gps_ublox.cpp"

# Keep the existing Arduino time/Stream/GPIO shims, not its finite reply list.
ARDUINO = base.ARDUINO.split("class DriverSerial : public Stream {", 1)[0] + r'''
enum class PVTMode { LATE_35, LATE_45, PROVISIONAL, STALL, BUFFERED_REPEAT,
                     BAD_CRC, DOMAIN_STALL, DOMAIN_AT_29, DOMAIN_LATE_FIX,
                     PARTIAL_TIME_PROGRESS, PARTIAL_TIME_FROZEN, REACQUIRE };
inline PVTMode pvt_mode = PVTMode::LATE_35;
inline uint32_t pvt_phase_origin=0u, reacquire_fix_after=UINT32_MAX;

class ColdSerial : public Stream {
public:
  struct Arrival { uint64_t at; uint8_t value; };
  std::deque<uint8_t> rx;
  std::deque<Arrival> wire;
  std::vector<uint8_t> assembling;
  uint64_t tx_ready_us = 0u;
  uint32_t polls = 0u, delivered = 0u, dropped = 0u, prefetched = 0u;
  uint32_t first_valid_epoch = UINT32_MAX, second_valid_epoch = UINT32_MAX;
  uint32_t first_valid_frame_complete_ms = 0u, last_poll_ms = 0u;
  uint32_t partial_time_frames = 0u, first_partial_epoch = UINT32_MAX;
  uint32_t prior_reacquire_epoch=UINT32_MAX, first_fix_reply_epoch=UINT32_MAX;
  uint32_t first_new_fix_reply_epoch=UINT32_MAX;
  uint64_t first_fix_reply_complete_us=0u, first_new_fix_reply_complete_us=0u;

  void begin(uint32_t) {}
  void flush() override {}
  int availableForWrite() override { return 63; }
  void service() {
    while (!wire.empty() && wire.front().at <= fixture_us) {
      if (rx.size() < 63u) rx.push_back(wire.front().value);
      else ++dropped;
      wire.pop_front();
    }
  }
  int available() override { service(); return int(rx.size()); }
  int peek() override { service(); return rx.empty() ? -1 : rx.front(); }
  int read() override {
    service();
    if (rx.empty()) return -1;
    uint8_t byte = rx.front(); rx.pop_front(); ++delivered;
    fixture_us += 10u;
    return byte;
  }
  static void put32(std::vector<uint8_t>& bytes, size_t at, uint32_t value) {
    for (unsigned i=0u; i<4u; ++i) bytes[at+i] = uint8_t(value >> (8u*i));
  }
  static void checksum(std::vector<uint8_t>& bytes, bool corrupt=false) {
    uint8_t a=0u, b=0u;
    for (size_t i=2u; i<bytes.size(); ++i) { a+=bytes[i]; b+=a; }
    bytes.push_back(a); bytes.push_back(corrupt ? uint8_t(b^0xffu) : b);
  }
  std::vector<uint8_t> pvt(uint32_t now_ms) {
    const uint32_t absolute_ms=now_ms;
    now_ms-=pvt_phase_origin;
    const uint32_t second = now_ms/1000u;
    const uint32_t valid_at = pvt_mode==PVTMode::LATE_45 ? 44000u :
                              pvt_mode==PVTMode::DOMAIN_AT_29 ? 29000u : 34000u;
    bool valid = now_ms >= valid_at;
    uint32_t epoch = valid ? 348000000u + (second-valid_at/1000u)*1000u : second*1000u;
    if (pvt_mode==PVTMode::PROVISIONAL) { valid=false; epoch=second*1000u; }
    if (pvt_mode==PVTMode::STALL) { valid=false; epoch=(second<5u?second:5u)*1000u; }
    if (pvt_mode==PVTMode::BUFFERED_REPEAT) { valid=true; epoch=123456000u; }
    if (pvt_mode==PVTMode::DOMAIN_STALL && valid) epoch=348000000u;
    uint8_t valid_flags = valid?3u:0u;
    if (pvt_mode==PVTMode::REACQUIRE) {
      // The receiver keeps date/time and advances real epochs while it has no
      // position. Do not fabricate a reset, stale epoch, or new time domain.
      valid=true; valid_flags=3u;
      // Continue the initial LATE_35 mapping exactly: epoch348000000 at34s.
      epoch=348000000u+(absolute_ms/1000u-34u)*1000u;
    }
    if (pvt_mode==PVTMode::PARTIAL_TIME_PROGRESS ||
        pvt_mode==PVTMode::PARTIAL_TIME_FROZEN) {
      // Match the observed 0->2 low-bit transition across a >half-week jump.
      // Time-only may sustain cold progress but must never qualify a position.
      valid_flags = now_ms<10000u ? 0u :
          (pvt_mode==PVTMode::PARTIAL_TIME_PROGRESS && now_ms>=34000u ? 3u : 2u);
      epoch = now_ms<10000u ? (second<8u?second+2u:10u)*1000u :
          349899000u + (pvt_mode==PVTMode::PARTIAL_TIME_PROGRESS ?
              (second-10u)*1000u : 0u);
      valid = (valid_flags&3u)==3u;
      if (valid_flags==2u) {
        ++partial_time_frames;
        if (first_partial_epoch==UINT32_MAX) first_partial_epoch=epoch;
      }
    }
    std::vector<uint8_t> payload(92u,0u);
    put32(payload,0u,epoch);
    payload[4]=0xea; payload[5]=7; payload[6]=10; payload[7]=8;
    // Deliberately leave fullyResolved clear; production accepts validDate+Time.
    payload[11]=valid_flags; payload[20]=3u; payload[21]=1u; payload[23]=5u;
    if (pvt_mode==PVTMode::REACQUIRE && now_ms<reacquire_fix_after) payload[21]=0u;
    if (pvt_mode==PVTMode::DOMAIN_LATE_FIX && now_ms<40000u) payload[21]=0u;
    put32(payload,24u,uint32_t(-1220000000)); put32(payload,28u,370000000u);
    put32(payload,32u,123000u); put32(payload,36u,456000u);
    put32(payload,60u,1000u); put32(payload,64u,9000000u);
    if (valid && pvt_mode!=PVTMode::BAD_CRC) {
      if (first_valid_epoch==UINT32_MAX) first_valid_epoch=epoch;
      else if (epoch!=first_valid_epoch && second_valid_epoch==UINT32_MAX)
        second_valid_epoch=epoch;
    }
    std::vector<uint8_t> bytes={0xb5,0x62,1,7,92,0};
    bytes.insert(bytes.end(),payload.begin(),payload.end());
    checksum(bytes,pvt_mode==PVTMode::BAD_CRC);
    return bytes;
  }
  void reply_to_request() {
    const size_t length=assembling[4]+256u*assembling[5];
    if (assembling[2]==6u && assembling[3]==0x8bu && length==8u) {
      // Existing fixture's ideal, checksum-valid CFG-VALGET response. No PVT
      // payload or parser state is fabricated by this configuration boundary.
      std::vector<uint8_t> reply={0xb5,0x62,6,0x8b,9,0,1,0,0,0,
          assembling[10],assembling[11],assembling[12],assembling[13],
          uint8_t(assembling[10]==1u && assembling[12]==0x73u?1u:8u)};
      checksum(reply); rx.insert(rx.end(),reply.begin(),reply.end());
    } else if (assembling[2]==1u && assembling[3]==7u && length==0u) {
      ++polls; last_poll_ms=millis();
      auto bytes=pvt(uint32_t(tx_ready_us/1000u));
      size_t offset=0u;
      if (pvt_mode==PVTMode::BUFFERED_REPEAT && polls==1u) {
        // A cached frame prefix already buffered when this poll completes.
        // Its remaining bytes still arrive on the real parser's UART stream.
        for (; offset<63u; ++offset) rx.push_back(bytes[offset]);
        prefetched=63u;
      }
      uint64_t arrival=tx_ready_us+1042u;
      if (!wire.empty() && arrival<=wire.back().at) arrival=wire.back().at+1042u;
      for (; offset<bytes.size(); ++offset,arrival+=1042u)
        wire.push_back({arrival,bytes[offset]});
      if (pvt_mode==PVTMode::REACQUIRE) {
        const uint32_t epoch=uint32_t(bytes[6])|(uint32_t(bytes[7])<<8u)|
            (uint32_t(bytes[8])<<16u)|(uint32_t(bytes[9])<<24u);
        if ((bytes[17]&3u)==3u && (bytes[27]&1u)!=0u) {
          if (first_fix_reply_epoch==UINT32_MAX) {
            first_fix_reply_epoch=epoch;
            first_fix_reply_complete_us=arrival-1042u;
          }
          if (prior_reacquire_epoch!=UINT32_MAX && epoch!=prior_reacquire_epoch &&
              first_new_fix_reply_epoch==UINT32_MAX) {
            first_new_fix_reply_epoch=epoch;
            first_new_fix_reply_complete_us=arrival-1042u;
          }
        }
        prior_reacquire_epoch=epoch;
      }
      if (first_valid_epoch!=UINT32_MAX && first_valid_frame_complete_ms==0u)
        first_valid_frame_complete_ms=uint32_t((arrival-1042u+999u)/1000u);
    }
  }
  size_t write(uint8_t value) override { return write(&value,1u); }
  size_t write(const uint8_t* bytes, size_t count) override {
    if (tx_ready_us<fixture_us) tx_ready_us=fixture_us;
    tx_ready_us+=1042u*count;
    for (size_t i=0u; i<count; ++i) {
      if (assembling.empty() && bytes[i]!=0xb5u) continue;
      assembling.push_back(bytes[i]);
      if (assembling.size()==2u && bytes[i]!=0x62u) { assembling.clear(); continue; }
      if (assembling.size()<6u) continue;
      const size_t length=assembling[4]+256u*assembling[5];
      if (assembling.size()==length+8u) { reply_to_request(); assembling.clear(); }
    }
    return count;
  }
};
inline ColdSerial Serial1;
'''

TEST = r'''
#include <cstdio>
#include <cstring>
#include "gps_ublox.cpp"
uint16_t power_adc_read_vSTOR_mv() { return 4660u; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }

static bool acquire(gps_fix_t* fix, bool permit) {
#if TEST_HAS_EXTENSION
  return static_cast<bool(*)(gps_fix_t*,uint32_t,bool)>(&gps_ublox_get_fix)(fix,30000u,permit);
#else
  (void)permit;
  return static_cast<bool(*)(gps_fix_t*,uint32_t)>(&gps_ublox_get_fix)(fix,30000u);
#endif
}
static unsigned extension_started() {
#if TEST_HAS_EXTENSION
  return s_gps_diag.cold_extension_started;
#else
  return 0u;
#endif
}
static bool invalid(const gps_fix_t& fix, unsigned accepted_count=0u) {
  return !fix.valid && fix.satellites==0u && !last_fix.valid && s_gps_diag.accepted_fixes==accepted_count;
}
static bool position(const gps_fix_t& fix, unsigned accepted_count=1u) {
  return fix.valid && fix.lat_e7==370000000 && fix.lon_e7==-1220000000 &&
      fix.altitude_m==123 && fix.speed_cm_s==100 && fix.heading_cd==9000 &&
      fix.satellites==5 && s_gps_diag.accepted_fixes==accepted_count;
}
static int reacquisition_sequence(const char* name, bool never_fixes) {
  // Preserve all production/library state and the UART stream between calls.
  // Only the external receiver's position-availability schedule changes.
  gps_fix_t fix={};
  bool passed=acquire(&fix,true) && position(fix) && millis()>=35000u && millis()<=35400u;
  std::printf("[PHASE] %s initial: ms=%u accepted=%u extension=%u resets=%u streak=%u\n",
      name,unsigned(millis()),unsigned(s_gps_diag.accepted_fixes),extension_started(),
      unsigned(s_gps_diag.hardware_resets),unsigned(consecutive_no_fresh));
  pvt_mode=PVTMode::REACQUIRE;
  for(unsigned phase=0u; phase<2u; ++phase) {
    pvt_phase_origin=millis();
    // Reset observation-only event records, never production/parser state.
    Serial1.prior_reacquire_epoch=Serial1.first_fix_reply_epoch=UINT32_MAX;
    Serial1.first_new_fix_reply_epoch=UINT32_MAX;
    Serial1.first_fix_reply_complete_us=Serial1.first_new_fix_reply_complete_us=0u;
    reacquire_fix_after=never_fixes?UINT32_MAX:(phase==0u?35000u:45000u);
    const bool accepted=acquire(&fix,true);
    const uint32_t elapsed=millis()-pvt_phase_origin;
    // Position becomes usable inside a previously seen absolute 1 Hz epoch.
    // The next distinct fix epoch is the acceptance event, not phase+35/45s.
    // Allow at most2ms after its last wire byte: one1ms parser poll plus byte
    // service; this is separate from the unchanged180s acquisition ceiling.
    const bool timing_ok=never_fixes ?
        elapsed>=180000u && elapsed<=180100u &&
            Serial1.last_poll_ms-pvt_phase_origin<180000u :
        elapsed>=reacquire_fix_after && elapsed<180000u &&
            Serial1.first_new_fix_reply_epoch!=UINT32_MAX &&
            Serial1.first_new_fix_reply_epoch==Serial1.first_fix_reply_epoch+1000u &&
            Serial1.first_fix_reply_complete_us<Serial1.first_new_fix_reply_complete_us &&
            fixture_us>=Serial1.first_new_fix_reply_complete_us &&
            fixture_us-Serial1.first_new_fix_reply_complete_us<=2000u &&
            Serial1.last_poll_ms-pvt_phase_origin<180000u;
    const bool phase_ok=accepted!=never_fixes &&
        (never_fixes?invalid(fix,1u):position(fix,phase+2u)) &&
        timing_ok &&
        extension_started()==phase+2u && s_gps_diag.hardware_resets==0u &&
        consecutive_no_fresh==0u && Serial1.dropped==0u;
    passed=passed && phase_ok;
    std::printf("[PHASE] %s #%u: elapsed=%u accepted=%u total_accepted=%u "
        "extension=%u resets=%u streak=%u nofresh=%u\n",name,phase+1u,elapsed,
        unsigned(accepted),unsigned(s_gps_diag.accepted_fixes),extension_started(),
        unsigned(s_gps_diag.hardware_resets),unsigned(consecutive_no_fresh),
        unsigned(s_gps_diag.no_fresh_cycles));
    std::printf("[WIRE] first_fix_epoch=%u complete_us=%llu first_new_fix_epoch=%u "
        "complete_us=%llu returned_us=%llu\n",Serial1.first_fix_reply_epoch,
        static_cast<unsigned long long>(Serial1.first_fix_reply_complete_us),
        Serial1.first_new_fix_reply_epoch,
        static_cast<unsigned long long>(Serial1.first_new_fix_reply_complete_us),
        static_cast<unsigned long long>(fixture_us));
  }
  std::printf("[%s] %s: ms=%u dropped=%u\n",passed?"PASS":"FAIL",name,unsigned(millis()),Serial1.dropped);
  return passed?0:1;
}
int main(int argc,char** argv) {
  if (argc!=2) return 2;
  const char* name=argv[1]; bool permit=true;
  if (!strcmp(name,"accepted-fix-then-late-35-and-45s-reacquisition"))
    return reacquisition_sequence(name,false);
  if (!strcmp(name,"accepted-fix-then-repeated-nofix-reacquisition"))
    return reacquisition_sequence(name,true);
  uint32_t lower=0u, upper=30100u; bool want_fix=false, want_extension=false;
  uint32_t expected_first=348000000u, expected_second=348001000u;
  if (!strcmp(name,"late-fix-35s")) {
    pvt_mode=PVTMode::LATE_35; lower=35000u; upper=35400u; want_fix=want_extension=true;
  } else if (!strcmp(name,"late-fix-45s")) {
    pvt_mode=PVTMode::LATE_45; lower=45000u; upper=45400u; want_fix=want_extension=true;
  } else if (!strcmp(name,"optout-keeps-30s")) {
    pvt_mode=PVTMode::LATE_35; permit=false; lower=30000u;
  } else if (!strcmp(name,"provisional-cannot-publish")) {
    pvt_mode=PVTMode::PROVISIONAL; lower=180000u; upper=180100u; want_extension=true;
  } else if (!strcmp(name,"stalled-provisional-denies-extension")) {
    pvt_mode=PVTMode::STALL; lower=30000u;
  } else if (!strcmp(name,"buffered-cached-epoch-cannot-publish")) {
    pvt_mode=PVTMode::BUFFERED_REPEAT; lower=30000u;
  } else if (!strcmp(name,"bad-crc-cannot-publish")) {
    pvt_mode=PVTMode::BAD_CRC; lower=30000u;
  } else if (!strcmp(name,"domain-reanchor-without-next-epoch-aborts")) {
    pvt_mode=PVTMode::DOMAIN_STALL; lower=35000u; upper=38000u; want_extension=true;
  } else if (!strcmp(name,"domain-reanchor-before-deadline-denies-extension")) {
    pvt_mode=PVTMode::DOMAIN_AT_29; lower=30000u;
  } else if (!strcmp(name,"domain-reanchor-keeps-progress-until-later-fix")) {
    pvt_mode=PVTMode::DOMAIN_LATE_FIX; lower=40000u; upper=40400u; want_fix=want_extension=true;
  } else if (!strcmp(name,"time-only-transition-keeps-progress-until-date-valid-35s")) {
    pvt_mode=PVTMode::PARTIAL_TIME_PROGRESS;
    lower=35000u; upper=35400u; want_fix=want_extension=true;
    expected_first=349923000u; expected_second=349924000u;
  } else if (!strcmp(name,"time-only-transition-frozen-denies-extension")) {
    pvt_mode=PVTMode::PARTIAL_TIME_FROZEN; lower=30000u;
  } else return 2;
  gps_fix_t fix={}; fix.valid=true; fix.satellites=9u;
  const bool accepted=acquire(&fix,permit);
  const uint32_t elapsed=millis();
  bool passed=accepted==want_fix && (want_fix?position(fix):invalid(fix)) &&
      elapsed>=lower && elapsed<=upper && extension_started()==unsigned(want_extension) &&
      Serial1.polls>=2u && Serial1.dropped==0u;
  if (want_fix) passed=passed && s_gps_diag.hardware_resets==0u &&
      Serial1.first_valid_epoch==expected_first && Serial1.second_valid_epoch==expected_second &&
      elapsed>Serial1.first_valid_frame_complete_ms;
  if (pvt_mode==PVTMode::BUFFERED_REPEAT) passed=passed && Serial1.prefetched==63u;
  if (!want_fix && !want_extension) passed=passed && Serial1.last_poll_ms<30000u;
  if (pvt_mode==PVTMode::PROVISIONAL) passed=passed &&
      Serial1.last_poll_ms<180000u && s_gps_diag.hardware_resets==0u;
  if (pvt_mode==PVTMode::DOMAIN_STALL) passed=passed &&
      Serial1.second_valid_epoch==UINT32_MAX && s_gps_diag.hardware_resets==0u;
  if (pvt_mode==PVTMode::PARTIAL_TIME_PROGRESS || pvt_mode==PVTMode::PARTIAL_TIME_FROZEN)
    passed=passed && Serial1.partial_time_frames>=2u &&
        Serial1.first_partial_epoch==349899000u && s_gps_diag.hardware_resets==0u;
  if (pvt_mode==PVTMode::PARTIAL_TIME_FROZEN)
    passed=passed && Serial1.first_valid_epoch==UINT32_MAX;
  std::printf("[%s] %s: ms=%u polls=%u bytes=%u dropped=%u prefetched=%u "
      "accepted=%u extension=%u resets=%u first_valid=%u second_valid=%u last_poll=%u\n",
      passed?"PASS":"FAIL",name,elapsed,Serial1.polls,Serial1.delivered,Serial1.dropped,
      Serial1.prefetched,unsigned(accepted),extension_started(),unsigned(s_gps_diag.hardware_resets),
      Serial1.first_valid_epoch,Serial1.second_valid_epoch,Serial1.last_poll_ms);
  return passed?0:1;
}
'''

CASES = (
    "late-fix-35s", "late-fix-45s", "optout-keeps-30s",
    "provisional-cannot-publish", "stalled-provisional-denies-extension",
    "buffered-cached-epoch-cannot-publish", "bad-crc-cannot-publish",
    "domain-reanchor-without-next-epoch-aborts",
    "domain-reanchor-before-deadline-denies-extension",
    "domain-reanchor-keeps-progress-until-later-fix",
    "time-only-transition-keeps-progress-until-date-valid-35s",
    "time-only-transition-frozen-denies-extension",
    "accepted-fix-then-late-35-and-45s-reacquisition",
    "accepted-fix-then-repeated-nofix-reacquisition",
)


def fingerprint(paths):
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-source", type=Path, default=SOURCE)
    args = parser.parse_args()
    original_bytes = args.driver_source.read_bytes()
    original = original_bytes.decode("utf-8")
    has_extension = bool(re.search(
        r"bool\s+gps_ublox_get_fix\([^)]*\ballow_cold_extension\b", original))
    declaration = "static GpsGnss gnss;"
    assert original.count(declaration) == 1
    source = original.replace(declaration, base.WRAPPER, 1)
    paths = [args.driver_source, Path(__file__), Path(base.__file__),
             Path(base.fixture.__file__), Path(base.fixture.base.__file__),
             ROOT / "firmware/src/power_manager.h"]
    paths += list((ROOT / "firmware/include").glob("*.h"))
    paths += [ROOT / f"firmware/src/{name}.cpp" for name in
              ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")]
    paths += [path for path in LIB.rglob("*") if path.suffix in (".h", ".cpp")]
    before = fingerprint(paths)
    assert before[str(args.driver_source.resolve())] == hashlib.sha256(original_bytes).hexdigest(), \
        "Driver changed between frozen source read and provenance capture"
    print(json.dumps({"driver_source": str(args.driver_source.resolve()),
                      "driver_sha256": before[str(args.driver_source.resolve())],
                      "sparkfun_parser_sha256": before[str((LIB / "u-blox_GNSS.cpp").resolve())],
                      "has_extension_api": has_extension}, sort_keys=True), flush=True)
    with tempfile.TemporaryDirectory(prefix="gps-cold-real-parser-") as name:
        directory = Path(name)
        for filename, content in (("Arduino.h", ARDUINO), ("Wire.h", base.fixture.WIRE),
                                  ("SPI.h", base.fixture.SPI), ("gps_ublox.cpp", source),
                                  ("test.cpp", TEST)):
            (directory / filename).write_text(content)
        binary = directory / "test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++17", "-Wno-vla-cxx-extension",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
            f"-DTEST_HAS_EXTENSION={int(has_extension)}", "-I", str(directory),
            "-I", str(ROOT / "firmware/include"), "-I", str(ROOT / "firmware/src"),
            "-I", str(LIB), str(LIB / "u-blox_GNSS.cpp"), str(LIB / "sfe_bus.cpp"),
            str(directory / "test.cpp"), *(str(ROOT / f"firmware/src/{name}.cpp")
                for name in ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
            "-o", str(binary)], check=True, timeout=60)
        failures = 0
        for case in CASES:
            result = subprocess.run([str(binary), case], capture_output=True, text=True,
                timeout=20, env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                    UBSAN_OPTIONS="halt_on_error=1"))
            print(result.stdout, end="", flush=True)
            assert result.returncode in (0, 1) and not result.stderr, result
            failures += result.returncode != 0
    assert before == fingerprint(paths), "Production/test/library inputs changed during run"
    print(f"Real-parser cold-extension cases={len(CASES)} failures={failures}; "
          "all input hashes stable; ASan/UBSan clean; CFG timing idealized")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
