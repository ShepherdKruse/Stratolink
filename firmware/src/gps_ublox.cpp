#include "gps_ublox.h"
#include "gps_backup_policy.h"
#include "gps_freshness.h"
#include "gps_pvt_validation.h"
#include "stratolink_pins.h"
#include "config.h"
#include "power_manager.h"
#include "power_adc.h"
#include <Arduino.h>

#if defined(GNSS_ENABLE) && GNSS_ENABLE

#if __has_include(<SparkFun_u-blox_GNSS_v3.h>)
#include <SparkFun_u-blox_GNSS_v3.h>
static SFE_UBLOX_GNSS_SERIAL gnss;
#else
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
static SFE_UBLOX_GNSS gnss;
#endif

static gps_fix_t last_fix;
static gps_freshness_t pvt_freshness = {0, false};
static uint8_t   consecutive_no_fresh = 0; /* no-fresh-fix cycles, drives reset recovery */
static bool      gps_sleep_confirmed = false;
static_assert(GPS_STALE_RECOVERY_CYCLES > 0u &&
              GPS_STALE_RECOVERY_CYCLES <= UINT8_MAX,
              "GNSS stale-recovery ladder must fit its saturating counter");

typedef struct {
    uint32_t begin_failures;
    uint32_t dyn_model_failures;
    uint32_t backup_failures;
    uint32_t hardware_resets;
    uint32_t accepted_fixes;
    uint32_t power_aborts;
    uint32_t mission_aborts;
    uint32_t no_fresh_cycles;
    uint32_t backup_confirmations;
    uint32_t backup_terminal_failures;
    uint32_t rejected_value_fixes;
    /* Append-only: preserve every v8 HIL decoder offset above. */
    uint32_t dyn_model_terminal_failures;
} gps_diag_t;

/* J-Link-readable GPS recovery evidence without changing the stable telemetry
 * packet. All fields are monotonic for the current boot. */
static volatile gps_diag_t s_gps_diag = {};

bool gps_ublox_init(void) {
    GPS_SERIAL.begin(GPS_BAUD);
    bool ok = gnss.begin(GPS_SERIAL, GPS_BEGIN_MAX_WAIT_MS);
    if (!ok) s_gps_diag.begin_failures++;
    bool dyn_model_ok = ok && gps_ublox_set_airborne_4g();
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    gps_sleep_confirmed = false;
    last_fix.valid = false;
    /* A receiver which answers but cannot prove AIRBORNE_4G is not
     * flight-ready. get_fix() performs one bounded hardware-reset recovery,
     * but setup must not report this initialization as successful. */
    return ok && dyn_model_ok;
}

bool gps_ublox_set_airborne_4g(void) {
    /* A successful VALSET ACK alone is useful but not sufficient launch
     * evidence: read the model back. Without AIRBORNE_4G the receiver can
     * behave normally through ascent and then stop producing fixes above its
     * default altitude limit—the exact sort of delayed dropout a bench soak
     * misses. Retry is bounded and runs only once per mission cycle. */
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
#if defined(DYN_MODEL_AIRBORNE_4G)
        const uint8_t expected = (uint8_t)DYN_MODEL_AIRBORNE_4G;
        if (gnss.getDynamicModel(VAL_LAYER_RAM,
                                 GPS_DYNMODEL_MAX_WAIT_MS) == expected) {
            return true;
        }
        bool set_ok = gnss.setDynamicModel(
            DYN_MODEL_AIRBORNE_4G, VAL_LAYER_RAM_BBR,
            GPS_DYNMODEL_MAX_WAIT_MS);
#else
        const uint8_t expected = (uint8_t)GPS_DYNMODEL_AIRBORNE_4G;
        bool set_ok = gnss.setDynamicModel(
            (dynModel)GPS_DYNMODEL_AIRBORNE_4G, VAL_LAYER_RAM_BBR,
            GPS_DYNMODEL_MAX_WAIT_MS);
#endif
        if (set_ok &&
            gnss.getDynamicModel(VAL_LAYER_RAM,
                                 GPS_DYNMODEL_MAX_WAIT_MS) == expected) {
            return true;
        }
        s_gps_diag.dyn_model_failures++;
        power_manager_kick_watchdog();
        delay(20);
    }
    return false;
}

