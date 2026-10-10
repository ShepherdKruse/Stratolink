#!/usr/bin/env python3
"""Startup cancellation and strict configuration proof through pinned real parser.

Only UART, clock, reset pin and power/mission inputs are simulated. Responses
arrive at 9600 baud after the complete request reaches the external receiver.
Each case runs in a fresh process; no library, parser or driver method is mocked.
Breaks caught: starting work after cancellation, blocking startup past the entry
deadline, needless SET on an already configured receiver, and accepting a CFG
response with the wrong key/layer/version/length/checksum.
"""

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
) + r'''
#include <deque>
#include <vector>
#include <string>
#include <climits>
#define INPUT 0
#define PA_0 0
inline unsigned reset_edges = 0;
inline unsigned releases = 0;
inline bool reset_low = false;
inline void digitalWrite(int, int level) {
  if(level == LOW && !reset_low) ++reset_edges;
  reset_low = level == LOW;
}
inline void pinMode(int, int mode) { if(mode==INPUT) { if(reset_low) ++releases; reset_low=false; } }
inline std::string scenario;
inline uint64_t origin_us = 0;
inline uint64_t elapsed_us() { return fixture_us - origin_us; }
inline std::vector<uint8_t> frame(uint8_t cls, uint8_t id, std::vector<uint8_t> payload) {
  std::vector<uint8_t> out = {0xb5,0x62,cls,id,uint8_t(payload.size()),uint8_t(payload.size()>>8)};
  out.insert(out.end(), payload.begin(), payload.end());
  uint8_t a=0,b=0;
  for(size_t i=2;i<out.size();++i) { a+=out[i]; b+=a; }
  out.push_back(a); out.push_back(b); return out;
}
class StartupSerial : public Stream {
public:
  std::deque<std::pair<uint64_t,uint8_t>> wire;
  std::deque<uint8_t> rx;
  std::vector<uint8_t> assembling;
  unsigned writes=0, sets=0, gets=0, polls=0, flushes=0;
  uint8_t model=8;
  uint64_t tx_end=0, last_tx=0;
  void begin(uint32_t) {}
  void service() {
    while(!wire.empty() && wire.front().first<=fixture_us) {
      if(rx.size()<63u) rx.push_back(wire.front().second);
      wire.pop_front();
    }
  }
  void reply(std::vector<uint8_t> bytes) {
    uint64_t next=tx_end+1042;
    if(!wire.empty() && wire.back().first>=next) next=wire.back().first+1042;
    for(auto byte:bytes) { wire.push_back({next,byte}); next+=1042; }
  }
  int available() override { service(); return int(rx.size()); }
  int read() override {
    service(); if(rx.empty()) return -1;
    auto b=rx.front(); rx.pop_front();
    fixture_us += scenario=="rx_load" ? 2000 : 10;
    return b;
  }
  int peek() override { service(); return rx.empty()?-1:rx.front(); }
  int availableForWrite() override { return scenario=="tx_stall"?0:63; }
  void flush() override { ++flushes; if(fixture_us<tx_end) fixture_us=tx_end; }
  size_t write(uint8_t b) override { return write(&b,1); }
  size_t write(const uint8_t* data,size_t n) override {
    if(scenario=="tx_stall") fixture_us+=250000;
    size_t accepted=scenario=="partial_tx" && n>1 ? n-1:n;
    for(size_t i=0;i<accepted;++i) {
      ++writes; last_tx=elapsed_us();
      tx_end=(tx_end>fixture_us?tx_end:fixture_us)+1042;
      uint8_t b=data[i];
      if(assembling.empty() && b!=0xb5) continue;
      assembling.push_back(b);
      if(assembling.size()==2 && b!=0x62) { assembling.clear(); continue; }
      if(assembling.size()<6) continue;
      size_t len=assembling[4]+256u*assembling[5];
      if(assembling.size()!=len+8) continue;
      auto request=assembling; assembling.clear();
      if(request[2]==6 && request[3]==0x8b) {
        ++gets;
        if(scenario=="silent" || scenario=="connection_deadline" || scenario=="deadline" || scenario=="cancel_model" ||
           scenario=="power_model" || scenario=="reset_cancel" || scenario=="stale_queued") continue;
        if(scenario=="late_ready" && elapsed_us()<1200000) continue;
        std::vector<uint8_t> payload={1,0,0,0,request[10],request[11],request[12],request[13],model};
        // UART1INPROT-UBX connection proof uses one-bit key, not model key.
        if(request[10]==1 && request[12]==0x73) payload[8]=1;
        if(scenario=="wrong_key") payload[4]^=1;
        if(scenario=="wrong_layer") payload[1]=1;
        if(scenario=="wrong_version") payload[0]=0;
        if(scenario=="wrong_position") payload[2]=1;
        if(scenario=="short") payload.resize(8);
        auto response=frame(6,0x8b,payload);
        if(scenario=="bad_crc") response.back()^=1;
        if(scenario=="truncated") response.resize(10);
        if(scenario=="rx_load") reply(std::vector<uint8_t>(272,'x'));
        reply(response);
      } else if(request[2]==6 && request[3]==0x8a) {
        ++sets;
        if(scenario!="nack") { if(len>=9) model=request[14]; reply(frame(5,1,{6,0x8a})); }
        else reply(frame(5,0,{6,0x8a}));
      } else if(request[2]==1 && request[3]==7) {
        ++polls;
        std::vector<uint8_t> p(92,0);
        uint32_t itow=100000u+polls*1000u;
        std::memcpy(p.data(),&itow,4);
        p[4]=0xea;p[5]=7;p[6]=10;p[7]=6;p[11]=3;p[20]=3;p[21]=1;p[23]=5;
        reply(frame(1,7,p));
      }
    }
    return accepted;
  }
};
inline StartupSerial Serial1;
'''

