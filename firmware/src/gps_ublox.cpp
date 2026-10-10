#include "gps_ublox.h"
#include "gps_backup_policy.h"
#include "gps_freshness.h"
#include "gps_pvt_validation.h"
#include "gps_bounded_stream.h"
#include "stratolink_pins.h"
#include "config.h"
#include "power_manager.h"
#include "power_adc.h"
#include <Arduino.h>

static gps_fix_t last_fix;

#if defined(GNSS_ENABLE) && GNSS_ENABLE

static GpsBoundedStream gps_gnss_stream(GPS_SERIAL);

#if __has_include(<SparkFun_u-blox_GNSS_v3.h>)
#include <SparkFun_u-blox_GNSS_v3.h>
using GpsGnssBase = SFE_UBLOX_GNSS_SERIAL;
#else
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
using GpsGnssBase = SFE_UBLOX_GNSS;
#endif

class GpsGnss : public GpsGnssBase {
public:
    ubxPacket& configuration_packet() { return packetCfg; }
    ubxPacket& acknowledgement_packet() { return packetAck; }
    bool parser_idle() const {
        return currentSentence == SFE_UBLOX_SENTENCE_TYPE_NONE;
    }
    void discard_partial_response() {
        currentSentence = SFE_UBLOX_SENTENCE_TYPE_NONE;
        ubxFrameCounter = 0u;
        activePacketBuffer = SFE_UBLOX_PACKET_PACKETBUF;
    }
};
static GpsGnss gnss;

static gps_freshness_t pvt_freshness = {0, false};
static uint8_t   consecutive_no_fresh = 0; /* no-fresh-fix cycles, drives reset recovery */
static gps_quiescence_result_t gps_quiescence_state =
    GPS_QUIESCENCE_UNCONTAINED;
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
    uint32_t early_reset_hold_entries;
    uint32_t reset_hold_entries;
    uint32_t reset_hold_reuses;
    uint32_t reset_release_attempts;
    uint32_t reset_release_denied_low_rail;
    uint32_t reset_release_failures;
    uint32_t containment_state;
    uint32_t cold_extension_started;
    uint32_t cold_extension_exhausted;
    uint32_t cold_extension_aborted;
} gps_diag_t;

/* J-Link-readable GPS recovery evidence without changing the stable telemetry
 * packet. All fields are monotonic for the current boot. */
static volatile gps_diag_t s_gps_diag = {};

static bool gps_init_supervised();

static void gps_set_quiescence_state(gps_quiescence_result_t state) {
    gps_quiescence_state = state;
    s_gps_diag.containment_state = (uint32_t)state;
}

static void gps_drive_reset_hold(void) {
    digitalWrite(PIN_GPS_RESET_N, LOW);
    pinMode(PIN_GPS_RESET_N, OUTPUT);
    digitalWrite(PIN_GPS_RESET_N, LOW);
    gps_set_quiescence_state(GPS_QUIESCENCE_RESET_HELD);
}

void gps_ublox_assert_reset_early(void) {
    gps_drive_reset_hold();
    s_gps_diag.early_reset_hold_entries++;
}

/* RESET_N is the only board-level actuator which can stop a receiver after a
 * terminal PMREQ failure. Leave PA0 actively driven for the entire MCU STOP1
 * interval. This proves the command posture, not the reset-held current; that
 * current is deliberately launch-blocking until exact-assembly measurement. */
static void gps_assert_reset_hold(void) {
    gps_drive_reset_hold();
    s_gps_diag.reset_hold_entries++;
}

bool gps_ublox_init(void) {
    return gps_init_supervised();
}

static constexpr uint32_t GPS_MODEL_FIRST_SET_WAIT_MS =
    4u * GPS_DYNMODEL_MAX_WAIT_MS;
static constexpr uint32_t GPS_MODEL_BUDGET_MS =
    6u * GPS_DYNMODEL_MAX_WAIT_MS;
static_assert(GPS_DYNMODEL_MAX_WAIT_MS > 0u &&
              GPS_DYNMODEL_MAX_WAIT_MS <= UINT16_MAX / 6u,
              "GNSS model waits must fit positive uint16_t transport waits");

static uint16_t gps_model_remaining_ms(uint32_t deadline, uint16_t cap_ms) {
    const int32_t remaining = (int32_t)(deadline - (uint32_t)millis());
    if (remaining <= 0) return 0;
    return (uint32_t)remaining < cap_ms ? (uint16_t)remaining : cap_ms;
}

bool gps_ublox_set_airborne_4g(void) {
    /* Preserve the public/shutdown compatibility path. setup() and get_fix()
     * use the supervised read-first transaction below, never this helper. */
    /* A successful VALSET ACK alone is useful but not sufficient launch
     * evidence: read the model back. Without AIRBORNE_4G the receiver can
     * behave normally through ascent and then stop producing fixes above its
     * default altitude limit—the exact sort of delayed dropout a bench soak
     * misses. Allow startup time before a later retry without RESET_N, which
     * destroys retained navigation state. One shared deadline includes retry
     * pauses and bounds acceptance/start of further calls, not library return
     * time: UART enqueue and RX draining can exceed a supplied wait. */
    const uint32_t deadline = (uint32_t)millis() + GPS_MODEL_BUDGET_MS;
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        uint16_t wait_ms;
#if defined(DYN_MODEL_AIRBORNE_4G)
        const uint8_t expected = (uint8_t)DYN_MODEL_AIRBORNE_4G;
        wait_ms = gps_model_remaining_ms(deadline, GPS_DYNMODEL_MAX_WAIT_MS);
        if (wait_ms != 0 &&
            gnss.getDynamicModel(VAL_LAYER_RAM, wait_ms) == expected &&
            gps_model_remaining_ms(deadline, 1u) != 0) {
            return true;
        }
#else
        const uint8_t expected = (uint8_t)GPS_DYNMODEL_AIRBORNE_4G;
#endif
        wait_ms = gps_model_remaining_ms(deadline, attempt == 0
            ? GPS_MODEL_FIRST_SET_WAIT_MS : GPS_DYNMODEL_MAX_WAIT_MS);
        const bool set_ok = wait_ms != 0 && gnss.setDynamicModel(
            (dynModel)expected, VAL_LAYER_RAM_BBR, wait_ms);
        wait_ms = gps_model_remaining_ms(deadline, GPS_DYNMODEL_MAX_WAIT_MS);
        if (set_ok && wait_ms != 0 &&
            gnss.getDynamicModel(VAL_LAYER_RAM, wait_ms) == expected &&
            gps_model_remaining_ms(deadline, 1u) != 0) {
            return true;
        }
        s_gps_diag.dyn_model_failures++;
        power_manager_kick_watchdog();
        wait_ms = gps_model_remaining_ms(deadline, 20u);
        if (wait_ms == 0) break;
        delay(wait_ms);
    }
    return false;
}