/* Hardware-reset the u-blox via PIN_GPS_RESET_N (active-low, 10 kΩ pullup R18)
 * to un-stick a module that has WEDGED, stopped answering after a backup-wake.
 * A wedged module ignores the UART, so a UBX soft-reset can't reach it; only
 * the reset line works.  After the pulse, re-sync the library + dyn model. */
static bool gps_ublox_reset(void) {
    gps_sleep_confirmed = false;
    s_gps_diag.hardware_resets++;
    pinMode(PIN_GPS_RESET_N, OUTPUT);
    digitalWrite(PIN_GPS_RESET_N, LOW);     /* assert reset */
    delay(20);
    pinMode(PIN_GPS_RESET_N, INPUT);        /* release: pullup deasserts reset */
    power_manager_kick_watchdog();
    delay(1000);                            /* let the module cold-boot */
    bool begin_ok = gnss.begin(GPS_SERIAL, GPS_BEGIN_MAX_WAIT_MS);
                                             /* re-sync to the fresh module */
    if (!begin_ok) s_gps_diag.begin_failures++;
    bool dyn_model_ok = begin_ok && gps_ublox_set_airborne_4g();
    gps_freshness_reset(&pvt_freshness);
    power_manager_kick_watchdog();
    return begin_ok && dyn_model_ok;
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms) {
    if (!fix) return false;

    /* The tier decision and this call are separated by sensor work, and the
     * REDUCED tier begins below the stricter acquisition floor. Re-check at
     * the actual load boundary so we never wake a ~25 mA GNSS acquisition on
     * a rail that already cannot fund it. A power-gated skip is not evidence
     * of a GPS wedge, so it deliberately does not advance the reset ladder. */
    if (power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV) {
        /* The gap before the next PVT observation can now be arbitrarily long.
         * Drop the old week-order anchor so recovery proves freshness with two
         * new advancing PVTs instead of comparing across an unobserved gap. */
        gps_freshness_reset(&pvt_freshness);
        last_fix.valid = false;
        fix->valid = false;
        fix->satellites = 0;
        return false;
    }

    /* Wake the module from software-backup (UBX-RXM-PMREQ with UARTRX wakeup
     * source).  Passive UART reads don't generate the TX activity the module
     * needs to wake, push a couple of dummy bytes, then give the module's UART
     * RX handler ~10 ms to come up (MAX-M10S spec ~2 ms wake-up). */
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.flush();
    delay(10);
    gps_sleep_confirmed = false;

    /* Re-apply AIRBORNE_4G on every wake.  A hot-wake from software-backup keeps
     * its config, but a cold start (brown-out, or the PA0 reset below) reverts to
     * the default "Portable" model (12 km ceiling) and would silently kill fixes
     * at float, so re-assert it each cycle.  Idempotent, ~60 ms.  (NB: not an SEU
     * guard, cosmic-ray upset was quantitatively refuted; see
     * analysis/diagnostics/WAKE_WEDGE_ROOT_CAUSE.md.) */
    bool model_reset_performed = false;
    if (!gps_ublox_set_airborne_4g()) {
        /* A low-altitude PVT does not prove the receiver will keep navigating
         * above the Portable model's ceiling. Recover once through RESET_N,
         * which also re-synchronizes the host library, then fail closed if the
         * AIRBORNE_4G readback still cannot be proven. This is deliberately
         * resolved before any position getters are consulted. */
        if (power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV) {
            /* Three bounded model attempts are already a real acquisition
             * load. Do not spend another cold-boot/reset interval after they
             * have pulled the rail through the mission reserve boundary. */
            s_gps_diag.power_aborts++;
            gps_freshness_reset(&pvt_freshness);
            last_fix.valid = false;
            fix->valid = false;
            fix->satellites = 0;
            return false;
        }
        if (!gps_ublox_reset()) {
            s_gps_diag.dyn_model_terminal_failures++;
            gps_freshness_reset(&pvt_freshness);
            last_fix.valid = false;
            fix->valid = false;
            fix->satellites = 0;
            return false;
        }
        model_reset_performed = true;
        if (power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV) {
            s_gps_diag.power_aborts++;
            gps_freshness_reset(&pvt_freshness);
            last_fix.valid = false;
            fix->valid = false;
            fix->satellites = 0;
            return false;
        }
    }

    /* Accept a fix ONLY when a genuinely FRESH NAV-PVT arrives this cycle:
     *   - gnss.getPVT() returns true only when a NEW PVT was received, AND
     *   - its iTOW advanced after a prior anchor epoch (a re-served buffered
     *     PVT, including the first cache read after an MCU reset, can't pass),
     *     AND
     *   - the fix is OK with >= 4 satellites.
     * We never read the cached position getters on a silent module, so a wedged
     * GPS can no longer have its last fix re-shipped as valid, it reports
     * NOGPS.  (The stale-fix bug: getGnssFixOk()/getLatitude() return the last
     * cached PVT with no freshness check when the module is silent, see
     * GPS_BUG_BOARD2.md and the SparkFun u-blox v3 source.) */
    uint32_t deadline = millis() + timeout_ms;
    uint32_t acquisition_started = millis();
    uint32_t last_kick = millis();
    uint32_t last_power_check = last_kick;
    uint32_t last_pvt_ms = acquisition_started;
    uint32_t last_epoch_progress_ms = acquisition_started;
    bool module_responded = false;          /* did the module answer at all this cycle? */
    bool itow_advanced = false;             /* did any answer carry a NEW epoch? */
    bool power_aborted = false;             /* rail fell below acquisition floor */
    bool mission_aborted = false;           /* freefall needs the radio/GPS now */
    bool dyn_model_aborted = false;         /* reset could not prove AIRBORNE_4G */
    bool inline_reset_attempted = model_reset_performed;
                                             /* at most one PA0 reset per energy-bounded poll */
    bool epoch_anchor_available = pvt_freshness.anchored;
    while ((int32_t)(deadline - millis()) > 0) {
        if (gnss.getPVT()) {
            module_responded = true;        /* alive, sent a PVT (with or without a fix) */
            last_pvt_ms = millis();
            uint32_t itow = gnss.getTimeOfWeek();
            bool was_anchored = pvt_freshness.anchored;
            if (gps_freshness_observe(&pvt_freshness, itow)) {
                itow_advanced = true;               /* nav engine is actually running */
                epoch_anchor_available = true;
                last_epoch_progress_ms = last_pvt_ms;
                uint8_t siv = (uint8_t)gnss.getSIV();
                if (gnss.getGnssFixOk() && siv >= 4) {
                    gps_pvt_values_t pvt = {
                        gnss.getLatitude(),
                        gnss.getLongitude(),
                        gnss.getAltitude(),
                        gnss.getGroundSpeed(),
                        gnss.getHeading(),
                        siv,
                    };
                    gps_wire_fix_t wire = {};
                    if (gps_pvt_to_wire_fix(&pvt, &wire)) {
                        last_fix.lat_e7 = wire.lat_e7;
                        last_fix.lon_e7 = wire.lon_e7;
                        last_fix.altitude_m = wire.altitude_m;
                        last_fix.speed_cm_s = wire.speed_cm_s;
                        last_fix.heading_cd = wire.heading_cdeg;
                        last_fix.satellites = wire.satellites;
                        last_fix.valid = true;
                        consecutive_no_fresh = 0;
                        s_gps_diag.accepted_fixes++;
                        *fix = last_fix;
                        return true;
                    }
                    /* A checksum-valid, advancing epoch can still contain an
                     * impossible field. Keep the navigation engine classified
                     * alive, but never let that PVT reach telemetry, regional
                     * selection, or the B2B crumb path. */
                    s_gps_diag.rejected_value_fixes++;
                }
            } else if (!was_anchored && pvt_freshness.anchored) {
                /* The first valid epoch is an anchor, not yet a freshness
                 * proof. SparkFun's explicit poll may legitimately return
                 * that same 1 Hz epoch several times, so stagnation is timed
                 * from this anchor rather than counted per API call. */
                epoch_anchor_available = true;
                last_epoch_progress_ms = last_pvt_ms;
            }
        }
        uint32_t now = millis();
        /* Sample the rail at 1 Hz, matching the relay and CTT long-window
         * posture. Five seconds at GNSS acquisition current is material on a
         * marginal 1 F cap; one second bounds the extra energy after a sag. */
        if (now - last_power_check >= 1000) {
            last_power_check = now;
            if (power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV) {
                power_aborted = true;
                break;
            }
        }
        /* INT1 can fire while the MCU is already awake in this poll. Waiting
         * out the remaining 30 s acquisition would defeat rapid descent
         * beaconing even though the interrupt is already latched. The caller
         * yields the current normal cycle and re-enters immediately in burst
         * mode. This is not evidence of a GNSS wedge, so keep it out of the
         * reset ladder just like a rail-driven abort. */
        if (power_manager_freefall_pending()) {
            mission_aborted = true;
            break;
        }
        /* Recover inside THIS acquisition instead of reporting NOGPS and
         * waiting another 20-minute flight cadence. A healthy 1 Hz nav engine
         * advances well inside three seconds even though explicit getPVT()
         * polls can legitimately return the same epoch multiple times. Three
         * elapsed seconds without epoch progress catches the cached-iTOW
         * wedge; five seconds without another PVT catches the silent or
         * one-anchor-then-silent variant. One reset maximum bounds energy and
         * avoids a reset storm on dead hardware. gps_ublox_reset() clears the
         * freshness anchor, so the recovered module must still prove two
         * advancing epochs before a position is accepted. */
        if (!inline_reset_attempted &&
            gps_recovery_due(epoch_anchor_available, now,
                             last_epoch_progress_ms, last_pvt_ms)) {
            if (!gps_ublox_reset()) {
                s_gps_diag.dyn_model_terminal_failures++;
                dyn_model_aborted = true;
                break;
            }
            inline_reset_attempted = true;
            module_responded = false;
            itow_advanced = false;
            epoch_anchor_available = false;
            last_pvt_ms = millis();
            last_epoch_progress_ms = last_pvt_ms;
            power_manager_kick_watchdog();
            continue;
        }
        /* Refresh IWDG every ~5 s so a long no-fix poll can't outlast the
         * watchdog's 32.7 s timeout. */
        if (now - last_kick >= 5000) {
            power_manager_kick_watchdog();
            last_kick = now;
        }
        delay(100);
    }

    /* No fresh, usable fix this cycle -> report NOGPS.  Invalidate the cache so
     * nothing downstream can resurrect a stale fix. */
    last_fix.valid  = false;
    fix->valid      = false;
    fix->satellites = 0;

    /* A rail-driven abort is not evidence of a wedged navigation engine.
     * Reset the epoch anchor because the interval before the next observed PVT
     * is now unbounded, and do not advance the hardware-reset ladder. */
    if (power_aborted || mission_aborted || dyn_model_aborted) {
        if (power_aborted) {
            s_gps_diag.power_aborts++;
            gps_freshness_reset(&pvt_freshness);
        }
        if (mission_aborted) s_gps_diag.mission_aborts++;
        return false;
    }

    /* Escalate to a reset ONLY for a truly SILENT (wedged) module.  A module
     * that answered getPVT() but had no usable fix is just acquiring / poor
     * sky, an honest NOGPS, not a wedge, so don't reset it and interrupt a
     * legitimate cold acquisition.  The wedge (flight freezes lasting hours)
     * is specifically "module stopped answering after its backup-wake." */
    /* Recovery must key on the NAV ENGINE, not just the UART.  The observed
     * flight wedge is a module that still answers getPVT() while its iTOW is
     * frozen, so gating the ladder on module_responded alone made it dead
     * code for exactly the failure it exists to clear.  A module that answers
     * with a stale epoch is wedged and does need the PA0 reset; one that is
     * merely acquiring under poor sky keeps advancing iTOW and is left alone. */
    /* A same-cycle reset and this legacy cross-cycle ladder must be mutually
     * exclusive. Otherwise a threshold boundary can issue a second RESET_N in
     * one acquisition, violating its energy bound and leaving no poll time to
     * observe recovery. */
    if (gps_stale_ladder_step(module_responded && itow_advanced,
                              inline_reset_attempted,
                              (uint8_t)GPS_STALE_RECOVERY_CYCLES,
                              &consecutive_no_fresh)) {
        (void)gps_ublox_reset();
    }
    s_gps_diag.no_fresh_cycles++;
    return false;
}