TEST = r'''
#include <cstdio>
#include <cstdlib>
bool fail_arrays=false;
void* operator new[](size_t n) {
  if(fail_arrays) return nullptr;
  return std::malloc(n);
}
void operator delete[](void* p) noexcept { std::free(p); }
#include "gps_ublox.cpp"
unsigned adc_calls=0, adc_after_reply=0;
bool adc_triggered=false;
uint16_t power_adc_read_vSTOR_mv() {
  ++adc_calls;
  if(scenario=="adc_set" && Serial1.gets==1 && Serial1.rx.empty() && Serial1.wire.empty() && ++adc_after_reply==1)
    adc_triggered=true;
  if(scenario=="adc_release" && adc_calls==2) adc_triggered=true;
  if(scenario=="adc_mission" || scenario=="adc_deadline") fixture_us+=20000;
  return scenario=="power_model" && elapsed_us()>=20000 ? 3300:4660;
}
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() {
  return adc_triggered || scenario=="cancel_entry" ||
    ((scenario=="cancel_model" || scenario=="cancel_settle" || scenario=="adc_mission") && elapsed_us()>=20000) ||
    (scenario=="rx_load" && elapsed_us()>=60000) ||
    (scenario=="reset_cancel" && reset_edges!=0);
}
int main(int argc,char**argv) {
  if(argc!=2)return 2;
  scenario=argv[1];
  // Bind the genuine library before the measured call. No response is pending.
  if(scenario!="allocation_failure" && scenario!="first_bind" && scenario!="init_held" && scenario!="init_allocation_failure") gnss.begin(gps_gnss_stream,0);
  fail_arrays=scenario=="allocation_failure" || scenario=="init_allocation_failure";
  Serial1=StartupSerial{};
  if(scenario=="wrong_model" || scenario=="nack" || scenario=="adc_set") Serial1.model=0;
  if(scenario=="cancel_settle" || scenario=="adc_release") gps_ublox_assert_reset_early();
  if(scenario=="init_held" || scenario=="init_allocation_failure") gps_ublox_assert_reset_early();
  if(scenario=="wrap") fixture_us=uint64_t(UINT32_MAX-20u)*1000u;
  if(scenario=="stale_queued") {
    auto old=frame(6,0x8b,{1,0,0,0,0x21,0,0x11,0x20,8});
    Serial1.rx.insert(Serial1.rx.end(),old.begin(),old.end());
  }
  origin_us=fixture_us;
  unsigned initial_resets=reset_edges;
  gps_fix_t fix{};fix.valid=true;fix.satellites=9;
  uint32_t timeout=scenario=="zero"?0:scenario=="adc_deadline"?10:scenario=="deadline"?50:scenario=="connection_deadline"?6000:10000;
  bool init_case=scenario=="init_held" || scenario=="init_allocation_failure";
  bool ok=init_case?gps_ublox_init():gps_ublox_get_fix(&fix,timeout);
  uint64_t elapsed=elapsed_us()/1000;
  bool good=false;
  if(scenario=="healthy" || scenario=="wrap" || scenario=="first_bind")
    good=ok && fix.valid && Serial1.sets==0 && Serial1.polls==2 && reset_edges==0;
  else if(scenario=="wrong_model")
    good=ok && fix.valid && Serial1.sets==1 && Serial1.polls==2 && reset_edges==0;
  else if(scenario=="late_ready")
    good=ok && fix.valid && Serial1.sets==0 && reset_edges==0 && elapsed>=1200 && elapsed<2000;
  else if(scenario=="adc_mission" || scenario=="adc_deadline")
    good=!ok && !fix.valid && Serial1.writes==0 && reset_edges==0 && elapsed<=20;
  else if(scenario=="adc_set")
    good=adc_triggered && !ok && !fix.valid && Serial1.sets==0 && reset_edges==0;
  else if(scenario=="adc_release")
    good=adc_triggered && !ok && !fix.valid && releases==0 && Serial1.writes==0;
  else if(scenario=="allocation_failure")
    good=!ok && !fix.valid && Serial1.writes==0 && reset_edges==0;
  else if(scenario=="init_held")
    good=ok && !last_fix.valid && releases==1 && Serial1.gets==2 && Serial1.sets==0;
  else if(scenario=="init_allocation_failure")
    good=!ok && !last_fix.valid && releases==0 && Serial1.writes==0 && reset_low && gps_quiescence_state==GPS_QUIESCENCE_RESET_HELD;
  else if(scenario=="connection_deadline")
    good=!ok && !fix.valid && Serial1.polls==0 && elapsed<=6001 && reset_edges==1 &&
      s_gps_diag.begin_failures==0 && s_gps_diag.dyn_model_terminal_failures==0;
  else if(scenario=="zero" || scenario=="cancel_entry")
    good=!ok && !fix.valid && fix.satellites==0 && Serial1.writes==0 && reset_edges==initial_resets;
  else if(scenario=="deadline")
    good=!ok && !fix.valid && elapsed<=51 && Serial1.polls==0 && reset_edges==0;
  else if(scenario=="cancel_model" || scenario=="power_model" || scenario=="rx_load" || scenario=="cancel_settle")
    good=!ok && !fix.valid && elapsed<=125 && Serial1.polls==0 && reset_edges==initial_resets;
  else if(scenario=="tx_stall" || scenario=="partial_tx")
    good=!ok && !fix.valid && elapsed<=25 && Serial1.polls==0 && reset_edges==0;
  else if(scenario=="reset_cancel")
    good=!ok && !fix.valid && Serial1.polls==0 && reset_edges==1 && elapsed<3000 &&
      reset_low && releases==0 && gps_quiescence_state==GPS_QUIESCENCE_RESET_HELD;
  else
    good=!ok && !fix.valid && Serial1.polls==0 && reset_edges<=1 && elapsed<=10001;
  std::printf("[%s] %s ms=%llu ok=%u gets=%u sets=%u polls=%u resets=%u tx=%u flush=%u\n",
    good?"PASS":"FAIL",scenario.c_str(),(unsigned long long)elapsed,ok,Serial1.gets,Serial1.sets,Serial1.polls,reset_edges,Serial1.writes,Serial1.flushes);
  return good?0:1;
}
'''

