#!/usr/bin/env python3
"""Execute the production CTT window against controlled radio/power boundaries.

No target or credentials are accessed. The production CTT window, decoder,
queue, and LoRaWAN PHY restoration helpers are compiled on the host. RadioLib
SPI calls, IRQ delivery, time, and power inputs remain explicit boundaries.
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
                return source[start : end + 1]
    raise AssertionError(f"unterminated production function: {opening}")


def harness() -> str:
    source = (ROOT / "firmware/src/lorawan.cpp").read_text()
    phy = block(source, "static bool radio_apply_lora_phy(")
    phy += "\n" + block(source, "static bool radio_apply_lorawan_tx(")
    restore = block(source, "static bool relay_restore_lorawan_phy(")
    restore += "\n" + block(source, "static bool restore_lorawan_or_reset(")
    ctt = source[
        source.index("static volatile bool s_ctt_rx = false;") :
        source.index("/* ========== Class-A downlink", source.index("static volatile bool s_ctt_rx = false;"))
    ]
    # Baseline has no runtime record: a test-only zero record lets the missing
    # observations fail at runtime rather than failing to compile.
    if "static volatile ctt_runtime_t s_ctt_runtime" not in ctt:
        ctt = r'''
enum : uint8_t { CTT_PHASE_IDLE, CTT_PHASE_CONFIG, CTT_PHASE_RX,
                 CTT_PHASE_READ, CTT_PHASE_RESTORE, CTT_PHASE_DONE };
enum : uint8_t { CTT_EXIT_NONE, CTT_EXIT_DEADLINE, CTT_EXIT_NOT_READY,
                 CTT_EXIT_CONFIG_FAIL, CTT_EXIT_INITIAL_ARM_FAIL,
                 CTT_EXIT_REARM_FAIL, CTT_EXIT_RAIL, CTT_EXIT_FREEFALL, CTT_EXIT_SOLAR };
enum : uint8_t { CTT_SAMPLE_RAIL = 1, CTT_SAMPLE_SOLAR = 2, CTT_SAMPLE_READ = 4 };
struct ctt_runtime_t {
    uint32_t window_start_ms, last_arm_ms, window_end_ms;
    uint32_t successful_arms, irq_count, read_errors;
    int16_t last_read_status;
    uint16_t latest_rail_mv, latest_solar_mv, floor_mv;
    uint8_t phase, exit_reason, sample_mask, reserved;
};
static volatile ctt_runtime_t s_ctt_runtime = {};
''' + ctt
    return r'''
#include "config.h"
#include "lorawan.h"
#include "ctt_decode.h"
#include "ctt_queue.h"
#include <climits>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <string>

static constexpr int16_t RADIOLIB_ERR_NONE = 0;
static constexpr uint8_t RADIOLIB_SX126X_SYNC_WORD_PUBLIC = 0x34;
static constexpr uint8_t RADIOLIB_SHAPING_NONE = 0;
static constexpr uint32_t RADIOLIB_SX126X_RX_TIMEOUT_INF = 0xFFFFFF;
static constexpr uint32_t RADIOLIB_IRQ_RX_DEFAULT_FLAGS = 0x36;
static constexpr uint32_t RADIOLIB_IRQ_RX_DEFAULT_MASK = 0x02;
static constexpr uint8_t RADIOLIB_RADIO_MODE_RX = 3;
struct RadioModeConfig_t {
    struct {
        uint32_t timeout, irqFlags, irqMask;
        size_t len;
    } receive;
};

enum class Scenario {
    Deadline, Valid, CrcBad, ReadFault, InitialArmFault, RearmFault,
    Floor, Solar, Freefall, BeginRetry, BeginReset, ParamRestore, ReinitReset,
    ReadBoundaryIrq, ReadRecovery
};

struct HostReset {};
static Scenario stimulus;
static const char* test_name;
static uint32_t clock_ms, clock_origin;
static unsigned checks, failures, watchdogs, resets, init_calls, primary_tx;
static unsigned config_fault_stage, arm_fault_phase;
static bool injected, restore_param_failed;
static uint32_t restore_delay_ms, window_used;
static std::string power_calls;
static void observe_phase(uint8_t phase);
static void observe_registration();
static void observe_restore();

static void expect(bool condition, const char* message) {
    ++checks;
    if (!condition) {
        ++failures;
        std::printf("FAIL %s: %s\n", test_name, message);
    }
}

static uint32_t millis() { return clock_ms; }
static uint32_t power_manager_monotonic_seconds() {
    return (clock_ms - clock_origin) / 1000u;
}
static void power_manager_kick_watchdog() { ++watchdogs; }
static uint16_t power_adc_read_vSTOR_mv() {
    power_calls += 'V';
    return stimulus == Scenario::Floor ? 4199 : 4660;
}
static uint16_t power_adc_read_solar_mv() {
    power_calls += 'S';
    return stimulus == Scenario::Solar ? 2999 : 3100;
}
static bool power_manager_freefall_pending() {
    power_calls += 'F';
    return stimulus == Scenario::Freefall;
}
static void NVIC_SystemReset() { ++resets; throw HostReset{}; }

struct FakeRadio {
    void (*callback)() = nullptr;
    bool fsk = false, rx = false;
    float frequency = 0, bandwidth = 0;
    uint8_t sf = 0, coding = 0, sync = 0;
    uint16_t preamble = 0;
    bool crc = false, iq = true;
    unsigned begin_calls = 0, arm_calls = 0, read_calls = 0, clear_calls = 0;
    unsigned length_calls = 0, launch_calls = 0;
    size_t packet_length = 0;

    int16_t standby() { rx = false; return RADIOLIB_ERR_NONE; }
    int16_t beginFSK(float freq, float bit_rate, float deviation, float rx_bw,
                     int16_t power, uint16_t preamble_bits) {
        observe_phase(1);
        (void)power;
        expect(freq == 434.0f && bit_rate == 25.0f && deviation == 25.0f &&
               rx_bw == 93.8f && preamble_bits == 16,
               "production uses the exact CTT FSK profile");
        if (config_fault_stage == 1) return -11;
        fsk = true;
        return RADIOLIB_ERR_NONE;
    }
    int16_t setDataShaping(uint8_t shaping) {
        expect(shaping == RADIOLIB_SHAPING_NONE, "CTT disables data shaping");
        return config_fault_stage == 2 ? -12 : RADIOLIB_ERR_NONE;
    }
    int16_t setSyncWord(uint8_t* value, size_t size) {
        expect(size == 2 && value[0] == 0xD3 && value[1] == 0x91,
               "production uses the exact CTT sync word");
        return config_fault_stage == 3 ? -13 : RADIOLIB_ERR_NONE;
    }
    int16_t fixedPacketLengthMode(size_t size) {
        ++length_calls;
        expect(size == 5, "CTT modem accepts exactly five payload bytes");
        if (config_fault_stage == 4) return -14;
        int16_t state = arm_fault(2);
        if (state != RADIOLIB_ERR_NONE) return state;
        packet_length = size;
        return RADIOLIB_ERR_NONE;
    }
    int16_t setCRC(bool enabled) {
        if (fsk && !enabled && config_fault_stage == 5) return -15;
        if (fsk) packet_length = 255;
        crc = enabled;
        return RADIOLIB_ERR_NONE;
    }
    void setPacketReceivedAction(void (*action)()) { observe_registration(); callback = action; }
    void clearPacketReceivedAction() { callback = nullptr; rx = false; ++clear_calls; }
    int16_t arm_fault(unsigned phase) {
        if (arm_fault_phase != phase) return RADIOLIB_ERR_NONE;
        if (stimulus == Scenario::InitialArmFault && arm_calls == 1) return -31;
        if (stimulus == Scenario::RearmFault && arm_calls == 2) return -32;
        return RADIOLIB_ERR_NONE;
    }
    int16_t stageMode(uint8_t mode, RadioModeConfig_t* cfg) {
        observe_phase(1);
        ++arm_calls;
        expect(mode == RADIOLIB_RADIO_MODE_RX &&
               cfg->receive.timeout == RADIOLIB_SX126X_RX_TIMEOUT_INF &&
               cfg->receive.irqFlags == RADIOLIB_IRQ_RX_DEFAULT_FLAGS &&
               cfg->receive.irqMask == RADIOLIB_IRQ_RX_DEFAULT_MASK,
               "CTT preserves continuous RX and the default IRQ contract");
        rx = false;
        packet_length = 255;  // Pinned SX126x startReceiveCommon default payloadLen.
        return arm_fault(1);
    }
    int16_t launchMode() {
        observe_phase(1);
        ++launch_calls;
        int16_t state = arm_fault(3);
        if (state != RADIOLIB_ERR_NONE) return state;
        expect(packet_length == 5, "every CTT RX launch uses five-byte fixed length");
        rx = true;
        return RADIOLIB_ERR_NONE;
    }
    int16_t startReceive() {
        RadioModeConfig_t cfg = {};
        cfg.receive.timeout = RADIOLIB_SX126X_RX_TIMEOUT_INF;
        cfg.receive.irqFlags = RADIOLIB_IRQ_RX_DEFAULT_FLAGS;
        cfg.receive.irqMask = RADIOLIB_IRQ_RX_DEFAULT_MASK;
        int16_t state = stageMode(RADIOLIB_RADIO_MODE_RX, &cfg);
        return state != RADIOLIB_ERR_NONE ? state : launchMode();
    }
    int16_t readData(uint8_t* out, size_t size) {
        observe_phase(3);
        ++read_calls;
        expect(size == 5, "production reads exactly one fixed CTT payload");
        if (stimulus == Scenario::ReadBoundaryIrq && callback) callback();
        if (stimulus == Scenario::ReadFault ||
            (stimulus == Scenario::ReadRecovery && read_calls == 1)) return -41;
        const uint8_t valid[5] = {0x78, 0x55, 0x4C, 0x33, 0x58};
        std::memcpy(out, valid, sizeof(valid));
        if (stimulus == Scenario::CrcBad) out[4] ^= 1;
        return RADIOLIB_ERR_NONE;
    }
    float getRSSI() { return -67.8f; }

    int16_t begin(float freq, float bw, uint8_t spreading, uint8_t coding_rate,
                  uint8_t sync_word, int8_t power, uint16_t preamble_len,
                  float gain, bool tcxo) {
        (void)power; (void)gain; (void)tcxo;
        observe_restore();
        clock_ms += restore_delay_ms;
        ++begin_calls;
        expect(freq == 904.1f && bw == 125.0f && spreading == 9 &&
               coding_rate == 7 && sync_word == 0x34 && preamble_len == 8,
               "full restore begins with the regional LoRa profile");
        if (stimulus == Scenario::BeginReset) return -52;
        if (stimulus == Scenario::BeginRetry && begin_calls == 1) return -51;
        fsk = false; frequency = freq; bandwidth = bw; sf = spreading;
        coding = coding_rate; sync = sync_word; preamble = preamble_len;
        return RADIOLIB_ERR_NONE;
    }
    int16_t setFrequency(float value) {
        if ((stimulus == Scenario::ParamRestore || stimulus == Scenario::ReinitReset) &&
            !restore_param_failed) {
            restore_param_failed = true;
            return -61;
        }
        frequency = value;
        return RADIOLIB_ERR_NONE;
    }
    int16_t setSpreadingFactor(uint8_t value) { sf = value; return RADIOLIB_ERR_NONE; }
    int16_t setBandwidth(float value) { bandwidth = value; return RADIOLIB_ERR_NONE; }
    int16_t setCodingRate(uint8_t value) { coding = value; return RADIOLIB_ERR_NONE; }
    int16_t setSyncWord(uint8_t value) { sync = value; return RADIOLIB_ERR_NONE; }
    int16_t setPreambleLength(uint16_t value) { preamble = value; return RADIOLIB_ERR_NONE; }
    int16_t invertIQ(bool value) { iq = value; return RADIOLIB_ERR_NONE; }
    int16_t transmit(const uint8_t*, size_t) {
        bool exact = !fsk && frequency == 904.1f && bandwidth == 125.0f &&
                     sf == 9 && coding == 5 && sync == 0x34 && preamble == 8 &&
                     crc && !iq && callback == nullptr;
        if (!exact) return -70;
        ++primary_tx;
        return RADIOLIB_ERR_NONE;
    }
};

static FakeRadio device;
static FakeRadio* radio = &device;
static bool radio_ready = true;
static struct {
    uint32_t begin_failures, config_failures, restore_attempts, restore_recovered,
             sleep_failures;
    int16_t last_error;
    uint16_t allocation_failures;
} s_radio_diag;
static struct {
    float init_freq = 904.1f;
    uint8_t tx_sf = 9;
    float tx_bw = 125.0f;
} REGION;

static void radio_idle_until_interrupt() {
    observe_phase(2);
    clock_ms += 100;
    bool has_frame = stimulus == Scenario::Valid || stimulus == Scenario::CrcBad ||
                     stimulus == Scenario::ReadFault || stimulus == Scenario::RearmFault ||
                     stimulus == Scenario::ReadBoundaryIrq || stimulus == Scenario::ReadRecovery;
    if (has_frame && !injected && device.rx && device.callback) {
        injected = true;
        device.callback();
    }
    if (stimulus == Scenario::ReadRecovery && injected && device.read_calls == 1 &&
        device.rx && device.callback) device.callback();
}
''' + phy + "\n" + restore + r'''

bool lorawan_init() {
    ++init_calls;
    if (stimulus == Scenario::ReinitReset) return false;
    int16_t state = device.begin(REGION.init_freq, REGION.tx_bw, 9, 7,
                                 RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 14, 8, 1.7f, false);
    if (state != RADIOLIB_ERR_NONE) return false;
    radio_ready = true;
    return radio_apply_lorawan_tx(REGION.init_freq);
}
''' + ctt + r'''

static_assert(sizeof(lorawan_ctt_stats_t) == 32, "existing stats ABI remains unchanged");
static_assert(sizeof(ctt_runtime_t) == 36, "bounded runtime record size");

static void observe_phase(uint8_t phase) {
    expect(s_ctt_runtime.phase == phase, "runtime phase matches current radio operation");
}
static void observe_registration() {
    expect(device.callback == nullptr && s_ctt_runtime.phase == CTT_PHASE_CONFIG &&
           s_ctt_runtime.irq_count == 0 && s_ctt_runtime.successful_arms == 0 &&
           s_ctt_runtime.read_errors == 0 && s_ctt_runtime.sample_mask == 0,
           "per-window record is reset before CTT callback registration");
}
static void observe_restore() {
    expect(s_ctt_runtime.phase == CTT_PHASE_RESTORE &&
           s_ctt_runtime.exit_reason != CTT_EXIT_NONE,
           "exit reason is published before potentially nonreturning restore");
    expect(s_ctt_runtime.window_end_ms == clock_ms || restore_delay_ms != 0,
           "window end is published before restore starts");
}
static void expect_runtime(uint8_t reason, uint32_t arms, uint32_t irqs,
                           uint32_t read_errors, uint8_t samples, uint32_t elapsed) {
    expect(s_ctt_runtime.phase == CTT_PHASE_DONE && s_ctt_runtime.exit_reason == reason,
           "completed runtime record identifies the exact exit reason");
    expect(s_ctt_runtime.window_start_ms == clock_origin &&
           s_ctt_runtime.window_end_ms - s_ctt_runtime.window_start_ms == elapsed,
           "runtime window timestamps are wrap-safe and exclude restore");
    expect(s_ctt_runtime.successful_arms == arms && s_ctt_runtime.irq_count == irqs &&
           s_ctt_runtime.read_errors == read_errors,
           "runtime arm IRQ and read-error counts describe this invocation only");
    expect(s_ctt_runtime.sample_mask == samples && s_ctt_runtime.floor_mv == 4200 &&
           s_ctt_runtime.reserved == 0,
           "sample validity distinguishes actually observed values from zeros");
    expect(arms != 0 || s_ctt_runtime.last_arm_ms == 0,
           "failed initial arm never publishes a successful arm timestamp");
}

static void reset_case(Scenario selected, const char* label,
                       uint32_t start = 0, unsigned fail_stage = 0) {
    stimulus = selected;
    test_name = label;
    clock_ms = clock_origin = start;
    watchdogs = resets = init_calls = primary_tx = 0;
    config_fault_stage = fail_stage;
    arm_fault_phase = 1;
    injected = restore_param_failed = false;
    restore_delay_ms = window_used = 0;
    power_calls.clear();
    device = FakeRadio{};
    radio = &device;
    radio_ready = true;
    s_radio_diag = {};
    s_ctt = {};
    s_ctt_rx = false;
    ctt_queue_init(&s_ctt_queue);
}

static bool exact_primary_phy() {
    return !device.fsk && device.frequency == 904.1f && device.bandwidth == 125.0f &&
           device.sf == 9 && device.coding == 5 && device.sync == 0x34 &&
           device.preamble == 8 && device.crc && !device.iq;
}

static void expect_cleanup_and_primary() {
    expect(device.callback == nullptr && !device.rx,
           "window leaves no optional RX callback or receive ownership");
    expect(exact_primary_phy(), "window restores the exact regional LoRaWAN TX PHY");
    uint8_t packet[3] = {};
    expect(device.transmit(packet, sizeof(packet)) == RADIOLIB_ERR_NONE && primary_tx == 1,
           "the next primary transmission uses the restored PHY");
}

static void run_window(uint32_t max_ms = 1500, uint16_t floor_mv = 4200) {
    try {
        window_used = lorawan_ctt_window(max_ms, floor_mv);
    } catch (const HostReset&) {
    }
}

int main() {
    reset_case(Scenario::Deadline, "radio unavailable");
    radio_ready = false;
    expect(lorawan_ctt_window(1500, 4200) == 0 && device.begin_calls == 0 &&
           s_ctt.windows == 0, "an unavailable shared radio is a zero-work no-op");
    expect_runtime(CTT_EXIT_NOT_READY, 0, 0, 0, 0, 0);

    for (unsigned stage = 1; stage <= 5; ++stage) {
        reset_case(Scenario::Deadline, "FSK configuration fault", 0, stage);
        run_window();
        expect(s_ctt.windows == 0 && lorawan_ctt_pending_count() == 0,
               "configuration failure never opens a window or queues data");
        expect(device.arm_calls == 0 && resets == 0,
               "configuration failure never arms optional receive or resets");
        expect_runtime(CTT_EXIT_CONFIG_FAIL, 0, 0, 0, 0, 0);
        expect(power_calls.empty(), "configuration failure performs no ADC or mission-gate reads");
        expect_cleanup_and_primary();
    }

    for (unsigned phase = 1; phase <= 3; ++phase) {
        reset_case(Scenario::InitialArmFault, "initial receive arm fault");
        arm_fault_phase = phase;
        run_window();
        expect(s_ctt.windows == 1 && s_ctt.rx_arm_fail == 1 &&
               s_radio_diag.last_error == -31, "initial arm failure is diagnosed once");
        expect(device.clear_calls == 1 && lorawan_ctt_pending_count() == 0,
               "initial arm failure detaches without queue mutation");
        expect(device.arm_calls == 1 && device.length_calls == (phase == 1 ? 1u : 2u) &&
               device.launch_calls == (phase == 3 ? 1u : 0u),
               "initial arm stops immediately at the failed radio operation");
        expect_runtime(CTT_EXIT_INITIAL_ARM_FAIL, 0, 0, 0, 0, 0);
        expect_cleanup_and_primary();
    }

    reset_case(Scenario::Valid, "valid CTT frame");
    run_window();
    ctt_detection_t detection = {};
    expect(s_ctt.frames_rx == 1 && s_ctt.crc_fail == 0 && s_ctt.tags_seen == 1,
           "a valid production-decoded frame is counted and logged once");
    expect(lorawan_ctt_pending_count() == 1 && lorawan_ctt_peek_pending(&detection) &&
           detection.id_raw == 0x78554C33u && detection.id_motus == 0x3256Eu &&
           detection.motus_valid == 1 && detection.rssi_best == -67 && detection.hits == 1,
           "the real queue holds the exact decoded tag and RSSI");
    expect_runtime(CTT_EXIT_DEADLINE, 2, 1, 0, 7, 1500);
    expect(s_ctt_runtime.last_arm_ms == 100 && s_ctt_runtime.last_read_status == 0 &&
           s_ctt_runtime.latest_rail_mv == 4660 && s_ctt_runtime.latest_solar_mv == 3100 &&
           power_calls == "VFS", "successful reads preserve the exact sampled values and gate order");
    expect_cleanup_and_primary();

    reset_case(Scenario::CrcBad, "CRC-invalid CTT frame");
    run_window();
    expect(s_ctt.frames_rx == 1 && s_ctt.crc_fail == 1 && s_ctt.tags_seen == 0 &&
           lorawan_ctt_pending_count() == 0,
           "software CRC rejection cannot enqueue a tag");
    expect_runtime(CTT_EXIT_DEADLINE, 2, 1, 0, 7, 1500);
    expect_cleanup_and_primary();

    reset_case(Scenario::ReadFault, "RadioLib read fault");
    run_window();
    expect(device.read_calls == 1 && s_ctt.frames_rx == 0 && s_ctt.tags_seen == 0 &&
           lorawan_ctt_pending_count() == 0,
           "a failed five-byte read cannot decode or enqueue uninitialized data");
    expect_runtime(CTT_EXIT_DEADLINE, 2, 1, 1, 7, 1500);
    expect(s_ctt_runtime.last_read_status == -41, "failed read status is retained exactly");
    expect_cleanup_and_primary();

    for (unsigned phase = 1; phase <= 3; ++phase) {
        reset_case(Scenario::RearmFault, "receive re-arm fault");
        arm_fault_phase = phase;
        run_window();
        expect(s_ctt.frames_rx == 1 && s_ctt.tags_seen == 1 && s_ctt.rx_arm_fail == 1 &&
               s_radio_diag.last_error == -32 && lorawan_ctt_pending_count() == 1,
               "re-arm failure preserves the already validated queue event and is diagnosed");
        expect(clock_ms < 1500, "re-arm failure exits instead of waiting deaf");
        expect_runtime(CTT_EXIT_REARM_FAIL, 1, 1, 0, 4, 100);
        expect(s_ctt_runtime.last_arm_ms == 0, "failed rearm preserves last successful arm timestamp");
        expect(device.arm_calls == 2 && device.length_calls == (phase == 1 ? 2u : 3u) &&
               device.launch_calls == (phase == 3 ? 2u : 1u),
               "re-arm stops immediately at the failed radio operation");
        expect_cleanup_and_primary();
    }

    for (Scenario selected : {Scenario::Floor, Scenario::Solar, Scenario::Freefall}) {
        reset_case(selected, selected == Scenario::Floor ? "VSTOR abort" :
                   selected == Scenario::Solar ? "solar abort" : "freefall abort");
        run_window(2500);
        expect(clock_ms == 1000 && watchdogs == 1 && lorawan_ctt_pending_count() == 0,
               "fresh one-hertz mission gate aborts the optional window");
        expect_runtime(selected == Scenario::Floor ? CTT_EXIT_RAIL :
                       selected == Scenario::Solar ? CTT_EXIT_SOLAR : CTT_EXIT_FREEFALL,
                       1, 0, 0, selected == Scenario::Solar ? 3 : 1, 1000);
        expect(power_calls == (selected == Scenario::Floor ? "V" :
                               selected == Scenario::Solar ? "VFS" : "VF"),
               "instrumentation preserves short-circuit gate reads and order");
        expect(s_ctt_runtime.latest_rail_mv == (selected == Scenario::Floor ? 4199 : 4660) &&
               s_ctt_runtime.latest_solar_mv == (selected == Scenario::Solar ? 2999 : 0),
               "abort records only values actually read before the failed gate");
        expect_cleanup_and_primary();
    }

    reset_case(Scenario::Deadline, "deadline wraps millis", UINT_MAX - 499u);
    run_window(1500);
    expect(clock_ms - clock_origin == 1500 && watchdogs == 1 && resets == 0,
           "window deadline is bounded and wrap-safe");
    expect_runtime(CTT_EXIT_DEADLINE, 1, 0, 0, 3, 1500);
    expect(s_ctt_runtime.last_arm_ms == UINT_MAX - 499u, "arm timestamp preserves wrap boundary");
    expect_cleanup_and_primary();

    reset_case(Scenario::Valid, "successful rearm crosses millis wrap", UINT_MAX - 49u);
    run_window(1500);
    expect_runtime(CTT_EXIT_DEADLINE, 2, 1, 0, 7, 1500);
    expect(s_ctt_runtime.last_arm_ms == 50, "latest successful rearm timestamp wraps without stale data");
    expect_cleanup_and_primary();

    reset_case(Scenario::Deadline, "zero budget preserves existing arm then exit");
    run_window(0);
    expect_runtime(CTT_EXIT_DEADLINE, 1, 0, 0, 0, 0);
    expect(power_calls.empty() && device.arm_calls == 1, "zero budget adds no housekeeping reads");
    expect_cleanup_and_primary();

    reset_case(Scenario::BeginRetry, "full LoRa begin retries once");
    run_window(100);
    expect(device.begin_calls == 2 && s_radio_diag.begin_failures == 1 && resets == 0,
           "one failed full-LoRa restore is retried and recovered");
    expect_cleanup_and_primary();

    reset_case(Scenario::BeginReset, "full LoRa begin fails twice");
    run_window(100);
    expect(device.begin_calls == 2 && s_radio_diag.begin_failures == 2 && resets == 1,
           "two failed full-LoRa restores reset instead of returning in FSK mode");
    expect(device.callback == nullptr, "reset path detached the optional callback first");
    expect(s_ctt_runtime.phase == CTT_PHASE_RESTORE && s_ctt_runtime.exit_reason == CTT_EXIT_DEADLINE &&
           s_ctt_runtime.window_end_ms == 100, "failed restore never reports done");

    reset_case(Scenario::ParamRestore, "parameter restore reinitializes");
    run_window(100);
    expect(s_radio_diag.restore_attempts == 1 && s_radio_diag.restore_recovered == 1 &&
           init_calls == 1 && resets == 0,
           "failed parameter restore reaches one bounded full initialization");
    expect_cleanup_and_primary();

    reset_case(Scenario::ReinitReset, "parameter restore reinit fails");
    run_window(100);
    expect(s_radio_diag.restore_attempts == 1 && init_calls == 1 && resets == 1,
           "failed bounded reinitialization resets rather than returning unknown PHY");
    expect(device.callback == nullptr, "reinitialization reset path detached callback first");
    expect(s_ctt_runtime.phase == CTT_PHASE_RESTORE, "failed reinitialization remains restoring");

    reset_case(Scenario::ReadBoundaryIrq, "IRQ during read boundary");
    run_window();
    expect_runtime(CTT_EXIT_DEADLINE, 2, 2, 0, 7, 1500);
    expect(device.read_calls == 1 && s_ctt.frames_rx == 1,
           "IRQ observation does not change the existing second flag-clear behavior");
    expect_cleanup_and_primary();

    reset_case(Scenario::ReadRecovery, "read failure followed by success");
    run_window();
    expect_runtime(CTT_EXIT_DEADLINE, 3, 2, 1, 7, 1500);
    expect(s_ctt_runtime.last_read_status == 0 && s_ctt.frames_rx == 1,
           "latest read status updates while read-error total remains visible");
    expect_cleanup_and_primary();

    reset_case(Scenario::Deadline, "restore timing excluded");
    restore_delay_ms = 7;
    run_window(100);
    expect_runtime(CTT_EXIT_DEADLINE, 1, 0, 0, 0, 100);
    expect(window_used == 107, "original returned duration still includes restore work");
    expect_cleanup_and_primary();

    reset_case(Scenario::Valid, "per-window reset without resetting cumulative stats");
    run_window();
    const uint32_t prior_frames = s_ctt.frames_rx;
    stimulus = Scenario::Deadline;
    clock_origin = clock_ms;
    power_calls.clear();
    run_window(100);
    expect_runtime(CTT_EXIT_DEADLINE, 1, 0, 0, 0, 100);
    expect(s_ctt_runtime.last_read_status == 0 && s_ctt_runtime.latest_rail_mv == 0 &&
           s_ctt_runtime.latest_solar_mv == 0 && s_ctt.frames_rx == prior_frames && s_ctt.windows == 2,
           "only the separate per-window record resets between real invocations");

    std::printf("%u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
'''


def main() -> None:
    code = harness()
    final_cleanup = ("radio->clearPacketReceivedAction();\n" +
                     ("    s_ctt_runtime.exit_reason = exit_reason;\n"
                      if "s_ctt_runtime.exit_reason = exit_reason;" in code else "") +
                     "    ctt_restore_lorawan();\n    return millis() - start;\n}")

    def mutate(old: str, new: str) -> str:
        assert code.count(old) == 1, f"mutation target changed: {old}"
        return code.replace(old, new, 1)

    mutants = [
        (
            "CRC validation bypassed",
            mutate("if (ctt_decode(buf, &f))", "if (ctt_decode(buf, &f) || true)"),
            "FAIL CRC-invalid CTT frame: software CRC rejection cannot enqueue a tag",
        ),
        (
            "callback cleanup removed",
            mutate(final_cleanup, final_cleanup.replace("radio->clearPacketReceivedAction();", "")),
            "window leaves no optional RX callback or receive ownership",
        ),
        (
            "final LoRaWAN restore removed",
            mutate(final_cleanup, final_cleanup.replace("    ctt_restore_lorawan();\n", "")),
            "window restores the exact regional LoRaWAN TX PHY",
        ),
        (
            "re-arm failure no longer exits",
            mutate("break;  /* re-arm failed: bail, don't busy-loop deaf */", "(void)0;"),
            "FAIL receive re-arm fault: re-arm failure exits instead of waiting deaf",
        ),
    ]
    if "static int16_t ctt_start_receive(" in code:
        mutants.extend([
            (
                "initial arm reverted to driver default length",
                mutate("int16_t rx_state = ctt_start_receive();",
                       "int16_t rx_state = radio->startReceive();"),
                "every CTT RX launch uses five-byte fixed length",
            ),
            (
                "rearm reverted to driver default length",
                mutate("            rx_state = ctt_start_receive();",
                       "            rx_state = radio->startReceive();"),
                "every CTT RX launch uses five-byte fixed length",
            ),
            (
                "RX stage error ignored",
                mutate("if (state != RADIOLIB_ERR_NONE) return state;\n"
                       "    state = radio->fixedPacketLengthMode(5);",
                       "(void)state;\n    state = radio->fixedPacketLengthMode(5);"),
                "initial arm stops immediately at the failed radio operation",
            ),
            (
                "fixed length error ignored",
                mutate("if (state != RADIOLIB_ERR_NONE) return state;\n"
                       "    return radio->launchMode();",
                       "(void)state;\n    return radio->launchMode();"),
                "initial arm stops immediately at the failed radio operation",
            ),
            (
                "RX launch error ignored",
                mutate("return radio->launchMode();",
                       "(void)radio->launchMode(); return RADIOLIB_ERR_NONE;"),
                "initial arm failure is diagnosed once",
            ),
            (
                "fixed length reinstall omitted",
                mutate("state = radio->fixedPacketLengthMode(5);",
                       "state = RADIOLIB_ERR_NONE;"),
                "every CTT RX launch uses five-byte fixed length",
            ),
        ])
    if "static void ctt_runtime_reset(" in code:
        mutants.extend([
            ("IRQ count omitted", mutate("s_ctt_runtime.irq_count++;", "(void)0;"),
             "runtime arm IRQ and read-error counts describe this invocation only"),
            ("read error count omitted", mutate("s_ctt_runtime.read_errors++;", "(void)0;"),
             "runtime arm IRQ and read-error counts describe this invocation only"),
            ("sample validity not reset", mutate("s_ctt_runtime.sample_mask = 0;", "(void)0;"),
             "per-window record is reset before CTT callback registration"),
            ("RX phase never published", mutate("s_ctt_runtime.phase = CTT_PHASE_RX;", "(void)0;"),
             "runtime phase matches current radio operation"),
            ("read status discarded", mutate("s_ctt_runtime.last_read_status = read_state;",
                                             "s_ctt_runtime.last_read_status = 0;"),
             "failed read status is retained exactly"),
            ("restore prematurely reports done", mutate("s_ctt_runtime.phase = CTT_PHASE_RESTORE;",
                                                        "s_ctt_runtime.phase = CTT_PHASE_DONE;"),
             "exit reason is published before potentially nonreturning restore"),
            ("gate instrumentation rereads solar", mutate("s_ctt_runtime.latest_solar_mv = solar_mv;",
                                                          "s_ctt_runtime.latest_solar_mv = power_adc_read_solar_mv();"),
             "successful reads preserve the exact sampled values and gate order"),
        ])

    compiler = os.environ.get("CXX", "c++")
    flags = [
        compiler,
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-I",
        str(ROOT / "firmware/include"),
        "-I",
        str(ROOT / "firmware/src"),
    ]
    linked = [
        str(ROOT / "firmware/src/ctt_decode.cpp"),
        str(ROOT / "firmware/src/ctt_queue.cpp"),
    ]
    with tempfile.TemporaryDirectory(prefix="stratolink-ctt-window-") as temp:
        binary = str(Path(temp) / "ctt-window")

        def run(source: str) -> subprocess.CompletedProcess[str]:
            compiled = subprocess.run(
                flags + ["-x", "c++", "-"] + linked + ["-o", binary],
                input=source,
                text=True,
                capture_output=True,
            )
            assert compiled.returncode == 0, compiled.stderr
            return subprocess.run(
                [binary],
                text=True,
                capture_output=True,
                timeout=15,
                env={
                    **os.environ,
                    "ASAN_OPTIONS": "detect_leaks=0",
                    "UBSAN_OPTIONS": "halt_on_error=1",
                },
            )

        result = run(code)
        print(result.stdout, end="")
        print(result.stderr, end="")
        assert result.returncode == 0, "production CTT-window regression failed"
        for label, changed, expected_failure in mutants:
            result = run(changed)
            assert result.returncode == 1 and expected_failure in result.stdout, (
                f"mutant not rejected by intended runtime assertion: {label}\n"
                f"{result.stdout}{result.stderr}"
            )
            print(f"MUTATION REJECTED: {label}", flush=True)

    print(f"PASS: production CTT window and {len(mutants)} behavioral mutation checks")


if __name__ == "__main__":
    main()
