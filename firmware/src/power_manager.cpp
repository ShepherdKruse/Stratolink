#include "power_manager.h"
#include "config.h"
#include "stratolink_pins.h"
#include "power_adc.h"
#include <Arduino.h>

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
#include <STM32LowPower.h>
#include <STM32RTC.h>
#endif

static bool inited = false;
static volatile bool s_burst_wake = false;

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
static void freefall_wake_callback(void) {
    s_burst_wake = true;
}

/* IWDG handle.  Independent watchdog runs from LSI (32 kHz typ.).
 * Max timeout = 4095 reload / (32 kHz / 256 prescaler) = 32.7 s.
 * We refresh once per loop iteration, so any run-mode hang > 32 s
 * reboots the chip and recovers.  IWDG is FROZEN in STOP modes by
 * the FZ_STOP1.IWGEN_STOP option byte (default 1 on STM32WL), so
 * it doesn't false-fire during multi-minute sleep cycles. */
static IWDG_HandleTypeDef s_iwdg;
#endif

void power_manager_init(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    /* RAK3172 module has no LSE crystal — only LSI feeds the RTC and
     * the IWDG.  STM32RTC defaults to LSI_CLOCK in its constructor;
     * we set it explicitly + begin() to bring the RTC up before any
     * sleep entry (STM32duino's library configures it lazily on the
     * first deepSleep call otherwise). */
    STM32RTC& rtc = STM32RTC::getInstance();
    rtc.setClockSource(STM32RTC::LSI_CLOCK);
    rtc.begin();
    LowPower.begin();

    /* Independent watchdog: 32.7 s timeout, refreshed at the top of each
     * loop iteration in main.cpp.  Recovers from any run-mode firmware
     * hang (lockup in a peripheral driver, deadlock, etc.) within ~33 s. */
    s_iwdg.Instance       = IWDG;
    s_iwdg.Init.Prescaler = IWDG_PRESCALER_256;
    s_iwdg.Init.Reload    = 0x0FFF;            /* max */
    s_iwdg.Init.Window    = IWDG_WINDOW_DISABLE;
    HAL_IWDG_Init(&s_iwdg);

    inited = true;
#endif
}

void power_manager_attach_freefall_wakeup(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        pinMode(PIN_ACCEL_INT1, INPUT_PULLUP);
        LowPower.attachInterruptWakeup(PIN_ACCEL_INT1, freefall_wake_callback,
                                       RISING, DEEP_SLEEP_MODE);
    }
#endif
}

bool power_manager_did_wake_from_freefall(void) {
    bool v = s_burst_wake;
    s_burst_wake = false;
    return v;
}

void power_manager_kick_watchdog(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        HAL_IWDG_Refresh(&s_iwdg);
    }
#endif
}

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
/* Single STOP1 entry for up to ~28 s.  IWDG keeps running in STOP on this
 * chip (FZ_STOP1.IWGEN_STOP=0 by default option byte), so any single
 * sleep interval longer than ~32 s would let the watchdog fire and
 * reboot the MCU mid-sleep.  Caller wraps this with chunking +
 * HAL_IWDG_Refresh between chunks.
 *
 * STOP1 (LP regulator on, Vcore held) — the right balance for the
 * RAK3172 module: STOP2 caused PINRSTF every cycle (1.2 V Vcore droop
 * during regulator-off transition reads as a pin reset).
 *
 * Wake-up plumbing on STM32WL:
 *   - HAL_RTC_SetAlarm_IT (via STM32RTC::setAlarmEpoch) configures the
 *     alarm, sets ALRAE+ALRAIE, unmasks EXTI line 17, enables NVIC.
 *   - HAL_PWREx_EnableInternalWakeUpLine sets PWR.CR3.EIWUL so the
 *     internal RTC wake-up line can exit STOP.  STM32duino's library
 *     skips this on STM32WL (PWR_WAKEUP_RTC undefined for WL).
 *   - PWR_SCR_CWUF clears stale wake-up flags so STOP entry doesn't
 *     immediately exit on a left-over event. */
static void enter_stop1_for_ms(uint32_t chunk_ms) {
    STM32RTC& rtc = STM32RTC::getInstance();
    time_t alarm_at = rtc.getEpoch() + (chunk_ms / 1000);
    rtc.setAlarmEpoch(alarm_at, STM32RTC::MATCH_HHMMSS);

    HAL_PWREx_EnableInternalWakeUpLine();
    WRITE_REG(PWR->SCR, PWR_SCR_CWUF);
#if defined(PWR_EXTSCR_C1CSSF)
    WRITE_REG(PWR->EXTSCR, PWR_EXTSCR_C1CSSF);
#endif

    /* Mask noisy UART RX IRQs.  USART1 is GPS at 9600 baud (RXNE every
     * ~1 ms while GPS is talking).  LPUART1 is Serial debug; PA_3 is
     * not broken out so the input floats and can pick up EMI. */
    NVIC_DisableIRQ(USART1_IRQn);
    NVIC_DisableIRQ(LPUART1_IRQn);
    NVIC_ClearPendingIRQ(RTC_Alarm_IRQn);

    HAL_SuspendTick();
    HAL_PWR_EnterSTOPMode(PWR_LOWPOWERREGULATOR_ON, PWR_STOPENTRY_WFI);
    SystemClock_Config();
    HAL_ResumeTick();

    NVIC_EnableIRQ(USART1_IRQn);
    NVIC_EnableIRQ(LPUART1_IRQn);
    HAL_PWREx_DisableInternalWakeUpLine();
}
#endif

void power_manager_sleep_ms(uint32_t durationMs) {
    if (durationMs == 0) return;
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        /* IWDG runs in STOP1 on this chip's default option bytes (max
         * ~32.7 s timeout).  Split long sleeps into < 32 s chunks and
         * refresh the watchdog between each so it doesn't false-fire
         * mid-sleep — gives multi-minute deepSleep targets while keeping
         * the watchdog protection that recovers from run-mode hangs. */
        const uint32_t MAX_CHUNK_MS = 28000;
        uint32_t remaining = durationMs;
        while (remaining > 0) {
            HAL_IWDG_Refresh(&s_iwdg);
            uint32_t chunk = remaining > MAX_CHUNK_MS ? MAX_CHUNK_MS : remaining;
            enter_stop1_for_ms(chunk);
            if (s_burst_wake) break;        /* freefall: bail out early */
            remaining -= chunk;
        }
        HAL_IWDG_Refresh(&s_iwdg);
        return;
    }
#endif
    delay(durationMs);
}

bool power_manager_is_low_battery(void) {
    return power_adc_get_tier() == POWER_TIER_CRITICAL;
}
