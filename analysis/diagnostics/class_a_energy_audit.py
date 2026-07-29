#!/usr/bin/env python3
"""Source-bound energy screen for the always-open Class-A command windows."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LORAWAN = ROOT / "firmware" / "src" / "lorawan.cpp"
CONFIG = ROOT / "firmware" / "include" / "config.h"

# Engineering screen only. RAK3172's quoted receive current is a module-level
# typical; CPU-sleep current in this exact clock/peripheral state is not yet
# measured. Use the former active-current estimate only as the upper comparison
# that exposed the busy-wait defect.
RAK3172_RX_TYP_A = 5.5e-3
MCU_ACTIVE_SCREEN_A = 5.0e-3
V_RAIL = 3.3
CONVERTER_EFFICIENCY = 0.85
MIN_CAPACITANCE_F = 0.8
SCREEN_CEILING_V = 5.2
HISTORICAL_REPORTED_PLATEAU_V = 3.32


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_u32(source: str, pattern: str, name: str) -> int:
    match = re.search(pattern, source)
    require(match is not None, f"missing source-bound {name}")
    return int(match.group(1))


def rail_energy_j(current_a: float, duration_ms: int) -> float:
    return current_a * V_RAIL / CONVERTER_EFFICIENCY * duration_ms / 1000.0


def build_audit() -> dict[str, object]:
    source = LORAWAN.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")

    default_rx_delay_s = source_u32(
        source, r"static uint8_t s_rx_delay_s\s*=\s*([0-9]+)\s*;",
        "default RxDelay",
    )
    preopen_ms = source_u32(
        source, r"const uint32_t preopen_ms\s*=\s*([0-9]+)u\s*;",
        "pre-open guard",
    )
    rx1_tail_ms = source_u32(
        source, r"rx1_deadline\s*=\s*s_tx_end_ms\s*\+\s*rx1_at\s*\+\s*([0-9]+)u",
        "RX1 post-center tail",
    )
    rx2_tail_ms = source_u32(
        source, r"rx2_deadline\s*=\s*s_tx_end_ms\s*\+\s*rx2_at\s*\+\s*([0-9]+)u",
        "RX2 post-center tail",
    )
    rx2_spacing_ms = source_u32(
        source, r"rx2_at\s*=\s*rx1_at\s*\+\s*([0-9]+)u",
        "RX1-to-RX2 spacing",
    )
    full_cadence_s = source_u32(
        config, r"#define SLEEP_INTERVAL_FULL_SEC\s+([0-9]+)",
        "FULL cadence",
    )
    reduced_cadence_s = source_u32(
        config, r"#define SLEEP_INTERVAL_REDUCED_SEC\s+([0-9]+)",
        "REDUCED cadence",
    )

    helper_start = source.index("static void radio_idle_until_interrupt")
    helper_end = source.index("/* A bounded asynchronous join window", helper_start)
    helper_source = source[helper_start:helper_end]
    join_start = source.index("static size_t join_rx_window", helper_end)
    join_end = source.index("/* ========== Uplink MIC", join_start)
    join_source = source[join_start:join_end]
    class_a_start = source.index("/* ========== Class-A downlink", join_end)
    class_a_end = source.index(
        "/* ========== Runtime region switching", class_a_start
    )
    class_a_source = source[class_a_start:class_a_end]

    require("__WFI();" in helper_source, "Class-A wait no longer uses CPU sleep")
    require(
        "SCB_SCR_SLEEPDEEP_Msk" in helper_source,
        "Class-A WFI no longer explicitly selects shallow sleep",
    )
    require(
        "power_manager_freefall_pending()" in helper_source,
        "shared RF wait no longer yields to recovery/freefall",
    )
    require(
        "radio_wait_until(txEnd, 4750u)" in join_source
        and "radio_wait_until(txEnd, 5750u)" in join_source,
        "OTAA pre-window wait no longer uses the shared WFI path",
    )
    require(
        "mission_aborted" in join_source
        and "power_manager_freefall_pending()" in join_source,
        "OTAA receive no longer yields to recovery/freefall",
    )
    require(
        "delay(2)" not in join_source,
        "OTAA receive path regressed to the STM32duino busy wait",
    )
    require(
        "mission_aborted" in class_a_source
        and "power_manager_freefall_pending()" in class_a_source,
        "Class-A receive no longer yields to recovery/freefall",
    )
    require(
        "delay(2)" not in class_a_source,
        "Class-A receive path regressed to the STM32duino busy wait",
    )

    rx_on_ms = 2 * preopen_ms + rx1_tail_ms + rx2_tail_ms
    awake_span_ms = (
        default_rx_delay_s * 1000 + rx2_spacing_ms + rx2_tail_ms
    )
    non_rx_wait_ms = awake_span_ms - rx_on_ms
    require(rx_on_ms > 0 and non_rx_wait_ms >= 0, "invalid window geometry")

    rx_only_j = rail_energy_j(RAK3172_RX_TYP_A, rx_on_ms)
    former_busy_wait_j = rail_energy_j(MCU_ACTIVE_SCREEN_A, non_rx_wait_ms)
    prior_one_second_rx_j = rail_energy_j(RAK3172_RX_TYP_A, 1000)
    minimum_cap_window_j = (
        0.5
        * MIN_CAPACITANCE_F
        * (SCREEN_CEILING_V**2 - HISTORICAL_REPORTED_PLATEAU_V**2)
    )

    def cadence_row(cadence_s: int) -> dict[str, float]:
        cycles = 86_400.0 / cadence_s
        return {
            "successful_primary_cycles_per_day": cycles,
            "radio_rx_typical_j_per_day": rx_only_j * cycles,
            "former_busy_wait_screen_j_per_day": former_busy_wait_j * cycles,
            "former_combined_screen_j_per_day": (
                rx_only_j + former_busy_wait_j
            ) * cycles,
        }

    return {
        "status": "PARTIAL_WFI_REPAIRED_EXACT_CURRENT_HIL_REQUIRED",
        "passed": False,
        "scope": (
            "source-bound timing and current screen; not measured current, "
            "converter efficiency, or fitted-supercap endurance"
        ),
        "source_contract": {
            "ttn_assigned_rx_delay_default_s": default_rx_delay_s,
            "preopen_ms_per_window": preopen_ms,
            "rx1_post_center_tail_ms": rx1_tail_ms,
            "rx2_post_center_tail_ms": rx2_tail_ms,
            "rx1_to_rx2_spacing_ms": rx2_spacing_ms,
            "empty_rx_on_ms_per_primary": rx_on_ms,
            "tx_end_to_empty_rx2_close_ms": awake_span_ms,
            "non_rx_wait_ms_per_primary": non_rx_wait_ms,
            "cpu_wait_uses_wfi": True,
            "wfi_explicitly_clears_sleepdeep": True,
            "freefall_preempts_wait": True,
            "otaa_wait_and_rx_use_wfi": True,
            "otaa_freefall_preempts_wait_and_rx": True,
        },
        "screen_inputs": {
            "rak3172_rx_typical_a": RAK3172_RX_TYP_A,
            "former_mcu_active_screen_a": MCU_ACTIVE_SCREEN_A,
            "rail_v": V_RAIL,
            "converter_efficiency": CONVERTER_EFFICIENCY,
            "minimum_capacitance_f": MIN_CAPACITANCE_F,
            "screen_ceiling_v": SCREEN_CEILING_V,
            "historical_reported_plateau_v_not_bor": (
                HISTORICAL_REPORTED_PLATEAU_V
            ),
        },
        "energy_screen": {
            "prior_documented_one_second_rx_j_per_cycle": prior_one_second_rx_j,
            "actual_empty_radio_rx_typical_j_per_cycle": rx_only_j,
            "former_five_second_busy_wait_screen_j_per_cycle": former_busy_wait_j,
            "former_combined_screen_j_per_cycle": rx_only_j + former_busy_wait_j,
            "minimum_cap_energy_window_j": minimum_cap_window_j,
            "full_tier": cadence_row(full_cadence_s),
            "reduced_tier": cadence_row(reduced_cadence_s),
        },
        "interpretation": (
            "The previous command-channel model counted at most one second of "
            "RX and omitted the network-assigned five-second pre-window wait. "
            "STM32duino delay() busy-spins because yield() is empty, making the "
            "old implementation a material daily load; the same defect also "
            "affected every OTAA exchange. The repaired source uses WFI while "
            "preserving SysTick/radio/EXTI clocks and aborts on freefall in "
            "both joined Class-A and OTAA windows. A strong application yield "
            "hook also prevents remaining framework delays from busy-spinning, "
            "but these command paths retain explicit deadline/abort helpers. "
            "Exact WFI and RX current remain unmeasured. The "
            "radio-only 1.74-second receive cost also exceeds the old one-second "
            "model and cannot be optimized away without reducing command "
            "reliability."
        ),
        "required_hil": (
            "After the soak and exact-candidate flash, use PPK2 phase capture "
            "to measure TX-end through empty RX2 close, require the 4.75 s "
            "pre-window WFI floor, both RX plateaus, correct RX1/RX2 timing, "
            "and immediate INT1/freefall preemption. Repeat at FULL and REDUCED "
            "rails with the final supercapacitor."
        ),
    }


def main() -> None:
    print(json.dumps(build_audit(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
