#!/usr/bin/env python3
"""Run the real flight primary/Class-A/aux scheduler with hardware boundaries.

This is not MCU emulation: ADC/radio/persistence/window time are controlled.
The complete primary gate and the complete subsequent optional-service gates
come from main.cpp, including all nested preprocessor branches. The intervening
sleep/lease accounting is outside this test; its resulting budgets are inputs.
Real liveness transitions, wrappers, confirmed-send transaction, complete
Class-A receive function, CTT queue and CTT encoding are executed. Controlled
radio/frame-decoder boundaries do not manufacture RX health or revoke proof.

Mutants alter only the temporary compilation input, never firmware files. Each
must compile and fail a specific behavioral assertion, not merely fail to build.
"""

from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def block(source: str, opening: str) -> str:
    start = source.index(opening)
    brace = source.index("{", start)
    depth = 0
    for end in range(brace, len(source)):
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
            if depth == 0:
                return source[start:end + 1]
    raise AssertionError(f"unterminated production block: {opening}")


def replace_once(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, f"mutation target changed: {old}"
    return source.replace(old, new, 1)


def harness() -> str:
    main = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
    radio = (ROOT / "firmware/src/lorawan.cpp").read_text(encoding="utf-8")
    voltage_start = main.index("bool vstor_ok_for_tx =")
    primary = main[voltage_start:main.index(";", voltage_start) + 1] + "\n" + block(
        main, "if (!suppress_optional_after_recovery &&\n        power_adc_can_tx()")
    windows_start = main.index("#if defined(CTT_LISTEN_ENABLE) && CTT_LISTEN_ENABLE\n    /* Bird/bat")
    windows = main[windows_start:main.index("    /* Quiesce the radio before MCU STOP1", windows_start)]
    callback = block(main, "static bool complete_server_probe_before_rx_return(")
    receive = block(radio, "lorawan_class_a_result_t lorawan_receive_downlink_result(")
    wrappers = "\n".join(block(radio, name) for name in (
        "bool lorawan_send_uplink_port(",
        "bool lorawan_send_uplink(",
        "bool lorawan_server_probe_due(",
        "bool lorawan_server_note_ordinary_primary(",
        "bool lorawan_server_abandon_probe(",
        "lorawan_liveness_event_t lorawan_server_complete_probe(",
        "bool lorawan_server_recovery_due(",
        "bool lorawan_server_session_proven(",
        "bool lorawan_send_confirmed_uplink(",
        "bool lorawan_joined("))
    return r'''
#include "config.h"
#include "lorawan.h"
#include "lorawan_frame.h"
#include "ctt_event.h"
#include "ctt_queue.h"
#include "power_adc.h"
#include "gps_ublox.h"
#include "telemetry.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#define LOG(...) ((void)0)
enum class Tx { Success, RadioFailure, ReservationFailure };
enum class Rx { Empty, Authenticated, PhyFailure, PersistenceFailure,
                AuthenticatedRestoreFailure, MissionAbort, ReadFailure };
static struct Inputs {
    Tx primary = Tx::Success, auxiliary = Tx::Success;
    Rx rx = Rx::Empty;
    uint16_t before_mv = 4660, after_mv = 4660, solar_mv = 3100;
    power_tier_t before_tier = POWER_TIER_FULL, after_tier = POWER_TIER_FULL;
    bool can_tx = true, legal_before = true, legal_after = true;
    bool gnss_authority = true, freefall = false, post_rx_freefall = false;
    bool post_rx_sag = false;
    bool fresh_fix = true, burst = false, optical_fault = false;
    bool known_region = true, recovered = false, relay_enabled = true;
    gps_quiescence_result_t gps = GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY;
    uint32_t sleep_ms = 120000, region_budget_ms = 90000;
    uint32_t ctt_used = 10000, relay_used = 20000;
    bool command_payload = false, liveness_save_fail = false;
} in;
static std::vector<std::string> events;
static std::vector<uint8_t> ports, last_aux_payload;
static lorawan_liveness_state_t s_liveness_state;
static lorawan_liveness_diag_t s_liveness_diag;
static bool _joined, tx_done, rx_done, primary_transaction_ok;
static bool s_optical_quiescence_fault, region_known, aux_prefer_b2b;
static uint8_t aux_uplink_cooldown, tx_fail_streak;
static uint32_t s_reported_relay_fwd, s_reported_ctt_tags;
static ctt_queue_t ctt;
static bool b2b_pending;
static unsigned b2b_acks, resets, recoveries, command_calls;
static uint8_t recovery_entry_misses;
static uint32_t observed_sleep, observed_region_budget, ctt_budget, relay_budget;
static bool observed_meshtastic;
static unsigned failures, checks;
static const char* scenario;
static void expect(bool ok, const char* contract) {
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL %s: %s\n", scenario, contract); }
}
static size_t at(const char* event) {
    return static_cast<size_t>(std::find(events.begin(), events.end(), event) - events.begin());
}
static bool seen(const char* event) { return at(event) < events.size(); }
uint16_t power_adc_read_vSTOR_mv() {
    if (rx_done && in.post_rx_sag) return 2999;
    return tx_done ? in.after_mv : in.before_mv;
}
uint16_t power_adc_read_solar_mv() { return in.solar_mv; }
power_tier_t power_adc_get_tier() {
    if (rx_done && in.post_rx_sag) return POWER_TIER_EMERGENCY;
    return tx_done ? in.after_tier : in.before_tier;
}
bool power_adc_can_tx() { return in.can_tx; }
static bool power_manager_freefall_pending() {
    return in.freefall || (rx_done && in.post_rx_freefall);
}
static uint32_t power_manager_monotonic_seconds() { return 6000u; }
static bool region_authority_is_gnss() { return in.gnss_authority; }
static bool region_tx_allowed_now(uint32_t) {
    // Preserve the real helper's side effect on a lease expiring mid-cycle.
    if (!(rx_done ? in.legal_after : in.legal_before)) region_known = false;
    return region_known;
}
static void NVIC_SystemReset() { ++resets; events.push_back("reset"); }
static void fail_session_persistence() {
    _joined = false;
    lorawan_liveness_begin_session(&s_liveness_state);
    events.push_back("session-retired");
}
static void retire_invalid_liveness_session() { fail_session_persistence(); }
static bool persist_current_session() {
    events.push_back("liveness-commit");
    if (in.liveness_save_fail) { fail_session_persistence(); return false; }
    return _joined;
}
// Literal send boundary: failed reservation never hands RF a frame; radio
// failure may follow a durable reservation. No scheduler logic lives here.
static bool send_uplink_port_mode(uint8_t port, const uint8_t* data, uint8_t len,
                                 bool, bool* reserved) {
    if (reserved) *reserved = false;
    const bool primary = port == 1u;
    Tx outcome = primary ? in.primary : in.auxiliary;
    events.push_back(primary ? "primary-reserve" : "aux-reserve");
    if (outcome == Tx::ReservationFailure) {
        fail_session_persistence();
        return false;
    }
    if (reserved) *reserved = true;
    events.push_back(primary ? "primary-rf" : "aux-rf");
    ports.push_back(port);
    if (!primary) last_aux_payload.assign(data, data + len);
    if (outcome == Tx::RadioFailure) return false;
    if (primary) tx_done = true;
    return true;
}
''' + wrappers + r'''

static bool recover_stale_server_session(uint32_t, bool) {
    ++recoveries; events.push_back("recover");
    recovery_entry_misses = s_liveness_state.qualified_miss_streak;
    fail_session_persistence();
    return false;
}
struct server_probe_completion_context_t {
    lorawan_liveness_qualification_t* qualification;
    uint32_t cycle_started_ms;
    lorawan_liveness_event_t* event;
};
''' + callback + r'''

// Radio/timer/decode boundaries for the complete production Class-A function.
// Frame cryptography has separate strict host suites. Here the decoder emits
// one authenticated frame only when explicitly injected, with a real counter.
static lorawan_downlink_stats_t s_dl_stats;
static struct {
    unsigned rx1_mod = 8, tx_sf = 9, rx1_bw = 500, tx_ch_count = 1;
    float rx1_base = 923.3f, rx1_step = 0.6f, tx_freqs[1] = {904.3f};
    float rx2_freq = 923.3f; unsigned rx2_sf = 12, rx2_bw = 500;
} REGION;
static bool radio_ready = true, s_dl_rx;
static uint32_t now_ms, s_tx_end_ms, fCntDown, devAddr;
static uint8_t s_tx_ch, s_rx_delay_s = 5, nwkSKey[16], appSKey[16];
static constexpr unsigned RADIOLIB_SX126X_SYNC_WORD_PUBLIC = 0x34;
static bool radio_apply_lora_phy(float, unsigned, unsigned, unsigned, int, bool, bool) {
    return in.rx != Rx::PhyFailure;
}
static bool restore_lorawan_or_reset() {
    events.push_back("phy-restored");
    return in.rx != Rx::AuthenticatedRestoreFailure;
}
static uint32_t millis() { return now_ms; }
static bool radio_wait_until(uint32_t since, uint32_t offset) {
    if (!rx_done) events.push_back("class-a");
    rx_done = true;
    now_ms = since + offset;
    return in.rx != Rx::MissionAbort;
}
static size_t rx_window(uint8_t* bytes, size_t, uint32_t deadline, int16_t* state,
                        bool* aborted, bool* fault) {
    *state = 0; *aborted = false; *fault = in.rx == Rx::ReadFailure;
    now_ms = deadline;
    bytes[0] = 0x60;
    return in.rx == Rx::Authenticated || in.rx == Rx::AuthenticatedRestoreFailure ||
           in.rx == Rx::PersistenceFailure ? 1 : 0;
}
bool lorawan_frame_decode_downlink(const uint8_t*, const uint8_t*, uint32_t, uint32_t,
                                   const uint8_t*, size_t, lorawan_decoded_downlink_t* out,
                                   uint8_t* reject) {
    *reject = 0; *out = {}; out->ack = true; out->frame_counter = 41;
    if (in.command_payload) { out->fport = 10; out->len = 4; }
    return true;
}
void lorawan_export_session(lorawan_session_t* out) { *out = {}; }
static bool power_manager_save_session(const lorawan_session_t*) {
    if (in.rx == Rx::PersistenceFailure) return false;
    events.push_back("downlink-commit");
    return true;
}
''' + receive + r'''
bool command_handle(const lorawan_downlink_t*) {
    ++command_calls; events.push_back("command"); return true;
}
bool command_relay_enabled() { return in.relay_enabled; }
bool lorawan_b2b_queue_command(const lorawan_downlink_t*) {
    events.push_back("b2b-command"); return true;
}
bool lorawan_ctt_peek_pending(ctt_detection_t* detection) { return ctt_queue_peek(&ctt, detection); }
void lorawan_ctt_ack_pending() { events.push_back("ctt-ack"); ctt_queue_ack(&ctt); }
bool lorawan_b2b_peek_pending_uplink(uint8_t* out, uint8_t cap, uint8_t* len) {
    if (!b2b_pending || cap < 3u) return false;
    out[0] = 0xB2; out[1] = 0x02; out[2] = 0x19; *len = 3;
    return true;
}
void lorawan_b2b_ack_pending_uplink() {
    events.push_back("b2b-ack"); b2b_pending = false; ++b2b_acks;
}
uint32_t lorawan_ctt_window(uint32_t budget, uint16_t floor) {
    events.push_back("ctt-window"); ctt_budget = budget;
    expect(floor == 4200u, "CTT floor stays 4200 mV");
    return in.ctt_used;
}
uint32_t lorawan_relay_window(uint32_t budget, uint16_t floor, bool enabled) {
    events.push_back("relay-window"); relay_budget = budget; observed_meshtastic = enabled;
    expect(floor == 4200u, "relay floor stays 4200 mV");
    return in.relay_used;
}
static void cycle() {
    const uint32_t cycle_started_ms = 0;
    bool suppress_optional_after_recovery = in.recovered;
    bool fresh_fix_this_cycle = in.fresh_fix, burst_mode = in.burst;
    gps_quiescence_result_t gps_quiescence = in.gps;
    const uint32_t cycle_relay_fwd_total = 12, cycle_ctt_tags_total = 34;
    uint8_t tx_payload[TELEMETRY_PAYLOAD_SIZE] = {};
    primary_transaction_ok = tx_done = rx_done = false;
    s_optical_quiescence_fault = in.optical_fault;
    region_known = in.known_region;
''' + primary + r'''
    uint32_t sleep_ms = in.sleep_ms, relay_region_budget_ms = in.region_budget_ms;
''' + windows + r'''
    observed_sleep = sleep_ms;
    observed_region_budget = relay_region_budget_ms;
}
static void reset(const char* name) {
    scenario = name; in = Inputs{};
    events.clear(); ports.clear(); last_aux_payload.clear();
    lorawan_liveness_begin_session(&s_liveness_state);
    lorawan_liveness_mark_server_proven(&s_liveness_state);
    s_liveness_diag = {}; s_dl_stats = {};
    _joined = true; tx_done = rx_done = false;
    radio_ready = true;
    now_ms = s_tx_end_ms = fCntDown = 0;
    s_reported_relay_fwd = s_reported_ctt_tags = 0;
    aux_uplink_cooldown = tx_fail_streak = 0; aux_prefer_b2b = false;
    ctt_queue_init(&ctt);
    ctt_detection_t detection = {};
    detection.id_raw = 0x12345678u; detection.rssi_best = -70;
    detection.hits = 3; detection.queued_min = 95;
    (void)ctt_queue_record(&ctt, &detection);
    b2b_pending = true; b2b_acks = resets = recoveries = command_calls = 0;
    recovery_entry_misses = 0;
    ctt_budget = relay_budget = observed_sleep = observed_region_budget = 0;
    observed_meshtastic = false;
}
static void closed() {
    expect(!seen("aux-reserve") && !seen("ctt-window") && !seen("relay-window"),
           "all optional services closed");
    expect(ctt_queue_count(&ctt) == 1 && b2b_pending && b2b_acks == 0,
           "closed gates preserve both event queues");
}
int main() {
    reset("healthy ordering and shared budget");
    in.rx = Rx::Authenticated; in.command_payload = true; cycle();
    expect(ports == std::vector<uint8_t>({1, 11}), "one CTT auxiliary, never both queues");
    expect(at("primary-rf") < at("class-a") && at("class-a") < at("aux-rf"),
           "primary Class-A precedes auxiliary RF");
    expect(at("downlink-commit") < at("command") && at("command") < at("aux-rf"),
           "authenticated command dispatch follows durable RX and precedes auxiliary");
    expect(at("aux-rf") < at("ctt-ack") && at("ctt-ack") < at("ctt-window") &&
           at("ctt-window") < at("relay-window"), "transaction then CTT then shared LongFast");
    expect(ctt_queue_count(&ctt) == 0 && b2b_pending && aux_uplink_cooldown == 7 && aux_prefer_b2b,
           "successful CTT commits queue cooldown and alternation");
    expect(last_aux_payload.size() == 17 && last_aux_payload[0] == 'C' &&
           last_aux_payload[1] == 'T' && last_aux_payload[4] == 0x12 &&
           last_aux_payload[16] == 5, "real CTT wire encoder receives queued detection and time");
    expect(ctt_budget == 60000 && relay_budget == 80000 && observed_sleep == 90000 &&
           observed_region_budget == 80000, "CTT elapsed subtracts from sleep and regional budgets");
    expect(s_reported_relay_fwd == 12 && s_reported_ctt_tags == 34, "primary success advances reports");

    for (Tx failure : {Tx::RadioFailure, Tx::ReservationFailure}) {
        reset(failure == Tx::RadioFailure ? "primary RF failure with old proof" : "primary reservation failure");
        in.primary = failure; cycle(); closed();
        expect(!seen("class-a") && !primary_transaction_ok && tx_fail_streak == 1,
               "failed primary cannot open Class-A or become a transaction");
        expect(s_reported_relay_fwd == 0 && s_reported_ctt_tags == 0, "failed primary preserves reports");
        expect((failure != Tx::ReservationFailure || !seen("primary-rf")), "reservation failure never reaches RF");
    }
    reset("fifth primary failure resets"); in.primary = Tx::RadioFailure; tx_fail_streak = 4; cycle();
    expect(resets == 1, "five failed primary transmissions reset");

    reset("unproven ordinary session"); lorawan_liveness_begin_session(&s_liveness_state);
    in.fresh_fix = false; cycle(); closed();
    reset("initial confirmed empty"); lorawan_liveness_begin_session(&s_liveness_state); cycle(); closed();
    expect(s_liveness_diag.confirmed_probe_tx == 1 && s_liveness_state.qualified_miss_streak == 1,
           "real confirmed transaction records one qualified miss");
    reset("confirmed ambiguity"); s_liveness_state.countdown = 0; in.rx = Rx::PhyFailure; cycle(); closed();
    expect(!s_liveness_state.server_proven && !s_liveness_state.probe_pending &&
           s_liveness_state.qualified_miss_streak == 0, "ambiguous confirmed probe is not a miss or proof");
    reset("third confirmed miss"); s_liveness_state.server_proven = false;
    s_liveness_state.countdown = 0; s_liveness_state.qualified_miss_streak = 2; cycle(); closed();
    expect(recoveries == 1 && recovery_entry_misses == 3 && !_joined,
           "third miss suppresses optional service before retiring suspect session");
    reset("authenticated first probe"); lorawan_liveness_begin_session(&s_liveness_state);
    in.rx = Rx::Authenticated; cycle();
    expect(s_liveness_state.server_proven && seen("aux-rf"), "authenticated probe opens optional service");
    reset("downlink persistence fault"); in.rx = Rx::PersistenceFailure; cycle(); closed();
    expect(!_joined && command_calls == 0, "uncommitted downlink cannot dispatch command");
    reset("ordinary countdown persistence fault"); in.liveness_save_fail = true; cycle(); closed();
    expect(!_joined && !s_liveness_state.server_proven, "failed countdown commit retires prior proof");

    // Historical proof remains durable while current-cycle health closes
    // optional service. Healthy next-cycle recovery must not need a new probe.
    {
        for (Rx fault : {Rx::PhyFailure, Rx::ReadFailure, Rx::MissionAbort,
                         Rx::AuthenticatedRestoreFailure}) {
            reset(fault == Rx::AuthenticatedRestoreFailure ? "authenticated restore fault" :
                  fault == Rx::MissionAbort ? "mission abort" : "ordinary RX local fault closes optional service");
            in.rx = fault; in.command_payload = true; cycle(); closed();
            expect(seen("primary-rf") && seen("class-a"), "RX fault follows successful primary");
            expect(s_liveness_state.server_proven && s_liveness_state.countdown == 23 &&
                   s_liveness_state.qualified_miss_streak == 0,
                   "transient unhealthy exchange preserves durable proof and sparse policy");
            expect(command_calls == (fault == Rx::AuthenticatedRestoreFailure ? 1u : 0u),
                   "authenticated unhealthy RX still delivers command exactly once");
            if (fault == Rx::AuthenticatedRestoreFailure) {
                expect(fCntDown == 42 && at("downlink-commit") < at("command"),
                       "authenticated unhealthy RX commits counter before command");
            }
            events.clear(); ports.clear(); in.rx = Rx::Empty; in.command_payload = false; cycle();
            expect(ports == std::vector<uint8_t>({1, 11}) && command_calls ==
                       (fault == Rx::AuthenticatedRestoreFailure ? 1u : 0u),
                   "next healthy cycle resumes queued auxiliary without command replay or new probe");
        }
    }

    reset("LAUNCH authority no GNSS"); in.gnss_authority = false; in.fresh_fix = false; cycle(); closed();
    expect(primary_transaction_ok && seen("class-a"), "LAUNCH still permits primary health/control");
    reset("leased GNSS authority without new fix"); in.fresh_fix = false; cycle();
    expect(seen("aux-rf"), "fresh PVT not required for auxiliary under live GNSS lease and proof");
    for (gps_quiescence_result_t gps : {GPS_QUIESCENCE_UNCONTAINED, GPS_QUIESCENCE_RESET_HELD, GPS_QUIESCENCE_NOT_PRESENT}) {
        reset("unqualified GNSS quiescence"); in.gps = gps; aux_uplink_cooldown = 3; cycle(); closed();
        expect(primary_transaction_ok && aux_uplink_cooldown == 3, "GNSS fault preserves primary and cooldown");
    }
    reset("optical fault"); in.optical_fault = true; aux_uplink_cooldown = 3; cycle(); closed();
    expect(primary_transaction_ok && aux_uplink_cooldown == 3, "optical fault preserves primary and cooldown");
    reset("burst"); in.burst = true; cycle(); closed(); expect(!seen("class-a"), "burst omits Class-A");
    reset("freefall pending"); in.freefall = true; cycle(); closed();
    reset("freefall during RX"); in.post_rx_freefall = true; cycle(); closed();
    reset("recovery already attempted"); in.recovered = true; cycle(); closed();
    expect(!seen("primary-reserve"), "same-cycle recovery never follows with a primary");
    reset("low initial rail"); in.before_mv = 2999; cycle(); closed();
    expect(tx_fail_streak == 0 && !seen("primary-reserve"), "low rail skips rather than fails primary");
    reset("unknown region"); in.known_region = false; cycle(); closed();
    reset("expired initial region"); in.legal_before = false; cycle(); closed();
    reset("post TX rail sag"); in.after_mv = 2999; in.after_tier = POWER_TIER_EMERGENCY; cycle(); closed();
    reset("post RX rail sag"); in.post_rx_sag = true; cycle(); closed();
    expect(seen("class-a"), "post RX rail sag actually occurs after Class-A starts");
    reset("post RX lease expiry"); in.legal_after = false; in.region_budget_ms = 0; cycle(); closed();
    reset("dark preserves queued event but closes long windows"); in.solar_mv = 2999; cycle();
    expect(seen("aux-rf") && !seen("ctt-window") && !seen("relay-window"), "solar gates listening not queued LoRaWAN events");
    reset("solar threshold and public relay disabled"); in.solar_mv = 3000; in.relay_enabled = false; cycle();
    expect(seen("ctt-window") && seen("relay-window") && !observed_meshtastic, "B2B shared window survives public relay disable");
    reset("reduced tier"); in.after_tier = POWER_TIER_REDUCED; cycle();
    expect(seen("class-a") && seen("aux-rf") && !seen("ctt-window") && !seen("relay-window"), "FULL only applies to long windows");
    reset("unattempted RX at low tier preserves existing aux policy");
    in.after_tier = POWER_TIER_NO_GPS; in.after_mv = 3300; cycle();
    expect(!seen("class-a") && seen("aux-rf") && !seen("ctt-window") && !seen("relay-window"),
           "unattempted low tier Class-A keeps 3.0V queued-event policy");
    reset("CTT exhausts regional budget"); in.region_budget_ms = 5000; cycle();
    expect(seen("ctt-window") && !seen("relay-window") && observed_region_budget == 0,
           "RX-only CTT may exhaust lease, never underflow relay airtime");
    reset("CTT exhausts sleep budget"); in.sleep_ms = 5000; in.ctt_used = 5000; cycle();
    expect(ctt_budget == 5000 && !seen("relay-window") && observed_sleep == 0, "short sleep budget saturates at zero");

    for (bool prefer_b2b : {false, true}) {
        reset(prefer_b2b ? "B2B failed auxiliary" : "CTT failed auxiliary");
        aux_prefer_b2b = prefer_b2b; in.auxiliary = Tx::RadioFailure; cycle();
        expect(ports.size() == 2 && ctt_queue_count(&ctt) == 1 && b2b_pending && b2b_acks == 0,
               "failed auxiliary retains queue and never tries other queue");
        expect(aux_uplink_cooldown == 0 && aux_prefer_b2b == prefer_b2b,
               "failed auxiliary preserves cooldown and alternation");
        events.clear(); ports.clear(); in.auxiliary = Tx::Success; cycle();
        expect(ports == std::vector<uint8_t>({1, static_cast<uint8_t>(prefer_b2b ? 12 : 11)}),
               "next healthy primary retries same queue");
        expect(aux_uplink_cooldown == 7 && aux_prefer_b2b != prefer_b2b, "successful retry commits shared allowance");
    }
    reset("both queues B2B priority"); aux_prefer_b2b = true; cycle();
    expect(ports == std::vector<uint8_t>({1, 12}) && ctt_queue_count(&ctt) == 1 && !b2b_pending,
           "B2B priority sends only one shared auxiliary frame");
    expect(last_aux_payload == std::vector<uint8_t>({0xB2, 0x02, 0x19}) && b2b_acks == 1,
           "B2B preserves queued bytes and acknowledges once");
    reset("auxiliary reservation failure"); in.auxiliary = Tx::ReservationFailure; cycle();
    expect(!seen("aux-rf") && ctt_queue_count(&ctt) == 1 && b2b_pending &&
           aux_uplink_cooldown == 0 && !aux_prefer_b2b && !_joined,
           "auxiliary reservation failure preserves queues and invalidates session");
    expect(!seen("ctt-window") && !seen("relay-window"), "failed auxiliary reservation closes later windows");
    reset("empty event queues"); ctt_queue_ack(&ctt); b2b_pending = false; cycle();
    expect(!seen("aux-reserve") && aux_uplink_cooldown == 0, "empty queues consume no shared allowance");
    reset("cooldown seven then next auxiliary"); cycle();
    for (unsigned n = 0; n < 7; ++n) {
        events.clear(); ports.clear(); cycle();
        expect(!seen("aux-reserve") && aux_uplink_cooldown == 6u - n,
               "seven qualified successful primary cycles decrement without auxiliary");
    }
    events.clear(); ports.clear(); cycle();
    expect(ports == std::vector<uint8_t>({1, 12}) && aux_uplink_cooldown == 7,
           "eighth later primary serves waiting B2B queue");
    for (Rx result : {Rx::Empty, Rx::Authenticated, Rx::PhyFailure, Rx::ReadFailure,
                      Rx::MissionAbort, Rx::PersistenceFailure, Rx::AuthenticatedRestoreFailure}) {
        reset("direct production receive health output"); in.rx = result;
        lorawan_downlink_t downlink = {};
        bool healthy = true; // Every fault must overwrite a caller's old true.
        lorawan_class_a_result_t received = lorawan_receive_downlink_result(
            &downlink, nullptr, nullptr, &healthy);
        expect(healthy == (result == Rx::Empty || result == Rx::Authenticated),
               "RX health reflects completed healthy exchange, never enum alone");
        if (result == Rx::AuthenticatedRestoreFailure) {
            expect(received == LORAWAN_CLASS_A_AUTHENTICATED && fCntDown == 42,
                   "authenticated unhealthy receive still commits and exposes authentication");
        }
    }
    reset("receive preflight health output"); radio_ready = false;
    lorawan_downlink_t downlink = {}; bool healthy = true;
    expect(lorawan_receive_downlink_result(&downlink, nullptr, nullptr, &healthy) ==
               LORAWAN_CLASS_A_AMBIGUOUS && !healthy,
           "unready radio clears caller health output");
    std::printf("%u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
'''


def main() -> None:
    source = harness()
    aux_start = source.index("#if (defined(CTT_LISTEN_ENABLE) && CTT_LISTEN_ENABLE) ||")
    aux_end = source.index("\n#endif\n        } else {", aux_start) + len("\n#endif")
    aux_block = source[aux_start:aux_end]
    early_aux = source[:aux_start] + source[aux_end:]
    early_aux = replace_once(early_aux, "lorawan_class_a_result_t rx_result =",
                             aux_block + "\n            lorawan_class_a_result_t rx_result =")
    # Main's event gate is nested in primary_sent; long service windows are not.
    mutants = [
        ("primary-result bypass", replace_once(source, "if (primary_sent) {", "if (true) { (void)primary_sent;"),
         "failed primary cannot open Class-A"),
        ("aux before Class-A", early_aux,
         "primary Class-A precedes auxiliary RF"),
        ("double auxiliary dispatch", replace_once(source, "} else if (ctt_pending) {", "} if (ctt_pending) {"),
         "B2B priority sends only one shared auxiliary frame"),
        ("failed CTT acknowledged", replace_once(source, "if (lorawan_send_uplink_port(CTT_EVENT_FPORT, event_payload,\n                                                 CTT_EVENT_PAYLOAD_SIZE)) {",
          "if ((lorawan_send_uplink_port(CTT_EVENT_FPORT, event_payload,\n                                                 CTT_EVENT_PAYLOAD_SIZE), true)) {"),
         "failed auxiliary retains queue"),
        ("cooldown shortened", replace_once(source, "(uint8_t)(AUX_UPLINK_INTERVAL_CYCLES - 1u);", "0;"),
         "successful CTT commits queue cooldown and alternation"),
        ("LAUNCH auxiliary bypass", replace_once(source, "} else if (!region_authority_is_gnss()) {", "} else if (false) {"),
         "FAIL LAUNCH authority no GNSS: all optional services closed"),
        ("idle primary gate removed", source.replace("if (primary_transaction_ok && !suppress_optional_after_recovery &&", "if (!suppress_optional_after_recovery &&"),
         "FAIL primary RF failure with old proof: all optional services closed"),
        ("solar gate removed", source.replace("power_adc_read_solar_mv() >= RELAY_SOLAR_MIN_MV", "true"),
         "solar gates listening not queued LoRaWAN events"),
        ("ignore attempted RX health", replace_once(source,
          "if (!primary_rx_healthy) primary_transaction_ok = false;", "(void)primary_rx_healthy;"),
         "FAIL ordinary RX local fault closes optional service: all optional services closed"),
        ("authenticated restore failure reported healthy", replace_once(source,
          "if (rx_path_healthy_out) *rx_path_healthy_out = rx_path_healthy;",
          "if (rx_path_healthy_out) *rx_path_healthy_out = true;"),
         "FAIL authenticated restore fault: all optional services closed"),
        ("stale RX output retained", replace_once(source,
          "if (rx_path_healthy_out) *rx_path_healthy_out = false;", "(void)rx_path_healthy_out;"),
         "RX health reflects completed healthy exchange, never enum alone"),
    ]
    flags = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-I", str(ROOT / "firmware/include")]
    linked = [str(ROOT / "firmware/src" / name) for name in ("lorawan_liveness.cpp", "ctt_queue.cpp", "ctt_event.cpp")]
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1")
    with tempfile.TemporaryDirectory(prefix="stratolink-primary-aux-") as temp:
        binary = str(Path(temp) / "scheduler")

        def run(code: str) -> subprocess.CompletedProcess:
            subprocess.run(flags + ["-x", "c++", "-"] + linked + ["-o", binary], input=code,
                           text=True, check=True, capture_output=True)
            return subprocess.run([binary],
                                  text=True, capture_output=True, env=env, check=False)

        baseline = run(source)
        print(baseline.stdout, end="", flush=True)
        if baseline.stderr:
            print(baseline.stderr, end="", flush=True)
        for name, changed, assertion in mutants:
            assert changed != source, f"mutation {name} did not alter production code"
            result = run(changed)
            assert result.returncode == 1 and assertion in result.stdout, (
                f"mutation {name} was not rejected by its runtime contract:\n{result.stdout}{result.stderr}")
            print(f"MUTATION REJECTED: {name}", flush=True)
        if baseline.returncode:
            raise SystemExit(baseline.returncode)
    print(f"PASS: production primary/Class-A/auxiliary sequencing and {len(mutants)} behavioral mutation checks")


if __name__ == "__main__":
    main()