/* Bounded recovery via PIN_GPS_RESET_N (active-low, 10 kΩ pullup R18).
 * Failed command proof does not by itself prove a wedged receiver. This pulse
 * clears retained navigation state; re-sync and re-prove the model afterward. */
static bool gps_ublox_reset(void) {
    /* Shutdown recovery only; acquisition uses gps_startup_reset(). */
    gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);
    s_gps_diag.hardware_resets++;
    pinMode(PIN_GPS_RESET_N, OUTPUT);
    digitalWrite(PIN_GPS_RESET_N, LOW);     /* assert reset */
    delay(20);
    pinMode(PIN_GPS_RESET_N, INPUT);        /* release: pullup deasserts reset */
    gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);
    power_manager_kick_watchdog();
    delay(1000);                            /* let the module cold-boot */
    bool begin_ok = gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);
                                             /* re-sync to the fresh module */
    if (!begin_ok) s_gps_diag.begin_failures++;
    bool dyn_model_ok = begin_ok && gps_ublox_set_airborne_4g();
    gps_freshness_reset(&pvt_freshness);
    power_manager_kick_watchdog();
    return begin_ok && dyn_model_ok;
}

gps_recovery_result_t gps_ublox_prepare_acquisition(void) {
    /* Public compatibility entry. Production init/get_fix use the supervised
     * release below so their entry deadline also covers cold boot and begin. */
    if (gps_quiescence_state != GPS_QUIESCENCE_RESET_HELD) {
        return GPS_RECOVERY_ALREADY_RELEASED;
    }

    /* Keep PA0 low unless the rail can pay for a cold module start and host
     * re-sync. A caller cannot accidentally wake a held receiver merely by
     * sending UART bytes at the ordinary acquisition floor. */
    if (!gps_backup_containment_release_allowed(power_adc_read_vSTOR_mv())) {
        s_gps_diag.reset_release_denied_low_rail++;
        return GPS_RECOVERY_BLOCKED_LOW_RAIL;
    }

    s_gps_diag.reset_release_attempts++;
    pinMode(PIN_GPS_RESET_N, INPUT);        /* external R18 deasserts RESET_N */
    gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);
    power_manager_kick_watchdog();
    delay(1000);                            /* complete MAX-M10S cold boot */

    bool begin_ok = gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);
    if (!begin_ok) {
        s_gps_diag.begin_failures++;
        s_gps_diag.reset_release_failures++;
        gps_assert_reset_hold();
        gps_freshness_reset(&pvt_freshness);
        consecutive_no_fresh = 0;
        last_fix.valid = false;
        return GPS_RECOVERY_REINIT_FAILED_RESET_HELD;
    }

    /* AIRBORNE_4G is applied and read back by get_fix() immediately after its
     * UART wake edge. Here we prove only that releasing containment restored
     * the command path; duplicating the three-attempt model transaction would
     * spend the recovery bound twice. */
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    last_fix.valid = false;
    power_manager_kick_watchdog();
    return GPS_RECOVERY_RESET_RELEASED;
}

enum GpsStartupCancellation { GPS_STARTUP_ACTIVE, GPS_STARTUP_DEADLINE,
    GPS_STARTUP_POWER, GPS_STARTUP_MISSION, GPS_STARTUP_TRANSPORT };

struct GpsStartupContext {
    uint32_t deadline;
    GpsStartupCancellation cancelled = GPS_STARTUP_ACTIVE;
    uint32_t last_power_check = 0u;
    bool power_checked = false;
};

static bool gps_startup_allowed(GpsStartupContext& context, bool sample_power = false) {
    if (context.cancelled != GPS_STARTUP_ACTIVE) return false;
    if ((int32_t)(context.deadline - (uint32_t)millis()) <= 0) {
        context.cancelled = GPS_STARTUP_DEADLINE;
    } else if (power_manager_freefall_pending()) {
        context.cancelled = GPS_STARTUP_MISSION;
        s_gps_diag.mission_aborts++;
    } else if (sample_power || !context.power_checked ||
               (uint32_t)((uint32_t)millis() - context.last_power_check) >= 100u) {
        uint16_t rail = power_adc_read_vSTOR_mv();
        context.last_power_check = millis();
        context.power_checked = true;
        if (rail < GPS_ACQ_FLOOR_MV) {
            context.cancelled = GPS_STARTUP_POWER;
            s_gps_diag.power_aborts++;
        }
    }
    /* ADC conversion is synchronous: authority may change during it. */
    if (context.cancelled == GPS_STARTUP_ACTIVE) {
        if ((int32_t)(context.deadline - (uint32_t)millis()) <= 0)
            context.cancelled = GPS_STARTUP_DEADLINE;
        else if (power_manager_freefall_pending()) {
            context.cancelled = GPS_STARTUP_MISSION;
            s_gps_diag.mission_aborts++;
        }
    }
    return context.cancelled == GPS_STARTUP_ACTIVE;
}

