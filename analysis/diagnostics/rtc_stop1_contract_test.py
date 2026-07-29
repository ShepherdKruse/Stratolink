#!/usr/bin/env python3
"""Prove the pinned STM32 RTC alarm contract used by flight STOP1 sleep."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"
PLATFORMIO = FIRMWARE / "platformio.ini"
POWER_MANAGER = FIRMWARE / "src" / "power_manager.cpp"
RTC_DIR = (
    FIRMWARE
    / ".pio"
    / "libdeps"
    / "stratolink"
    / "STM32duino RTC"
    / "src"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def numeric_constant(source: str, name: str) -> int:
    match = re.search(
        rf"\b{name}\s*=\s*(0[xX][0-9A-Fa-f]+|[0-9]+)u?\s*;",
        source,
    )
    require(match is not None, f"missing numeric constant {name}")
    return int(match.group(1), 0)


def main() -> None:
    platformio = PLATFORMIO.read_text()
    power = POWER_MANAGER.read_text()

    require(
        "stm32duino/STM32duino RTC@1.9.0" in platformio,
        "flight RTC dependency is not pinned to reviewed 1.9.0",
    )
    require(RTC_DIR.is_dir(), "build env missing: run PlatformIO flight build first")

    rtc_header = (RTC_DIR / "STM32RTC.h").read_text()
    rtc_cpp = (RTC_DIR / "STM32RTC.cpp").read_text()
    rtc_c = (RTC_DIR / "rtc.c").read_text()

    require(
        "MATCH_HHMMSS       = SS_MSK | MM_MSK | HH_MSK" in rtc_header,
        "MATCH_HHMMSS no longer matches exactly hour/minute/second",
    )
    require(
        "MATCH_DHHMMSS      = SS_MSK | MM_MSK | HH_MSK | D_MSK" in rtc_header,
        "date-mask distinction changed in the pinned RTC library",
    )
    require(
        "struct tm *tmp = gmtime(&t);" in rtc_cpp
        and "setAlarmHours(tmp->tm_hour, name);" in rtc_cpp
        and "setAlarmMinutes(tmp->tm_min, name);" in rtc_cpp
        and "setAlarmSeconds(tmp->tm_sec, name);" in rtc_cpp
        and "enableAlarm(match, name);" in rtc_cpp,
        "setAlarmEpoch no longer derives and enables the requested time fields",
    )
    require(
        "LL_RTC_IsActiveFlag_INITS" in rtc_c
        and "RTC_SetDate(1, 1, 1, 6);" in rtc_c,
        "RTC initialization/retention contract changed",
    )
    require(
        "rtc.setAlarmEpoch(alarm_at, STM32RTC::MATCH_HHMMSS);" in power,
        "flight STOP1 no longer uses the reviewed daily HH:MM:SS alarm",
    )

    chunk_ms = numeric_constant(power, "MAX_STOP1_CHUNK_MS")
    rtc_hz = numeric_constant(power, "RTC_CONFIGURED_LSI_HZ")
    reload_value = numeric_constant(power, "IWDG_RELOAD_VALUE")
    prescaler = numeric_constant(power, "IWDG_PRESCALER_DIV")

    require(chunk_ms == 28_000, "reviewed STOP1 chunk changed")
    require(chunk_ms % 1000 == 0, "RTC alarm chunk must be whole seconds")
    require(chunk_ms < 86_400_000, "daily date-masked alarm became ambiguous")
    require(
        (chunk_ms // 1000) * rtc_hz < (reload_value + 1) * prescaler,
        "STOP1 alarm no longer expires before the shared-LSI watchdog",
    )

    # getEpoch() supplies whole seconds and setAlarmEpoch() programs subsecond
    # zero. Exhaust every possible second-of-day and representative subsecond
    # phases. The next daily HH:MM:SS match must always be the intended one,
    # including 23:59:xx -> 00:00:xx.
    day_ms = 86_400_000
    for second_of_day in range(86_400):
        for sub_ms in (0, 1, 499, 999):
            now_ms = second_of_day * 1000 + sub_ms
            target_second = second_of_day + chunk_ms // 1000
            target_ms_of_day = (target_second % 86_400) * 1000
            delay_ms = (target_ms_of_day - now_ms) % day_ms
            expected = chunk_ms - sub_ms
            require(
                delay_ms == expected,
                "daily alarm selected the wrong occurrence at "
                f"{second_of_day=} {sub_ms=}: {delay_ms=} {expected=}",
            )

    print(
        "PASS: pinned RTC 1.9.0 HH:MM:SS alarm, all-day/midnight "
        "oracle, and shared-LSI watchdog margin"
    )


if __name__ == "__main__":
    main()
