#include "power_manager.h"
#include "command_sequence_store.h"
#include "config.h"
#include "stratolink_pins.h"
#include "power_adc.h"
#include "sensor_lis2dh12.h"
#include "b2b_id_store.h"
#include "stop1_progress_policy.h"
#include "region_manager.h"
#include "tamp_record.h"
#include <Arduino.h>

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
#include <STM32LowPower.h>
#include <STM32RTC.h>
#endif

static bool inited = false;
static volatile bool s_burst_wake = false;
static volatile uint32_t s_burst_wake_generation = 0;
static volatile bool s_ff_suppressed = false;  /* chatter latch: INT1 wakes don't abort sleep */

#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
static void freefall_wake_callback(void) {
    /* Publish a generation before the pending flag. The generation lets the
     * suppressed-noise path detect an INT1 arriving while it performs I2C and
     * restore pending state instead of erasing the newer edge. */
    (void)__atomic_add_fetch(
        &s_burst_wake_generation, 1u, __ATOMIC_RELAXED);
    __atomic_store_n(&s_burst_wake, true, __ATOMIC_RELEASE);
}

/* The RTC alarm and IWDG are both clocked from the same LSI on RAK3172.
 * STM32RTC divides its configured 32 kHz LSI_VALUE to 1 Hz, so a 28 s alarm
 * consumes 896,000 LSI cycles regardless of the oscillator's absolute error.
 * The IWDG has 4096 * 256 = 1,048,576 cycles.  Keeping the comparison in
 * oscillator cycles avoids relying on the LSI's wall-clock accuracy and
 * leaves 152,576 cycles (4.49 s even at the 34 kHz datasheet maximum).
 */
static constexpr uint32_t IWDG_RELOAD_VALUE = 0x0FFFu;
static constexpr uint32_t IWDG_PRESCALER_DIV = 256u;
static constexpr uint32_t IWDG_LSI_CYCLES =
    (IWDG_RELOAD_VALUE + 1u) * IWDG_PRESCALER_DIV;
static constexpr uint32_t RTC_CONFIGURED_LSI_HZ = 32000u;
#if defined(LSI_VALUE)
static_assert(RTC_CONFIGURED_LSI_HZ == LSI_VALUE,
              "STOP1 proof must track STM32RTC's configured LSI_VALUE");
#endif
static constexpr uint32_t MAX_STOP1_CHUNK_MS = 28000u;
static constexpr uint32_t MAX_STOP1_CHUNK_LSI_CYCLES =
    (MAX_STOP1_CHUNK_MS / 1000u) * RTC_CONFIGURED_LSI_HZ;
static_assert(MAX_STOP1_CHUNK_LSI_CYCLES < IWDG_LSI_CYCLES,
              "STOP1 chunk must expire before the independent watchdog");

/* IWDG handle.  Independent watchdog runs from LSI (32 kHz typ.).
 * Typical max timeout = 4096 / (32 kHz / 256 prescaler) = 32.768 s.
 * At the specified 34 kHz LSI maximum, the guaranteed wall-clock timeout is
 * 30.84 s (32.768 s typical). Any longer run-mode hang reboots the chip and
 * recovers. On STM32WL the FLASH IWDG_STOP option
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
    s_iwdg.Init.Reload    = IWDG_RELOAD_VALUE; /* max */
    s_iwdg.Init.Window    = IWDG_WINDOW_DISABLE;
    HAL_IWDG_Init(&s_iwdg);

    inited = true;
#endif
}

void power_manager_attach_freefall_wakeup(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        /* No pull: the LIS2DH12 INT1 pad is push-pull and idles LOW
         * (active-high), so a pull-up would fight the driven-low pad
         * and leak ~80 uA continuously, 10x the whole STOP1 floor. */
        pinMode(PIN_ACCEL_INT1, INPUT);
        LowPower.attachInterruptWakeup(PIN_ACCEL_INT1, freefall_wake_callback,
                                       RISING, DEEP_SLEEP_MODE);
    }