void gps_ublox_note_power_skip(void) {
    gps_freshness_reset(&pvt_freshness);
    last_fix.valid = false;
}

void gps_ublox_get_last_fix(gps_fix_t* fix) {
    if (fix) *fix = last_fix;
}

static void gps_uart_discard_buffered_input(void) {
    while (GPS_SERIAL.available() > 0) {
        (void)GPS_SERIAL.read();
    }
}

static bool gps_wait_for_nav_eoe_marker(uint32_t window_ms) {
    gps_backup_marker_parser_t parser;
    gps_backup_marker_reset(&parser);
    uint32_t deadline = millis() + window_ms;
    uint32_t last_kick = millis();
    while ((int32_t)(deadline - millis()) > 0) {
        while (GPS_SERIAL.available() > 0) {
            if (gps_backup_marker_feed(
                    &parser, (uint8_t)GPS_SERIAL.read())) {
                return true;
            }
        }
        uint32_t now = millis();
        if (now - last_kick >= 250u) {
            power_manager_kick_watchdog();
            last_kick = now;
        }
        delay(1);
    }
    return false;
}

static bool gps_uart_activity_seen(uint32_t window_ms) {
    uint32_t deadline = millis() + window_ms;
    uint32_t last_kick = millis();
    while ((int32_t)(deadline - millis()) > 0) {
        if (GPS_SERIAL.available() > 0) return true;
        uint32_t now = millis();
        if (now - last_kick >= 250u) {
            power_manager_kick_watchdog();
            last_kick = now;
        }
        delay(1);
    }
    return false;
}

