/**
 * Stratolink firmware, Phase 1, 4.
 * Normal: tier → GPS/sensors → pack → TX → sleep. Burst: on LIS2DH12 freefall (INT1/PA8) wake, rapid beacon until freefall clears.
 */
#include <Arduino.h>
#if __has_include("secrets.h")
#include "secrets.h"
#else
#define LORAWAN_DEV_EUI ""
#define LORAWAN_APP_EUI ""
#define LORAWAN_APP_KEY ""
#endif
#include "config.h"
#include "stratolink_pins.h"
#include "telemetry.h"
#include "power_adc.h"
#include "gps_backup_policy.h"
#include "gps_ublox.h"
#include "lorawan.h"
#include "ctt_event.h"
#include "command.h"
#include "power_manager.h"
#include "sensors.h"
#include "sensor_tmp117.h"
#include "sensor_ms5611.h"
#include "sensor_lis2dh12.h"
#include "sensor_ltr390.h"
#include "mic_acoustic.h"
#include "optical_fault_policy.h"
#include "region_manager.h"
#include "reset_cause.h"

static_assert(STRATO_RCC_CSR_OBLRSTF == RCC_CSR_OBLRSTF &&
              STRATO_RCC_CSR_PINRSTF == RCC_CSR_PINRSTF &&
              STRATO_RCC_CSR_BORRSTF == RCC_CSR_BORRSTF &&
              STRATO_RCC_CSR_SFTRSTF == RCC_CSR_SFTRSTF &&
              STRATO_RCC_CSR_IWDGRSTF == RCC_CSR_IWDGRSTF &&
              STRATO_RCC_CSR_WWDGRSTF == RCC_CSR_WWDGRSTF &&
              STRATO_RCC_CSR_LPWRRSTF == RCC_CSR_LPWRRSTF,
              "reset-cause decoder must track STM32WL CMSIS flag positions");

#ifndef BURST_GPS_TIMEOUT_MS
#define BURST_GPS_TIMEOUT_MS 10000
#endif
#ifndef BURST_SLEEP_SEC
#define BURST_SLEEP_SEC 10
#endif

static_assert(BURST_MAX_CYCLES > 0u && BURST_MAX_CYCLES <= UINT16_MAX,
              "burst cycle cap must fit its retained RAM counter");
static_assert(BURST_COOLDOWN_CYCLES > 0u &&
              BURST_COOLDOWN_CYCLES <= UINT8_MAX,
              "burst cooldown must fit its retained RAM counter");
static_assert(AUX_UPLINK_INTERVAL_CYCLES > 0u &&
              AUX_UPLINK_INTERVAL_CYCLES <= (uint32_t)UINT8_MAX + 1u,
              "auxiliary interval must encode as interval-1 cooldown");

/* Every normal scheduled sleep must leave one complete conservative active-
 * cycle allowance inside the GNSS-backed region lease. At the datasheet-
 * minimum 29.5 kHz LSI, a nominal 1200 s RTC sleep can occupy 1302 s of wall
 * time; 1302 + 300 = 1602 remains strictly before the 1800 s RF deadline.
 * Pin every tier independently so a future power-policy edit cannot recreate
 * the deterministic REDUCED/NO_GPS self-expiry that silenced the next wake. */
#define REGION_SLEEP_CHARGE_CONST_SEC(nominal_sec) \
    ((((uint64_t)(nominal_sec) * (uint64_t)REGION_RTC_CONFIGURED_LSI_HZ) + \
      (uint64_t)REGION_RTC_MIN_LSI_HZ - 1u) / \
     (uint64_t)REGION_RTC_MIN_LSI_HZ)
