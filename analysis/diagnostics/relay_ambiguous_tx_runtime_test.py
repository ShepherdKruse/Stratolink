#!/usr/bin/env python3
"""Regress possibly-emitted optional RF, not RF delivery or physical timing.

Reuse the CAD harness's real optional-window, B2B authentication/queues, mesh
MAC and subsequent primary path. Only external radio behavior changes: a TX
may consume one nominal packet's airtime and then return an error, as pinned
SX126x::transmit can do after startTransmit or finishTransmit. The public test
key and synthetic zero-coordinate crumb are not deployment credentials/data.

Breaks caught: success-only airtime charging; repeated ambiguous handoffs in
one window; refunding emitted airtime; falsely committing delivery/dedup;
losing a retryable B2B frame; charging a CAD-aborted pre-handoff reservation.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from relay_cad_runtime_test import ROOT, block, harness as cad_harness


def harness() -> str:
    code = cad_harness()
    # Keep every production function and shared fake boundary, but replace the
    # old test main. Source extraction is not an assertion about source text.
    code = code[:code.index("int main() {")]
    code = code.replace("static unsigned checks, failures;",
                        "static unsigned checks, failures;\n"
                        "static std::vector<std::vector<uint8_t>> emitted_frames;", 1)
    code = code.replace("events.clear(); device = FakeRadio{};",
                        "events.clear(); emitted_frames.clear(); device = FakeRadio{};", 1)
    old_transmit = block(code, "int16_t transmit(const uint8_t*, size_t)")
    code = code.replace(old_transmit, r'''
int16_t transmit(const uint8_t* data, size_t len) {
    events.push_back(in_primary ? "primary-tx" : "optional-tx");
    if (in_primary) {
        expect(sf == 9 && bandwidth == 125.0f && sync == 0x34 && coding == 5 &&
               preamble == 8 && crc && !iq, "next primary uses exact LoRaWAN PHY");
    } else {
        expect(sync == 0x2B && sf == 11 && bandwidth == 250.0f,
               "optional TX retains original LongFast PHY");
        ++tx_count; // Observable RF handoff, independent of returned status.
        emitted_frames.emplace_back(data, data + len);
    }
    clock_ms += (getTimeOnAir(len) + 999u) / 1000u;
    irq_pending = false;
    if (!in_primary && stimulus == Scenario::TxFault) return -74;
    return 0;
}''', 1)
    # Low SNR makes the real contention MAC retry within this 2.5 s fixture;
    # without this, a randomly late retry could conceal the repeated-handoff bug.
    code = code.replace("float getSNR() { return 10; }",
                        "float getSNR() { return -20; }", 1)
    return code + r'''
static void seed_ambiguous_route(unsigned route) {
    if (route == 3) lorawan_b2b_set_local_crumb(0, 0, 0);
    else seed_route(route);
}

static void expect_primary_restore() {
    expect(!cad_active && device.callback == nullptr && device.sync == 0x34,
           "optional exit cleans callbacks and restores primary PHY");
    expect(guard_count == 0 && resets == 0,
           "optional error requires neither host guard nor MCU reset");
    next_primary();
}

static void expect_same_retry_identity() {
    expect(emitted_frames.size() == 2, "exactly one failed and one healthy handoff recorded");
    if (emitted_frames.size() != 2) return;
    b2b_frame_t first = {}, retry = {};
    bool parsed = b2b_parse(emitted_frames[0].data(), (int)emitted_frames[0].size(), &first) &&
                  b2b_parse(emitted_frames[1].data(), (int)emitted_frames[1].size(), &retry);
    expect(parsed && first.src == retry.src && first.msg_id == retry.msg_id &&
           first.type == retry.type && first.ttl == retry.ttl && first.len == retry.len,
           "later retry retains authenticated frame identity and hop count");
    expect(parsed && b2b_auth_verify(s_b2b_fleet_key, &first) &&
           b2b_auth_verify(s_b2b_fleet_key, &retry),
           "retained retry authenticates even when real crumb-age refresh changes payload");
}

int main() {
    const char* labels[] = {"ambiguous mesh", "ambiguous origin",
                            "ambiguous forward", "ambiguous crumb"};
    for (unsigned route = 0; route < 4; ++route) {
        reset(Scenario::TxFault, labels[route], route == 0);
        seed_ambiguous_route(route);
        run_window();
        expect(tx_count == 1, "possibly emitted TX is not retried in the same window");
        expect(clock_ms - elapsed_origin < 2500,
               "ambiguous TX aborts optional window instead of waiting or retrying");
        expect((route == 0 ? s_relay.tx_error : s_b2b.stats.tx_error) == 1,
               "exactly one ambiguous error is recorded");
        expect(s_relay.fwd == 0 && !relay_dd_seen(0x22, 0x33),
               "ambiguous RF does not commit mesh forward success or dedup");
        if (route == 1) {
            expect(s_b2b_origin_n == 1,
                   "ambiguous origin remains queued for a later window");
        } else if (route == 2) {
            expect(s_b2b.fwd_count == 1 && s_b2b.stats.fwd == 0,
                   "ambiguous forward remains queued without successful-forward count");
            expect(s_b2b.stats.airtime_ms == 100 && s_b2b.airtime_budget_ms == 25,
                   "ambiguous forward retains its 100 ms debit from the 125 ms grant");
        } else if (route == 3) {
            expect(s_b2b_crumb_pending && s_b2b_crumb_frame_ready && !s_b2b_ever_sent_crumb,
                   "ambiguous crumb retains its prepared identity without success");
        }
        expect_primary_restore();

        // B2B retains its queues. Mesh is window-scoped and must be heard again;
        // the fixture below supplies that new copy, without resetting dedup.
        stimulus = Scenario::Clear; in_primary = false;
        tx_count = 0; mesh_delivered = false;
        run_window();
        expect(tx_count == 1, route == 0
               ? "later healthy window can forward a newly heard Mesh copy once"
               : "later healthy window can send the retained B2B frame once");
        if (route == 0) expect(s_relay.fwd == 1 && relay_dd_seen(0x22, 0x33),
                               "only successful mesh retry commits dedup");
        if (route == 1) expect(s_b2b_origin_n == 0, "successful later origin dequeues once");
        if (route == 2) expect(s_b2b.fwd_count == 0 && s_b2b.stats.fwd == 1 &&
                               s_b2b.stats.airtime_ms == 200 && s_b2b.airtime_budget_ms == 50,
                               "later forward pays a second debit, never recovering emitted credit");
        if (route == 3) expect(!s_b2b_crumb_pending && !s_b2b_crumb_frame_ready && s_b2b_ever_sent_crumb,
                               "successful later crumb commits only once");
        if (route != 0) expect_same_retry_identity();
    }

    // A pre-handoff CAD fault is different: the popped forward emitted nothing.
    reset(Scenario::Missing, "pre-handoff forward abort", false);
    (void)seed_forward(); run_window();
    expect(tx_count == 0 && s_b2b.fwd_count == 1 && s_b2b.stats.fwd == 0 &&
           s_b2b.stats.airtime_ms == 0 && s_b2b.airtime_budget_ms == 125,
           "pre-handoff CAD abort requeues and refunds the complete reservation");
    expect_primary_restore();

    // Observe the shared window budget directly, not only forwarder credit.
    reset(Scenario::TxFault, "B2B shared budget", false);
    seed_route(1);
    uint32_t used_ms = 0; bool abort_window = false;
    expect(radio_apply_lora_phy(904.3f, 11, 250.0f, 0x2B, 16, true, false),
           "configure direct handoff fixture");
    expect(!relay_send_b2b_frame(&s_b2b_origin[s_b2b_origin_head], 0, 2500,
                                &used_ms, 4200, &abort_window),
           "post-emission error is not delivery success");
    expect(used_ms == 100 && abort_window,
           "shared budget charges ambiguous handoff and requests window abort");
    expect(!relay_airtime_allows(used_ms, 0, 100),
           "ambiguous handoff cannot reuse the free first-frame admission");

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
        ("B2B handoff charge omitted", mutate("*used_ms += toa;", "(void)toa;"),
         "shared budget charges ambiguous handoff and requests window abort"),
        ("B2B ambiguous TX does not abort", mutate(
            "s_radio_diag.last_error = state;\n        *abort_window = true;",
            "s_radio_diag.last_error = state;"),
         "ambiguous TX aborts optional window instead of waiting or retrying"),
        ("mesh ambiguous TX does not abort", mutate(
            "s_relay.tx_error++;\n                        break;",
            "s_relay.tx_error++;"),
         "ambiguous TX aborts optional window instead of waiting or retrying"),
        ("emitted forward airtime refunded", mutate(
            "tx_airtime_ms == airtime_before ? toa : 0u",
            "((void)airtime_before, toa)"),
         "ambiguous forward retains its 100 ms debit from the 125 ms grant"),
    ]
    flags = [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
             "-Werror", "-pedantic", "-fsanitize=address,undefined",
             "-fno-omit-frame-pointer", "-I", str(ROOT / "firmware/include"),
             "-I", str(ROOT / "firmware/src")]
    linked = [str(ROOT / "firmware/src" / name) for name in (
        "b2b.cpp", "crypto_aes128.cpp", "meshtastic_relay_mac.cpp", "lorawan_liveness.cpp",
        "lorawan_crypto.cpp", "lorawan_frame.cpp", "lorawan_counter.cpp")]
    with tempfile.TemporaryDirectory(prefix="stratolink-relay-ambiguous-") as temp:
        binary = str(Path(temp) / "ambiguous")

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
        assert result.returncode == 0, "possibly-emitted optional TX regression failed"
        for label, changed, expected_failure in mutants:
            result = run(changed)
            assert result.returncode == 1 and expected_failure in result.stdout, (
                f"mutant not rejected by intended runtime assertion: {label}\n"
                f"{result.stdout}{result.stderr}")
            print(f"MUTATION REJECTED: {label}", flush=True)
    print(f"PASS: actual optional ambiguous-TX callers and {len(mutants)} behavioral mutation checks")


if __name__ == "__main__":
    main()
