#!/usr/bin/env python3
"""Bind the pure STOP1 short-progress policy to flight sleep implementation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POWER = (ROOT / "firmware/src/power_manager.cpp").read_text(encoding="utf-8")
POLICY = (ROOT / "firmware/include/stop1_progress_policy.h").read_text(
    encoding="utf-8"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "#include \"stop1_progress_policy.h\"" in POWER,
    "flight power manager no longer includes the reviewed STOP1 policy",
)
require(
    "stop1_progress_observe(&progress, used, chunk)" in POWER,
    "measured STOP1 elapsed time no longer drives the progress policy",
)
require(
    "action == STOP1_PROGRESS_MASK_INT1" in POWER
    and "NVIC_DisableIRQ(EXTI9_5_IRQn);" in POWER,
    "zero-progress INT1 masking is no longer wired",
)
require(
    "action == STOP1_PROGRESS_SHALLOW_FALLBACK" in POWER
    and "shallow_fallback = true;" in POWER,
    "post-mask zero-progress streak no longer exits STOP1 retry",
)
require(
    "while (shallow_fallback && remaining > 0)" in POWER
    and "HAL_IWDG_Refresh(&s_iwdg);" in POWER
    and "power_manager_freefall_pending()" in POWER
    and "delay(slice);" in POWER,
    "watchdog/freefall-bounded shallow fallback changed",
)
require(
    "short_progress_wakes < UINT8_MAX" in POLICY,
    "short-progress counter can wrap and reopen the live-lock",
)
require(
    "STOP1_MIN_MEANINGFUL_PROGRESS_MS = 1000u" in POLICY
    and "STOP1_MASK_INT1_AFTER_SHORT_WAKES = 8u" in POLICY
    and "STOP1_SHALLOW_FALLBACK_AFTER_SHORT_WAKES = 16u" in POLICY,
    "reviewed STOP1 fault thresholds changed",
)

print("PASS: STOP1 short-progress live-lock has a bounded flight fallback")