#define ASSERT_NORMAL_SLEEP_FITS_REGION_LEASE(interval_sec) \
    static_assert( \
        REGION_SLEEP_CHARGE_CONST_SEC(interval_sec) + \
            REGION_RESET_UNACCOUNTED_CHARGE_SEC < REGION_FIX_MAX_AGE_SEC, \
        #interval_sec " plus active margin must fit the region lease")
ASSERT_NORMAL_SLEEP_FITS_REGION_LEASE(SLEEP_INTERVAL_FULL_SEC);
ASSERT_NORMAL_SLEEP_FITS_REGION_LEASE(SLEEP_INTERVAL_REDUCED_SEC);
ASSERT_NORMAL_SLEEP_FITS_REGION_LEASE(SLEEP_INTERVAL_NO_GPS_SEC);
ASSERT_NORMAL_SLEEP_FITS_REGION_LEASE(SLEEP_INTERVAL_EMERGENCY_SEC);
#undef ASSERT_NORMAL_SLEEP_FITS_REGION_LEASE
#undef REGION_SLEEP_CHARGE_CONST_SEC

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
#define LOG(x) Serial.println(x)
#else
#define LOG(x) ((void)0)
#endif

static uint8_t tx_payload[TELEMETRY_PAYLOAD_SIZE];
static gps_fix_t last_gps_fix;
static bool burst_mode = false;
static uint16_t burst_cycles = 0;    /* cycles spent in the current burst (runaway cap) */
static uint8_t burst_cooldown = 0;   /* normal cycles to ignore freefall re-trigger after a capped burst */
static uint8_t tx_fail_streak = 0;  /* consecutive TX failures; 5 → reset */
static uint8_t aux_uplink_cooldown = 0; /* successful primary cycles until the
                                        * next CTT/B2B auxiliary is allowed */
static bool aux_prefer_b2b = false; /* alternate when both queues are nonempty */
static uint8_t join_retry_skip = 0;  /* normal wakes before another OTAA try */
static uint8_t join_backoff_exp = 0; /* 1,2,4-cycle retry spacing, capped */
static bool region_known = false;   /* true once TAMP restore or a GPS fix has picked the
                                     * regulatory region; until then ALL join TX is held
                                     * (a cold-boot US915 default join would be out-of-band
                                     * anywhere outside the Americas) */
static uint32_t region_fix_age_sec = 0; /* age of the GNSS-backed frequency-plan
                                        * decision; TX fails closed after the lease */
static bool region_lease_trusted = false; /* provenance bit: set only by a valid
                                           * retained lease or fresh advancing PVT */
static tamp_region_authority_source_t region_authority_source =
    TAMP_REGION_AUTHORITY_GNSS;
static lora_region_id_t region_authority_region = LORA_REGION_SILENT;
static uint8_t spurious_ff_streak = 0; /* consecutive INT1 wakes that read ~1g on arrival */
static uint8_t ff_suppress_clean = 0;  /* scheduled wakes seen while the wake path is latched off */
static uint8_t s_boot_reset_code = RESET_CAUSE_UNKNOWN;
static bool s_have_fix_this_boot = false;
static uint32_t s_last_fix_monotonic_sec = 0;
static uint32_t s_reported_relay_fwd = 0;
static uint32_t s_reported_ctt_tags = 0;
static bool s_optical_quiescence_fault = false;
static uint8_t s_optical_quiet_retries = 0;
static_assert(SENSOR_QUIESCE_FAST_RETRIES > 0u &&
              SENSOR_QUIESCE_FAST_RETRIES <= UINT8_MAX,
              "optical fast-retry count must fit its saturating counter");

/* Never turn an absent/corrupt retained lease into a fresh authorization.
 * `region_fix_age_sec` starts at zero, so blindly saving end-of-cycle age after
 * a failed load could publish a plausible lease; one later reset would then
 * restore the stale LoRaWAN session and transmit on an unproven regional plan. */
static void persist_region_lease_if_trusted(void) {
    if (region_lease_trusted) {
        bool authority_consistent =
            region_authority_region < LORA_REGION_SILENT &&
            region_authority_region == lorawan_current_region();
        if (!authority_consistent ||
            !power_manager_save_region_authority(
                region_fix_age_sec,
                region_authority_region,
                region_authority_source)) {
            /* An unverified age must never authorize RF in this boot. Best-
             * effort invalidate both retained roots so a later reset cannot
             * restore the preceding, now-under-aged authorization either. */
            region_known = false;
            region_lease_trusted = false;
            region_authority_region = LORA_REGION_SILENT;
            (void)power_manager_clear_session();
        }
    }
}

/* Launch authorization is deliberately narrower than GNSS authorization. It
 * exists only to get the primary join/health path on-air while the payload is
 * still at its explicitly provisioned launch site. Optional transmissions and
 * long radio windows remain disabled until a fresh, advancing PVT takes over. */
static bool region_authority_is_gnss(void) {
    return region_lease_trusted && region_known &&
           region_authority_source == TAMP_REGION_AUTHORITY_GNSS &&
           region_authority_region == lorawan_current_region();
}

/* A third fully qualified missing server proof retires only the OTAA session,
 * not the freshly re-established frequency-plan authority. The recovery cycle
 * itself must have obtained an advancing PVT; retained provenance alone is not
 * enough to replace a network session. RAM is invalidated first so no later
 * same-cycle path can transmit through the suspect keys. */
static bool recover_stale_server_session(uint32_t cycle_started_ms,
                                         bool fresh_fix_this_cycle) {
    bool exact_fresh_authority = fresh_fix_this_cycle &&
        region_authority_is_gnss() &&
        region_authority_region < LORA_REGION_SILENT &&
        region_authority_region == lorawan_current_region();

    uint32_t active_sec = (millis() - cycle_started_ms + 999u) / 1000u;
    uint32_t live_age = region_fix_age_advance(
        region_fix_age_sec, active_sec);

    /* This must precede every optional-uplink/service branch below. Even a
     * failed TAMP write cannot leave the suspect RAM session usable. */
    lorawan_invalidate_session();
    bool session_clear_ok = power_manager_clear_lorawan_session();
    bool authority_republished = session_clear_ok && exact_fresh_authority &&
        power_manager_save_region_authority(
            live_age, region_authority_region,
            TAMP_REGION_AUTHORITY_GNSS);

    if (!authority_republished) {
        region_known = false;
        region_lease_trusted = false;
        region_authority_source = TAMP_REGION_AUTHORITY_GNSS;
        region_authority_region = LORA_REGION_SILENT;
        /* Best effort makes the next reset quiet too. Failure still leaves the
         * current boot quiet because both RAM roots above are revoked. */
        (void)power_manager_clear_session();
        lorawan_server_liveness_note_recovery(false);
        return false;
    }

    /* Publish the real current-cycle age, not the pre-GPS zero. End-of-cycle
     * accounting may conservatively charge this active interval again. */
    region_fix_age_sec = live_age;
    region_authority_source = TAMP_REGION_AUTHORITY_GNSS;
    region_known = true;
    region_lease_trusted = true;
    join_retry_skip = 0u;
    join_backoff_exp = 0u;
    lorawan_server_liveness_note_recovery(true);
    return true;
}

/* `region_fix_age_sec` is the conservative age stored at this cycle's entry
 * until the end-of-cycle precharge below. Include active time before every
 * actual TX decision so a lease that expires during GPS/sensor/RX work cannot
 * authorize a later packet. Do not call this after the future sleep has been
 * precharged into region_fix_age_sec; long-window TX uses its separately
 * captured remaining budget instead. */
static bool region_tx_allowed_now(uint32_t cycle_started_ms) {
#ifdef BENCH_SEED_REGION
    (void)cycle_started_ms;
    return region_known;
#else
    if (!region_known) return false;
    uint32_t active_sec = (millis() - cycle_started_ms + 999u) / 1000u;
    uint32_t live_age = region_fix_age_advance(
        region_fix_age_sec, active_sec);
    /* Demand the same whole-second close guard used by long windows. Primary,
     * join, and auxiliary frames are shorter than one second at their flight
     * PHYs, so this prevents a packet started on the final represented second
     * from completing after lease expiry. */
    if (!region_fix_age_allows_tx(live_age) ||
        region_fix_remaining_tx_ms(live_age) == 0u) {
        region_known = false;
        return false;
    }
    return true;
#endif
}

typedef struct {
    lorawan_liveness_qualification_t* qualification;
    uint32_t cycle_started_ms;
    lorawan_liveness_event_t* event;
} server_probe_completion_context_t;

/* Runs inside lorawan_receive_downlink_result(), before a completed empty
 * Class-A exchange can return to loop(). This closes the reset boundary between
 * observing RX2 completion and durably recording miss3. */
static bool complete_server_probe_before_rx_return(
    const lorawan_liveness_probe_result_t* result,
    void* opaque) {
    server_probe_completion_context_t* context =
        (server_probe_completion_context_t*)opaque;
    if (!result || !context || !context->qualification || !context->event) {
        return false;
    }
    lorawan_liveness_qualification_t* qualification = context->qualification;
    qualification->gnss_region_authority = region_authority_is_gnss();
    qualification->freefall_clear = !power_manager_freefall_pending();
    qualification->rx_power_qualified =
        power_adc_get_tier() <= POWER_TIER_REDUCED;
    qualification->region_tx_legal =
        region_tx_allowed_now(context->cycle_started_ms);
    bool durable = false;
    *context->event = lorawan_server_complete_probe(
        qualification, result, &durable);
    return durable && *context->event != LORAWAN_LIVENESS_NO_CHANGE;
}

/* Reset-cause snapshot. RAM-only diagnostic; read via J-Link.
 * Captured before RMVF clear so each new boot writes the precise cause. */
volatile uint32_t boot_reset_cause = 0;
volatile uint32_t boot_count = 0;

#ifdef BENCH_SEED_REGION
/* The setup() assembler reference below makes this survive release
 * section-GC so the launch checklist can prove, by inspecting the ELF, that
 * only bench images contain the RF-region bypass. */
extern "C" __attribute__((used))
const char stratolink_bench_region_build_marker[] =
    "BENCH_SEED_REGION active: NOT FLIGHT";
#endif

void setup() {
    /* MCU reset restores PA0 to input and can wake an uncontained MAX-M10S
     * before any retained/runtime state is available. Assert RESET_N at the
     * first executable point; gps_ublox_init() releases it only after a fresh
     * 4.4 V rail check and a bounded UART reinitialization. */
    gps_ublox_assert_reset_early();
#ifdef BENCH_SEED_REGION
    /* A zero-instruction reference: the address is an input to a compiler
     * barrier, which keeps the marker's section live without runtime cost. */
    __asm__ volatile("" : : "r"(stratolink_bench_region_build_marker) : "memory");
#endif
    boot_reset_cause = RCC->CSR;
    RCC->CSR |= RCC_CSR_RMVF;     /* clear flags so the next reset is unambiguous */

    /* Arm the independent watchdog before touching external peripherals.
     * Previously this happened only after GPS, radio, and every sensor had
     * initialized, so a wedged driver during setup() could strand the payload
     * forever even though run-time hangs were bounded. Freefall attachment
     * remains below, after the accelerometer INT1 has been configured. */
    power_manager_init();
    power_manager_kick_watchdog();

    /* STM32RTC::begin() above may initialize the RTC clock on a true cold
     * start. That operation resets the backup domain, so every retained-state
     * read or write must happen after it. Recording the boot and restoring the
     * command before RTC initialization made both appear durable on immediate
     * readback and then silently vanish later in the same boot. */
    boot_count = power_manager_record_boot();
    command_init();

#ifndef BENCH_SEED_REGION
    /* The ordinary end-of-cycle commit charges measured awake time plus the
     * planned STOP interval. A reset during setup, acquisition, TX/RX, or any
     * other pre-commit work would otherwise lose that awake interval; repeated
     * watchdog resets could keep an old geographic authorization artificially
     * young forever. Reserve a conservative complete active-cycle allowance
     * before touching any external peripheral. The later measured commit may
     * double-charge it, which is safe. A fresh PVT resets age to zero.
     *
     * If the commit/readback fails, this boot must not trust an older valid-
     * looking marker even if best-effort invalidation also fails. The next boot
     * retries this same precharge before any RF-capable work. */
    bool boot_lease_precharge_ok = true;
    tamp_region_lease_t boot_region_authority = {};
    bool boot_region_authority_loaded =
        power_manager_load_region_authority(&boot_region_authority);
    if (boot_region_authority_loaded) {
        boot_region_authority.age_sec = region_fix_age_advance(
            boot_region_authority.age_sec,
            REGION_RESET_UNACCOUNTED_CHARGE_SEC);
        bool precharge_saved = boot_region_authority.exact_region
            ? power_manager_save_region_authority(
                boot_region_authority.age_sec,
                (lora_region_id_t)boot_region_authority.region_id,
                boot_region_authority.source)
            : power_manager_save_region_lease(
                boot_region_authority.age_sec);
        if (!precharge_saved) {
            boot_lease_precharge_ok = false;
            (void)power_manager_clear_session();
        }
    }
#endif

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
    Serial.begin(DEBUG_SERIAL_BAUD);
    LOG("Stratolink Firmware Starting");
#endif

    power_adc_init();
    if (!gps_ublox_init()) {
        LOG("GPS init failed");
    }
    power_manager_kick_watchdog();
    if (!lorawan_init()) {
        LOG("LoRaWAN init failed");
    }
    power_manager_kick_watchdog();
    /* Try to restore the previous OTAA session from TAMP backup regs
     * before attempting a fresh join.  A successful restore preserves
     * region + DevAddr + FCntUp across reset (TX-fail auto-reset,
     * brown-out, freefall-wake, etc.), avoiding a join airtime hit and
     * an FCnt-anti-replay collision on the next uplink.  TAMP survives
     * STOP/standby but not full power loss, so a deep brown-out
     * (VSTOR < 1.8 V cold-start) still triggers a fresh join, which
     * is what we want for a real cold boot. */
    {
        lorawan_session_t s;
        bool retained_session_valid = power_manager_load_session(&s);
        s_boot_reset_code = reset_cause_decode(
            boot_reset_cause, retained_session_valid);
#ifdef BENCH_SEED_REGION
        /* The bench bypass is explicitly US915-only. A valid retained session
         * from any other plan is still not authority to import that plan at a
         * US bench: leave it untouched in TAMP for forensic inspection and
         * exercise a fresh US915 join instead. */
        bool retained_session_is_us915 = retained_session_valid &&
            s.region_id == (uint32_t)LORA_REGION_US915;
        bool retained_session_imported =
            retained_session_is_us915 && lorawan_import_session(&s);
        if (retained_session_imported) {
            region_fix_age_sec = 0;
            region_lease_trusted = true;
            region_known = true;
            region_authority_source = TAMP_REGION_AUTHORITY_GNSS;
            region_authority_region = lorawan_current_region();
            LOG("LoRaWAN session restored from TAMP");
        } else {
            /* BENCH HARNESS ONLY, never in a flight build. An indoor board has
             * no sky view, so seed the known-local US915 plan in RAM to exercise
             * the complete join/uplink path. This is not persisted as launch
             * authority and the flight environment does not define the bypass. */
            lorawan_set_region(LORA_REGION_US915);
            region_known = true;
            region_lease_trusted = true;
            region_authority_source = TAMP_REGION_AUTHORITY_GNSS;
            region_authority_region = LORA_REGION_US915;
            LOG("BENCH_SEED_REGION active: GNSS-first gate bypassed, NOT FLIGHT");
        }
#else
        /* A retained session is never regional authority by itself. Accept an
         * exact v2 authority without a session (the explicit pre-launch case),
         * or migrate a legacy GNSS age only when a separately CRC-protected
         * retained session supplies its exact region. Any mismatch is ignored
         * and the radio is configured from the authority record instead. */
        bool authority_usable = boot_lease_precharge_ok &&
            boot_region_authority_loaded &&
            region_fix_age_allows_tx(boot_region_authority.age_sec);
        lora_region_id_t authorized_region = LORA_REGION_SILENT;
        if (authority_usable && boot_region_authority.exact_region) {
            authorized_region =
                (lora_region_id_t)boot_region_authority.region_id;
        } else if (authority_usable && retained_session_valid &&
                   s.region_id < (uint32_t)LORA_REGION_SILENT) {
            authorized_region = (lora_region_id_t)s.region_id;
        } else {
            authority_usable = false;
        }

        bool retained_session_imported = authority_usable &&
            retained_session_valid &&
            s.region_id == (uint32_t)authorized_region &&
            lorawan_import_session(&s);

        if (authority_usable) {
            if (!retained_session_imported) {
                lorawan_set_region(authorized_region);
            }
            region_fix_age_sec = boot_region_authority.age_sec;
            region_lease_trusted = true;
            region_known = true;
            region_authority_source = boot_region_authority.source;
            region_authority_region = authorized_region;

            /* Convert a valid legacy age/session pair to the exact-region v2
             * record immediately. A failed migration revokes both roots. */
            if (!boot_region_authority.exact_region) {
                persist_region_lease_if_trusted();
            }
            if (retained_session_imported) {
                LOG("LoRaWAN session restored from TAMP");
            } else if (region_authority_source ==
                       TAMP_REGION_AUTHORITY_LAUNCH) {
                LOG("explicit retained launch authority active");
            }
        } else {
            /* Missing, corrupt, mismatched, or expired retained authority is a
             * true cold boot: RF stays quiet until fresh GNSS. A compile-time
             * boot default is intentionally never treated as authorization. */
            LOG("cold boot: RF quiet until first GPS fix picks the region");
        }
#endif
    }

    if (!sensors_init()) {
        LOG("Sensors init failed");
    }
    s_optical_quiescence_fault = !sensor_ltr390_quiesce();
    power_manager_kick_watchdog();

    (void)mic_acoustic_init();
    /* INT1 is flight-critical burst detection. A transient boot-time I2C NACK
     * must not silently disable it for the rest of the mission. */
    bool freefall_int_ready = false;
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        if (sensor_lis2dh12_enable_freefall_int1()) {
            freefall_int_ready = true;
            break;
        }
        delay(20);
    }
    if (!freefall_int_ready) LOG("Freefall INT1 init failed");
    power_manager_attach_freefall_wakeup();

    last_gps_fix.valid = false;
    LOG("Setup done");
}

