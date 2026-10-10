#!/usr/bin/env python3
"""Host-only real-caller IRQ-wait admission regression; never accesses hardware.

The existing real optional-window/CAD/B2B harness is retained. The pinned
SX126x::transmit implementation is compiled unchanged except its class name;
external SPI/IRQ/time boundaries model one emitted packet and missing TX_DONE.
At the final post-CAD ADC boundary, a controlled delay leaves 300 ms in the
window. Nominal 100 ms RF fits, but the pinned IRQ wait lasts 506 ms. Admission
must deny this handoff. This is not a total SPI/setup/cleanup wall-time bound.
"""

import os
from pathlib import Path
import subprocess
import tempfile

from relay_cad_runtime_test import ROOT, block, harness as cad_harness


def harness() -> str:
    code = cad_harness()
    code = code[:code.index("int main() {")]
    code = code.replace("static void next_primary()", "[[maybe_unused]] static void next_primary()", 1)
    code = code.replace("static unsigned checks, failures;", r'''
static unsigned checks, failures;
static bool delay_after_cad, deadline_delay_injected, tx_active, rf_emitted;
static uint32_t tx_started, tx_finished;
static unsigned emitted_count;
using RadioLibTime_t = uint32_t;
#define RADIOLIB_ERR_TX_TIMEOUT (-5)
#define RADIOLIB_ERR_PACKET_TOO_SHORT (-70)
#define RADIOLIB_ERR_PACKET_TOO_LONG (-4)
#define RADIOLIB_SX126X_LORA_CR_4_8 4
#define RADIOLIB_SX126X_LORA_CRC_ON 1
#define RADIOLIB_SX126X_MAX_PACKET_LENGTH 255
#define RADIOLIB_SX126X_PACKET_TYPE_LR_FHSS 3
#define RADIOLIB_SX126X_IRQ_TX_DONE 1
#define RADIOLIB_DEBUG_BASIC_PRINTLN(...) ((void)0)
''', 1)
    code = code.replace("static uint16_t power_adc_read_vSTOR_mv() {", r'''
static uint16_t power_adc_read_vSTOR_mv() {
    // An external ADC delay occurs before the production's final time check.
    // It is injected once and only after successful CAD, never in a caller.
    if (delay_after_cad && cad_ever && !cad_active && !deadline_delay_injected) {
        clock_ms = elapsed_origin + 2200u;
        deadline_delay_injected = true;
    }
''', 1)
    code = code.replace("struct FakeHal {", r'''
struct FakeHal {
    uint32_t millis() { return clock_ms; }
''', 1)
    code = code.replace("        idle_step();\n        if (cad_active", r'''
        idle_step();
        // RF completes at the nominal 100 ms; its completion IRQ never rises.
        if (tx_active && !rf_emitted && clock_ms - tx_started >= 100u) {
            rf_emitted = true;
            ++emitted_count;
        }
        if (cad_active''', 1)
    old_transmit = block(code, "int16_t transmit(const uint8_t*, size_t)")
    code = code.replace(old_transmit, r'''
uint8_t codingRate = 0, crcTypeLoRa = 0;
int16_t startTransmit(const uint8_t*, size_t, uint8_t) {
    expect(sync == 0x2B && sf == 11 && bandwidth == 250.0f,
           "optional handoff uses LongFast PHY");
    ++tx_count;
    tx_active = true; rf_emitted = false; tx_started = clock_ms;
    irq_pending = false;
    return RADIOLIB_ERR_NONE;
}
uint8_t getPacketType() { return 1; }
uint16_t getIrqFlags() { return 0; }
void hopLRFHSS() {}
int16_t finishTransmit() {
    tx_finished = clock_ms; tx_active = false;
    return RADIOLIB_ERR_NONE;
}
int16_t transmit(const uint8_t*, size_t, uint8_t = 0);
''', 1)
    library = (ROOT / "firmware/.pio/libdeps/stratolink/RadioLib/src/modules/SX126x/SX126x.cpp").read_text()
    transmit = block(library, "int16_t SX126x::transmit(const uint8_t* data, size_t len, uint8_t addr)")
    transmit = transmit.replace("SX126x::", "FakeRadio::", 1)
    code = code.replace("static FakeRadio device;", transmit + "\nstatic FakeRadio device;", 1)
    code = code.replace("events.clear(); device = FakeRadio{};", r'''
delay_after_cad = deadline_delay_injected = tx_active = rf_emitted = false;
    tx_started = tx_finished = 0; emitted_count = 0;
    events.clear(); device = FakeRadio{};''', 1)
    return code + r'''
static void seed(unsigned route) {
    if (route == 3) lorawan_b2b_set_local_crumb(0, 0, 0);
    else seed_route(route);
}

static void check_cleanup() {
    expect(!cad_active && !tx_active && device.callback == nullptr && device.sync == 0x34,
           "optional exit releases IRQ and restores primary PHY");
    expect(guard_count == 0 && resets == 0,
           "IRQ wait regression needs no host guard or MCU reset");
}

static void check_admission_boundaries() {
    name = "IRQ wait admission boundaries";
    struct Edge {
        uint32_t now, start, window, toa;
        bool allowed;
    };
    // Literal expectations: 100 ms nominal ToA needs 506 ms IRQ-wait budget
    // plus 100 ms guard, with strictly more remaining time for admission.
    const Edge edges[] = {
        {0u, 0u, 605u, 100u, false},
        {0u, 0u, 606u, 100u, false},
        {0u, 0u, 607u, 100u, true},
        {1894u, 0u, 2500u, 100u, false},
        {1893u, 0u, 2500u, 100u, true},
        {2500u, 0u, 2500u, 100u, false},
        {2501u, 0u, 2500u, 100u, false},
        {0u, 0u, 0u, 100u, false},
        {0u, 0u, 611u, 101u, false},
        {0u, 0u, 612u, 101u, true},
        {20u, UINT32_MAX - 19u, 646u, 100u, false},
        {20u, UINT32_MAX - 19u, 647u, 100u, true},
    };
    for (const Edge& edge : edges) {
        clock_ms = edge.now;
        expect(relay_cad_has_tx_room(edge.start, edge.window, edge.toa) == edge.allowed,
               "exact IRQ reserve boundary and expired/wrapped windows enforce admission");
    }
    clock_ms = 0;
    expect(!relay_cad_has_tx_room(0, UINT32_MAX, UINT32_MAX),
           "wide arithmetic refuses overflowing timeout reserve");
    expect(relay_airtime_allows(0, 0, 100) && !relay_cad_has_tx_room(0, 606, 100),
           "first-frame airtime exception does not create time for its IRQ wait");
}

int main() {
    check_admission_boundaries();
    const char* labels[] = {"Mesh", "B2B origin", "B2B forward", "B2B crumb"};
    for (uint32_t start : {0u, UINT32_MAX - 2300u}) {
        for (unsigned route = 0; route < 4; ++route) {
            reset(Scenario::Clear, labels[route], route == 0, start);
            delay_after_cad = true;
            seed(route); run_window();
            std::printf("NEAR_END route=%s start=%u elapsed_ms=%u handoffs=%u emitted=%u irq_wait_ms=%u\n",
                        name, start, clock_ms - start, tx_count, emitted_count,
                        tx_count ? tx_finished - tx_started : 0u);
            expect(deadline_delay_injected, "real route reaches final post-CAD time gate");
            expect(tx_count == 0 && emitted_count == 0,
                   "handoff denied when nominal RF fits but IRQ wait exceeds remaining window");
            expect(clock_ms - start <= 2500u,
                   "no admitted TX-DONE wait crosses the optional window deadline");
            if (route == 1) expect(s_b2b_origin_n == 1, "untransmitted origin stays queued");
            if (route == 2) expect(s_b2b.fwd_count == 1 && s_b2b.stats.airtime_ms == 0 &&
                                   s_b2b.airtime_budget_ms == 125,
                                   "pre-handoff refusal fully refunds forwarding airtime");
            if (route == 3) expect(s_b2b_crumb_pending, "untransmitted crumb remains pending");
            check_cleanup();
        }
    }

    // Positive controls: enough window for the actual IRQ timeout. Failure is
    // still ambiguous RF: charge nominal airtime, stop the window, retain retry.
    for (unsigned route = 0; route < 4; ++route) {
        reset(Scenario::Clear, labels[route], route == 0);
        seed(route); run_window();
        expect(tx_count == 1 && emitted_count == 1 && tx_finished - tx_started == 506u,
               "roomy window permits one emitted frame then real 506ms IRQ timeout");
        expect(clock_ms - elapsed_origin < 2500u,
               "ambiguous error exits immediately instead of retrying in window");
        expect((route == 0 ? s_relay.tx_error : s_b2b.stats.tx_error) == 1,
               "missing TX_DONE is recorded as one error, not delivery");
        if (route == 2) expect(s_b2b.fwd_count == 1 && s_b2b.stats.airtime_ms == 100 &&
                               s_b2b.airtime_budget_ms == 25,
                               "emitted RF charge stays nominal100ms, not506ms wait");
        check_cleanup();
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

    mutants = [
        ("IRQ wait reserve replaced by nominal RF airtime", mutate(
            "5ull * toa_ms + 6ull + 100ull",
            "static_cast<uint64_t>(toa_ms) + 100ull"),
         "handoff denied when nominal RF fits but IRQ wait exceeds remaining window"),
        ("timeout reserve narrowed to32-bit arithmetic", mutate(
            "5ull * toa_ms + 6ull + 100ull", "5u * toa_ms + 6u + 100u"),
         "wide arithmetic refuses overflowing timeout reserve"),
        ("exact reserve equality admitted", mutate(
            "return required_ms < remaining;", "return required_ms <= remaining;"),
         "exact IRQ reserve boundary and expired/wrapped windows enforce admission"),
    ]
    flags = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
             "-Werror", "-pedantic", "-fsanitize=address,undefined",
             "-fno-omit-frame-pointer", "-I", str(ROOT / "firmware/include"),
             "-I", str(ROOT / "firmware/src")]
    linked = [str(ROOT / "firmware/src" / name) for name in (
        "b2b.cpp", "crypto_aes128.cpp", "meshtastic_relay_mac.cpp", "lorawan_liveness.cpp",
        "lorawan_crypto.cpp", "lorawan_frame.cpp", "lorawan_counter.cpp")]
    with tempfile.TemporaryDirectory(prefix="stratolink-relay-irq-wait-") as temp:
        binary = str(Path(temp) / "irq_wait")

        def run(source: str) -> subprocess.CompletedProcess:
            compiled = subprocess.run(flags + ["-x", "c++", "-"] + linked + ["-o", binary],
                                      input=source, text=True, capture_output=True, timeout=60)
            assert compiled.returncode == 0, compiled.stderr
            return subprocess.run([binary], text=True, capture_output=True, timeout=15,
                                  env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                                       "UBSAN_OPTIONS": "halt_on_error=1"})

        result = run(code)
        print(result.stdout, end="")
        print(result.stderr, end="")
        assert result.returncode == 0, "optional TX IRQ-wait admission regression failed"
        for label, changed, expected_failure in mutants:
            result = run(changed)
            assert result.returncode == 1 and expected_failure in result.stdout, (
                f"mutant not rejected by intended runtime assertion: {label}\n"
                f"{result.stdout}{result.stderr}")
            if label == "IRQ wait reserve replaced by nominal RF airtime":
                assert result.stdout.count(expected_failure) == 8, result.stdout
                assert result.stdout.count("elapsed_ms=2706 handoffs=1 emitted=1 irq_wait_ms=506") == 8, result.stdout
            print(f"MUTATION REJECTED: {label}", flush=True)
    print(f"PASS: actual optional TX IRQ-wait admission and {len(mutants)} behavioral mutation checks")


if __name__ == "__main__":
    main()
