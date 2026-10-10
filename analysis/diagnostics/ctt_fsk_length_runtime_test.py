#!/usr/bin/env python3
"""CTT fixed-length RX contract against the pinned real RadioLib SPI implementation.

No hardware, network, or shared build outputs. Only the external SPI/GPIO/time
boundary is simulated; production CTT configuration/arm expressions and real
SX1262/SX126x/PhysicalLayer/Module methods execute in an isolated host build.
This proves command construction, not STM32 interrupt delivery or RF reception.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "firmware/.pio/libdeps/stratolink/RadioLib/src"
SOURCE = ROOT / "firmware/src/lorawan.cpp"
# SHA-256 of sorted "relative/path sha256\n" rows for RadioLib 7.6.0 sources.
LIBRARY_SOURCE_SHA256 = "7d2c9604045712cfbd6a79e060f9fbdea2e6fb63086e6d06cbd7f6fa611d83d7"


def function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def production_fragments(source: str) -> tuple[str, str, str, str]:
    window = function(source, "uint32_t lorawan_ctt_window(")
    start = window.index("int16_t st = radio->beginFSK(")
    end = window.index("if (st != RADIOLIB_ERR_NONE)", start)
    config = window[start:end] + "\nreturn st;"
    initial = re.search(r"int16_t rx_state = ([^;]+);", window)
    rearm = re.search(r"(?<!int16_t )rx_state = ([^;]+);", window)
    if not initial or not rearm:
        raise RuntimeError("Expected actual initial and rearm CTT expressions")
    helper = (function(source, "static int16_t ctt_start_receive(")
              if "static int16_t ctt_start_receive(" in source else "")
    return config, helper, initial.group(1), rearm.group(1)


HARNESS = r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "modules/SX126x/SX1262.h"

static unsigned checks = 0, failures = 0;
static void expect(bool ok, const char* message) {
    ++checks;
    if (!ok) { ++failures; std::fprintf(stderr, "FAIL: %s\n", message); }
}

struct FakeHal final : RadioLibHal {
    std::array<uint8_t, 65536> registers{};
    std::array<uint8_t, 9> packet{};
    std::vector<std::array<uint8_t, 9>> receive_packets;
    std::vector<uint8_t> opcodes;
    bool wrong_rx_timeout = false;
    uint8_t modem = 0;
    unsigned fault = 0, injected = 0;
    RadioLibTime_t clock = 0;
    FakeHal() : RadioLibHal(0, 1, 0, 1, 1, 2) {
        // SX1262 reports the same six-byte silicon string as SX1261.
        std::memcpy(&registers[RADIOLIB_SX126X_REG_VERSION_STRING], "SX1261", 6);
    }
    void pinMode(uint32_t, uint32_t) override {}
    void digitalWrite(uint32_t, uint32_t) override {}
    uint32_t digitalRead(uint32_t) override { return 0; }
    void attachInterrupt(uint32_t, void (*)(), uint32_t) override {}
    void detachInterrupt(uint32_t) override {}
    void delay(RadioLibTime_t value) override { clock += value * 1000; }
    void delayMicroseconds(RadioLibTime_t value) override { clock += value; }
    RadioLibTime_t millis() override { return ++clock / 1000; }
    RadioLibTime_t micros() override { return ++clock; }
    long pulseIn(uint32_t, uint32_t, RadioLibTime_t) override { return 0; }
    void spiBegin() override {}
    void spiBeginTransaction() override {}
    void spiEndTransaction() override {}
    void spiEnd() override {}
    void spiTransfer(uint8_t* out, size_t length, uint8_t* in) override {
        std::fill(in, in + length, uint8_t(0x24)); // standby + command success
        const uint8_t command = out[0];
        opcodes.push_back(command);
        const bool fail = fault && !injected &&
            ((fault == 1 && command == 0x80) ||
             (fault == 2 && command == 0x8C && length == 10 && out[7] == 5) ||
             (fault == 3 && command == 0x82));
        if (fail) {
            ++injected;
            std::fill(in, in + length, uint8_t(0x2A)); // actual command-failed status
            return;
        }
        if (command == 0x8A && length >= 2) modem = out[1];
        if (command == 0x11 && length >= 3) in[2] = modem;
        if (command == 0xC0 && length >= 3) in[2] = 0x24;
        if (command == 0x0D && length >= 3) {
            const uint16_t address = (uint16_t(out[1]) << 8) | out[2];
            for (size_t i = 3; i < length; ++i) registers[address + i - 3] = out[i];
        }
        if (command == 0x1D && length >= 4) {
            const uint16_t address = (uint16_t(out[1]) << 8) | out[2];
            for (size_t i = 4; i < length; ++i) in[i] = registers[address + i - 4];
        }
        if (command == 0x8C && length == 10) std::copy(out + 1, out + 10, packet.begin());
        if (command == 0x82) {
            receive_packets.push_back(packet);
            if (length != 4 || out[1] != 0xFF || out[2] != 0xFF || out[3] != 0xFF)
                wrong_rx_timeout = true;
        }
    }
};

static SX1262* radio = nullptr;
#define CTT_FREQ_MHZ 434.0
__HELPER__
static int16_t configure() { __CONFIG__ }
static int16_t initial_arm() { return __INITIAL__; }
static int16_t rearm() { return __REARM__; }

static void test_success() {
    FakeHal hal;
    Module module(&hal, 10, 11, 12, 13);
    SX1262 device(&module);
    radio = &device;
    const int16_t configured = configure();
    if (configured) std::fprintf(stderr, "configuration status %d\n", configured);
    expect(configured == 0, "real driver configures the production CTT profile");
    // Hand-derived opcode 0x8C payload: preamble16, detector16, sync16,
    // no address filter, fixed5, no hardware CRC, no whitening.
    const std::array<uint8_t, 9> expected{{0, 16, 5, 16, 0, 0, 5, 1, 0}};
    for (unsigned arm = 0; arm < 4; ++arm) {
        const int16_t result = arm == 0 ? initial_arm() : rearm();
        expect(result == 0, "initial and repeated real-driver RX arms succeed");
        expect(hal.receive_packets.size() == arm + 1, "each arm emits exactly one SetRx");
        expect(!hal.wrong_rx_timeout, "every CTT arm retains continuous RX timeout");
        if (hal.receive_packets.size() != arm + 1) continue;
        const auto& actual = hal.receive_packets.back();
        if (actual != expected) {
            std::fprintf(stderr, "actual 0x8C before SetRx[%u]:", arm);
            for (uint8_t byte : actual) std::fprintf(stderr, " %02X", byte);
            std::fprintf(stderr, "\n");
        }
        expect(actual == expected, "actual SPI payload length is five at every SetRx, not255");
    }
}

static void test_faults() {
    for (unsigned fault = 1; fault <= 3; ++fault) {
        for (bool is_rearm : {false, true}) {
            FakeHal hal;
            Module module(&hal, 10, 11, 12, 13);
            SX1262 device(&module);
            radio = &device;
            expect(configure() == 0, "fault scenario production configuration succeeds");
            if (is_rearm) expect(initial_arm() == 0, "first arm succeeds before rearm fault");
            hal.receive_packets.clear();
            hal.opcodes.clear();
            hal.fault = fault;
            const int16_t result = is_rearm ? rearm() : initial_arm();
            expect(hal.injected == 1, "requested stage/fixed/launch SPI fault is reached");
            expect(result == RADIOLIB_ERR_SPI_CMD_FAILED, "actual SPI error propagates to caller");
            expect(hal.receive_packets.empty(), "failure never produces successful SetRx");
            const auto launches = std::count(hal.opcodes.begin(), hal.opcodes.end(), uint8_t(0x82));
            expect(launches == (fault == 3 ? 1 : 0), "stage/length errors prevent launch; launch error not retried");
        }
    }
}

int main() {
    test_success();
    test_faults();
    std::printf("CTT real RadioLib SPI: %u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
'''


def mutations(harness: str) -> list[tuple[str, str, str]]:
    if "static int16_t ctt_start_receive(" not in harness:
        return []  # Original source must first fail the actual command contract.

    def change(old: str, new: str) -> str:
        if harness.count(old) != 1:
            raise RuntimeError(f"Mutation target must occur once: {old}")
        return harness.replace(old, new, 1)

    length = "actual SPI payload length is five at every SetRx, not255"
    error = "actual SPI error propagates to caller"
    return [
        ("initial driver default", change("static int16_t initial_arm() { return ctt_start_receive(); }",
                                         "static int16_t initial_arm() { return radio->startReceive(); }"), length),
        ("rearm driver default", change("static int16_t rearm() { return ctt_start_receive(); }",
                                       "static int16_t rearm() { return radio->startReceive(); }"), length),
        ("length reinstall missing", change("state = radio->fixedPacketLengthMode(5);",
                                            "state = RADIOLIB_ERR_NONE;"), length),
        ("wrong fixed length", change("state = radio->fixedPacketLengthMode(5);",
                                      "state = radio->fixedPacketLengthMode(4);"), length),
        ("stage error ignored", change("if (state != RADIOLIB_ERR_NONE) return state;\n"
                                       "    state = radio->fixedPacketLengthMode(5);",
                                       "(void)state;\n    state = radio->fixedPacketLengthMode(5);"), error),
        ("length error ignored", change("if (state != RADIOLIB_ERR_NONE) return state;\n"
                                        "    return radio->launchMode();",
                                        "(void)state;\n    return radio->launchMode();"), error),
        ("launch error ignored", change("return radio->launchMode();",
                                        "(void)radio->launchMode(); return RADIOLIB_ERR_NONE;"), error),
        ("continuous RX removed", change("cfg.receive.timeout = RADIOLIB_SX126X_RX_TIMEOUT_INF;",
                                          "cfg.receive.timeout = 0;"),
         "every CTT arm retains continuous RX timeout"),
    ]


def run() -> int:
    source = SOURCE.read_text()
    config, helper, initial, rearm = production_fragments(source)
    files = [LIB / name for name in ("Module.cpp", "Hal.cpp", "protocols/PhysicalLayer/PhysicalLayer.cpp")]
    files += sorted((LIB / "modules/SX126x").glob("SX126*.cpp"))
    files += sorted((LIB / "utils").glob("*.cpp"))
    manifest = []
    for path in sorted(LIB.rglob("*")):
        if path.suffix not in (".h", ".cpp") or not path.is_file():
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append(f"{path.relative_to(LIB).as_posix()} {actual}\n")
    if hashlib.sha256("".join(manifest).encode()).hexdigest() != LIBRARY_SOURCE_SHA256:
        raise RuntimeError("Pinned RadioLib source identity changed")
    harness = (HARNESS.replace("__HELPER__", helper).replace("__CONFIG__", config)
               .replace("__INITIAL__", initial).replace("__REARM__", rearm))
    with tempfile.TemporaryDirectory(prefix="ctt-real-radiolib-") as temporary:
        directory = Path(temporary)
        cpp = directory / "contract.cpp"
        binary = directory / "contract"
        flags = [os.environ.get("CXX", "c++"), "-std=c++20", "-O1", "-g",
                 "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-isystem", str(LIB)]
        # Isolated object reuse avoids recompiling unchanged pinned dependencies
        # for every behavioral mutation; no .pio build outputs are touched.
        subprocess.run([*flags, "-c", *(str(path) for path in files)],
                       cwd=directory, check=True, timeout=120)
        objects = sorted(directory.glob("*.o"))

        def execute(code: str) -> subprocess.CompletedProcess[str]:
            cpp.write_text(code)
            subprocess.run([*flags, "-Wall", "-Wextra", "-Werror", "-pedantic",
                            str(cpp), *(str(path) for path in objects), "-o", str(binary)],
                           check=True, timeout=60)
            return subprocess.run([str(binary)], timeout=15, text=True, capture_output=True,
                                  env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1"})

        result = execute(harness)
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", flush=True)
        if result.returncode == 0:
            for name, code, required_failure in mutations(harness):
                changed = execute(code)
                if changed.returncode != 1 or required_failure not in changed.stderr:
                    raise RuntimeError(f"Mutation not rejected by intended assertion: {name}\n"
                                       f"{changed.stdout}{changed.stderr}")
                print(f"MUTATION REJECTED: {name}", flush=True)
    print("Production SHA256:", hashlib.sha256(source.encode()).hexdigest(), flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(run())
