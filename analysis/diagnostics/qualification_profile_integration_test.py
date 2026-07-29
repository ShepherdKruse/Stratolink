#!/usr/bin/env python3
"""Pin the distinct relay-soak, power-profile, and flight contracts."""

from __future__ import annotations

from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def section(text: str, name: str) -> str:
    match = re.search(
        rf"^\[env:{re.escape(name)}\]\n(.*?)(?=^\[env:|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing env:{name}"
    return match.group(1)


def main() -> None:
    platformio = (ROOT / "firmware/platformio.ini").read_text(encoding="utf-8")
    flight = section(platformio, "stratolink")
    relay_soak = section(platformio, "stratolink_soak")
    power_profile = section(platformio, "stratolink_profile")

    assert "BENCH_SEED_REGION" not in flight
    assert "RELAY_SOLAR_MIN_MV=0" not in flight
    assert "-D BENCH_SEED_REGION" in relay_soak
    assert "-D RELAY_SOLAR_MIN_MV=0" in relay_soak
    assert "-D BENCH_SEED_REGION" in power_profile
    assert "RELAY_SOLAR_MIN_MV=0" not in power_profile

    config = (ROOT / "firmware/include/config.h").read_text(encoding="utf-8")
    assert "#define RELAY_SOLAR_MIN_MV        3000" in config
    assert "#define CTT_LISTEN_MS      60000u" in config

    mission = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
    ctt = mission.index("lorawan_ctt_window(ctt_budget, RELAY_FLOOR_MV)")
    relay = mission.index("lorawan_relay_window(")
    assert ctt < relay
    assert "sleep_ms = (ctt_used < sleep_ms)" in mission
    assert "sleep_ms = (used < sleep_ms)" in mission

    summary = (HERE / "soak_summary.py").read_text(encoding="utf-8")
    assert '"firmware_profile": args.firmware_profile' in summary
    assert "STOP1 sleep current or repeated STOP1 wake behavior" in summary
    assert "env:stratolink_soak sets RELAY_SOLAR_MIN_MV=0" in summary
    assert "entry remains a post-soak counter claim" in summary
    assert "--final requires explicit --handoff-power and --supabase" in summary

    traceability = (
        HERE / "STRATOLINK2_POSTFLIGHT_CHANGE_TRACEABILITY.md"
    ).read_text(encoding="utf-8")
    assert "does **not** qualify STOP1" in traceability
    assert "little or no time in STOP1" in traceability
    assert "require the post-soak counter snapshot" in traceability

    print(
        "PASS: relay-soak, power-profile, and flight qualification scopes "
        "remain distinct and fail closed"
    )


if __name__ == "__main__":
    main()
