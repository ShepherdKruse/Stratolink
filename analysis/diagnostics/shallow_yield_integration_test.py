#!/usr/bin/env python3
"""Bind all framework delay() calls to the application's shallow-WFI yield."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
YIELD = (ROOT / "firmware/src/shallow_yield.cpp").read_text(encoding="utf-8")
PIO = (ROOT / "firmware/platformio.ini").read_text(encoding="utf-8")
GPS = (ROOT / "firmware/src/gps_ublox.cpp").read_text(encoding="utf-8")
POWER = (ROOT / "firmware/src/power_manager.cpp").read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    """Return a C/C++ function including its balanced outer braces."""
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start : pos + 1]
    raise AssertionError(f"unterminated function: {signature}")

assert 'extern "C" void yield(void)' in YIELD
assert "SCB->SCR &= ~SCB_SCR_SLEEPDEEP_Msk;" in YIELD
assert "__DSB();" in YIELD and "__WFI();" in YIELD and "__ISB();" in YIELD
assert "delay(100);" in GPS, "GNSS polling geometry changed; re-audit the hook"
assert "delay(durationMs);" in POWER, "non-STM32 fallback contract changed"

# yield() needs an enabled interrupt source to return. Prove that flight source
# has no global interrupt-disable primitive and that the sole SysTick suspension
# belongs to STOP1 itself, with no delay/yield call before tick restoration.
flight_sources = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "firmware/src").glob("*.cpp"))
    if not path.name.startswith("main_") or path.name == "main.cpp"
)
for forbidden in (
    "__disable_irq(",
    "noInterrupts(",
    "taskENTER_CRITICAL(",
    "portENTER_CRITICAL(",
):
    assert forbidden not in flight_sources, (
        f"flight source now uses {forbidden}; audit every delay/yield call in "
        "that critical section before accepting shallow WFI"
    )

stop1 = function_body(POWER, "static void enter_stop1_for_ms")
assert POWER.count("HAL_SuspendTick();") == 1
assert stop1.count("HAL_SuspendTick();") == 1
assert stop1.count("HAL_ResumeTick();") == 1
suspend = stop1.index("HAL_SuspendTick();")
resume = stop1.index("HAL_ResumeTick();")
assert suspend < stop1.index("HAL_PWR_EnterSTOPMode", suspend) < resume
tick_off = stop1[suspend:resume]
assert not re.search(r"\b(?:delay|yield)\s*\(", tick_off), (
    "delay/yield entered while SysTick is suspended; shallow WFI cannot make "
    "forward progress"
)

# The flight environment includes every source except explicitly named
# diagnostic mains; a later filter that excludes shallow_yield.cpp would
# silently restore the framework's empty weak hook.
flight_filter = PIO.split("[env:stratolink]", 1)[1].split(
    "[env:stratolink_soak]", 1
)[0]
assert "build_src_filter = +<*>" in flight_filter
assert "-<shallow_yield.cpp>" not in flight_filter

print("PASS: every flight delay yields through explicit shallow WFI")