CASES = ("healthy", "wrong_model", "wrap", "zero", "cancel_entry", "deadline",
         "cancel_model", "power_model", "rx_load", "cancel_settle", "tx_stall",
         "partial_tx", "reset_cancel", "wrong_key", "wrong_layer", "wrong_version",
         "wrong_position", "short", "bad_crc", "truncated", "nack", "silent")
CASES += ("late_ready", "stale_queued", "adc_mission", "adc_deadline")
CASES += ("adc_set", "adc_release")
CASES += ("first_bind", "allocation_failure")
CASES += ("init_held", "init_allocation_failure")
CASES += ("connection_deadline",)


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="gps-startup-supervision-") as name:
        build = Path(name)
        for filename, contents in (("Arduino.h", ARDUINO), ("Wire.h", fixture.WIRE),
                                   ("SPI.h", fixture.SPI), ("test.cpp", TEST)):
            (build / filename).write_text(contents)
        binary = build / "test"
        subprocess.run([
            os.environ.get("CXX", "c++"), "-std=c++17", "-Wno-vla-cxx-extension",
            "-fcheck-new", "-Wno-new-returns-null",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
            "-I", str(build), "-I", str(ROOT / "firmware/include"),
            "-I", str(ROOT / "firmware/src"), "-I", str(LIB),
            str(LIB / "u-blox_GNSS.cpp"), str(LIB / "sfe_bus.cpp"), str(build / "test.cpp"),
            *(str(ROOT / f"firmware/src/{n}.cpp") for n in
              ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
            "-o", str(binary)], check=True, timeout=60)
        for case in CASES:
            result = subprocess.run([str(binary), case], capture_output=True, text=True,
                                    timeout=20, env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                                         UBSAN_OPTIONS="halt_on_error=1"))
            print(result.stdout, end="")
            print(result.stderr, end="")
            if result.returncode or result.stderr:
                failures.append(case)
    assert not failures, failures
    print(f"PASS: {len(CASES)} real-parser startup cases; ASan/UBSan clean")


if __name__ == "__main__":
    main()