#endif
}

bool power_manager_did_wake_from_freefall(void) {
    /* A plain read followed by a plain clear can erase an ISR store between
     * those two instructions. Exchange linearizes consumption: an interrupt
     * after it leaves a new true value for the next cycle. */
    return __atomic_exchange_n(
        &s_burst_wake, false, __ATOMIC_ACQ_REL);
}

/* Non-consuming peek for long-running windows (GPS/relay/CTT) that must yield
 * to freefall promptly but must NOT eat a genuine flag; main.cpp's cycle-top
 * consume drives burst entry/cooldown accounting.
 *
 * The anti-chatter latch cannot blindly hide INT1: descent may begin while an
 * earlier noise streak has suppression armed. Confirm a suppressed event with
 * the accelerometer. ~1 g is cheap noise to swallow; persistent low-g is the
 * real recovery event, so clear suppression and expose it immediately. An I2C
 * error is also handed to main.cpp rather than being silently swallowed;
 * main treats unknown acceleration as recovery-worthy, while the six-cycle
 * burst cap bounds a persistent sensor fault. */
bool power_manager_freefall_pending(void) {
    uint32_t generation_before = __atomic_load_n(
        &s_burst_wake_generation, __ATOMIC_ACQUIRE);
    if (!__atomic_load_n(&s_burst_wake, __ATOMIC_ACQUIRE)) return false;
    if (!s_ff_suppressed) return true;
    bool cleared = false;
    if (sensor_lis2dh12_get_freefall_cleared(&cleared) && cleared) {
        __atomic_store_n(&s_burst_wake, false, __ATOMIC_RELEASE);
        uint32_t generation_after = __atomic_load_n(
            &s_burst_wake_generation, __ATOMIC_ACQUIRE);
        if (generation_after != generation_before) {
            /* An ISR overlapped the sensor transaction or the clear. Preserve
             * it for a fresh classification rather than converting it into a
             * false quiet result. */
            __atomic_store_n(&s_burst_wake, true, __ATOMIC_RELEASE);
        }
        return false;
    }
    s_ff_suppressed = false;
    return true;
}

/* Chatter latch: while suppressed, an INT1 wake no longer aborts sleep merely
 * because the edge arrived. The EXTI still wakes the MCU, then
 * power_manager_freefall_pending() cheaply checks acceleration: ~1 g clears
 * the noise flag and returns to STOP, while confirmed low-g overrides the
 * latch. main.cpp drives suppression from accel-confirmed spurious streaks. */
void power_manager_suppress_freefall_wake(bool on) {
    s_ff_suppressed = on;
}

void power_manager_kick_watchdog(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        HAL_IWDG_Refresh(&s_iwdg);
    }
#endif
}

uint32_t power_manager_monotonic_seconds(void) {
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        /* RTC is deliberately not synchronized to civil/GPS time. Its LSI
         * epoch is still monotonic while VDD is retained and, unlike millis(),
         * continues through STOP1. Unsigned deltas are the only contract. */
        return (uint32_t)STM32RTC::getInstance().getEpoch();
    }
#endif
    return millis() / 1000u;
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
    const bool usart1_irq_was_enabled = NVIC_GetEnableIRQ(USART1_IRQn) != 0u;
    const bool lpuart1_irq_was_enabled = NVIC_GetEnableIRQ(LPUART1_IRQn) != 0u;
    NVIC_DisableIRQ(USART1_IRQn);
    NVIC_DisableIRQ(LPUART1_IRQn);
    NVIC_ClearPendingIRQ(RTC_Alarm_IRQn);

    HAL_SuspendTick();
    HAL_PWR_EnterSTOPMode(PWR_LOWPOWERREGULATOR_ON, PWR_STOPENTRY_WFI);
    SystemClock_Config();
    HAL_ResumeTick();

    /* Restore the exact entry state. In the release image DEBUG_ENABLE=0 and
     * LPUART1 may never have been enabled; turning a previously disabled,
     * floating-pin UART IRQ on after every STOP chunk creates an avoidable
     * interrupt/current surface. */
    if (usart1_irq_was_enabled) NVIC_EnableIRQ(USART1_IRQn);
    if (lpuart1_irq_was_enabled) NVIC_EnableIRQ(LPUART1_IRQn);
    HAL_PWREx_DisableInternalWakeUpLine();
}
#endif

