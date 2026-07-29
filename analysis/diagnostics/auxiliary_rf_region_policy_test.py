#!/usr/bin/env python3
"""Pin the source-level regional eligibility of the shared LongFast window."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
LORAWAN = ROOT / "firmware/src/lorawan.cpp"


def source_mapping() -> dict[str, float]:
    source = LORAWAN.read_text(encoding="utf-8")
    match = re.search(
        r"static float meshtastic_longfast_freq\(.*?\) \{(.*?)\n\}",
        source,
        re.S,
    )
    assert match, "meshtastic_longfast_freq source function missing"
    body = match.group(1)
    pairs = re.findall(
        r"case\s+LORA_REGION_(\w+):\s+return\s+([0-9.]+)f;", body
    )
    mapping = {name: float(value) for name, value in pairs}
    assert "default:                return 0.0f;" in body
    return mapping


def main() -> None:
    mapping = source_mapping()
    assert mapping == {
        "US915": 906.875,
        "EU868": 869.525,
        "AS923": 0.0,
        "AU915": 919.875,
    }

    source = LORAWAN.read_text(encoding="utf-8")
    assert source.count("meshtastic_longfast_freq(REGION_ID)") == 1
    assert "if (freq <= 0.0f) return 0;" in source
    assert "uint32_t lorawan_relay_window(" in source
    assert "b2b_init_once();" in source
    print(
        "PASS: shared Meshtastic/B2B LongFast window is source-gated to "
        "US915/EU868/AU915; AS923 and SILENT are disabled"
    )


if __name__ == "__main__":
    main()