static bool gps_startup_settle(GpsStartupContext& context, uint32_t ms) {
    const uint32_t start = millis();
    while ((uint32_t)((uint32_t)millis() - start) < ms) {
        if (!gps_startup_allowed(context)) return false;
        power_manager_kick_watchdog();
        delay(1u);
    }
    return gps_startup_allowed(context);
}

static bool gps_startup_bind(GpsStartupContext& context) {
    if (!gps_startup_allowed(context)) return false;
    /* Pinned begin() does not stop after allocation failure before its poll. */
    if (gnss.configuration_packet().payload == nullptr &&
        !gnss.setPacketCfgPayloadSize(MAX_PAYLOAD_SIZE)) {
        context.cancelled = GPS_STARTUP_TRANSPORT;
        s_gps_diag.begin_failures++;
        return false;
    }
    /* Initialize library storage and bind the bus without its three implicit
     * connection polls. The bounded stream rejects writes and reads until a
     * caller explicitly opens a transaction. Connection proof follows below. */
    gps_gnss_stream.begin_position_phase();
    (void)gnss.begin(gps_gnss_stream, 0u);
    gps_gnss_stream.end_position_phase();
    return gnss.configuration_packet().payload != nullptr &&
        gps_startup_allowed(context);
}

static bool gps_startup_wake(GpsStartupContext& context) {
    if (!gps_startup_allowed(context, true)) return false;
    gps_gnss_stream.begin_position_phase();
    bool sent = gps_gnss_stream.begin_poll_write(2u);
    if (sent) {
        const uint8_t wake[] = {0xff, 0xff};
        (void)gps_gnss_stream.write(wake, sizeof(wake));
        sent = gps_gnss_stream.finish_poll_write();
    }
    gps_gnss_stream.end_position_phase();
    if (!sent) {
        context.cancelled = GPS_STARTUP_TRANSPORT;
        return false;
    }
    gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);
    /* At 9600 baud the admitted two-byte write plus ten milliseconds settling
     * fit here without a blocking UART flush. */
    return gps_startup_settle(context, 13u);
}

static bool gps_startup_response(GpsStartupContext& context, uint8_t request_id,
                                 uint32_t deadline, uint32_t key,
                                 uint8_t* value) {
    auto& packet = gnss.configuration_packet();
    auto& ack = gnss.acknowledgement_packet();
    while ((int32_t)(deadline - (uint32_t)millis()) > 0 &&
           gps_startup_allowed(context)) {
        gps_gnss_stream.begin_read_slice(5u, 16u);
        (void)gnss.checkUblox(UBX_CLASS_CFG, request_id);
        gps_gnss_stream.finish_read_slice();
        if (!gps_startup_allowed(context) ||
            (int32_t)(deadline - (uint32_t)millis()) <= 0) return false;
        if (request_id == UBX_CFG_VALGET &&
            packet.valid == SFE_UBLOX_PACKET_VALIDITY_VALID &&
            packet.classAndIDmatch == SFE_UBLOX_PACKET_VALIDITY_VALID &&
            packet.cls == UBX_CLASS_CFG && packet.id == UBX_CFG_VALGET &&
            packet.len == 9u && packet.payload[0] == 1u &&
            packet.payload[1] == 0u && packet.payload[2] == 0u &&
            packet.payload[3] == 0u) {
            uint32_t returned_key = (uint32_t)packet.payload[4] |
                ((uint32_t)packet.payload[5] << 8) |
                ((uint32_t)packet.payload[6] << 16) |
                ((uint32_t)packet.payload[7] << 24);
            if (returned_key == key) {
                *value = packet.payload[8];
                return true;
            }
        }
        if (ack.valid == SFE_UBLOX_PACKET_VALIDITY_VALID && ack.len == 2u &&
            ack.cls == UBX_CLASS_ACK && ack.payload[0] == UBX_CLASS_CFG &&
            ack.payload[1] == request_id) {
            if (ack.id == UBX_ACK_NACK) return false;
            if (request_id == UBX_CFG_VALSET && ack.id == UBX_ACK_ACK) return true;
        }
        packet.valid = packet.classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED;
        ack.valid = ack.classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED;
        power_manager_kick_watchdog();
        delay(1u);
    }
    /* The response deadline can end the loop before its authority predicate. */
    (void)gps_startup_allowed(context);
    return false;
}

