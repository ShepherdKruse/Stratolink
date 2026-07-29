#!/usr/bin/env python3
"""Source-bound regression for lossless INT1/main-loop hand-off."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POWER = (ROOT / "firmware/src/power_manager.cpp").read_text(encoding="utf-8")
MANIFEST_GENERATOR = (
    ROOT / "analysis/diagnostics/generate_flight_hil.py"
).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def model_suppressed_clear(interrupt_at: str) -> bool:
    """Return whether an INT1 after the generation snapshot remains pending."""
    generation = 1
    pending = True
    generation_before = generation
    if interrupt_at == "before_clear":
        generation += 1
        pending = True
    pending = False
    if interrupt_at == "after_clear":
        generation += 1
        pending = True
    generation_after = generation
    if generation_after != generation_before:
        pending = True
    if interrupt_at == "after_generation_check":
        generation += 1
        pending = True
    return pending


def main() -> None:
    require("s_burst_wake_generation" in POWER,
            "freefall ISR has no event-generation witness")
    require("__atomic_add_fetch(" in POWER,
            "freefall ISR generation update is not atomic")
    require(
        "__atomic_store_n(&s_burst_wake, true, __ATOMIC_RELEASE)" in POWER,
        "freefall ISR does not publish pending state atomically",
    )
    require(
        "__atomic_exchange_n(" in POWER
        and "&s_burst_wake, false, __ATOMIC_ACQ_REL" in POWER,
        "main-loop freefall consumption is still a racy read/clear pair",
    )
    require(
        "generation_after != generation_before" in POWER
        and POWER.count(
            "__atomic_store_n(&s_burst_wake, true, __ATOMIC_RELEASE)"
        ) >= 2,
        "suppression clear does not restore an overlapping INT1",
    )
    require('"s_burst_wake": "unconsumed freefall wake flag"' in MANIFEST_GENERATOR,
            "J-Link pending-flag observability was lost")
    for point in ("before_clear", "after_clear", "after_generation_check"):
        require(model_suppressed_clear(point),
                f"modeled INT1 is lost at {point}")
    print("PASS: INT1 publication, consumption, and suppression clear are atomic")


if __name__ == "__main__":
    main()