void power_manager_sleep_ms(uint32_t durationMs) {
    if (durationMs == 0) return;
#if defined(POWER_SAVE_MODE) && POWER_SAVE_MODE && defined(ARDUINO_ARCH_STM32)
    if (inited) {
        /* RM0461 requires the ADC's dedicated regulator to be disabled before
         * Stop mode. power_adc_quiesce() also clears the VREFINT path and
         * verifies ADEN/ADVREGEN/VREFEN; a failed normal shutdown gets one
         * peripheral reset. Never enter a multi-minute STOP1 with an analog
         * block whose quiescent state is still unknown. */
        if (!power_adc_quiesce()) {
            NVIC_SystemReset();
            return;
        }
        /* RTC and IWDG share LSI, so the cycle-count assertion above proves
         * this chunk expires before IWDG even as LSI frequency varies. Split
         * long sleeps and refresh between chunks while retaining run-mode
         * hang recovery. */
        uint32_t remaining = durationMs;
        stop1_progress_state_t progress = {0u, false};
        bool     shallow_fallback = false;
        bool     int1_irq_was_enabled = false;
        STM32RTC& rtc = STM32RTC::getInstance();
        while (remaining > 0) {
            HAL_IWDG_Refresh(&s_iwdg);
            /* A freefall can arrive while the preceding CTT/relay window is
             * active. Those windows yield as soon as they see the flag, but
             * main.cpp still calls this routine with the remaining sleep
             * budget. Do not enter one 28 s STOP1 chunk before noticing an
             * event that is already pending: return immediately so the next
             * loop iteration enters burst mode. Suppressed chatter is allowed
             * to continue sleeping and is cleared by the normal post-wake
             * path below. */
            if (power_manager_freefall_pending()) break;
            uint32_t chunk = remaining > MAX_STOP1_CHUNK_MS
                                 ? MAX_STOP1_CHUNK_MS : remaining;
            uint32_t sub_before = 0;
            time_t   t_before = rtc.getEpoch(&sub_before);
            if (chunk < 2000) {
                /* The RTC alarm has 1 s resolution (alarm_at = epoch + chunk/1000,
                 * MATCH_HHMMSS): a sub-second chunk arms the CURRENT second, whose
                 * match boundary already passed, so STOP1 would hang until the
                 * IWDG reset. Sub-2 s residues use framework delay(), whose
                 * strong application yield sleeps shallowly between SysTicks;
                 * this stays IWDG-safe without arming an invalid RTC alarm. */
                delay(chunk);
            } else {
                enter_stop1_for_ms(chunk);
            }
            /* Debit the time that ACTUALLY passed, never the requested chunk.
             * STOP1 exits early on an INT1 edge, so debiting `chunk` would
             * fast-forward the schedule: a swallowed chatter wake 100 ms into
             * a 28 s chunk used to retire the whole 28 s, collapsing a 1200 s
             * sleep to a few seconds and running a GPS acquisition (the bulk
             * of the energy budget) every few seconds until the cap emptied.
             * The RTC is the only clock that survives STOP1, so measure it. */
            uint32_t sub_after = 0;
            time_t   t_after = rtc.getEpoch(&sub_after);
            int32_t  elapsed = (int32_t)((int32_t)(t_after - t_before) * 1000
                                         + (int32_t)sub_after - (int32_t)sub_before);
            if (elapsed < 0) elapsed = 0;                  /* clock wrap guard */
            if ((uint32_t)elapsed > chunk) elapsed = (int32_t)chunk;

            if (power_manager_freefall_pending()) break;

            uint32_t used = (uint32_t)elapsed;
            if (used >= remaining) {
                remaining = 0;
            } else {
                remaining -= used;
            }

            /* A stuck/asserted or chattering active-high INT1 can truncate
             * every chunk to a negligible interval while this loop keeps
             * refreshing IWDG.
             * First mask that expected wake source and retry STOP1. If another
             * complete streak advances less than one second per entry even
             * with INT1 masked, the
             * wake source or RTC path is not behaving as assumed. Continuing
             * to kick IWDG there would be a permanent scheduler live-lock.
             * Escape to the bounded shallow path below instead. */
            if (remaining > 0) {
                stop1_progress_action_t action =
                    stop1_progress_observe(&progress, used, chunk);
                if (action == STOP1_PROGRESS_MASK_INT1) {
                    int1_irq_was_enabled =
                        NVIC_GetEnableIRQ(EXTI9_5_IRQn) != 0u;
                    NVIC_DisableIRQ(EXTI9_5_IRQn);
                } else if (action == STOP1_PROGRESS_SHALLOW_FALLBACK) {
                    shallow_fallback = true;
                    break;
                }
            }
        }
        if (progress.int1_masked && int1_irq_was_enabled) {
            NVIC_EnableIRQ(EXTI9_5_IRQn);
        }
        /* Fault containment only: this is intentionally not normal flight
         * sleep and does not claim STOP1-level current. One-second delay()
         * slices use the application's shallow-WFI yield, poll freefall, and
         * refresh IWDG. If SysTick itself cannot advance, delay() stops
         * returning and the independent watchdog resets the MCU instead of
         * allowing another software-maintained live-lock. */
        while (shallow_fallback && remaining > 0) {
            HAL_IWDG_Refresh(&s_iwdg);
            if (power_manager_freefall_pending()) break;
            uint32_t slice = remaining > 1000u ? 1000u : remaining;
            delay(slice);
            remaining -= slice;
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
 * STM32WLE5 has 20 x 32-bit TAMP_BKPxR (BKP0R..BKP19R) - 80 bytes that
 * persist across reset, STOP, and standby while VDD is present. We use the
 * first 16: a 15-word session struct followed by its CRC32. The CRC makes a
 * retained one-bit key/address/counter corruption fail closed into OTAA
 * instead of restoring a permanently dead session.
 *
 * The "BREN" retention bit that some larger STM32 families need to keep
 * BKPSRAM alive across standby does NOT exist on STM32WL — these regs
 * are retained automatically.  Access is via direct register reads;
 * the RTC clock domain must be enabled (done by power_manager_init()
 * via STM32RTC::begin()) for TAMP writes to succeed. */

#define STRATO_SESSION_MAGIC   0x53545241u   /* "STRA" big-endian */
#define STRATO_SESSION_VER     3u   /* v3 adds CRC32 in the word after the struct */
#define SESSION_WORD_COUNT     (sizeof(lorawan_session_t) / sizeof(uint32_t))
#define STRATO_SESSION_CRC_WORD SESSION_WORD_COUNT
#define STRATO_COMMAND_SEQ_WORD 16
#define STRATO_B2B_ID_WORD      17
#define STRATO_LEASE_WORD       18
#define STRATO_BOOT_WORD        19
#define STRATO_TAMP_WORD_COUNT  20
static_assert((sizeof(lorawan_session_t) % sizeof(uint32_t)) == 0,
              "TAMP session must be word-aligned");
static_assert(STRATO_SESSION_CRC_WORD < STRATO_B2B_ID_WORD,
              "TAMP session CRC overlaps retained B2B/lease/boot diagnostics");
static_assert(STRATO_SESSION_CRC_WORD < STRATO_COMMAND_SEQ_WORD &&
              STRATO_COMMAND_SEQ_WORD < STRATO_B2B_ID_WORD,
              "retained command sequence overlaps another TAMP record");
static_assert(STRATO_BOOT_WORD == STRATO_TAMP_WORD_COUNT - 1,
              "retained layout exceeds STM32WLE5 BKP0R..BKP19R");
static_assert(REGION_FIX_MAX_AGE_SEC <= TAMP_LEASE_AGE_MASK,
              "packed retained lease cannot represent the legal age limit");

#if defined(ARDUINO_ARCH_STM32)
static volatile uint32_t* tamp_bkp_word(size_t idx) {
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
    /* DBP is itself synchronized into the backup domain.  The first flight
     * boot reaches this helper before STM32RTC::begin(), so a write followed
     * immediately by BKP access can be dropped even though RAM reports the
     * intended value.  Require the enable to read back before publishing any
     * retained record. */
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        SET_BIT(PWR->CR1, PWR_CR1_DBP);
        if (READ_BIT(PWR->CR1, PWR_CR1_DBP) != 0) break;
    }
    __DSB();
}

/* These commit markers are the only retained roots that can restore a radio
 * session and its geographic authorization. Any failed durability check must
 * make both unpublishable, with exact readback, before returning to callers. */
static bool invalidate_session_and_lease_markers(void) {
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        *tamp_bkp_word(0) = 0;
        *tamp_bkp_word(STRATO_LEASE_WORD) = 0;
        if (*tamp_bkp_word(0) == 0 &&
            *tamp_bkp_word(STRATO_LEASE_WORD) == 0) {
            return true;
        }
    }
    return false;
}

static uint32_t session_crc32(const lorawan_session_t* s) {
    /* Standard reflected CRC-32 over every committed word except magic.
     * Magic is the atomic publish marker and is checked independently. */
    const uint8_t* bytes = (const uint8_t*)s;
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = sizeof(uint32_t); i < sizeof(*s); ++i) {
        crc ^= bytes[i];
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}
#endif

bool power_manager_load_session(lorawan_session_t* s) {
    if (!s) return false;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    uint32_t* dst = (uint32_t*)s;
    for (size_t i = 0; i < SESSION_WORD_COUNT; i++) dst[i] = *tamp_bkp_word(i);
    uint32_t stored_crc = *tamp_bkp_word(STRATO_SESSION_CRC_WORD);
    return s->magic == STRATO_SESSION_MAGIC &&
           s->version == STRATO_SESSION_VER &&
           stored_crc == session_crc32(s);
#else
    (void)s; return false;
#endif
}

bool power_manager_save_session(const lorawan_session_t* s_in) {
    if (!s_in) return false;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    /* Copy + stamp magic/version so the caller doesn't have to. */
    lorawan_session_t s = *s_in;
    s.magic   = STRATO_SESSION_MAGIC;
    s.version = STRATO_SESSION_VER;
    const uint32_t* src = (const uint32_t*)&s;
    /* Two-phase commit. The previous implementation wrote magic first, so a
     * watchdog/brownout between later words could make a torn mix of old and
     * new keys/counters pass load_session(). Clear validity, write the entire
     * body and its CRC, then publish the marker last. An interrupted save or
     * retained-bit corruption now fails closed into OTAA rejoin instead of
     * importing a corrupt session. */
    *tamp_bkp_word(0) = 0;
    for (size_t i = 1; i < SESSION_WORD_COUNT; i++) {
        *tamp_bkp_word(i) = src[i];
    }
    uint32_t crc = session_crc32(&s);
    *tamp_bkp_word(STRATO_SESSION_CRC_WORD) = crc;
    *tamp_bkp_word(0) = src[0];

    /* Counter reservation is only safe if it is durable before RF or
     * application dispatch. A gated TAMP clock or marginal backup-domain
     * write must therefore fail closed rather than silently returning
     * success and reopening a replay window after reset. Read back every
     * committed word, CRC, and the publish marker. */
    for (size_t i = 0; i < SESSION_WORD_COUNT; i++) {
        if (*tamp_bkp_word(i) != src[i]) {
            (void)invalidate_session_and_lease_markers();
            return false;
        }
    }
    if (*tamp_bkp_word(STRATO_SESSION_CRC_WORD) != crc) {
        (void)invalidate_session_and_lease_markers();
        return false;
    }
    return true;
#else
    (void)s_in; return false;
#endif
}

bool power_manager_clear_session(void) {
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    return invalidate_session_and_lease_markers();
#else
    return true;
#endif
}

bool power_manager_load_region_lease(uint32_t* age_sec) {
    if (!age_sec) return false;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    return tamp_lease_record_decode(
        *tamp_bkp_word(STRATO_LEASE_WORD), age_sec);
#else
    return false;
#endif
}

bool power_manager_save_region_lease(uint32_t age_sec) {
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    /* STM32WLE5 exposes only BKP0R..BKP19R.  The lease therefore occupies
     * one word: 10-bit tag, 11-bit complemented check, and 11-bit saturating
     * age.  The 2,047 s saturation is beyond the 1,800 s legal lease, so an
     * over-range age remains expired after reset. */
    uint32_t record = tamp_lease_record_encode(age_sec);
    *tamp_bkp_word(STRATO_LEASE_WORD) = record;
    uint32_t decoded_age = 0;
    return *tamp_bkp_word(STRATO_LEASE_WORD) == record &&
           tamp_lease_record_decode(record, &decoded_age) &&
           decoded_age == (age_sec > TAMP_LEASE_AGE_MASK
               ? TAMP_LEASE_AGE_MASK : age_sec);
#else
    (void)age_sec;
    return false;
#endif
}

uint32_t power_manager_record_boot(void) {
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    volatile uint32_t* boot_word = tamp_bkp_word(STRATO_BOOT_WORD);
    uint32_t previous = 0;
    uint32_t next = tamp_boot_record_decode(*boot_word, &previous)
        ? (previous == TAMP_BOOT_COUNT_MASK ? previous : previous + 1u)
        : 1u;
    uint32_t record = tamp_boot_record_encode(next);
    /* The non-safety boot counter shares one physical word with its tag and
     * complemented check. Returning zero exposes a durability failure in
     * telemetry/HIL rather than claiming a retained count that never reached
     * TAMP. */
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        *boot_word = record;
        __DSB();
        uint32_t observed = 0;
        if (*boot_word == record &&
            tamp_boot_record_decode(*boot_word, &observed) &&
            observed == next) return next;
    }
    *boot_word = 0;
    return 0;
#else
    return 1;
#endif
}

