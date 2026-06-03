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
 * reboots the chip and recovers.  On STM32WL the FLASH IWDG_STOP option
 * bit defaults to 1, so the counter keeps running in Stop mode; a multi-
 * minute sleep would otherwise trip it, so power_manager_sleep_ms() chunks
 * the sleep and refreshes the IWDG between chunks. */
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
 * chip (FLASH IWDG_STOP option bit = 1 by default, counter runs in Stop),
 * so any single sleep interval longer than ~32 s would let the watchdog fire and
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

/* ========== LoRaWAN session persistence (TAMP backup registers) ==========
 *
 * STM32WL has 32× 32-bit TAMP_BKPxR (BKP0R..BKP31R) — 128 bytes that
 * persist across reset, STOP, and standby while VDD is present.  We use
 * the first 15 of them: magic + version + session payload (13 words).
 *
 * The "BREN" retention bit that some larger STM32 families need to keep
 * BKPSRAM alive across standby does NOT exist on STM32WL — these regs
 * are retained automatically.  Access is via direct register reads;
 * the RTC clock domain must be enabled (done by power_manager_init()
 * via STM32RTC::begin()) for TAMP writes to succeed. */

#define STRATO_SESSION_MAGIC   0x53545241u   /* "STRA" big-endian */
#define STRATO_SESSION_VER     1u
#define SESSION_WORD_COUNT     (sizeof(lorawan_session_t) / sizeof(uint32_t))

#if defined(ARDUINO_ARCH_STM32)
static volatile uint32_t* tamp_bkp_word(int idx) {
    return &(&TAMP->BKP0R)[idx];
}

/* Unlock the backup domain so the CPU can touch RTC/TAMP backup
 * registers.  Idempotent — safe to call before STM32RTC::begin()
 * (handles cold-boot session load that runs before
 * power_manager_init()) or after.
 *
 * Two bits matter on STM32WL:
 *   RCC_APB1ENR1.RTCAPBEN — gates the APB clock to the RTC + TAMP
 *     register interface.  Without it, BKPxR reads return garbage
 *     and writes silently drop.  Hardware-verified bug: prior to
 *     adding this, session save/load was returning false on the
 *     bench because TAMP was un-clocked when power_manager_init
 *     hadn't yet run.  PWR is always clocked on STM32WL (no
 *     APB1ENR1_PWREN bit) so PWR access works even without this.
 *   PWR_CR1.DBP — disables backup-domain write protection.
 *
 * The readback after the RCC write forces the bus to retire the
 * clock-enable before we touch any TAMP register (ARM Cortex-M
 * peripheral clock-enable barrier). */
static void enable_backup_access(void) {
    SET_BIT(RCC->APB1ENR1, RCC_APB1ENR1_RTCAPBEN);
    (void)READ_BIT(RCC->APB1ENR1, RCC_APB1ENR1_RTCAPBEN);
    SET_BIT(PWR->CR1, PWR_CR1_DBP);
}
#endif

bool power_manager_load_session(lorawan_session_t* s) {
    if (!s) return false;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    uint32_t* dst = (uint32_t*)s;
    for (size_t i = 0; i < SESSION_WORD_COUNT; i++) dst[i] = *tamp_bkp_word(i);
    return s->magic == STRATO_SESSION_MAGIC && s->version == STRATO_SESSION_VER;
#else
    (void)s; return false;
#endif
}

void power_manager_save_session(const lorawan_session_t* s_in) {
    if (!s_in) return;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    /* Copy + stamp magic/version so the caller doesn't have to. */
    lorawan_session_t s = *s_in;
    s.magic   = STRATO_SESSION_MAGIC;
    s.version = STRATO_SESSION_VER;
    const uint32_t* src = (const uint32_t*)&s;
    for (size_t i = 0; i < SESSION_WORD_COUNT; i++) *tamp_bkp_word(i) = src[i];
#else
    (void)s_in;
#endif
}

void power_manager_clear_session(void) {
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    *tamp_bkp_word(0) = 0;  /* zero the magic — load_session returns false */
#endif
}