static bool gps_startup_config(GpsStartupContext& context, uint8_t id,
                               uint32_t key, uint8_t* value, uint32_t wait_ms) {
    if (!gps_startup_allowed(context, true) || wait_ms == 0u) return false;
    const uint32_t start = millis();
    const uint32_t remaining = context.deadline - start;
    const uint32_t deadline = start + (wait_ms < remaining ? wait_ms : remaining);
    /* Discard already-buffered replies before opening a new request. UBX CFG
     * has no transaction identifier; an old same-key response must not satisfy
     * a new proof just because its parser validity flags were left set. */
    gps_gnss_stream.begin_position_phase();
    bool buffered = true;
    while (buffered && gps_startup_allowed(context) &&
           (int32_t)(deadline - (uint32_t)millis()) > 0) {
        gps_gnss_stream.begin_read_slice(5u, 16u);
        buffered = gps_gnss_stream.available() > 0;
        (void)gnss.checkUblox(0u, 0u);
        gps_gnss_stream.finish_read_slice();
        if (buffered) delay(1u);
    }
    gps_gnss_stream.end_position_phase();
    if (!gps_startup_allowed(context) ||
        (int32_t)(deadline - (uint32_t)millis()) <= 0) return false;
    gnss.discard_partial_response();
    key &= ~UBX_CFG_SIZE_MASK;
    auto& packet = gnss.configuration_packet();
    auto& ack = gnss.acknowledgement_packet();
    packet.cls = UBX_CLASS_CFG;
    packet.id = id;
    packet.len = id == UBX_CFG_VALGET ? 8u : 9u;
    packet.startingSpot = 0u;
    packet.valid = packet.classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED;
    ack.valid = ack.classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED;
    packet.payload[0] = 0u;
    packet.payload[1] = id == UBX_CFG_VALGET ? 0u : VAL_LAYER_RAM_BBR;
    packet.payload[2] = packet.payload[3] = 0u;
    for (uint8_t i = 0; i < 4u; ++i) packet.payload[4u + i] = key >> (8u * i);
    if (id == UBX_CFG_VALSET) packet.payload[8] = *value;
    gps_gnss_stream.begin_position_phase();
    bool sent = gps_gnss_stream.begin_poll_write(packet.len + 8u);
    if (sent) {
        (void)gnss.sendCommand(&packet, 0u);
        sent = gps_gnss_stream.finish_poll_write();
    }
    bool received = false;
    if (!sent) context.cancelled = GPS_STARTUP_TRANSPORT;
    else received = gps_startup_response(context, id, deadline, key, value);
    gps_gnss_stream.end_position_phase();
    return received;
}

static bool gps_startup_model(GpsStartupContext& context) {
    const uint32_t start = millis();
    for (uint8_t attempt = 0; attempt < 3u && gps_startup_allowed(context); ++attempt) {
        const uint32_t elapsed = (uint32_t)millis() - start;
        if (elapsed >= GPS_MODEL_BUDGET_MS) break;
        uint32_t remaining = GPS_MODEL_BUDGET_MS - elapsed;
        uint32_t cap = attempt == 0 ? GPS_MODEL_FIRST_SET_WAIT_MS : GPS_DYNMODEL_MAX_WAIT_MS;
        uint8_t model = 255u;
        if (gps_startup_config(context, UBX_CFG_VALGET, UBLOX_CFG_NAVSPG_DYNMODEL,
                               &model, remaining < cap ? remaining : cap)) {
            if (model == GPS_DYNMODEL_AIRBORNE_4G) return true;
            model = GPS_DYNMODEL_AIRBORNE_4G;
            uint32_t used = (uint32_t)millis() - start;
            if (used >= GPS_MODEL_BUDGET_MS) break;
            remaining = GPS_MODEL_BUDGET_MS - used;
            if (gps_startup_config(context, UBX_CFG_VALSET, UBLOX_CFG_NAVSPG_DYNMODEL,
                                   &model, remaining)) {
                used = (uint32_t)millis() - start;
                if (used < GPS_MODEL_BUDGET_MS &&
                    gps_startup_config(context, UBX_CFG_VALGET, UBLOX_CFG_NAVSPG_DYNMODEL,
                                       &model, GPS_MODEL_BUDGET_MS - used) &&
                    model == GPS_DYNMODEL_AIRBORNE_4G) return true;
            }
        }
        s_gps_diag.dyn_model_failures++;
        const uint32_t used = (uint32_t)millis() - start;
        if (used >= GPS_MODEL_BUDGET_MS) break;
        remaining = GPS_MODEL_BUDGET_MS - used;
        if (!gps_startup_settle(context, remaining < 20u ? remaining : 20u)) break;
    }
    return false;
}

static bool gps_startup_connection(GpsStartupContext& context) {
    if (!gps_startup_bind(context)) return false;
    for (uint8_t attempt = 0; attempt < 3u && gps_startup_allowed(context); ++attempt) {
        uint8_t enabled = 0u;
        if (gps_startup_config(context, UBX_CFG_VALGET, UBLOX_CFG_UART1INPROT_UBX,
                               &enabled, GPS_BEGIN_MAX_WAIT_MS) && enabled == 1u) return true;
    }
    if (context.cancelled == GPS_STARTUP_ACTIVE) s_gps_diag.begin_failures++;
    return false;
}

static bool gps_startup_release(GpsStartupContext& context) {
    if (gps_quiescence_state != GPS_QUIESCENCE_RESET_HELD) return true;
    if (!gps_startup_allowed(context)) return false;
    uint16_t rail = power_adc_read_vSTOR_mv();
    if (!gps_startup_allowed(context)) return false;
    if (!gps_backup_containment_release_allowed(rail)) {
        s_gps_diag.reset_release_denied_low_rail++;
        context.cancelled = GPS_STARTUP_POWER;
        return false;
    }
    s_gps_diag.reset_release_attempts++;
    pinMode(PIN_GPS_RESET_N, INPUT);
    gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    last_fix.valid = false;
    if (!gps_startup_settle(context, 1000u) || !gps_startup_connection(context)) {
        if (context.cancelled == GPS_STARTUP_ACTIVE) {
            s_gps_diag.reset_release_failures++;
            gps_assert_reset_hold();
        }
        return false;
    }
    return true;
}

static bool gps_startup_reset(GpsStartupContext& context) {
    if (!gps_startup_allowed(context, true)) return false;
    s_gps_diag.hardware_resets++;
    gps_drive_reset_hold();
    gps_freshness_reset(&pvt_freshness);
    last_fix.valid = false;
    if (!gps_startup_settle(context, 20u)) return false;
    pinMode(PIN_GPS_RESET_N, INPUT);
    gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);
    return gps_startup_settle(context, 1000u) &&
        gps_startup_connection(context) && gps_startup_model(context);
}

