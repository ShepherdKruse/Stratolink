#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "lorawan_session_meta.h"

int main(void) {
    /* Every unmarked legacy v3 RxDelay imports unproven and due immediately. */
    for (uint8_t delay = 1u; delay <= 15u; ++delay) {
        lorawan_session_meta_t decoded = {};
        assert(lorawan_session_meta_decode(delay, &decoded));
        assert(decoded.rx_delay_sec == delay);
        assert(decoded.legacy_without_liveness);
        assert(decoded.liveness.countdown == 0u);
        assert(decoded.liveness.qualified_miss_streak == 0u);
        assert(!decoded.liveness.probe_pending);
        assert(!decoded.liveness.server_proven);
        assert(!decoded.liveness.initial_probe_attempted);
    }

    /* Exhaust every structurally valid marked state and demand bit-exact
     * round-trip parity, including the two new qualification bits. */
    for (uint8_t delay = 1u; delay <= 15u; ++delay) {
        for (uint8_t countdown = 0u; countdown <= 23u; ++countdown) {
            for (uint8_t misses = 0u; misses <= 3u; ++misses) {
                for (uint8_t pending = 0u; pending <= 1u; ++pending) {
                    for (uint8_t proven = 0u; proven <= 1u; ++proven) {
                        for (uint8_t attempted = 0u;
                             attempted <= 1u; ++attempted) {
                            lorawan_liveness_state_t state = {
                                countdown, misses, pending != 0u,
                                proven != 0u, attempted != 0u
                            };
                            bool valid = lorawan_liveness_state_valid(&state);
                            uint32_t encoded = UINT32_MAX;
                            assert(lorawan_session_meta_encode(
                                       delay, &state, &encoded) == valid);
                            if (!valid) continue;
                            assert((encoded & 0x0Fu) == delay);
                            assert((encoded &
                                    LORAWAN_SESSION_LIVENESS_MARKER) != 0u);
                            assert(((encoded & LORAWAN_SESSION_SERVER_PROVEN)
                                    != 0u) == (proven != 0u));
                            assert(((encoded &
                                     LORAWAN_SESSION_INITIAL_PROBE_TRIED)
                                    != 0u) == (attempted != 0u));
                            assert((encoded &
                                    ~LORAWAN_SESSION_META_ALLOWED_MASK) == 0u);
                            lorawan_session_meta_t decoded = {};
                            assert(lorawan_session_meta_decode(
                                encoded, &decoded));
                            assert(!decoded.legacy_without_liveness);
                            assert(decoded.rx_delay_sec == delay);
                            assert(decoded.liveness.countdown == countdown);
                            assert(decoded.liveness.qualified_miss_streak ==
                                   misses);
                            assert(decoded.liveness.probe_pending ==
                                   (pending != 0u));
                            assert(decoded.liveness.server_proven ==
                                   (proven != 0u));
                            assert(decoded.liveness.initial_probe_attempted ==
                                   (attempted != 0u));
                        }
                    }
                }
            }
        }
    }

    lorawan_session_meta_t decoded = {};
    assert(!lorawan_session_meta_decode(0u, &decoded));
    assert(!lorawan_session_meta_decode(
        LORAWAN_SESSION_LIVENESS_MARKER, &decoded));
    /* Metadata without the marker is neither legacy nor current. */
    assert(!lorawan_session_meta_decode(0x0011u, &decoded));
    for (uint8_t bit = 15u; bit < 32u; ++bit) {
        assert(!lorawan_session_meta_decode(
            5u | LORAWAN_SESSION_LIVENESS_MARKER | (1u << bit), &decoded));
    }
    /* Proof cannot exist without an initial probe/data-down opportunity. */
    assert(!lorawan_session_meta_decode(
        5u | LORAWAN_SESSION_LIVENESS_MARKER |
        LORAWAN_SESSION_SERVER_PROVEN, &decoded));

    /* A d880/pre-patch marked record has neither new bit. It still decodes
     * byte-for-byte, then import forces a prompt first eligible probe. */
    uint32_t old_current_word = 5u |
        LORAWAN_SESSION_LIVENESS_MARKER |
        (23u << 4);
    assert(lorawan_session_meta_decode(old_current_word, &decoded));
    assert(!decoded.liveness.server_proven);
    assert(!decoded.liveness.initial_probe_attempted);
    assert(decoded.liveness.countdown == 23u);
    assert(lorawan_liveness_normalize_after_import(&decoded.liveness));
    assert(decoded.liveness.countdown == 0u);

    /* A local failure before FCnt/pending reservation leaves the last durable
     * record untouched. Reset therefore retries the one prompt first probe
     * instead of imposing the 24-cycle sparse delay. */
    lorawan_liveness_state_t due_before_reservation = {
        0u, 0u, false, false, false
    };
    uint32_t due_word = 0u;
    assert(lorawan_session_meta_encode(
        5u, &due_before_reservation, &due_word));
    assert(lorawan_session_meta_decode(due_word, &decoded));
    assert(lorawan_liveness_normalize_after_import(&decoded.liveness));
    assert(decoded.liveness.countdown == 0u);
    assert(!decoded.liveness.probe_pending);
    assert(!decoded.liveness.initial_probe_attempted);

    /* Reset after the arm-before-RF save records attempted=true. Pending intent
     * imports as ambiguity and resumes sparse cadence without another prompt
     * confirmed uplink or a manufactured miss. */
    lorawan_liveness_state_t pending = {0u, 2u, true, false, true};
    uint32_t pending_word = 0u;
    assert(lorawan_session_meta_encode(5u, &pending, &pending_word));
    assert((pending_word & LORAWAN_SESSION_INITIAL_PROBE_TRIED) != 0u);
    assert(lorawan_session_meta_decode(pending_word, &decoded));
    assert(lorawan_liveness_normalize_after_import(&decoded.liveness));
    assert(decoded.liveness.countdown == 23u);
    assert(decoded.liveness.qualified_miss_streak == 2u);
    assert(!decoded.liveness.probe_pending);
    assert(!decoded.liveness.server_proven);
    assert(decoded.liveness.initial_probe_attempted);
    assert(!lorawan_liveness_recovery_due(&decoded.liveness));

    /* If reset lands after RX2 but before a miss transaction can publish, the
     * old durable pending record is still only ambiguous miss2. The receive
     * API is responsible for withholding COMPLETE until the new record saves. */
    lorawan_session_meta_t before_miss_save = {};
    assert(lorawan_session_meta_decode(pending_word, &before_miss_save));
    assert(lorawan_liveness_normalize_after_import(
        &before_miss_save.liveness));
    assert(before_miss_save.liveness.qualified_miss_streak == 2u);
    assert(before_miss_save.liveness.countdown == 23u);
    assert(!lorawan_liveness_recovery_due(&before_miss_save.liveness));

    /* Authenticated proof survives reset only because it is session-bound,
     * CRC-protected metadata. Import does not generate another first probe. */
    lorawan_liveness_state_t proven = {17u, 0u, false, true, true};
    uint32_t proven_word = 0u;
    assert(lorawan_session_meta_encode(5u, &proven, &proven_word));
    assert((proven_word & LORAWAN_SESSION_SERVER_PROVEN) != 0u);
    assert((proven_word & LORAWAN_SESSION_INITIAL_PROBE_TRIED) != 0u);
    assert(lorawan_session_meta_decode(proven_word, &decoded));
    assert(lorawan_liveness_normalize_after_import(&decoded.liveness));
    assert(decoded.liveness.server_proven);
    assert(decoded.liveness.initial_probe_attempted);
    assert(decoded.liveness.countdown == 17u);

    /* A durably completed third miss remains recovery-due until session
     * invalidation succeeds; proof must be false in that state. */
    lorawan_liveness_state_t recovery = {23u, 3u, false, false, true};
    uint32_t recovery_word = 0u;
    assert(lorawan_session_meta_encode(5u, &recovery, &recovery_word));
    assert(lorawan_session_meta_decode(recovery_word, &decoded));
    assert(lorawan_liveness_normalize_after_import(&decoded.liveness));
    assert(!decoded.liveness.server_proven);
    assert(lorawan_liveness_recovery_due(&decoded.liveness));

    puts("LoRaWAN retained liveness metadata: proof/reset layouts passed");
    return 0;
}