bool power_manager_load_b2b_msg_id(uint8_t* next_id) {
    if (!next_id) return false;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    uint32_t record = *tamp_bkp_word(STRATO_B2B_ID_WORD);
    return b2b_id_record_decode(record, next_id);
#else
    return false;
#endif
}

bool power_manager_save_b2b_msg_id(uint8_t next_id) {
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    uint32_t record = b2b_id_record_encode(next_id);
    *tamp_bkp_word(STRATO_B2B_ID_WORD) = record;
    return *tamp_bkp_word(STRATO_B2B_ID_WORD) == record;
#else
    (void)next_id;
    return false;
#endif
}

bool power_manager_load_command_state(uint8_t* sequence, bool* relay_enabled) {
    if (!sequence || !relay_enabled) return false;
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    return command_state_record_decode(
        *tamp_bkp_word(STRATO_COMMAND_SEQ_WORD), sequence, relay_enabled);
#else
    return false;
#endif
}

bool power_manager_save_command_state(uint8_t sequence, bool relay_enabled) {
#if defined(ARDUINO_ARCH_STM32)
    enable_backup_access();
    uint32_t record = command_state_record_encode(sequence, relay_enabled);
    *tamp_bkp_word(STRATO_COMMAND_SEQ_WORD) = record;
    return *tamp_bkp_word(STRATO_COMMAND_SEQ_WORD) == record;
#else
    (void)sequence;
    (void)relay_enabled;
    return false;
#endif
}