void loop() {
    const uint32_t cycle_started_ms = millis();
    /* IWDG runs from LSI in run mode and STOP on this board's option-byte
     * configuration. Sleep is chunked in power_manager; refresh here so any
     * run-mode hang lasting > 33 s reboots the chip. */
    power_manager_kick_watchdog();

    /* Enter burst on a freefall wake, unless we're in the post-cap cooldown.
     * The cooldown re-arms only after BURST_COOLDOWN_CYCLES *consecutive*
     * freefall-free wakes; a freefall wake during cooldown restarts the count,
     * so a persistently stuck/chattering INT1 never re-arms burst (one capped
     * window total).  Always consume the wake flag so it can't accumulate. */
    bool freefall_wake = power_manager_did_wake_from_freefall();
    bool spurious_freefall_wake = false;

    /* Chatter guard: a REAL freefall wake still reads low-g when we get here
     * (the INT needs 30 ms sustained < 0.35 g and wake latency is ~ms); a
     * bump/EMI/stuck-pin wake reads ~1 g again.  Three consecutive spurious
     * wakes latch the INT1 sleep-abort OFF (power_manager suppression), so a
     * chattering pin can't collapse the TX cadence. Confirmed spurious wakes
     * now return to sleep without GPS/TX below; after three, the latch prevents
     * even the repeated full-loop wakeups. Flight-3 data: all real in-flight
     * trips were single self-clearing events, so a healthy sensor never
     * accumulates a streak. */
    if (freefall_wake && sensor_lis2dh12_is_freefall_cleared()) {
        freefall_wake = false;                        /* spurious: no burst entry */
        spurious_freefall_wake = true;
        if (spurious_ff_streak < 255) spurious_ff_streak++;
        if (spurious_ff_streak >= 3) {
            power_manager_suppress_freefall_wake(true);
            ff_suppress_clean = 0;
        }
    } else if (freefall_wake) {
        /* Confirmed low-g or an unavailable sample: neither is evidence that
         * the wake cleared, so fail open into bounded recovery. Clear the
         * chatter latch too, not just the streak: leaving it engaged kept the
         * wake path suppressed for the rest of the flight once a streak had
         * ever tripped, permanently disabling burst mode on descent. The
         * six-cycle burst cap and cooldown contain a persistent I2C fault. */
        spurious_ff_streak = 0;
        ff_suppress_clean = 0;
        power_manager_suppress_freefall_wake(false);
    } else if (spurious_ff_streak >= 3) {
        if (++ff_suppress_clean >= 16) {              /* probation served: re-arm */
            spurious_ff_streak = 0;
            power_manager_suppress_freefall_wake(false);
        }
    } else {
        spurious_ff_streak = 0;                       /* clean cycle clears a sub-latch streak */
    }

    /* A wake that the accelerometer itself disproves must not become an
     * unscheduled GPS acquisition + TTN uplink. Three such early full cycles
     * per 16 normal cycles inflated the nominal daily airtime by 19% and could
    * erase the entire fair-use/energy margin. Quiesce immediately and retry
     * after one minute; genuine low-g continues into burst below. */
    if (spurious_freefall_wake) {
        (void)gps_ublox_quiesce();
        lorawan_sleep();
        uint32_t backoff_sec = (uint32_t)SPURIOUS_WAKE_BACKOFF_SEC;
#ifndef BENCH_SEED_REGION
        /* This early-return path bypasses the normal end-of-cycle lease
         * accounting. Charge awake recovery and the slow-RTC backoff so INT1
         * chatter cannot under-age a regional authorization. The
         * interrupted preceding sleep was already precharged, so this is
         * deliberately conservative. */
        region_fix_age_sec = region_fix_age_after_sleep(
            region_fix_age_sec, millis() - cycle_started_ms,
            backoff_sec * 1000u);
        persist_region_lease_if_trusted();
#endif
        power_manager_sleep_ms(backoff_sec * 1000u);
        return;
    }

    /* A successful LTR390 enable followed by an unconfirmed standby can leave
     * up to the datasheet's 200 uA active current across the whole mission
     * sleep. Retry only bus recovery/quiescence at the short cadence first:
     * repeating GPS and TX every minute would amplify the fault. A permanently
     * failed non-critical optical sensor must not suppress primary tracking or
     * let the regional lease expire forever, though. After the bounded fast
     * attempts, fall through into a normal degraded cycle; optical reads and
     * every auxiliary service remain disabled. Freefall/burst stays higher
     * priority and bypasses this recovery block. */
    if (s_optical_quiescence_fault && !freefall_wake && !burst_mode) {
        sensors_recover_i2c_bus();
        if (sensor_ltr390_quiesce()) {
            s_optical_quiescence_fault = false;
            s_optical_quiet_retries = 0;
        } else if (optical_fault_consume_fast_retry(
                       &s_optical_quiet_retries,
                       (uint8_t)SENSOR_QUIESCE_FAST_RETRIES)) {
            (void)gps_ublox_quiesce();
            lorawan_sleep();
            uint32_t retry_ms = (uint32_t)SENSOR_QUIESCE_RETRY_SLEEP_MS;
#ifndef BENCH_SEED_REGION
            region_fix_age_sec = region_fix_age_after_sleep(
                region_fix_age_sec, millis() - cycle_started_ms, retry_ms);
            persist_region_lease_if_trusted();
#endif
            power_manager_sleep_ms(retry_ms);
            return;
        }
    }

    if (burst_cooldown > 0) {
        burst_cooldown = freefall_wake ? BURST_COOLDOWN_CYCLES : (uint8_t)(burst_cooldown - 1);
    } else if (freefall_wake && !burst_mode &&
               lorawan_joined() && region_known &&
               power_adc_read_vSTOR_mv() >= GPS_ACQ_FLOOR_MV) {
        /* Burst forbids OTAA and is useful only when a legal, powered session
         * can actually transmit. It also runs GPS on every rapid cycle, so
         * the weaker LoRa-only TX floor is insufficient: entering at
         * 2.8-3.6 V could spend the recovery reserve on repeated acquisition
         * attempts that the GPS floor immediately rejects. */
        burst_mode = true;
        burst_cycles = 0;
    }

    telemetry_input_t ti;
    telemetry_input_init(&ti);

    ti.battery_mv = power_adc_read_vSTOR_mv();
    ti.solar_mv   = power_adc_read_solar_mv();

    uint32_t gps_timeout_ms = burst_mode ? (uint32_t)BURST_GPS_TIMEOUT_MS : 30000;
    bool fresh_fix_this_cycle = false;
    gps_quiescence_result_t gps_quiescence = GPS_QUIESCENCE_UNCONTAINED;
    const bool gps_attempted_this_cycle = power_adc_can_use_gps() || burst_mode;
    if (gps_attempted_this_cycle) {
        if (gps_ublox_get_fix(&last_gps_fix, gps_timeout_ms, !burst_mode)) {
            fresh_fix_this_cycle = true;
            s_have_fix_this_boot = true;
            s_last_fix_monotonic_sec = power_manager_monotonic_seconds();
            ti.lat_e7         = last_gps_fix.lat_e7;
            ti.lon_e7         = last_gps_fix.lon_e7;
            ti.altitude_m     = last_gps_fix.altitude_m;
            ti.gps_speed_cm_s = last_gps_fix.speed_cm_s;
            ti.gps_heading_cd = last_gps_fix.heading_cd;
            ti.gps_satellites = last_gps_fix.satellites;
#if defined(B2B_ENABLE) && B2B_ENABLE
            lorawan_b2b_set_local_crumb(last_gps_fix.lat_e7,
                                        last_gps_fix.lon_e7,
                                        last_gps_fix.altitude_m);
#endif
        }
        /* No fresh fix this cycle -> GPS fields stay zero (NOGPS).  We do NOT
         * fall back to the last known fix: a wedged/silent GPS must report
         * NOGPS, never a frozen position re-shipped as valid (the stale-fix
         * bug).  gps_ublox_get_fix() gates on a fresh PVT + advancing iTOW. */

        /* Sleep the module HERE, the instant the fix attempt is done.  Nothing
         * after this point reads the GPS: the region switch, telemetry pack,
         * join, uplink and downlink windows all work from last_gps_fix in RAM.
         * Left awake it holds continuous nav at ~25 mA across the join (up to
         * 15 s), the uplink and both RX windows, which on flight-3 numbers is
         * tens of joules a day against a 24.7 J budget and the nominal cap
         * model's 8.86 J (7.09 J at the part's 0.8 F minimum). This is the
         * single largest avoidable draw in the cycle. */
        gps_quiescence = gps_ublox_quiesce();
    } else {
        gps_ublox_note_power_skip();
    }

    /* GPS-driven region switch.  If the balloon crossed a regulatory
     * boundary (Atlantic mid-ocean, Persian Gulf, Wallace Line) since
     * the last cycle, lorawan_set_region() invalidates the current
     * session and the re-join logic below picks it up before the next
     * TX.  No-op if region unchanged. */
    if (fresh_fix_this_cycle) {
        region_fix_age_sec = 0;
        bool authority_was_launch =
            region_authority_source == TAMP_REGION_AUTHORITY_LAUNCH;
        lora_region_id_t region_before = lorawan_current_region();
        lora_region_id_t fresh_region = region_for_latlon(
            last_gps_fix.lat_e7, last_gps_fix.lon_e7);
        lorawan_set_region(fresh_region);
        region_authority_source = TAMP_REGION_AUTHORITY_GNSS;
        region_authority_region = fresh_region;
        region_known = fresh_region < LORA_REGION_SILENT;
        region_lease_trusted = region_known;
        bool region_changed = lorawan_current_region() != region_before;
        if (region_changed || authority_was_launch) {
            /* A same-region LAUNCH -> GNSS takeover is as significant to the
             * short authority window as a frequency-plan change. Do not let
             * failed launch joins leave a 1/2/4-cycle skip that can consume
             * every GNSS-authorized wake before the lease expires. */
            join_retry_skip = 0;
            join_backoff_exp = 0;
        }
        if (!lorawan_joined()) {
            /* Any unjoined RAM state must invalidate the retained session
             * before publishing this fresh lease. Usually this is the normal
             * region-change path. Applying it to every unjoined fresh-fix
             * cycle also retries a preceding failed TAMP clear: RAM already
             * holds the new region then, so region_changed alone would be
             * false and could otherwise pair the old-band retained session
             * with a newly valid lease. Cold boot/failed join clears are
             * harmless and keep the same invariant. */
            if (!power_manager_clear_session()) {
                /* The old-region retained session could not be proven
                 * invalid. Keep this boot RF-silent and do not publish the
                 * fresh lease beside an unverified old session. */
                region_known = false;
                region_lease_trusted = false;
            }
        }
        /* Save after the possible session clear above. A reboot anywhere after
         * this point restores a zero-age lease only because this cycle really
         * obtained a fresh, advancing PVT. */
        persist_region_lease_if_trusted();
    }
#ifndef BENCH_SEED_REGION
    else if (!region_tx_allowed_now(cycle_started_ms)) {
        /* The payload may have crossed a regulatory boundary while GNSS was
         * unavailable. Keep the in-RAM/TAMP session intact, but suppress every
         * transmitting path until a genuinely fresh PVT renews the lease.
         * Include this cycle's active GNSS time, not merely the age captured
         * at wake. The helper revokes region_known when the live age expired. */
    }
#endif

    /* A genuine freefall may arrive while the MCU is already active rather
     * than during STOP1. gps_ublox_get_fix() now yields within 100 ms, but the
     * normal cycle would otherwise continue through sensors, primary TX, and
     * Class-A RX before the pending flag is consumed at the next loop top.
     * Apply any fresh GNSS region decision above first, then quiesce and let
     * the next iteration enter burst mode on the correct legal plan. */
    if (power_manager_freefall_pending()) {
        /* The acquisition path already quiesced GNSS immediately after its
         * poll. Cover only the power-gated path here; issuing PMREQ twice
         * would add another ~300 ms to the burst response for no benefit. */
        if (!gps_attempted_this_cycle) (void)gps_ublox_quiesce();
        lorawan_sleep();
#ifndef BENCH_SEED_REGION
        uint32_t interrupted_active_sec =
            (millis() - cycle_started_ms + 999u) / 1000u;
        region_fix_age_sec = region_fix_age_advance(
            region_fix_age_sec, interrupted_active_sec);
        persist_region_lease_if_trusted();
#endif
        return;
    }

    /* A reset can land after the third miss was durably committed but before
     * same-region invalidation. Recovery-due is therefore a state, not only an
     * edge event. Hold every normal-cycle RF path until this actual cycle has
     * a fresh advancing PVT and can complete the durable transition. Emergency
     * burst remains mission-priority and never advances the liveness policy;
     * the first later normal cycle performs this recovery. */
    bool suppress_optional_after_recovery = false;
    /* A prior authenticated proof is not permission to open a secondary radio
     * after this cycle's primary failed before RF. Set only after the current
     * FCnt reservation and primary transmit both succeed. */
    bool primary_transaction_ok = false;
    if (!burst_mode && lorawan_server_recovery_due()) {
        suppress_optional_after_recovery = true;
        if (fresh_fix_this_cycle && region_authority_is_gnss() &&
            (gps_quiescence ==
                 GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY ||
             gps_quiescence == GPS_QUIESCENCE_RESET_HELD)) {
            (void)recover_stale_server_session(
                cycle_started_ms, fresh_fix_this_cycle);
        }
    }

    /* IWDG timeout is 30.84 s minimum / 32.768 s typical. GPS fix can run
     * for up to 30 s but refreshes every ~5 s; TX +
     * RX1/RX2 windows ~5 s, sensor + mic reads ~1 s, kick the dog
     * between phases so the watchdog only catches genuine hangs. */
    power_manager_kick_watchdog();

    if (power_adc_should_read_sensors()) {
        bool temperature_ok =
            sensor_tmp117_read_decidegrees(&ti.temperature_dc);
        bool pressure_ok =
            sensor_ms5611_read_pressure_centihpa(&ti.pressure_ch);
        bool accel_ok = sensor_lis2dh12_read_accel_cm_s2(
            &ti.accel_x_cm_s2, &ti.accel_y_cm_s2, &ti.accel_z_cm_s2);
        bool uv_ok = false;
        bool lux_ok = false;
        if (!s_optical_quiescence_fault) {
            uv_ok = sensor_ltr390_read_uv_index(&ti.uv_index);
            lux_ok = sensor_ltr390_read_ambient_lux(&ti.ambient_lux);
        }

        /* STM32duino times a broken transfer out, but a HAL handle can remain
         * BUSY afterward. If every independent I2C path failed, reset and
         * clock-recover the bus once, then make one bounded retry. Do not do
         * this for one bad/absent sensor: its driver already reinitializes
         * independently and the rest of the bus has proven healthy. */
        if (!(temperature_ok || pressure_ok || accel_ok || uv_ok || lux_ok)) {
            sensors_recover_i2c_bus();
            (void)sensor_tmp117_read_decidegrees(&ti.temperature_dc);
            (void)sensor_ms5611_read_pressure_centihpa(&ti.pressure_ch);
            (void)sensor_lis2dh12_read_accel_cm_s2(
                &ti.accel_x_cm_s2, &ti.accel_y_cm_s2,
                &ti.accel_z_cm_s2);
            if (!s_optical_quiescence_fault) {
                (void)sensor_ltr390_read_uv_index(&ti.uv_index);
                (void)sensor_ltr390_read_ambient_lux(&ti.ambient_lux);
            }
        }
        if (!s_optical_quiescence_fault) {
            if (!sensor_ltr390_quiesce()) {
                sensors_recover_i2c_bus();
                s_optical_quiescence_fault = !sensor_ltr390_quiesce();
            }
            if (!s_optical_quiescence_fault) {
                s_optical_quiet_retries = 0;
            }
        }
        ti.acoustic_valid =
            mic_acoustic_detect(&ti.acoustic_event) ? 1u : 0u;
    }

    /* Five extra bytes occupy the same SF9 symbol group as a one-byte
     * extension, so use them to surface the failures that made Flight-3 hard
     * to diagnose remotely. Counter baselines advance only after a successful
     * primary uplink below; a failed TX therefore retries the same deltas. */
    ti.power_tier = (uint8_t)power_adc_get_tier();
    ti.reset_cause = s_boot_reset_code;
    ti.boot_count = (uint8_t)boot_count;
    if (s_have_fix_this_boot) {
        uint32_t age_min =
            (power_manager_monotonic_seconds() - s_last_fix_monotonic_sec) / 60u;
        ti.fix_age_min = age_min > UINT16_MAX ? UINT16_MAX : (uint16_t)age_min;
    } else {
        ti.fix_age_min = UINT16_MAX;
    }
    bool retained_relay_enabled = command_relay_enabled();
    ti.command_ack_valid = command_get_applied_state(
        &ti.last_command_seq, &retained_relay_enabled) ? 1u : 0u;
    ti.relay_enabled = retained_relay_enabled ? 1u : 0u;

    lorawan_relay_stats_t relay_stats = {};
    lorawan_relay_get_stats(&relay_stats);
    lorawan_ctt_stats_t ctt_stats = {};
    lorawan_ctt_get_stats(&ctt_stats);
    const uint32_t cycle_relay_fwd_total = relay_stats.fwd;
    const uint32_t cycle_ctt_tags_total = ctt_stats.tags_seen;
    uint32_t relay_delta = cycle_relay_fwd_total - s_reported_relay_fwd;
    uint32_t ctt_delta = cycle_ctt_tags_total - s_reported_ctt_tags;
    ti.relay_fwd_delta = relay_delta > UINT8_MAX ? UINT8_MAX : (uint8_t)relay_delta;
    ti.ctt_tags_delta = ctt_delta > UINT8_MAX ? UINT8_MAX : (uint8_t)ctt_delta;

    telemetry_pack(&ti, tx_payload);
    power_manager_kick_watchdog();

    /* If a previous join failed, retry with an exponential 1/2/4-cycle
     * backoff.  A balloon can spend days beyond gateway coverage after a
     * region transition; one OTAA request every 20 minutes would waste almost
     * the entire regional fair-use allowance while having no chance to join.
     * A region change clears the backoff above so the new plan gets one prompt
     * attempt. IWDG (30.84 s guaranteed minimum) still bounds each active
     * attempt. */
    /* A freefall burst is useful only with an already-restored/joined
     * session. OTAA inside the rapid loop burns the recovery reserve and can
     * spend several join requests before the 1/2/4-cycle backoff advances;
     * wait for the next normal cycle instead. */
    if (!suppress_optional_after_recovery && !burst_mode &&
        !lorawan_joined() &&
        region_tx_allowed_now(cycle_started_ms) && power_adc_can_tx()) {
        /* Launch authority is short-lived and normally permits only the first
         * two scheduled health cycles. Retry OTAA on each of those legal wakes
         * instead of spending the second one merely decrementing backoff. */
        if (join_retry_skip > 0 &&
            region_authority_source != TAMP_REGION_AUTHORITY_LAUNCH) {
            join_retry_skip--;
        } else {
            if (lorawan_join(15000)) {
                /* New region → new session.  Persist it so a reset (TX
                 * fail, brown-out, freefall) doesn't force another join. */
                (void)lorawan_persist_session();
                join_backoff_exp = 0;
            } else {
                join_retry_skip = (uint8_t)(1u << join_backoff_exp);
                if (join_backoff_exp < 2) join_backoff_exp++;
            }
        }
        power_manager_kick_watchdog();
    }

    /* VSTOR floor for uplink TX, mirroring lorawan_join()'s 3.0 V guard.  Below
     * ~3.0 V the buck is in dropout and Vdd droops hard during the +14 dBm/~50 mA
     * peak, worse at SF9 (~308 ms TX, ~3x SF7) where a long uplink can brown out
     * mid-transmit.  Gating HERE (not inside send_uplink) keeps a low-rail cycle a
     * clean skip: it must NOT feed tx_fail_streak, or a stable 2.8-3.0 V dusk rail
     * would log 5 false "failures" and force the very NVIC reset (-> rejoin spiral)
     * this guard exists to avoid. */
    bool vstor_ok_for_tx = power_adc_read_vSTOR_mv() >= 3000;
    /* `lorawan_joined()` may be true because a session survived reset; it is
     * not authorization to use that session after the independent GNSS region
     * lease expired. region_known gates the primary packet as well as the
     * join/relay paths, so no transmitting path can renew itself from stale
     * persisted state. */
    if (!suppress_optional_after_recovery &&
        power_adc_can_tx() && vstor_ok_for_tx &&
        region_tx_allowed_now(cycle_started_ms) &&
        lorawan_joined()) {
        lorawan_liveness_qualification_t liveness_qualification = {};
        liveness_qualification.fresh_advancing_pvt = fresh_fix_this_cycle;
        liveness_qualification.gnss_region_authority =
            region_authority_is_gnss();
        liveness_qualification.normal_primary = !burst_mode;
        liveness_qualification.freefall_clear =
            !power_manager_freefall_pending();
        liveness_qualification.rx_power_qualified =
            power_adc_get_tier() <= POWER_TIER_REDUCED;
        /* The enclosing gate just proved this exact live lease. Re-evaluate it
         * after RX before a missing ACK is allowed to count. */
        liveness_qualification.region_tx_legal = true;
        bool confirmed_probe = lorawan_server_probe_due(
            &liveness_qualification);
        bool primary_sent = confirmed_probe
            ? lorawan_send_confirmed_uplink(
                  tx_payload, TELEMETRY_PAYLOAD_SIZE,
                  &liveness_qualification)
            : lorawan_send_uplink(tx_payload, TELEMETRY_PAYLOAD_SIZE);
        if (primary_sent) {
            primary_transaction_ok = true;
            tx_fail_streak = 0;
            s_reported_relay_fwd = cycle_relay_fwd_total;
            s_reported_ctt_tags = cycle_ctt_tags_total;
            /* send_uplink reserved and atomically persisted the next FCntUp
             * before RF, so even a TX-induced reset cannot replay this frame. */
            LOG("TX OK");

            /* Listen against the PRIMARY uplink immediately.  TTN schedules a
             * queued Class-A downlink from the first uplink it receives; if an
             * auxiliary CTT/B2B TX happened first, it would move s_tx_end_ms
             * and our RX1/RX2 windows hundreds of milliseconds late. */
            /* The cycle-start tier can be stale by a volt after a 30 s GPS
             * acquisition plus the primary TX. Re-read it before committing
             * to up to ~6.7 s of Class-A RX; otherwise a cycle that started
             * FULL can keep the receiver awake after the cap has already
             * fallen into NO_GPS/EMERGENCY reserve. */
            lorawan_class_a_result_t rx_result =
                LORAWAN_CLASS_A_AMBIGUOUS;
            lorawan_liveness_event_t probe_event =
                LORAWAN_LIVENESS_NO_CHANGE;
            server_probe_completion_context_t probe_completion = {
                &liveness_qualification, cycle_started_ms, &probe_event
            };
            bool rx_attempted = false;
            bool post_tx_rx_power_ok =
                power_adc_get_tier() <= POWER_TIER_REDUCED;
            bool receive_primary = confirmed_probe;
#if defined(CMD_ENABLE) && CMD_ENABLE
            receive_primary = true;
#endif
            if (receive_primary && !burst_mode &&
                !power_manager_freefall_pending() && post_tx_rx_power_ok) {
                lorawan_downlink_t dl = {};
                rx_attempted = true;
                bool primary_rx_healthy = false;
                rx_result = lorawan_receive_downlink_result(
                    &dl,
                    confirmed_probe
                        ? complete_server_probe_before_rx_return : nullptr,
                    confirmed_probe ? &probe_completion : nullptr,
                    &primary_rx_healthy);
                /* Historical server proof is not proof of this exchange's
                 * local health. A transient RX fault closes optional work for
                 * this cycle without changing the sparse probe policy. Keep
                 * authenticated command delivery even after a restore fault. */
                if (!primary_rx_healthy) primary_transaction_ok = false;
                if (rx_result == LORAWAN_CLASS_A_AUTHENTICATED && dl.len > 0u) {
#if defined(CMD_ENABLE) && CMD_ENABLE
                    (void)command_handle(&dl);
#endif
#if defined(B2B_ENABLE) && B2B_ENABLE
                    /* A command addressed to another balloon (or broadcast)
                     * arrived through authenticated LoRaWAN. Wrap it in the
                     * fleet-key CMAC before it enters the public B2B carrier. */
                    (void)lorawan_b2b_queue_command(&dl);
#endif
                    /* receive_downlink() reserved and atomically persisted
                     * FCntDown before exposing this authenticated frame. */
                }
            }

            /* Re-qualify at completion. Freefall, rail sag, lease expiry, an
             * incomplete window, or any local RX/PHY fault makes a confirmed
             * exchange ambiguous and restarts the sparse interval without a
             * miss. An authenticated frame already reset the state atomically
             * with FCntDown inside lorawan_receive_downlink_result(). */
            liveness_qualification.freefall_clear =
                !power_manager_freefall_pending();
            liveness_qualification.rx_power_qualified =
                power_adc_get_tier() <= POWER_TIER_REDUCED;
            liveness_qualification.region_tx_legal =
                region_tx_allowed_now(cycle_started_ms);
            if (confirmed_probe &&
                rx_result != LORAWAN_CLASS_A_AUTHENTICATED) {
                if (probe_event == LORAWAN_LIVENESS_NO_CHANGE &&
                    rx_result == LORAWAN_CLASS_A_AMBIGUOUS) {
                    /* Completed empty windows were resolved durably inside the
                     * receive function, and a persistence fault already retired
                     * the complete session. Only preemption/local ambiguity
                     * reaches this fallback; reset already normalizes retained
                     * pending intent to that same sparse, non-miss outcome. */
                    lorawan_liveness_probe_result_t probe_result = {};
                    probe_result.local_tx_succeeded = true;
                    bool durable = false;
                    probe_event = lorawan_server_complete_probe(
                        &liveness_qualification, &probe_result, &durable);
                }
                if (probe_event == LORAWAN_LIVENESS_RECOVERY_DUE &&
                    lorawan_server_recovery_due()) {
                    suppress_optional_after_recovery = true;
                    (void)recover_stale_server_session(
                        cycle_started_ms, fresh_fix_this_cycle);
                }
            } else if (!confirmed_probe &&
                       (rx_result == LORAWAN_CLASS_A_COMPLETE_NO_EVIDENCE ||
                        (!receive_primary && !rx_attempted))) {
                (void)lorawan_server_note_ordinary_primary(
                    &liveness_qualification, true);
            }

#if (defined(CTT_LISTEN_ENABLE) && CTT_LISTEN_ENABLE) || \
    (defined(B2B_ENABLE) && B2B_ENABLE)
            /* CTT and B2B share a single, hard auxiliary airtime allowance.
             * Sending each independently could add one packet of each per
             * cycle and exceed TTN's 30 s/day guideline.  At most one shorter
             * auxiliary is attempted every AUX_UPLINK_INTERVAL_CYCLES primary
             * successes; when both queues have work, alternate them. */
            if (!primary_transaction_ok) {
                /* An attempted but unhealthy Class-A exchange cannot be
                 * followed by optional RF, even with prior server proof. */
            } else if (suppress_optional_after_recovery) {
                /* Suspect session was invalidated above. No optional TTN frame
                 * may run before a later cycle completes fresh OTAA. */
            } else if (!lorawan_server_session_proven()) {
                /* JoinAccept or local TX success is not server proof for this
                 * data session. Preserve queued events until an authenticated
                 * Class-A data-down/ACK is committed with FCntDown. */
            } else if (!region_authority_is_gnss()) {
                /* Launch authority permits primary health/control only. CTT
                 * and B2B event uplinks wait for fresh GNSS authorization. */
            } else if (gps_quiescence !=
                           GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY ||
                       s_optical_quiescence_fault) {
                /* Preserve the primary tracking/control exchange, but do not
                 * amplify an unresolved peripheral-current fault with a
                 * second optional TTN transmission. Leave the pending queue
                 * and cooldown untouched for a healthy later cycle. */
            } else if (burst_mode || power_manager_freefall_pending()) {
                /* Emergency/recovery beacons already consume the reserved TX
                 * margin. Never add optional event traffic during a burst or
                 * after freefall has requested the next rapid-beacon cycle. */
            } else if (aux_uplink_cooldown > 0) {
                aux_uplink_cooldown--;
            } else if (power_adc_read_vSTOR_mv() < 3000u) {
                /* Primary TX and optional Class-A RX happen before auxiliary
                 * traffic. Their load can cross the TX floor even when the
                 * earlier outer gate passed; never spend the mission reserve
                 * on a CTT/B2B packet. Leave the queue and cooldown unchanged
                 * so a later recharged cycle retries transactionally. */
            } else if (!region_tx_allowed_now(cycle_started_ms)) {
                /* Primary Class-A receive can run for ~6.7 s. If that work
                 * crossed the regional lease deadline, do not emit a later
                 * auxiliary packet even though the primary was legal. */
            } else {
                bool aux_sent = false;

#if defined(CTT_LISTEN_ENABLE) && CTT_LISTEN_ENABLE
                ctt_detection_t pending_ctt;
                bool ctt_pending = lorawan_ctt_peek_pending(&pending_ctt);
#else
                bool ctt_pending = false;
#endif

#if defined(B2B_ENABLE) && B2B_ENABLE
                uint8_t pending_b2b[LORAWAN_PAYLOAD_MAX];
                uint8_t pending_b2b_len = 0;
                bool b2b_pending = lorawan_b2b_peek_pending_uplink(
                    pending_b2b, sizeof(pending_b2b), &pending_b2b_len);
#else
                bool b2b_pending = false;
#endif

                bool send_b2b = b2b_pending && (!ctt_pending || aux_prefer_b2b);
                if (send_b2b) {
#if defined(B2B_ENABLE) && B2B_ENABLE
                    if (lorawan_send_uplink_port(B2B_EVENT_FPORT, pending_b2b,
                                                 pending_b2b_len)) {
                        /* FCntUp was durably reserved before RF; only now may
                         * the current RAM queue remove the event. */
                        lorawan_b2b_ack_pending_uplink();
                        aux_sent = true;
                    }
#endif
                } else if (ctt_pending) {
#if defined(CTT_LISTEN_ENABLE) && CTT_LISTEN_ENABLE
                    uint8_t event_payload[CTT_EVENT_PAYLOAD_SIZE];
                    ctt_event_pack(
                        &pending_ctt,
                        power_manager_monotonic_seconds() / 60u,
                        event_payload);
                    if (lorawan_send_uplink_port(CTT_EVENT_FPORT, event_payload,
                                                 CTT_EVENT_PAYLOAD_SIZE)) {
                        /* The incremented FCnt was persisted before RF; only
                         * now may the current RAM queue remove the event. */
                        lorawan_ctt_ack_pending();
                        aux_sent = true;
                    }
#endif
                }

                if (aux_sent) {
                    aux_uplink_cooldown =
                        (uint8_t)(AUX_UPLINK_INTERVAL_CYCLES - 1u);
                    aux_prefer_b2b = !send_b2b;
                }
            }
#endif
        } else {
            /* TX failed but we believed we were joined.  Most likely the
             * SX1262 latched into a fault state, we observed this once
             * after the cap reached the nominal VBAT_OV region (~5.36 V;
             * received telemetry peaked at 5.412 V) at peak sun and the
             * radio went silent for hours despite IWDG kicking and the
             * MCU running.  After N consecutive TX failures, force a
             * full system reset so lorawan_init() can re-init the radio
             * from scratch (radio->begin() runs a full SX1262 reset). */
            tx_fail_streak++;
            if (tx_fail_streak >= 5) {
                NVIC_SystemReset();
            }
        }
    }

    if (burst_mode) {
        burst_cycles++;
        if (!lorawan_joined() || !region_known ||
            power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV) {
            /* A session/lease/GPS-capable rail lost during a burst cannot
             * benefit from rapid acquisition cycles. Return to the normal
             * power/join policy before scheduling another 10-second wake. */
            burst_mode = false;
        } else if (sensor_lis2dh12_is_freefall_cleared()) {
            /* Normal exit: payload reached terminal velocity / landed (~1g). */
            burst_mode = false;
        } else if (burst_cycles >= BURST_MAX_CYCLES) {
            /* Runaway guard: freefall never cleared (stuck/chattering INT1).
             * Force-exit and latch the cooldown (re-arm needs consecutive
             * freefall-free wakes, handled at the top of loop()). */
            burst_mode = false;
            burst_cooldown = BURST_COOLDOWN_CYCLES;
        }
    }

    /* Select the recovery interval from a fresh POST-load rail. The cycle's
     * initial tier can be a full volt stale after GPS + sensors + TX on a 1 F
     * cap; re-reading it preserves the tier policy even though every normal
     * tier now uses the lease-safe 1200 s cadence. */
    power_tier_t sleep_tier = power_adc_get_tier();
    uint32_t sleep_sec = burst_mode
        ? (uint32_t)BURST_SLEEP_SEC
        : power_adc_get_sleep_interval_sec(sleep_tier);
    uint32_t sleep_ms  = sleep_sec * 1000;

    /* Account both active work and the sleep we are about to enter. This must
     * run even after a fresh fix: saving age zero above without precharging
     * the immediately following 20-30 minute sleep made the next wake believe
     * that no time had passed and could authorize one extra stale-band TX.
     * Do it after all TX decisions so the current fresh decision remains
     * usable; an interrupted sleep only over-ages the lease conservatively. */
    uint32_t relay_region_budget_ms = UINT32_MAX;
#ifndef BENCH_SEED_REGION
    uint32_t active_sec = (millis() - cycle_started_ms + 999u) / 1000u;
    uint32_t live_region_age_sec = region_fix_age_advance(
        region_fix_age_sec, active_sec);
    /* Capture the actual remaining legal TX time BEFORE precharging the
     * future sleep into retained age. Mutating region_fix_age_sec first made a
     * live budget impossible to recover and previously let a stale-fix relay
     * window continue transmitting past the 30-minute lease. */
    relay_region_budget_ms = region_fix_remaining_tx_ms(
        live_region_age_sec);
    /* STOP wake timing comes from LSI. At its datasheet-minimum 29.5 kHz,
     * STM32RTC's fixed 32 kHz prescalers make a nominal sleep 8.48% longer in
     * real time. Persist the worst-case wall duration before sleeping so cold
     * oscillator drift cannot silently extend a regional RF lease. */
    uint32_t sleep_lease_charge_sec =
        region_sleep_age_charge_sec(sleep_sec);
    region_fix_age_sec = region_fix_age_advance(
        live_region_age_sec, sleep_lease_charge_sec);
    persist_region_lease_if_trusted();
#else
    (void)cycle_started_ms; /* fixed-location soak has an explicit US seed */
#endif

    /* Belt and braces only for tiers that SKIPPED the GPS block above (NO_GPS
     * and below): the module's state is unknown after a reset or a brownout,
     * so make one bounded quiescence attempt before the idle window. The
     * GPS-enabled path already called gps_ublox_quiesce() immediately after
     * acquisition. Re-entering it here after a terminal failure could spend a
     * second complete three-attempt/two-reset recovery path in the same cycle,
     * invalidating the per-call energy bound and accelerating brownout. A
     * terminal result now leaves RESET_N physically held and keeps optional
     * radios closed, but reset-held current remains a launch measurement gate;
     * the primary scheduler does not collapse into a cross-cycle fast retry. */
    if (!gps_attempted_this_cycle) {
        gps_quiescence = gps_ublox_quiesce();
    }
    if (s_optical_quiescence_fault &&
        s_optical_quiet_retries < SENSOR_QUIESCE_FAST_RETRIES &&
        sleep_ms > (uint32_t)SENSOR_QUIESCE_RETRY_SLEEP_MS) {
        /* The region lease was already charged for the longer planned sleep,
         * which is conservative. Make the bounded fast retries promptly; a
         * persistent fault later resumes normal primary cadence degraded. */
        sleep_ms = (uint32_t)SENSOR_QUIESCE_RETRY_SLEEP_MS;
    }

#if defined(CTT_LISTEN_ENABLE) && CTT_LISTEN_ENABLE
    /* Bird/bat tag listening rides the same surplus gate as the relay and
     * takes its slice first (RX-only, cheaper than relaying).  Self-aborts
     * on floor/solar/freefall like the relay; time spent counts against the
     * sleep budget so the uplink cadence is preserved. */
    if (primary_transaction_ok && !suppress_optional_after_recovery &&
        lorawan_server_session_proven() && region_authority_is_gnss() &&
        gps_quiescence == GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY &&
        !s_optical_quiescence_fault &&
        !burst_mode && !power_manager_freefall_pending() &&
        region_known && power_adc_get_tier() == POWER_TIER_FULL &&
        power_adc_read_solar_mv() >= RELAY_SOLAR_MIN_MV) {
        uint32_t ctt_budget = sleep_ms < CTT_LISTEN_MS ? sleep_ms : CTT_LISTEN_MS;
        uint32_t ctt_used = lorawan_ctt_window(ctt_budget, RELAY_FLOOR_MV);
        sleep_ms = (ctt_used < sleep_ms) ? (sleep_ms - ctt_used) : 0;
        relay_region_budget_ms =
            (ctt_used < relay_region_budget_ms)
                ? (relay_region_budget_ms - ctt_used) : 0u;
    }
#endif

#if (defined(MESHTASTIC_RELAY_ENABLE) && MESHTASTIC_RELAY_ENABLE) || \
    (defined(B2B_ENABLE) && B2B_ENABLE)
    /* Open the shared LongFast service window only on surplus power, never at
     * the expense of the telemetry mission. Authenticated B2B service remains
     * available when the public Meshtastic repeater is command-disabled.
     * Gate: FULL tier (cap full, fresh post-TX read) + solar actively charging
     * + not in freefall-burst. The window self-aborts below RELAY_FLOOR_MV and
     * restores the LoRaWAN PHY on exit, so the next TTN cycle is unaffected.
     * Time spent in the window counts against the sleep budget, preserving the
     * uplink cadence. */
    /* region_known is required: the relay TRANSMITS at +14 dBm on a
     * region-derived LongFast frequency, so running it before the first GPS
     * fix would emit on a band picked by the boot default, which is exactly
     * what the GNSS-first cold-boot gate exists to prevent.  The CTT window
     * carries the same gate for symmetry even though it is receive-only. */
    bool meshtastic_enabled = false;
#if defined(MESHTASTIC_RELAY_ENABLE) && MESHTASTIC_RELAY_ENABLE
    meshtastic_enabled = command_relay_enabled();
#endif
    uint32_t relay_window_budget =
        sleep_ms < relay_region_budget_ms ? sleep_ms : relay_region_budget_ms;
    if (primary_transaction_ok && !suppress_optional_after_recovery &&
        lorawan_server_session_proven() && relay_window_budget > 0u &&
        region_authority_is_gnss() &&
        gps_quiescence == GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY &&
        !s_optical_quiescence_fault &&
        !burst_mode && !power_manager_freefall_pending() &&
        region_known &&
        power_adc_get_tier() == POWER_TIER_FULL &&
        power_adc_read_solar_mv() >= RELAY_SOLAR_MIN_MV) {  /* fresh read: ti.solar_mv is
                                                             * up to ~50 s stale by now */
        uint32_t used = lorawan_relay_window(
            relay_window_budget, RELAY_FLOOR_MV, meshtastic_enabled);
        sleep_ms = (used < sleep_ms) ? (sleep_ms - used) : 0;
    }
#endif

    /* Quiesce the radio before MCU STOP1: the SX1262 otherwise sits in STDBY_RC
     * (~600 µA), draining the cap. The superseded STOP2 path additionally
     * hard-reset the MCU during entry. */
    lorawan_sleep();

    power_manager_sleep_ms(sleep_ms);
}
