#!/usr/bin/env python3
"""Lock the public-Meshtastic toggle away from authenticated B2B service."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware/src/main.cpp"
LORAWAN = ROOT / "firmware/src/lorawan.cpp"
HEADER = ROOT / "firmware/include/lorawan.h"
CONFIG = ROOT / "firmware/include/config.h"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    main_source = MAIN.read_text(encoding="utf-8")
    relay_source = LORAWAN.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")

    shared_gate = re.search(
        r"#if \(defined\(MESHTASTIC_RELAY_ENABLE\).*?"
        r"uint32_t used = lorawan_relay_window\(.*?"
        r"\n#endif",
        main_source,
        flags=re.DOTALL,
    )
    assert shared_gate, "shared LongFast window gate is missing"
    gate = compact(shared_gate.group(0))
    assert "(defined(B2B_ENABLE) && B2B_ENABLE)" in gate
    assert "meshtastic_enabled = command_relay_enabled();" in gate
    assert (
        "region_known && command_relay_enabled()" not in gate
    ), "public relay toggle still suppresses the shared B2B window"
    assert (
        "lorawan_relay_window( relay_window_budget, RELAY_FLOOR_MV, "
        "meshtastic_enabled)" in gate
    )
    assert "sleep_ms < relay_region_budget_ms" in gate

    assert (
        "uint32_t lorawan_relay_window( uint32_t max_ms, "
        "uint16_t floor_mv, bool meshtastic_enabled);" in compact(header)
    )
    implementation = compact(relay_source)
    b2b_branch = implementation.index("if (b2b_prefix)")
    mesh_branch = implementation.index(
        "} else if (meshtastic_enabled && len >= 16)"
    )
    assert b2b_branch < mesh_branch, (
        "authenticated B2B must be classified independently before public mesh"
    )
    assert "public Meshtastic only; never B2B" in config
    print("PASS: public Meshtastic toggle cannot disable B2B service")


if __name__ == "__main__":
    main()
