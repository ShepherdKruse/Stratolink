#!/usr/bin/env python3
"""Source-bound energy screen for long Meshtastic/B2B and CTT RX windows."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LORAWAN = ROOT / "firmware" / "src" / "lorawan.cpp"
MISSION = ROOT / "firmware" / "src" / "main.cpp"
CONFIG = ROOT / "firmware" / "include" / "config.h"

# Engineering screen inputs, not fitted-hardware measurements. The radio
# receive value is a module-level typical and the former active MCU current is
# the estimate that exposed the busy-wait defect. Exact shallow-WFI current
# with the final clocks/peripherals and supercapacitor remains a PPK2 gate.
RADIO_RX_TYP_A = 5.5e-3
FORMER_MCU_ACTIVE_SCREEN_A = 5.0e-3
V_RAIL = 3.3
CONVERTER_EFFICIENCY = 0.85
GPS_HOT_SCREEN_S = 2.0
SF9_35B_AIRTIME_SCREEN_S = 0.308


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_u32(source: str, pattern: str, name: str) -> int:
    match = re.search(pattern, source)
    require(match is not None, f"missing source-bound {name}")
    return int(match.group(1))


def rail_energy_j(current_a: float, duration_s: float) -> float:
    return current_a * V_RAIL / CONVERTER_EFFICIENCY * duration_s


def function_block(source: str, signature: str, next_marker: str) -> str:
    start = source.index(signature)
    end = source.index(next_marker, start)
    return source[start:end]


def build_audit() -> dict[str, object]:
    source = LORAWAN.read_text(encoding="utf-8")
    mission = MISSION.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")

    helper = function_block(
        source,
        "static void radio_idle_until_interrupt",
        "/* Wait to an absolute offset",
    )
    relay = function_block(
        source,
        "uint32_t lorawan_relay_window(",
        "/* ===== CTT wildlife-tag listener",
    )
    ctt = function_block(
        source,
        "uint32_t lorawan_ctt_window(",
        "/* ========== Class-A downlink",
    )

    require("__WFI();" in helper, "shared radio idle helper no longer uses WFI")
    require(
        "SCB_SCR_SLEEPDEEP_Msk" in helper,
        "shared radio idle helper no longer forces shallow CPU sleep",
    )
    require(
        "radio_idle_until_interrupt();" in relay,
        "relay window no longer uses the shared WFI idle path",
    )
    require(
        "radio_idle_until_interrupt();" in ctt,
        "CTT window no longer uses the shared WFI idle path",
    )
    require("delay(2)" not in relay, "relay window regressed to busy-spin delay")
    require("delay(2)" not in ctt, "CTT window regressed to busy-spin delay")
    for name, block in (("relay", relay), ("CTT", ctt)):
        require(
            "power_manager_kick_watchdog()" in block,
            f"{name} window lost watchdog service",
        )
        require(
            "power_manager_freefall_pending()" in block,
            f"{name} window lost freefall preemption",
        )
        require(
            "power_adc_read_vSTOR_mv()" in block
            and "power_adc_read_solar_mv()" in block,
            f"{name} window lost rail/solar abort",
        )

    full_cadence_s = source_u32(
        config,
        r"#define SLEEP_INTERVAL_FULL_SEC\s+([0-9]+)",
        "FULL cadence",
    )
    ctt_window_ms = source_u32(
        config, r"#define CTT_LISTEN_MS\s+([0-9]+)u", "CTT listen duration"
    )
    relay_floor_mv = source_u32(
        config, r"#define RELAY_FLOOR_MV\s+([0-9]+)", "relay floor"
    )
    solar_gate_mv = source_u32(
        config, r"#define RELAY_SOLAR_MIN_MV\s+([0-9]+)", "solar gate"
    )
    ctt_enabled_match = re.search(
        r"#define CTT_LISTEN_ENABLE\s+(true|false|0|1)\b", config
    )
    require(ctt_enabled_match is not None, "missing CTT flight enable")
    ctt_enabled = ctt_enabled_match.group(1) in {"true", "1"}

    require(
        "power_adc_get_tier() == POWER_TIER_FULL" in mission,
        "auxiliary RX mission gate no longer requires FULL tier",
    )
    require(
        "power_adc_read_solar_mv() >= RELAY_SOLAR_MIN_MV" in mission,
        "auxiliary RX mission gate no longer requires fresh solar surplus",
    )
    require(
        "sleep_ms < relay_region_budget_ms ? sleep_ms : relay_region_budget_ms"
        in mission
        and "relay_window_budget, RELAY_FLOOR_MV, meshtastic_enabled"
        in mission,
        "relay no longer obeys both cadence and regional-lease budgets",
    )

    comparison_window_s = (
        full_cadence_s - GPS_HOT_SCREEN_S - SF9_35B_AIRTIME_SCREEN_S
    )
    radio_only_j = rail_energy_j(RADIO_RX_TYP_A, comparison_window_s)
    former_mcu_j = rail_energy_j(
        FORMER_MCU_ACTIVE_SCREEN_A, comparison_window_s
    )

    return {
        "status": "PARTIAL_WFI_REPAIRED_EXACT_CURRENT_HIL_REQUIRED",
        "passed": False,
        "scope": (
            "source-bound long-window idle contract and historical current "
            "screen; not measured final-clock WFI current or system endurance"
        ),
        "source_contract": {
            "full_cadence_s": full_cadence_s,
            "ctt_listen_ms": ctt_window_ms,
            "ctt_enabled_in_flight": ctt_enabled,
            "relay_floor_mv": relay_floor_mv,
            "solar_gate_mv": solar_gate_mv,
            "shared_idle_uses_wfi": True,
            "wfi_explicitly_clears_sleepdeep": True,
            "relay_uses_shared_wfi": True,
            "ctt_uses_shared_wfi": True,
            "relay_watchdog_and_abort_checks_preserved": True,
            "ctt_watchdog_and_abort_checks_preserved": True,
            "mission_requires_full_tier_and_solar_surplus": True,
            "relay_capped_by_remaining_region_lease": True,
        },
        "screen_inputs": {
            "radio_rx_typical_a": RADIO_RX_TYP_A,
            "former_mcu_active_screen_a": FORMER_MCU_ACTIVE_SCREEN_A,
            "rail_v": V_RAIL,
            "converter_efficiency": CONVERTER_EFFICIENCY,
            "comparison_window_s": comparison_window_s,
        },
        "energy_screen": {
            "radio_rx_typical_lower_screen_j_per_window": radio_only_j,
            "former_mcu_busy_spin_screen_j_per_window": former_mcu_j,
            "former_combined_screen_j_per_window": radio_only_j + former_mcu_j,
            "repaired_total_j_per_window": None,
        },
        "interpretation": (
            "The former long service loops called STM32duino delay(2), whose "
            "empty yield hook kept the MCU active. A 1197.692-second comparison "
            "therefore cost about 48.82 J before other work, not the prior "
            "25.57 J radio-only estimate. The repaired loops use shallow WFI "
            "while continuous RX and SysTick remain live. A strong application "
            "yield hook now gives every remaining framework delay the same "
            "explicitly shallow behavior, but the radio loops retain their "
            "dedicated helper and tighter abort checks. The radio-only value "
            "is now a lower engineering screen, never a total-current claim. "
            "CTT remains disabled in the StratoLink-2 flight image."
        ),
        "required_hil": (
            "After the soak, capture the exact candidate with PPK2 through a "
            "controlled relay listen window and its VSTOR/solar/freefall exits. "
            "Measure the shallow-WFI floor plus radio RX, verify one-hertz "
            "housekeeping and immediate INT1 preemption, and repeat with the "
            "fitted final supercapacitor. CTT RF qualification is separately "
            "blocked by the fitted high-band RAK3172-9."
        ),
    }


def main() -> None:
    print(json.dumps(build_audit(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
