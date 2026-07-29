#!/usr/bin/env python3
"""Bind every flight peripheral to an explicit pre-STOP1 power-state contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
RADIO = (ROOT / "firmware/src/lorawan.cpp").read_text(encoding="utf-8")
GNSS = (ROOT / "firmware/src/gps_ublox.cpp").read_text(encoding="utf-8")
MIC = (ROOT / "firmware/src/mic_acoustic.cpp").read_text(encoding="utf-8")
LTR390 = (ROOT / "firmware/src/sensor_ltr390.cpp").read_text(encoding="utf-8")
TMP117 = (ROOT / "firmware/src/sensor_tmp117.cpp").read_text(encoding="utf-8")
MS5611 = (ROOT / "firmware/src/sensor_ms5611.cpp").read_text(encoding="utf-8")
LIS2DH12 = (ROOT / "firmware/src/sensor_lis2dh12.cpp").read_text(encoding="utf-8")
POWER = (ROOT / "firmware/src/power_manager.cpp").read_text(encoding="utf-8")
POWER_ADC = (ROOT / "firmware/src/power_adc.cpp").read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for pos in range(brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : pos]
    raise AssertionError(f"unterminated function {signature}")


def require_radio_before_every_mcu_sleep() -> None:
    sleep_calls = list(re.finditer(r"\bpower_manager_sleep_ms\s*\(", MAIN))
    assert len(sleep_calls) == 3, "review every new MCU sleep call explicitly"
    previous_sleep = 0
    for call in sleep_calls:
        prefix = MAIN[previous_sleep : call.start()]
        assert "lorawan_sleep();" in prefix, (
            "MCU sleep can begin without a preceding confirmed radio sleep"
        )
        previous_sleep = call.end()


def require_top_level_sleep_path_containment() -> None:
    """Pin the three scheduler paths which can actually start a timed sleep."""
    loop = function_body(MAIN, "void loop()")
    sleep_calls = [match.start() for match in re.finditer(
        r"\bpower_manager_sleep_ms\s*\(", loop
    )]
    assert len(sleep_calls) == 3, "review every new timed-sleep path"

    spurious_start = loop.index("if (spurious_freefall_wake)")
    optical_start = loop.index(
        "if (s_optical_quiescence_fault && !freefall_wake && !burst_mode)"
    )
    final_gps_start = loop.rindex("if (!gps_attempted_this_cycle)")
    final_radio_sleep = loop.rindex("lorawan_sleep();")

    spurious = loop[spurious_start:sleep_calls[0]]
    assert "bool gps_quiesced = gps_ublox_sleep();" in spurious
    assert "lorawan_sleep();" in spurious
    assert "persist_region_lease_if_trusted();" in spurious
    assert "GPS_BACKUP_RETRY_SLEEP_MS" in spurious

    optical = loop[optical_start:sleep_calls[1]]
    assert "bool gps_quiet = gps_ublox_sleep();" in optical
    assert "lorawan_sleep();" in optical
    assert "persist_region_lease_if_trusted();" in optical
    assert "GPS_BACKUP_RETRY_SLEEP_MS" in optical

    normal = loop[final_gps_start:sleep_calls[2]]
    assert "gps_quiesced = gps_ublox_sleep();" in normal
    assert "if (!gps_quiesced && sleep_ms >" in normal
    assert "sleep_ms = (uint32_t)GPS_BACKUP_RETRY_SLEEP_MS;" in normal
    assert "persist_region_lease_if_trusted();" not in normal
    # Normal-cycle age is charged before this slice; prohibit a second commit
    # after optional windows from disguising a future control-flow change.
    assert final_gps_start < final_radio_sleep < sleep_calls[2]

    # ADC shutdown is centralized inside the called sleep primitive, before
    # its STOP1 loop; the top-level paths must not bypass that primitive.
    sleep_primitive = function_body(
        POWER, "void power_manager_sleep_ms(uint32_t durationMs)"
    )
    assert sleep_primitive.index("if (!power_adc_quiesce())") < (
        sleep_primitive.index("while (remaining > 0)")
    )


def require_microphone_clock_off_on_every_exit() -> None:
    abort = function_body(MIC, "static bool mic_capture_abort(void)")
    detect = function_body(MIC, "bool mic_acoustic_detect(")
    assert "SPI1->CR1 &= ~SPI_CR1_SPE;" in abort
    assert detect.count("return mic_capture_abort();") == 3
    assert detect.count("SPI1->CR1 |= SPI_CR1_SPE;") == 1
    assert detect.count("SPI1->CR1 &= ~SPI_CR1_SPE;") == 1
    assert detect.rfind("SPI1->CR1 &= ~SPI_CR1_SPE;") < detect.rfind("return true;")


def require_gnss_and_optical_containment() -> None:
    gps_sleep = function_body(GNSS, "bool gps_ublox_sleep(void)")
    assert "gps_backup_decide(" in gps_sleep
    assert "gps_sleep_confirmed = true;" in gps_sleep
    assert "s_gps_diag.backup_terminal_failures++;" in gps_sleep
    assert "return false;" in gps_sleep

    optical_sleep = function_body(LTR390, "bool sensor_ltr390_quiesce(void)")
    assert optical_sleep.count("if (standby_readback())") == 1
    assert "reset_to_standby_readback()" in optical_sleep
    assert "ltr390_active_possible = false;" in optical_sleep
    assert "s_ltr390_quiesce_failures" in optical_sleep

    assert "if (!gps_quiesced || s_optical_quiescence_fault)" in MAIN
    assert MAIN.count("gps_quiesced && !s_optical_quiescence_fault") >= 2
    assert "SENSOR_QUIESCE_RETRY_SLEEP_MS" in MAIN
    assert "GPS_BACKUP_RETRY_SLEEP_MS" in MAIN


def require_other_sensor_power_contracts() -> None:
    # TMP117 MOD=11 is one-shot/shutdown; continuous conversion is never used.
    assert "#define TMP117_ONE_SHOT    (3u << 10)" in TMP117
    assert TMP117.count("TMP117_ONE_SHOT >> 8") == 1
    assert TMP117.count("TMP117_ONE_SHOT & 0xFF") == 1

    # MS5611 runs only explicit, finite D1/D2 conversions followed by ADC reads.
    adc = function_body(MS5611, "static bool cmd_adc(")
    assert "Wire.write(cmd);" in adc
    assert "MS5611_CMD_ADC_READ" in adc
    assert "MS5611_CONV_DELAY_MS" in adc

    # LIS2DH12 is intentionally left at 100 Hz low-power for INT1 freefall wake.
    enable = function_body(
        LIS2DH12, "bool sensor_lis2dh12_enable_freefall_int1(void)"
    )
    attach = function_body(POWER, "void power_manager_attach_freefall_wakeup(void)")
    assert "LIS2DH12_CTRL1_ODR_100HZ | LIS2DH12_CTRL1_LPEN" in enable
    assert "LIS2DH12_CTRL3_I1_IA1" in enable
    assert "LowPower.attachInterruptWakeup" in attach
    assert "RISING, DEEP_SLEEP_MODE" in attach


def require_radio_failure_containment() -> None:
    sleep = function_body(RADIO, "void lorawan_sleep(void)")
    assert "radio->sleep(true)" in sleep
    assert "radio_ready = false;" in sleep
    assert "!lorawan_init()" in sleep
    assert "NVIC_SystemReset();" in sleep


def require_adc_stop1_quiescence() -> None:
    quiesce = function_body(POWER_ADC, "bool power_adc_quiesce(void)")
    sleep = function_body(POWER, "void power_manager_sleep_ms(uint32_t durationMs)")

    assert "HAL_ADC_Stop(&s_hadc)" in quiesce
    assert "CLEAR_BIT(ADC_COMMON->CCR, ADC_CCR_VREFEN)" in quiesce
    assert "HAL_ADCEx_DisableVoltageRegulator(&s_hadc)" in quiesce
    assert "ADC_CR_ADEN | ADC_CR_ADVREGEN" in quiesce
    assert quiesce.count("ADC_COMMON->CCR & ADC_CCR_VREFEN") == 2
    assert "__HAL_RCC_ADC_FORCE_RESET();" in quiesce
    assert "__HAL_RCC_ADC_RELEASE_RESET();" in quiesce
    assert "__HAL_RCC_ADC_CLK_SLEEP_DISABLE();" in quiesce
    assert "__HAL_RCC_ADC_CLK_DISABLE();" in quiesce
    assert "adc_initialized = false;" in quiesce

    quiesce_call = sleep.index("if (!power_adc_quiesce())")
    stop_loop = sleep.index("while (remaining > 0)")
    assert quiesce_call < stop_loop
    fault = sleep[quiesce_call:stop_loop]
    assert "NVIC_SystemReset();" in fault
    assert "return;" in fault


def main() -> None:
    require_radio_before_every_mcu_sleep()
    require_top_level_sleep_path_containment()
    require_microphone_clock_off_on_every_exit()
    require_gnss_and_optical_containment()
    require_other_sensor_power_contracts()
    require_radio_failure_containment()
    require_adc_stop1_quiescence()
    print(
        "PASS: every flight peripheral has an explicit pre-STOP1 power-state "
        "contract; exact-image current HIL remains required"
    )


if __name__ == "__main__":
    main()