static bool gps_init_supervised() {
    GpsStartupContext context{(uint32_t)millis() + 1020u +
        3u * GPS_BEGIN_MAX_WAIT_MS + GPS_MODEL_BUDGET_MS};
    GPS_SERIAL.begin(GPS_BAUD);
    bool held = gps_quiescence_state == GPS_QUIESCENCE_RESET_HELD;
    bool ok = gps_startup_bind(context) && gps_startup_release(context) &&
        (held || gps_startup_connection(context)) && gps_startup_model(context);
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    last_fix.valid = false;
    return ok;
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms,
                       bool allow_cold_extension) {
    if (!fix) return false;
    const uint32_t entered_ms = millis();
    uint32_t deadline = entered_ms + timeout_ms;
    const uint32_t cold_deadline = entered_ms + 180000u;
    /* A prior fix cannot guarantee warm reacquisition after a long sleep. */
    const bool extension_candidate = allow_cold_extension && timeout_ms == 30000u;
    GpsStartupContext startup{deadline};
    last_fix.valid = false;
    fix->valid = false;
    fix->satellites = 0;
    bool model_reset_performed = false;
    if (!gps_startup_allowed(startup) || !gps_startup_bind(startup) ||
        !gps_startup_release(startup) || !gps_startup_wake(startup)) {
        gps_freshness_reset(&pvt_freshness);
        return false;
    }
    if (!gps_startup_model(startup)) {
        if (startup.cancelled != GPS_STARTUP_ACTIVE || !gps_startup_allowed(startup)) {
            gps_freshness_reset(&pvt_freshness);
            return false;
        }
        model_reset_performed = true;
        if (!gps_startup_reset(startup)) {
            if (startup.cancelled == GPS_STARTUP_ACTIVE) s_gps_diag.dyn_model_terminal_failures++;
            gps_freshness_reset(&pvt_freshness);
            return false;
        }
    }

    /* A position poll is caller-owned: getPVT(0) only emits one request, then
     * bounded parser slices consume its response. Copy the completed packet
     * directly so none of the cached getters can issue a hidden poll. */
    static constexpr uint32_t GPS_PVT_RESPONSE_WAIT_MS = 1100u;
    static constexpr uint32_t GPS_PVT_PARSER_SLICE_MS = 5u;
    static constexpr size_t GPS_PVT_PARSER_SLICE_BYTES = 16u;
    static constexpr size_t GPS_PVT_POLL_BYTES = 8u;
    uint32_t acquisition_started = millis();
    uint32_t last_kick = millis();
    uint32_t last_power_check = last_kick;
    uint32_t last_pvt_ms = acquisition_started;
    uint32_t last_epoch_progress_ms = acquisition_started;
    bool module_responded = false;          /* did the module answer at all this cycle? */
    bool last_pvt_time_valid = false;      /* provisional time is acquisition, not a wedge */
    bool itow_advanced = false;             /* did any answer carry a NEW epoch? */
    bool power_aborted = false;             /* rail fell below acquisition floor */
    bool mission_aborted = false;           /* freefall needs the radio/GPS now */
    bool dyn_model_aborted = false;         /* reset could not prove AIRBORNE_4G */
    bool transport_aborted = false;         /* poll could not be queued completely */
    bool inline_reset_attempted = model_reset_performed;
                                             /* at most one PA0 reset per energy-bounded poll */
    bool epoch_anchor_available = pvt_freshness.anchored;
    gps_freshness_t raw_progress = {0u, false};
    uint8_t raw_time_quality = 0u;
    bool raw_advanced = false;
    uint32_t raw_progress_ms = acquisition_started;
    bool extended = false;
    bool extension_progress_aborted = false;
    auto recent_progress = [&]() {
        const uint32_t now = millis();
        /* An admitted window may bridge a time-domain re-anchor only within
         * the existing progress grace. Re-anchoring never refreshes its age. */
        return (raw_advanced || extended) &&
            now - raw_progress_ms < GPS_FROZEN_EPOCH_RESET_MS &&
            now - last_pvt_ms < GPS_PVT_SILENCE_RESET_MS;
    };
    auto acquisition_budget_available = [&]() {
        if (extended && !recent_progress()) {
            extension_progress_aborted = true;
            return false;
        }
        if ((int32_t)(deadline - (uint32_t)millis()) > 0) return true;
        if (extended || !extension_candidate || inline_reset_attempted ||
            !recent_progress() ||
            (int32_t)(cold_deadline - (uint32_t)millis()) <= 0) return false;
        /* Requalify under the acquisition load, never from a cached boot or
         * solar-status reading. A failed attempt stays eligible next normal
         * cycle so temporary poor sky cannot permanently starve cold start. */
        const uint16_t rail = power_adc_read_vSTOR_mv();
        if (power_manager_freefall_pending()) {
            mission_aborted = true;
            return false;
        }
        if (rail < 4500u || !recent_progress() ||
            (int32_t)(cold_deadline - (uint32_t)millis()) <= 0) return false;
        extended = true;
        deadline = cold_deadline;
        last_power_check = millis();
        s_gps_diag.cold_extension_started++;
        return true;
    };
    while (acquisition_budget_available()) {
        /* Do not start a transaction after its launch authority has changed. */
        if (power_adc_read_vSTOR_mv() < (extended ? 4400u : GPS_ACQ_FLOOR_MV)) {
            power_aborted = true;
            break;
        }
        last_power_check = millis();
        if (power_manager_freefall_pending()) {
            mission_aborted = true;
            break;
        }
        if (!acquisition_budget_available()) break;

        UBX_NAV_PVT_data_t pvt_packet = {};
        bool pvt_received = false;
        gps_gnss_stream.begin_position_phase();
        if (!gps_gnss_stream.begin_poll_write(GPS_PVT_POLL_BYTES)) {
            gps_gnss_stream.end_position_phase();
            transport_aborted = true;
            break;
        }
        (void)gnss.getPVT(0u);
        if (!gps_gnss_stream.finish_poll_write() ||
            gnss.packetUBXNAVPVT == nullptr) {
            gps_gnss_stream.end_position_phase();
            transport_aborted = true;
            break;
        }
        gnss.packetUBXNAVPVT->moduleQueried.moduleQueried1.all = 0u;
        gnss.packetUBXNAVPVT->moduleQueried.moduleQueried2.all = 0u;

        const uint32_t response_started = millis();
        while (acquisition_budget_available() &&
               (uint32_t)((uint32_t)millis() - response_started) <
                   GPS_PVT_RESPONSE_WAIT_MS) {
            gps_gnss_stream.begin_read_slice(
                GPS_PVT_PARSER_SLICE_MS, GPS_PVT_PARSER_SLICE_BYTES);
            (void)gnss.checkUblox(UBX_CLASS_NAV, UBX_NAV_PVT);
            gps_gnss_stream.finish_read_slice();
            /* Parser execution can cross the hard deadline or the last
             * progress grace. A late packet must not renew expired authority. */
            if (!acquisition_budget_available()) break;
            if (gnss.packetUBXNAVPVT->moduleQueried.moduleQueried1.bits.all) {
                pvt_packet = gnss.packetUBXNAVPVT->data;
                gnss.packetUBXNAVPVT->moduleQueried.moduleQueried1.all = 0u;
                gnss.packetUBXNAVPVT->moduleQueried.moduleQueried2.all = 0u;
                pvt_received = true;
            }

            uint32_t response_now = millis();
            if (response_now - last_power_check >= 1000u) {
                last_power_check = response_now;
                if (power_adc_read_vSTOR_mv() < (extended ? 4400u : GPS_ACQ_FLOOR_MV)) {
                    power_aborted = true;
                }
            }
            if (!power_aborted && power_manager_freefall_pending()) {
                mission_aborted = true;
            }
            if (power_aborted || mission_aborted || pvt_received) break;
            if (!acquisition_budget_available()) break;
            delay(1u);
        }
        gps_gnss_stream.end_position_phase();
        if (power_aborted || mission_aborted) break;
        /* A synchronous response-time ADC check must not let a previously
         * copied packet refresh progress after its allowance has expired. */
        if (!acquisition_budget_available()) break;

        if (pvt_received) {
            module_responded = true;        /* alive, sent a PVT (with or without a fix) */
            last_pvt_ms = millis();
            uint32_t itow = pvt_packet.iTOW;
            /* MAX-M10S integration manual 3.7.3-3.7.5: startup time can use
             * provisional offsets. Anchor only after date/time are valid so
             * the first real time solution cannot look like a backward week
             * jump. Do not require fullyResolved: leap-second information can
             * take minutes, while these flags already permit use of time. */
            last_pvt_time_valid = pvt_packet.valid.bits.validDate &&
                                  pvt_packet.valid.bits.validTime;
            /* Time can resolve before date and jump by more than half a GPS
             * week. Re-anchor either quality-bit change without treating it
             * as progress; require a later actual epoch advancement. */
            const uint8_t time_quality =
                (pvt_packet.valid.bits.validDate ? 1u : 0u) |
                (pvt_packet.valid.bits.validTime ? 2u : 0u);
            if (time_quality != raw_time_quality) {
                gps_freshness_reset(&raw_progress);
                raw_advanced = false;
                raw_time_quality = time_quality;
            }
            if (gps_freshness_observe(&raw_progress, itow)) {
                raw_advanced = true;
                raw_progress_ms = last_pvt_ms;
            }
            bool was_anchored = pvt_freshness.anchored;
            if (gps_freshness_observe_qualified(
                    &pvt_freshness, itow, last_pvt_time_valid)) {
                itow_advanced = true;               /* nav engine is actually running */
                epoch_anchor_available = true;
                last_epoch_progress_ms = last_pvt_ms;
                uint8_t siv = pvt_packet.numSV;
                if (pvt_packet.flags.bits.gnssFixOK && siv >= 4) {
                    gps_pvt_values_t pvt = {
                        pvt_packet.lat,
                        pvt_packet.lon,
                        pvt_packet.height,
                        pvt_packet.gSpeed,
                        pvt_packet.headMot,
                        siv,
                    };
                    gps_wire_fix_t wire = {};
                    if (gps_pvt_to_wire_fix(&pvt, &wire)) {
                        /* Parser work and ADC sampling can outlive an earlier
                         * authority check. Recheck immediately before publish. */
                        if (power_adc_read_vSTOR_mv() < (extended ? 4400u : GPS_ACQ_FLOOR_MV)) {
                            power_aborted = true;
                            break;
                        }
                        if (power_manager_freefall_pending()) {
                            mission_aborted = true;
                            break;
                        }
                        if (!acquisition_budget_available()) {
                            break;
                        }
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
            } else if (!last_pvt_time_valid) {
                /* A responding receiver still acquiring time is not frozen.
                 * UART silence remains independently bounded below. */
                epoch_anchor_available = false;
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
        if (!acquisition_budget_available()) break;
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
        if (!extended && !inline_reset_attempted &&
            gps_recovery_due(epoch_anchor_available, now,
                             last_epoch_progress_ms, last_pvt_ms)) {
            if (!gps_startup_reset(startup)) {
                if (startup.cancelled == GPS_STARTUP_ACTIVE) s_gps_diag.dyn_model_terminal_failures++;
                gps_freshness_reset(&pvt_freshness);
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
        delay(100u);
    }

    /* No fresh, usable fix this cycle -> report NOGPS.  Invalidate the cache so
     * nothing downstream can resurrect a stale fix. */
    last_fix.valid  = false;
    fix->valid      = false;
    fix->satellites = 0;
    if (extended) {
        if (power_aborted || mission_aborted || transport_aborted ||
            extension_progress_aborted) s_gps_diag.cold_extension_aborted++;
        else s_gps_diag.cold_extension_exhausted++;
    }

    /* A rail-driven abort is not evidence of a wedged navigation engine.
     * Reset the epoch anchor because the interval before the next observed PVT
     * is now unbounded, and do not advance the hardware-reset ladder. */
    if (power_aborted || mission_aborted || dyn_model_aborted ||
        transport_aborted || extension_progress_aborted) {
        if (power_aborted) {
            s_gps_diag.power_aborts++;
            gps_freshness_reset(&pvt_freshness);
        }
        if (mission_aborted) s_gps_diag.mission_aborts++;
        if (transport_aborted || extension_progress_aborted)
            gps_freshness_reset(&pvt_freshness);
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
    if (gps_stale_ladder_step(module_responded &&
                              (itow_advanced || !last_pvt_time_valid),
                              inline_reset_attempted,
                              (uint8_t)GPS_STALE_RECOVERY_CYCLES,
                              &consecutive_no_fresh)) {
        (void)gps_startup_reset(startup);
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

static bool gps_uart_discard_buffered_input(uint32_t deadline) {
    while (GPS_SERIAL.available() > 0) {
        if ((int32_t)(deadline - (uint32_t)millis()) <= 0) return false;
        (void)GPS_SERIAL.read();
        power_manager_kick_watchdog();
    }
    return (int32_t)(deadline - (uint32_t)millis()) > 0;
}

static bool gps_wait_for_nav_eoe_marker(uint32_t deadline) {
    gps_backup_marker_parser_t parser;
    gps_backup_marker_reset(&parser);
    uint32_t last_kick = millis();
    while ((int32_t)(deadline - millis()) > 0) {
        while (GPS_SERIAL.available() > 0) {
            if ((int32_t)(deadline - (uint32_t)millis()) <= 0) return false;
            const int byte = GPS_SERIAL.read();
            if ((int32_t)(deadline - (uint32_t)millis()) <= 0) return false;
            if (byte >= 0 && gps_backup_marker_feed(&parser, (uint8_t)byte)) {
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

static_assert(GPS_BACKUP_CONFIG_BUDGET_MS > 0u &&
              GPS_BACKUP_CONFIG_BUDGET_MS <= UINT16_MAX,
              "GNSS configuration budget must fit the library wait argument");
static_assert(GPS_BACKUP_MARKER_WAIT_MS > 0u &&
              GPS_BACKUP_MARKER_WAIT_MS <= INT32_MAX - GPS_BACKUP_CONFIG_BUDGET_MS,
              "GNSS combined marker deadline must be wrap-safe");

static uint16_t gps_backup_config_remaining_ms(uint32_t deadline) {
    const int32_t remaining = (int32_t)(deadline - (uint32_t)millis());
    return remaining > 0 ? (uint16_t)remaining : 0;
}

static bool gps_configure_backup_marker(void) {
    const uint32_t deadline = millis() + GPS_BACKUP_CONFIG_BUDGET_MS;
    /* A timed-out position read may still own packetCfg. Finish that frame
     * before a setter reuses the buffer; discarding its framing can mistake
     * binary payload bytes for a new message and swallow the following ACK. */
    gps_gnss_stream.begin_position_phase();
    while (!gnss.parser_idle() && gps_backup_config_remaining_ms(deadline) != 0) {
        gps_gnss_stream.begin_read_slice(5u, 1u);
        const bool buffered = gps_gnss_stream.available() > 0;
        (void)gnss.checkUblox(0u, 0u);
        gps_gnss_stream.finish_read_slice();
        power_manager_kick_watchdog();
        if (!buffered) delay(1u);
    }
    gps_gnss_stream.end_position_phase();
    if (!gnss.parser_idle() || gps_backup_config_remaining_ms(deadline) == 0) {
        return false;
    }
    uint16_t wait_ms;
    /* Each remaining-time check also rejects an ACK returned after the
     * preceding synchronous call overran the deadline. Never pass zero:
     * SparkFun treats that as transmit-without-waiting, not an expired wait. */
    return (wait_ms = gps_backup_config_remaining_ms(deadline)) != 0 &&
        gnss.setVal8(UBLOX_CFG_UART1OUTPROT_UBX, 1, VAL_LAYER_RAM, wait_ms) &&
        (wait_ms = gps_backup_config_remaining_ms(deadline)) != 0 &&
        gnss.setVal8(UBLOX_CFG_UART1OUTPROT_NMEA, 0, VAL_LAYER_RAM, wait_ms) &&
        (wait_ms = gps_backup_config_remaining_ms(deadline)) != 0 &&
        gnss.setVal16(UBLOX_CFG_RATE_MEAS, 100, VAL_LAYER_RAM, wait_ms) &&
        (wait_ms = gps_backup_config_remaining_ms(deadline)) != 0 &&
        gnss.setVal16(UBLOX_CFG_RATE_NAV, 1, VAL_LAYER_RAM, wait_ms) &&
        (wait_ms = gps_backup_config_remaining_ms(deadline)) != 0 &&
        gnss.setVal8(UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1, 1, VAL_LAYER_RAM, wait_ms) &&
        gps_backup_config_remaining_ms(deadline) != 0;
}

gps_quiescence_result_t gps_ublox_quiesce(void) {
    /* Do not wake a receiver which this boot has already positively placed in
     * software standby. This makes the belt-and-braces low-tier call sites
     * genuinely free instead of waking the GNSS merely to put it back down. */
    if (gps_quiescence_state ==
        GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY) {
        return GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY;
    }
    /* A repeated belt-and-braces call must not release terminal containment.
     * Only gps_ublox_prepare_acquisition(), with its rail gate and begin()
     * proof, is allowed to do that. */
    if (gps_quiescence_state == GPS_QUIESCENCE_RESET_HELD) {
        s_gps_diag.reset_hold_reuses++;
        return GPS_QUIESCENCE_RESET_HELD;
    }

    for (uint8_t attempt = 1; attempt <= GPS_BACKUP_MAX_ATTEMPTS; ++attempt) {
        /* If the receiver was already in software standby but the local state
         * was lost/uncertain, PMREQ's first byte would only be a wake edge and
         * the frame could be discarded during the ~2 ms UART startup. Nudge,
         * flush, and settle before every bounded attempt. */
        GPS_SERIAL.write((uint8_t)0xFF);
        GPS_SERIAL.write((uint8_t)0xFF);
        GPS_SERIAL.flush();
        delay(10);
        gps_set_quiescence_state(GPS_QUIESCENCE_UNCONTAINED);

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
        /* Preserve the existing aggregate allowance, but let first-marker
         * observation use configuration time that was not needed. The CFG
         * helper retains its own cap, including partial-frame completion. */
        const uint32_t marker_deadline = (uint32_t)millis() +
            GPS_BACKUP_CONFIG_BUDGET_MS + GPS_BACKUP_MARKER_WAIT_MS;
        bool marker_armed = gps_configure_backup_marker();

        bool activity_seen = false;
        if (marker_armed) {
            marker_armed = gps_uart_discard_buffered_input(marker_deadline) &&
                gps_wait_for_nav_eoe_marker(marker_deadline);
        }
        if (marker_armed) {
            marker_armed = gps_uart_discard_buffered_input(marker_deadline);
        }
        if (marker_armed) {
            /* A complete NAV-EOE establishes a clean frame boundary. Send
             * PMREQ before the next 100 ms marker is due. maxWait=0 sends the
             * input-only command without inventing an ACK wait; hardware flush
             * proves every UART bit shifted before passive observation. */
            (void)gnss.powerOffWithInterrupt(
                0, VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, true, 0);
            GPS_SERIAL.flush();
            activity_seen =
                gps_uart_activity_seen((uint32_t)GPS_BACKUP_CONFIRM_MS);
        }

        gps_backup_action_t action =
            gps_backup_decide(marker_armed, activity_seen, attempt);
        if (action == GPS_BACKUP_CONFIRMED) {
            gps_set_quiescence_state(
                GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY);
            s_gps_diag.backup_confirmations++;
            return GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY;
        }

        s_gps_diag.backup_failures++;
        power_manager_kick_watchdog();
        if (action == GPS_BACKUP_RETRY_RESET) {
            /* A continued marker or a failed marker configuration means the
             * receiver state is not safely known. PA0 reset restores a bounded
             * command path before the next confirmation attempt. Do not spend
             * that cold-boot/reconfiguration energy out of the mission's last
             * rail reserve: the receiver has already received one PMREQ
             * attempt, and main will retry at the next normal scheduled cycle
             * with optional radios off. */
            if (!gps_backup_reset_allowed(power_adc_read_vSTOR_mv())) {
                break;
            }
            (void)gps_ublox_reset();
        }
    }

    /* Software standby is still unproven, so do not hide an awake ~25 mA
     * receiver behind a normal 1200 s STOP1 interval. PA0 is the only available
     * board actuator: assert it and deliberately retain the output-low state
     * through STOP1. The exact reset-held current remains unqualified and is a
     * launch gate even though the receiver is no longer left awake. */
    s_gps_diag.backup_terminal_failures++;
    gps_assert_reset_hold();
    return GPS_QUIESCENCE_RESET_HELD;
}

gps_quiescence_result_t gps_ublox_current_quiescence(void) {
    return gps_quiescence_state;
}

void gps_ublox_get_containment_diag(gps_containment_diag_t* diag) {
    if (!diag) return;
    diag->confirmed_software_standby = s_gps_diag.backup_confirmations;
    diag->early_reset_hold_entries = s_gps_diag.early_reset_hold_entries;
    diag->reset_hold_entries = s_gps_diag.reset_hold_entries;
    diag->reset_hold_reuses = s_gps_diag.reset_hold_reuses;
    diag->reset_release_attempts = s_gps_diag.reset_release_attempts;
    diag->reset_release_denied_low_rail =
        s_gps_diag.reset_release_denied_low_rail;
    diag->reset_release_failures = s_gps_diag.reset_release_failures;
    diag->current_state = s_gps_diag.containment_state;
}

bool gps_ublox_sleep(void) {
    gps_quiescence_result_t result = gps_ublox_quiesce();
    return result == GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY ||
           result == GPS_QUIESCENCE_NOT_PRESENT;
}

#else

void gps_ublox_assert_reset_early(void) {
}

bool gps_ublox_init(void) {
    last_fix.valid = false;
    return true;
}

bool gps_ublox_set_airborne_4g(void) {
    return true;
}

bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms,
                       bool allow_cold_extension) {
    (void)timeout_ms;
    (void)allow_cold_extension;
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

gps_quiescence_result_t gps_ublox_quiesce(void) {
    return GPS_QUIESCENCE_NOT_PRESENT;
}

gps_quiescence_result_t gps_ublox_current_quiescence(void) {
    return GPS_QUIESCENCE_NOT_PRESENT;
}

gps_recovery_result_t gps_ublox_prepare_acquisition(void) {
    return GPS_RECOVERY_NOT_PRESENT;
}

void gps_ublox_get_containment_diag(gps_containment_diag_t* diag) {
    if (!diag) return;
    *diag = {};
    diag->current_state = (uint32_t)GPS_QUIESCENCE_NOT_PRESENT;
}

bool gps_ublox_sleep(void) {
    /* No-op when GNSS is compiled out. */
    return true;
}

#endif /* GNSS_ENABLE */
