#!/usr/bin/env python3
"""Exercise the production no-mic driver and its actual telemetry encoding."""

from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
ARDUINO = r"""
#pragma once
#include <stdint.h>
struct FakeRcc { volatile uint32_t AHB2ENR; };
struct FakeGpio { volatile uint32_t MODER, PUPDR; };
extern FakeRcc rcc;
extern FakeGpio gpio;
extern unsigned barriers;
#define RCC (&rcc)
#define GPIOB (&gpio)
#define RCC_AHB2ENR_GPIOBEN (1u << 1)
#define __DSB() (++barriers)
// Deliberately no SPI registers, alternate-function controls, clock sources,
// millis(), or pinMode(): disabled code must not depend on any of them.
"""
HARNESS = r"""
#include <assert.h>
#include "Arduino.h"
#include "mic_acoustic.h"
#include "telemetry.h"

FakeRcc rcc = {};
FakeGpio gpio = {};
unsigned barriers = 0;

int main() {
    const uint32_t pins = (3u << 6) | (3u << 8);
    const uint32_t patterns[] = {0u, 0xFFFFFFFFu, 0xAAAAAAAAu, 0x55555555u};
    for (uint32_t pattern : patterns) {
        rcc.AHB2ENR = pattern;
        gpio.MODER = pattern;
        gpio.PUPDR = pattern;
        assert(!mic_acoustic_init());
        assert(rcc.AHB2ENR == (pattern | RCC_AHB2ENR_GPIOBEN));
        assert(gpio.MODER == (pattern | pins));
        assert(gpio.PUPDR == (pattern & ~pins));
    }
    assert(barriers == 4u);
    assert(!mic_acoustic_detect(nullptr));
    for (uint8_t tier = 0; tier <= 4; ++tier) {
        telemetry_input_t input;
        telemetry_input_init(&input);
        input.acoustic_event = 0xFFu;
        input.acoustic_valid = mic_acoustic_detect(&input.acoustic_event);
        input.power_tier = tier;
        assert(input.acoustic_valid == 0u && input.acoustic_event == 0u);
        uint8_t packet[TELEMETRY_PAYLOAD_SIZE] = {};
        telemetry_pack(&input, packet);
        assert((packet[34] & 0x0Fu) == 10u + tier);
    }
    // Detection must not reconfigure pins or write the GPIO clock register.
    assert(rcc.AHB2ENR == (patterns[3] | RCC_AHB2ENR_GPIOBEN));
    assert(gpio.MODER == (patterns[3] | pins));
    assert(gpio.PUPDR == (patterns[3] & ~pins));
    assert(barriers == 4u);
}
"""


def main():
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        raise SystemExit("A host C++ compiler is required")
    with tempfile.TemporaryDirectory(prefix="stratolink-no-mic-") as raw:
        directory = Path(raw)
        (directory / "Arduino.h").write_text(ARDUINO)
        (directory / "test.cpp").write_text(HARNESS)
        binary = directory / "test"
        subprocess.run([
            compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
            "-DSTRATOLINK_MIC_PRESENT=0", "-I", str(directory),
            "-I", str(ROOT / "firmware/include"),
            str(ROOT / "firmware/src/mic_acoustic.cpp"),
            str(ROOT / "firmware/src/telemetry.cpp"),
            str(directory / "test.cpp"), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)
    print("PASS: no-mic production driver uses no SPI API, quiets only PB3/PB4, "
          "and encodes unavailable at all five power tiers")


if __name__ == "__main__":
    main()