bool gps_ublox_sleep(void) {
    /* Do not wake a receiver which this boot has already positively placed in
     * software standby. This makes the belt-and-braces low-tier call sites
     * genuinely free instead of waking the GNSS merely to put it back down. */
    if (gps_sleep_confirmed) return true;

    for (uint8_t attempt = 1; attempt <= GPS_BACKUP_MAX_ATTEMPTS; ++attempt) {
        /* If the receiver was already in software standby but the local state
         * was lost/uncertain, PMREQ's first byte would only be a wake edge and
         * the frame could be discarded during the ~2 ms UART startup. Nudge,
         * flush, and settle before every bounded attempt. */
        GPS_SERIAL.write((uint8_t)0xFF);
        GPS_SERIAL.write((uint8_t)0xFF);
        GPS_SERIAL.flush();
        delay(10);
        gps_sleep_confirmed = false;

        /* PMREQ is an input-only command: the u-blox interface description
         * defines no positive response, and SparkFun's boolean merely means
         * "not explicitly NACKed" (a quiet timeout looks successful). Create
         * an independent liveness marker instead. All settings are RAM-only:
         * disable NMEA noise, enable UBX, select the compact periodic NAV-EOE,
         * and briefly
         * raise the measurement rate to the documented 100 ms (10 Hz). A real
         * CFG ACK and one complete checksum-valid marker frame are required
         * before silence can count as evidence. Software standby clears RAM
         * and the next wake restores defaults; no persistent configuration is
         * changed. */
        bool marker_armed =
            gnss.setVal8(UBLOX_CFG_UART1OUTPROT_UBX, 1,
                         VAL_LAYER_RAM, 300) &&
            gnss.setVal8(UBLOX_CFG_UART1OUTPROT_NMEA, 0,
                         VAL_LAYER_RAM, 300) &&
            gnss.setVal16(UBLOX_CFG_RATE_MEAS, 100,
                          VAL_LAYER_RAM, 300) &&
            gnss.setVal16(UBLOX_CFG_RATE_NAV, 1,
                          VAL_LAYER_RAM, 300) &&
            gnss.setVal8(UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1, 1,
                         VAL_LAYER_RAM, 300);

        bool activity_seen = false;
        if (marker_armed) {
            gps_uart_discard_buffered_input();
            marker_armed = gps_wait_for_nav_eoe_marker(
                (uint32_t)GPS_BACKUP_MARKER_WAIT_MS);
        }
        if (marker_armed) {
            /* A complete NAV-EOE establishes a clean frame boundary. Send
             * PMREQ before the next 100 ms marker is due. maxWait=0 sends the
             * input-only command without inventing an ACK wait; hardware flush
             * proves every UART bit shifted before passive observation. */
            gps_uart_discard_buffered_input();
            (void)gnss.powerOffWithInterrupt(
                0, VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, true, 0);
            GPS_SERIAL.flush();
            activity_seen =
                gps_uart_activity_seen((uint32_t)GPS_BACKUP_CONFIRM_MS);
        }

        gps_backup_action_t action =
            gps_backup_decide(marker_armed, activity_seen, attempt);
        if (action == GPS_BACKUP_CONFIRMED) {
            gps_sleep_confirmed = true;
            s_gps_diag.backup_confirmations++;
            return true;
        }

        s_gps_diag.backup_failures++;
        power_manager_kick_watchdog();
        if (action == GPS_BACKUP_RETRY_RESET) {
            /* A continued marker or a failed marker configuration means the
             * receiver state is not safely known. PA0 reset restores a bounded
             * command path before the next confirmation attempt. Do not spend
             * that cold-boot/reconfiguration energy out of the mission's last
             * rail reserve: the receiver has already received one PMREQ
             * attempt, and main will retry promptly with optional radios off. */
            if (!gps_backup_reset_allowed(power_adc_read_vSTOR_mv())) {
                break;
            }
            (void)gps_ublox_reset();
        }
    }

    /* Fail closed to the caller. Main suppresses optional radio-listen windows
     * and caps the next MCU sleep to a five-second retry interval. It must
     * never hide an unconfirmed, potentially ~25 mA receiver behind a normal
     * 20-30 minute sleep. */
    s_gps_diag.backup_terminal_failures++;
    return false;
}

#else

bool gps_ublox_init(void) {
    last_fix.valid = false;
    return true;
}

bool gps_ublox_set_airborne_4g(void) {
    return true;
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms) {
    (void)timeout_ms;
    if (fix) {
        fix->valid = false;
        *fix = last_fix;
    }
    return false;
}

void gps_ublox_note_power_skip(void) {
    last_fix.valid = false;
}

void gps_ublox_get_last_fix(gps_fix_t* fix) {
    if (fix) *fix = last_fix;
}

bool gps_ublox_sleep(void) {
    /* No-op when GNSS is compiled out. */
    return true;
}

#endif /* GNSS_ENABLE */
