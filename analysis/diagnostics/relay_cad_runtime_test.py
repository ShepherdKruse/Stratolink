#!/usr/bin/env python3
"""Execute production LongFast callers/queues with controlled CAD hardware.

No target or credentials are accessed. The entire production optional-window
section is compiled, with real B2B authentication/queues and Meshtastic MAC.
The old blocking CAD implementation is extracted from pinned RadioLib, with a
fake HAL that throws a host guard instead of hanging when its IRQ never arrives.
Radio SPI methods, power inputs and time are boundaries, not emulated silicon.
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
    raise AssertionError(f"unterminated production function: {opening}")


def harness() -> str:
    source = (ROOT / "firmware/src/lorawan.cpp").read_text()
    window = source[source.index("static float meshtastic_longfast_freq("):
                    source.index("/* ===== CTT wildlife-tag listener")]
    library = (ROOT / "firmware/.pio/libdeps/stratolink/RadioLib/src/modules/SX126x/SX126x.cpp").read_text()
    old_scan = block(library, "int16_t SX126x::scanChannel(const ChannelScanConfig_t &config)")
    old_scan = old_scan.replace("SX126x::", "FakeRadio::", 1)
    phy = block(source, "static bool radio_apply_lora_phy(") + "\n" + block(source, "static bool radio_apply_lorawan_tx(")
    primary = block(source, "static bool send_uplink_port_mode(")
    return r'''
#define B2B_FLEET_KEY "000102030405060708090a0b0c0d0e0f"
#include "config.h"
#include "lorawan.h"
#include "lorawan_crypto.h"
#include "lorawan_frame.h"
#include "b2b.h"
#include "meshtastic_relay_mac.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>

#define LOG(...) ((void)0)
#define LOGV(...) ((void)0)
static constexpr int16_t RADIOLIB_ERR_NONE = 0, RADIOLIB_ERR_UNKNOWN = -1;
#define RADIOLIB_ERR_RX_TIMEOUT (-6)
static constexpr int16_t RADIOLIB_CHANNEL_FREE = -15;
static constexpr int16_t RADIOLIB_LORA_DETECTED = -702, RADIOLIB_PREAMBLE_DETECTED = -14;
#define RADIOLIB_SX126X_IRQ_ALL 0xFFFF
static constexpr uint8_t RADIOLIB_SX126X_SYNC_WORD_PUBLIC = 0x34;
#define RADIOLIB_ASSERT(value) do { if ((value) != 0) return (value); } while (0)
enum class Scenario { Clear, Missing, Immediate, Busy, StartFault, ResultFault,
                      StandbyFault, ClearFault, Freefall, Rail, Solar,
                      Deadline, StaleIrq, TxFault, AdcDeadline, AdcFreefall,
                      PreRail, PreSolar, PreFreefall, RestoreFirst,
                      SetupDeadline, SetupFreefall, SetupFault };
static Scenario stimulus;
static uint32_t clock_ms, cad_at, elapsed_origin;
static bool cad_active, cad_ever, irq_pending, mesh_input, mesh_delivered;
static bool in_primary, started_after_stale;
static bool adc_preempted, restore_failed, setup_preempted;
static unsigned tx_count, cad_count, guard_count, init_count, resets, rx_arms;
static unsigned checks, failures;
static const char* name;
static std::vector<std::string> events;
static void expect(bool ok, const char* message) {
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL %s: %s\n", name, message); }
}
struct HostGuard {};
static uint32_t millis() { return clock_ms; }
/* micros() is used only as contention entropy in these extracted callers.
 * Keep it independent of the elapsed-time clock: this vector schedules Mesh
 * at 1232 ms and the first B2B attempt at 868 ms, so both reach the intended
 * CAD/fault boundary inside the unchanged 2500 ms, 125 ms-airtime window. */
static uint32_t micros() { return 15u; }
static uint32_t power_manager_monotonic_seconds() { return (clock_ms - elapsed_origin) / 1000u; }
static void power_manager_kick_watchdog() { events.push_back("watchdog"); }
static bool power_manager_freefall_pending() {
    return stimulus == Scenario::PreFreefall || adc_preempted ||
           (stimulus == Scenario::Freefall && cad_ever && (clock_ms - cad_at) >= 10);
}
static uint16_t power_adc_read_vSTOR_mv() {
    if (cad_ever && !cad_active && stimulus == Scenario::AdcDeadline) clock_ms += 2400;
    if (cad_ever && !cad_active && stimulus == Scenario::AdcFreefall) adc_preempted = true;
    if (stimulus == Scenario::PreRail) return 4199;
    return stimulus == Scenario::Rail && cad_ever && (clock_ms - cad_at) >= 10 ? 4199 : 4660;
}
static uint16_t power_adc_read_solar_mv() {
    if (stimulus == Scenario::PreSolar) return 2999;
    return stimulus == Scenario::Solar && cad_ever && (clock_ms - cad_at) >= 10 ? 2999 : 3100;
}
static bool power_manager_load_b2b_msg_id(uint8_t* id) { *id = 0; return true; }
static bool power_manager_save_b2b_msg_id(uint8_t) { return true; }
static bool exactHex(const char* value, size_t count) { return std::strlen(value) == count; }
static void hexToBytes(const char*, uint8_t* out, size_t count) {
    for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(i);
}
static bool command_validate_wire(const lorawan_downlink_t*) { return false; }
static bool command_handle(const lorawan_downlink_t*) { return false; }
static bool command_sequence_is_current(uint8_t) { return false; }
static void NVIC_SystemReset() { ++resets; throw HostGuard{}; }
static void idle_step();
struct FakeHal {
    int digitalRead(int) { return irq_pending; }
    void yield() {
        idle_step();
        if (cad_active && clock_ms - cad_at > 200u) { ++guard_count; throw HostGuard{}; }
    }
};
struct FakeModule { FakeHal backing; FakeHal* hal = &backing; int getIrq() { return 0; } };
struct ChannelScanConfig_t {};
struct FakeRadio {
    FakeModule backing; FakeModule* mod = &backing;
    void (*callback)() = nullptr;
    bool scan_callback = false, rx = false;
    float frequency = 0, bandwidth = 0;
    uint8_t sf = 0, sync = 0, coding = 0;
    uint16_t preamble = 0;
    bool crc = false, iq = true;
    int16_t standby() {
        events.push_back("standby"); rx = false;
        if (stimulus == Scenario::StandbyFault && cad_active) {
            cad_active = false; return -70;
        }
        cad_active = false; return 0;
    }
    int16_t setFrequency(float v) {
        frequency = v;
        if (stimulus == Scenario::RestoreFirst && cad_ever && v == 904.1f && !restore_failed) {
            restore_failed = true; return -75;
        }
        return 0;
    }
    int16_t setSpreadingFactor(uint8_t v) { sf = v; return 0; }
    int16_t setBandwidth(float v) { bandwidth = v; return 0; }
    int16_t setCodingRate(uint8_t v) { coding = v; return 0; }
    int16_t setSyncWord(uint8_t v) { sync = v; return 0; }
    int16_t setPreambleLength(uint16_t v) { preamble = v; return 0; }
    int16_t setCRC(bool v) { crc = v; return 0; }
    int16_t invertIQ(bool v) { iq = v; return 0; }
    void clearPacketReceivedAction() { callback = nullptr; events.push_back("detach-rx"); }
    void setPacketReceivedAction(void (*cb)()) { callback = cb; scan_callback = false; events.push_back("attach-rx"); }
    void setChannelScanAction(void (*cb)()) { callback = cb; scan_callback = true; events.push_back("attach-cad"); }
    void clearChannelScanAction() { callback = nullptr; scan_callback = false; events.push_back("detach-cad"); }
    int16_t clearIrqFlags(unsigned) {
        events.push_back("clear-irq");
        expect(!scan_callback, "CAD callback detached before pending IRQ cleanup");
        if (!cad_ever && !setup_preempted) {
            setup_preempted = true;
            if (stimulus == Scenario::SetupDeadline) clock_ms += 2400;
            if (stimulus == Scenario::SetupFreefall) adc_preempted = true;
            if (stimulus == Scenario::SetupFault) return -76;
        }
        if (stimulus == Scenario::ClearFault && cad_ever) return -71;
        irq_pending = false; return 0;
    }
    int16_t startReceive() {
        expect(callback != nullptr && !scan_callback, "RX rearm owns restored packet callback");
        ++rx_arms; rx = true; irq_pending = false; events.push_back("rx-arm"); return 0;
    }
    int16_t startChannelScan() {
        ++cad_count; cad_at = clock_ms; cad_active = cad_ever = true; rx = false;
        irq_pending = false; events.push_back("cad-start");
        if (stimulus == Scenario::StartFault) return -72;
        if (stimulus == Scenario::Deadline) clock_ms += 2400;
        if (stimulus == Scenario::Immediate) {
            irq_pending = true; if (callback) callback();
        }
        started_after_stale = stimulus == Scenario::StaleIrq;
        return 0;
    }
    int16_t startChannelScan(const ChannelScanConfig_t&) { return startChannelScan(); }
    int16_t getChannelScanResult() {
        if (!irq_pending) return RADIOLIB_ERR_UNKNOWN;
        if (stimulus == Scenario::ResultFault) return -73;
        return stimulus == Scenario::Busy ? RADIOLIB_LORA_DETECTED : RADIOLIB_CHANNEL_FREE;
    }
    int16_t scanChannel(const ChannelScanConfig_t&);
    int16_t scanChannel() { return scanChannel(ChannelScanConfig_t{}); }
    uint32_t getTimeOnAir(size_t) { return 100000; }
    int16_t transmit(const uint8_t*, size_t) {
        events.push_back(in_primary ? "primary-tx" : "optional-tx");
        if (in_primary) {
            expect(sf == 9 && bandwidth == 125.0f && sync == 0x34 && coding == 5 &&
                   preamble == 8 && crc && !iq, "next primary uses exact LoRaWAN PHY");
        } else {
            expect(sync == 0x2B && sf == 11 && bandwidth == 250.0f,
                   "optional TX retains original LongFast PHY");
            if (stimulus == Scenario::TxFault) return -74;
            ++tx_count;
        }
        irq_pending = false; clock_ms += 100; return 0;
    }
    size_t getPacketLength() { return 20; }
    int16_t readData(uint8_t* bytes, size_t len) {
        std::memset(bytes, 0, len); bytes[4] = 0x22; bytes[8] = 0x33; bytes[12] = 3;
        mesh_delivered = true; return 0;
    }
    float getRSSI() { return -70; }
    float getSNR() { return 10; }
};
static FakeRadio device;
static FakeRadio* radio = &device;
static bool radio_ready = true, _joined = true;
static uint32_t devAddr = 1, fCntUp, fCntDown, s_tx_end_ms;
static uint8_t appSKey[16] = {}, s_tx_ch, chIdx;
static uint16_t s_last_join_devnonce;
static bool s_have_join_devnonce;
static lorawan_liveness_state_t s_liveness_state;
static struct { unsigned config_failures, restore_attempts, restore_recovered; int16_t last_error; } s_radio_diag;
static float frequencies[] = {904.3f};
static struct {
    float init_freq = 904.1f; uint8_t tx_sf = 9; float tx_bw = 125;
    float* tx_freqs = frequencies; uint8_t tx_ch_count = 1;
} REGION;
static lora_region_id_t REGION_ID = LORA_REGION_US915;
static void idle_step() {
    ++clock_ms;
    if (cad_active) {
        if (stimulus != Scenario::Missing && clock_ms - cad_at >= 33u && !irq_pending) {
            irq_pending = true; if (device.callback) device.callback();
        }
    } else if (mesh_input && !mesh_delivered && device.rx && device.callback) {
        device.callback();
    }
}
static void radio_idle_until_interrupt() { idle_step(); }
''' + old_scan + "\n" + phy + r'''
bool lorawan_init() {
    ++init_count; irq_pending = false; cad_active = false;
    return radio_apply_lorawan_tx(REGION.init_freq);
}
static void retire_invalid_liveness_session() { _joined = false; }
static void fail_session_persistence() { _joined = false; }
static void compute_mic(const uint8_t*, size_t, uint8_t* mic) { std::memset(mic, 0, 4); }
void lorawan_export_session(lorawan_session_t* session) { *session = {}; }
static bool power_manager_save_session(const lorawan_session_t*) { return true; }
''' + primary + "\n" + window + r'''

static void reset(Scenario selected, const char* label, bool mesh, uint32_t start = 0) {
    stimulus = selected; name = label; clock_ms = elapsed_origin = start;
    cad_at = 0; cad_active = cad_ever = irq_pending = false;
    mesh_input = mesh; mesh_delivered = false; in_primary = started_after_stale = false;
    adc_preempted = restore_failed = setup_preempted = false;
    tx_count = cad_count = guard_count = init_count = resets = rx_arms = 0;
    events.clear(); device = FakeRadio{}; device.mod = &device.backing;
    device.backing.hal = &device.backing.backing;
    radio_ready = _joined = true; fCntUp = fCntDown = s_tx_end_ms = 0;
    s_tx_ch = chIdx = 0; s_radio_diag = {};
    lorawan_liveness_begin_session(&s_liveness_state);
    lorawan_liveness_mark_server_proven(&s_liveness_state);
    s_relay = {}; s_dd_head = 0; std::memset(s_dd_from, 0, sizeof(s_dd_from));
    std::memset(s_dd_id, 0, sizeof(s_dd_id)); s_relay_rx = false;
    s_b2b_initialized = s_b2b_origin_id_ready = false;
    s_b2b_crumb_pending = s_b2b_crumb_frame_ready = s_b2b_ever_sent_crumb = false;
    s_b2b_origin_head = s_b2b_origin_tail = s_b2b_origin_n = 0;
    s_b2b_uplink_head = s_b2b_uplink_tail = s_b2b_uplink_n = 0;
    b2b_init_once();
}
static b2b_frame_t seed_forward() {
    b2b_t sender; b2b_reset(&sender, 2);
    uint8_t body[B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN] = {};
    b2b_frame_t frame = {};
    expect(b2b_make(&sender, B2B_TYPE_CRUMB, body, sizeof(body), &frame), "create public test-vector frame");
    uint8_t tag[B2B_AUTH_TAG_LEN];
    expect(b2b_auth_tag(s_b2b_fleet_key, &frame, tag), "authenticate public test-vector frame");
    std::memcpy(frame.payload + B2B_CRUMB_LEN, tag, sizeof(tag));
    expect(b2b_ingest(&s_b2b, &frame, 0) == B2B_FORWARD, "seed real forwarding queue");
    return frame;
}
static void run_window() {
    try { (void)lorawan_relay_window(2500, 4200, mesh_input); }
    catch (const HostGuard&) {}
}
static void next_primary() {
    in_primary = true; uint8_t payload[40] = {};
    expect(send_uplink_port_mode(1, payload, sizeof(payload), false),
           "next primary succeeds after optional service");
    expect(fCntUp == 1 && _joined && s_liveness_state.server_proven,
           "optional CAD leaves primary session and durable proof intact");
}
static void seed_route(unsigned route) {
    if (route == 1) {
        uint8_t command[] = {0, 2, CMD_OP_PING, 1}; b2b_frame_t frame;
        expect(b2b_make_authenticated(B2B_TYPE_COMMAND, command, sizeof(command), &frame) &&
               b2b_origin_push(&frame), "seed real origin queue");
    } else if (route == 2) (void)seed_forward();
}
int main() {
    for (unsigned route = 0; route < 3; ++route) {
        reset(Scenario::Missing, route == 0 ? "missing IRQ mesh" : route == 1 ? "missing IRQ origin" : "missing IRQ forward", route == 0);
        b2b_frame_t original = {};
        if (route == 1) {
            uint8_t command[] = {0, 2, CMD_OP_PING, 1};
            expect(b2b_make_authenticated(B2B_TYPE_COMMAND, command, sizeof(command), &original) &&
                   b2b_origin_push(&original), "seed real origin queue");
        } else if (route == 2) original = seed_forward();
        run_window();
        expect(cad_count == 1 && guard_count == 0 && resets == 0,
               "missing IRQ exits bounded CAD without host guard or MCU reset");
        expect(tx_count == 0 && !cad_active && device.callback == nullptr,
               "missing IRQ stops optional RF and detaches callbacks");
        expect(clock_ms - cad_at <= 100u, "missing IRQ wait bounded to100ms");
        expect(device.sync == 0x34 && device.sf == 9, "window epilogue restores LoRaWAN");
        if (route == 1) expect(s_b2b_origin_n == 1 && s_b2b_origin[s_b2b_origin_head].msg_id == original.msg_id,
                               "aborted origin remains queued");
        if (route == 2) expect(s_b2b.fwd_count == 1 && s_b2b.stats.fwd == 0 &&
                               s_b2b.stats.airtime_ms == 0 && s_b2b.airtime_budget_ms == 125,
                               "aborted popped forward refunds queue and airtime before exit");
        next_primary();
    }
    for (unsigned route = 0; route < 3; ++route) {
        for (Scenario fault : {Scenario::StartFault, Scenario::ResultFault,
                               Scenario::StandbyFault, Scenario::ClearFault,
                               Scenario::Freefall, Scenario::Rail, Scenario::Solar,
                               Scenario::Deadline, Scenario::AdcDeadline, Scenario::AdcFreefall,
                               Scenario::PreRail, Scenario::PreSolar, Scenario::PreFreefall,
                               Scenario::SetupDeadline, Scenario::SetupFreefall, Scenario::SetupFault}) {
            reset(fault, fault == Scenario::AdcDeadline ? "ADC crosses deadline" :
                  fault == Scenario::AdcFreefall ? "ADC publishes freefall" : "fault or mission abort", route == 0);
            seed_route(route); run_window();
            expect(guard_count == 0 && resets == 0 && tx_count == 0,
                   "fault or fresh mission abort never transmits or waits for watchdog");
            expect(device.callback == nullptr && !cad_active && device.sync == 0x34,
                   "fault or mission abort cleans callback and restores primary PHY");
            bool local_fault = fault == Scenario::StartFault || fault == Scenario::ResultFault ||
                               fault == Scenario::StandbyFault || fault == Scenario::ClearFault ||
                               fault == Scenario::SetupFault;
            expect((route == 0 ? s_relay.cad_error : s_b2b.stats.cad_error) == (local_fault ? 1u : 0u),
                   "mission abort distinct from local CAD fault");
            if (route == 1) expect(s_b2b_origin_n == 1, "aborted origin remains queued");
            if (route == 2) expect(s_b2b.fwd_count == 1 && s_b2b.stats.fwd == 0 &&
                                   s_b2b.stats.airtime_ms == 0 && s_b2b.airtime_budget_ms == 125,
                                   "aborted forward refunded before window exit");
            if (cad_count) {
                auto last_cad = std::find(events.rbegin(), events.rend(), "cad-start");
                expect(std::find(events.rbegin(), last_cad, "rx-arm") == last_cad,
                       "abort exits before LongFast RX rearm");
            }
            next_primary();
        }
        for (Scenario healthy : {Scenario::Clear, Scenario::Immediate, Scenario::StaleIrq,
                                 Scenario::Busy, Scenario::TxFault, Scenario::RestoreFirst}) {
            reset(healthy, healthy == Scenario::Immediate ? "immediate CAD IRQ" :
                  healthy == Scenario::StaleIrq ? "stale CAD software flag" : "normal CAD ownership", route == 0,
                  UINT32_MAX - 500u);
            seed_route(route);
            if (healthy == Scenario::StaleIrq) s_relay_cad_done = true;
            run_window();
            bool succeeds = healthy != Scenario::Busy && healthy != Scenario::TxFault;
            expect(guard_count == 0 && resets == 0 && cad_count >= 1 && tx_count == (succeeds ? 1u : 0u),
                   "clear immediate stale busy and TX-failure outcomes preserve intended RF policy");
            expect(!cad_active && device.callback == nullptr && device.sync == 0x34,
                   "normal window cleanup and LoRaWAN restore");
            if (route == 1) expect(s_b2b_origin_n == (succeeds ? 0 : 1), "origin dequeues on TX success only");
            if (route == 2) expect(s_b2b.fwd_count == (succeeds ? 0 : 1) &&
                                   s_b2b.stats.airtime_ms ==
                                       ((succeeds || healthy == Scenario::TxFault) ? 100u : 0u),
                                   "forward preserves handoff debit; only pre-handoff failure refunds");
            if (healthy == Scenario::Busy) expect((route == 0 ? s_relay.cad_busy : s_b2b.stats.cad_busy) > 0,
                                                  "busy CAD keeps contention policy");
            if (healthy == Scenario::RestoreFirst) expect(init_count == 1, "failed parameter restore reaches bounded full init");
            next_primary();
        }
    }
    reset(Scenario::Missing, "CAD wait wraps millis", false, UINT32_MAX - 20u);
    device.setPacketReceivedAction(relay_rx_isr);
    expect(relay_scan_channel_bounded(clock_ms, 2500, 100, 4200) == RELAY_CAD_LOCAL_FAULT &&
           clock_ms - cad_at == 100 && guard_count == 0, "100ms CAD wait is wrap safe");
    reset(Scenario::Clear, "remaining window expires during CAD", false);
    device.setPacketReceivedAction(relay_rx_isr);
    expect(relay_scan_channel_bounded(clock_ms - 1874u, 2500, 100, 4200) == RELAY_CAD_MISSION_ABORT &&
           clock_ms - cad_at == 20 && tx_count == 0,
           "window deadline preempts CAD before its100ms timeout");
    reset(Scenario::Busy, "CAD completion clears pending IRQ", false);
    device.setPacketReceivedAction(relay_rx_isr);
    expect(relay_scan_channel_bounded(clock_ms, 2500, 100, 4200) == RELAY_CAD_BUSY &&
           !irq_pending && device.callback == relay_rx_isr && !device.scan_callback,
           "busy CAD clears pending IRQ and restores exact RX callback before caller rearms");
    for (bool local_origin : {false, true}) {
        reset(Scenario::Busy, local_origin ? "busy local crumb age" : "busy forward age", false);
        if (local_origin) lorawan_b2b_set_local_crumb(377000000, -1220000000, 100);
        else (void)seed_forward();
        (void)lorawan_relay_window(60000, 4200, false);
        const b2b_frame_t* pending = local_origin
            ? &s_b2b_crumb_frame : b2b_peek_forward(&s_b2b);
        expect(pending && (local_origin ? s_b2b_crumb_pending : s_b2b.fwd_count == 1),
               "busy retries preserve the pending crumb");
        expect(tx_count == 0 && s_b2b.stats.cad_busy > 20,
               "busy minute exercises repeated real queue retries without RF handoff");
        // 60 nominal seconds is at most 65.1 wall seconds: ceil is two minutes.
        expect(pending && pending->payload[5] == 2,
               "busy retries charge one elapsed minute interval only once");
        expect(pending && b2b_auth_verify(s_b2b_fleet_key, pending),
               "busy retry age retains a valid fleet authentication tag");
        next_primary();
    }
    reset(Scenario::Clear, "mixed origin priority ring wrap", false);
    // Exercise the real ring operations in every rotated empty state.
    for (uint8_t rotation = 0; rotation < B2B_ORIGIN_N; ++rotation) {
        s_b2b_origin_head = s_b2b_origin_tail = rotation; s_b2b_origin_n = 0;
        b2b_frame_t frame = {}; frame.msg_id = 10; expect(b2b_origin_push(&frame), "append normal origin");
        frame.msg_id = 20; expect(b2b_origin_push_priority(&frame), "prepend priority origin");
        frame.msg_id = 30; expect(b2b_origin_push(&frame), "append across ring wrap");
        frame.msg_id = 40; expect(b2b_origin_push_priority(&frame), "priority fills ring");
        frame.msg_id = 50;
        expect(!b2b_origin_push(&frame) && !b2b_origin_push_priority(&frame) && s_b2b_origin_n == 4,
               "full ring rejects normal and priority inserts without mutation");
        const uint8_t expected[] = {40, 20, 10, 30};
        for (uint8_t i = 0; i < 4; ++i) {
            expect(s_b2b_origin[(s_b2b_origin_head + i) % B2B_ORIGIN_N].msg_id == expected[i],
                   "mixed priority ring preserves queue ownership through wrap");
        }
        expect(s_b2b_origin_tail == s_b2b_origin_head, "full-ring head equals next insertion tail");
    }
    std::printf("%u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
'''


def main() -> None:
    code = harness()
    def mutate(old: str, new: str) -> str:
        assert code.count(old) == 1, f"mutation target changed: {old}"
        return code.replace(old, new, 1)

    stale_gate = """if (power_adc_read_vSTOR_mv() < floor_mv ||
            power_adc_read_solar_mv() < RELAY_SOLAR_MIN_MV ||
            !relay_cad_has_tx_room(start_ms, max_ms, toa_ms) ||
            power_manager_freefall_pending())"""
    reordered_gate = """if (!relay_cad_has_tx_room(start_ms, max_ms, toa_ms) ||
            power_manager_freefall_pending() ||
            power_adc_read_vSTOR_mv() < floor_mv ||
            power_adc_read_solar_mv() < RELAY_SOLAR_MIN_MV)"""
    assert code.count(stale_gate) == 2
    mutants = [
        ("IRQ timeout removed", mutate("millis() - cad_started_ms >= 100u", "millis() - cad_started_ms >= 10000u"),
         "missing IRQ wait bounded to100ms"),
        ("immediate IRQ erased", mutate("state = radio->startChannelScan();", "state = radio->startChannelScan(); s_relay_cad_done = false;"),
         "FAIL immediate CAD IRQ: clear immediate stale busy and TX-failure outcomes preserve intended RF policy"),
        ("RX callback not restored", mutate("} else {\n            radio->setPacketReceivedAction(relay_rx_isr);", "} else {\n            (void)0;"),
         "RX rearm owns restored packet callback"),
        ("CAD callback not detached", mutate("radio->clearChannelScanAction();", "(void)0;"),
         "CAD callback detached before pending IRQ cleanup"),
        ("popped forward not refunded", mutate("b2b_refund(&s_b2b, &frame,\n                                    tx_airtime_ms == airtime_before ? toa : 0u);", "(void)frame; (void)airtime_before;"),
         "aborted popped forward refunds queue and airtime before exit"),
        ("mission check before fresh ADC", code.replace(stale_gate, reordered_gate),
         "FAIL ADC crosses deadline: fault or fresh mission abort never transmits or waits for watchdog"),
        ("unknown CAD accepted free", mutate("} else {\n                    s_radio_diag.last_error = state;", "} else {\n                    result = RELAY_CAD_FREE;"),
         "fault or fresh mission abort never transmits or waits for watchdog"),
        ("local retry loses age credit", mutate("attempted = true;\n                    if (!b2b_refresh_authenticated_age(",
         "attempted = true;\n                    s_b2b_crumb_frame.age_rounding_credit = 0;\n                    if (!b2b_refresh_authenticated_age("),
         "FAIL busy local crumb age: busy retries charge one elapsed minute interval only once"),
        ("refunded forward loses age credit", mutate("b2b_refund(&s_b2b, &frame,",
         "frame.age_rounding_credit = 0;\n                                b2b_refund(&s_b2b, &frame,"),
         "FAIL busy forward age: busy retries charge one elapsed minute interval only once"),
    ]
    flags = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
             "-I", str(ROOT / "firmware/include"), "-I", str(ROOT / "firmware/src")]
    linked = [str(ROOT / "firmware/src" / name) for name in (
        "b2b.cpp", "crypto_aes128.cpp", "meshtastic_relay_mac.cpp", "lorawan_liveness.cpp",
        "lorawan_crypto.cpp", "lorawan_frame.cpp", "lorawan_counter.cpp")]
    with tempfile.TemporaryDirectory(prefix="stratolink-relay-cad-") as temp:
        binary = str(Path(temp) / "cad")
        def run(source: str) -> subprocess.CompletedProcess:
            compiled = subprocess.run(flags + ["-x", "c++", "-"] + linked + ["-o", binary],
                                      input=source, text=True, capture_output=True)
            assert compiled.returncode == 0, compiled.stderr
            return subprocess.run([binary], text=True, capture_output=True, timeout=15,
                                  env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0", "UBSAN_OPTIONS": "halt_on_error=1"})
        result = run(code)
        print(result.stdout, end="")
        print(result.stderr, end="")
        assert result.returncode == 0, "production CAD regression failed"
        for label, changed, expected_failure in mutants:
            result = run(changed)
            assert result.returncode == 1 and expected_failure in result.stdout, (
                f"mutant not rejected by intended runtime assertion: {label}\n{result.stdout}{result.stderr}")
            print(f"MUTATION REJECTED: {label}", flush=True)
    print(f"PASS: production bounded CAD callers and {len(mutants)} behavioral mutation checks")


if __name__ == "__main__":
    main()
