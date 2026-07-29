#!/usr/bin/env python3
"""Bind every end-of-cycle radio state to confirmed sleep or reset."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LORAWAN = ROOT / "firmware/src/lorawan.cpp"
MAIN = ROOT / "firmware/src/main.cpp"
HIL_GENERATOR = ROOT / "analysis/diagnostics/generate_flight_hil.py"
HIL_DECODER = ROOT / "analysis/diagnostics/decode_flight_state.py"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    source_raw = LORAWAN.read_text(encoding="utf-8")
    source = compact(source_raw)
    start = source.index("void lorawan_sleep(void)")
    end = source.index("/* ========== Meshtastic open-relay", start)
    sleep = source[start:end]

    assert "if (!radio_ready) return;" not in sleep, (
        "unknown/unready modem state still bypasses quiescence"
    )
    assert "if (radio_ready) { sleep_state = radio->sleep(true);" in sleep
    assert "radio_ready = false;" in sleep
    assert "if (!lorawan_init() ||" in sleep
    assert "(retry_state = radio->sleep(true)) != RADIOLIB_ERR_NONE" in sleep
    assert "NVIC_SystemReset();" in sleep
    assert sleep.index("radio_ready = false;") < sleep.index("lorawan_init()")
    assert sleep.index("lorawan_init()") < sleep.index("NVIC_SystemReset();")

    main_source = MAIN.read_text(encoding="utf-8")
    assert main_source.count("lorawan_sleep();") >= 2, (
        "normal and early-return paths no longer demand radio quiescence"
    )

    hil_generator = HIL_GENERATOR.read_text(encoding="utf-8")
    hil_decoder = HIL_DECODER.read_text(encoding="utf-8")
    assert '"s_radio_diag"' in hil_generator
    assert '"sleep_failures": u32(radio, 16)' in hil_decoder, (
        "exact-image HIL does not expose radio sleep-containment failures"
    )
    assert 'health["radio_diag"]["sleep_failures"] == 0' in hil_decoder
    print(
        "PASS: ready, unready, and failed-sleep radio states require confirmed "
        "SX1262 sleep or reset before the mission idle interval"
    )


if __name__ == "__main__":
    main()
