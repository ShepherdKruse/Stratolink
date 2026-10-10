#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "lorawan_liveness.h"

static lorawan_liveness_qualification_t qualified_primary(void) {
    lorawan_liveness_qualification_t q = {};
    q.fresh_advancing_pvt = true;
    q.gnss_region_authority = true;
    q.normal_primary = true;
    q.freefall_clear = true;
    q.rx_power_qualified = true;
    q.region_tx_legal = true;
    return q;
}

static lorawan_liveness_probe_result_t completed_empty_exchange(void) {
    lorawan_liveness_probe_result_t result = {};
    result.local_tx_succeeded = true;
    result.rx1_completed = true;
    result.rx2_completed = true;
    result.rx_path_healthy = true;
    return result;
}

static void advance_to_probe(lorawan_liveness_state_t* state,
                             const lorawan_liveness_qualification_t* q,
                             uint32_t* next_fcnt) {
    for (uint8_t i = 0; i < LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX; ++i) {
        assert(!lorawan_liveness_probe_due(state, q));
        assert(lorawan_liveness_note_ordinary_primary(state, q, true));
        (*next_fcnt)++; /* every ordinary uplink reserves a fresh FCnt */
    }
    assert(state->countdown == 0u);
    assert(lorawan_liveness_probe_due(state, q));
}

int main(void) {
    lorawan_liveness_state_t state = {};
    lorawan_liveness_begin_session(&state);
    assert(lorawan_liveness_state_valid(&state));
    assert(state.countdown == 0u && state.qualified_miss_streak == 0u);
    assert(!state.probe_pending && !state.server_proven &&
           !state.initial_probe_attempted);

    lorawan_liveness_qualification_t q = qualified_primary();
    uint32_t next_fcnt = 100u;

    /* A fresh OTAA session never waits 24 ordinary cycles for its first
     * authenticated primary proof. */
    assert(lorawan_liveness_probe_due(&state, &q));
    assert(!lorawan_liveness_note_ordinary_primary(&state, &q, false));
    assert(state.countdown == 0u);

    /* Reset/fault boundary matrix around the initial confirmed primary.
     * Before the FCnt/pending transaction is durable, a local PHY failure
     * restores this snapshot and reset must keep the first probe due now.
     * Once the pending reservation is durable, reset treats it as ambiguous
     * and moves to sparse cadence, preventing confirmed-frame amplification. */
    lorawan_liveness_state_t before_reservation = state;
    assert(lorawan_liveness_arm_probe(&state, &q));
    state = before_reservation;  /* injected pre-reservation local failure */
    assert(lorawan_liveness_normalize_after_import(&state));
    assert(lorawan_liveness_probe_due(&state, &q));
    assert(!state.probe_pending && !state.initial_probe_attempted);

    lorawan_liveness_state_t durably_reserved = state;
    assert(lorawan_liveness_arm_probe(&durably_reserved, &q));
    lorawan_liveness_state_t reset_after_reservation = durably_reserved;
    assert(lorawan_liveness_normalize_after_import(
        &reset_after_reservation));
    assert(reset_after_reservation.countdown == 23u);
    assert(!reset_after_reservation.probe_pending &&
           reset_after_reservation.initial_probe_attempted &&
           !reset_after_reservation.server_proven);

    /* Every individual mission gate is mandatory. */
    lorawan_liveness_qualification_t bad = q;
#define ASSERT_GATE_REQUIRED(field) do { \
        bad = q; bad.field = false; \
        assert(!lorawan_liveness_primary_qualified(&bad)); \
        assert(!lorawan_liveness_probe_due(&state, &bad)); \
    } while (0)
    ASSERT_GATE_REQUIRED(fresh_advancing_pvt);
    ASSERT_GATE_REQUIRED(gnss_region_authority);
    ASSERT_GATE_REQUIRED(normal_primary);
    ASSERT_GATE_REQUIRED(freefall_clear);
    ASSERT_GATE_REQUIRED(rx_power_qualified);
    ASSERT_GATE_REQUIRED(region_tx_legal);
#undef ASSERT_GATE_REQUIRED

    assert(lorawan_liveness_arm_probe(&state, &q));
    uint32_t first_probe_fcnt = next_fcnt++;
    assert(state.probe_pending && state.initial_probe_attempted);
    assert(!state.server_proven);
    assert(!lorawan_liveness_arm_probe(&state, &q));

    /* Local-TX ambiguity records that the initial probe was already attempted,
     * restarts the sparse interval, and cannot create reset amplification. */
    assert(lorawan_liveness_abandon_probe(&state));
    assert(!state.probe_pending && state.countdown == 23u);
    assert(state.qualified_miss_streak == 0u && !state.server_proven &&
           state.initial_probe_attempted);
    lorawan_liveness_state_t imported = state;
    assert(lorawan_liveness_normalize_after_import(&imported));
    assert(imported.countdown == 23u && !imported.probe_pending &&
           imported.initial_probe_attempted && !imported.server_proven);

    advance_to_probe(&state, &q, &next_fcnt);
    assert(lorawan_liveness_arm_probe(&state, &q));
    uint32_t second_probe_fcnt = next_fcnt++;
    assert(second_probe_fcnt > first_probe_fcnt);

    /* None of the locally ambiguous Class-A outcomes may advance the streak
     * or qualify optional services. */
    lorawan_liveness_probe_result_t complete = completed_empty_exchange();
#define ASSERT_AMBIGUOUS(field) do { \
        lorawan_liveness_probe_result_t ambiguous = complete; \
        ambiguous.field = false; \
        assert(lorawan_liveness_complete_probe(&state, &q, &ambiguous) == \
               LORAWAN_LIVENESS_PROBE_ABANDONED); \
        assert(!state.probe_pending && state.qualified_miss_streak == 0u && \
               state.countdown == 23u && !state.server_proven && \
               state.initial_probe_attempted); \
        advance_to_probe(&state, &q, &next_fcnt); \
        assert(lorawan_liveness_arm_probe(&state, &q)); \
        next_fcnt++; \
    } while (0)
    ASSERT_AMBIGUOUS(local_tx_succeeded);
    ASSERT_AMBIGUOUS(rx1_completed);
    ASSERT_AMBIGUOUS(rx2_completed);
    ASSERT_AMBIGUOUS(rx_path_healthy);
#undef ASSERT_AMBIGUOUS

    /* A mission gate that changes before completion (power sag, freefall,
     * lease expiry, or loss of same-cycle PVT provenance) is also ambiguous. */
#define ASSERT_COMPLETION_GATE(field) do { \
        bad = q; bad.field = false; \
        assert(lorawan_liveness_complete_probe(&state, &bad, &complete) == \
               LORAWAN_LIVENESS_PROBE_ABANDONED); \
        assert(!state.probe_pending && state.qualified_miss_streak == 0u && \
               state.countdown == 23u && !state.server_proven); \
        advance_to_probe(&state, &q, &next_fcnt); \
        assert(lorawan_liveness_arm_probe(&state, &q)); \
        next_fcnt++; \
    } while (0)
    ASSERT_COMPLETION_GATE(fresh_advancing_pvt);
    ASSERT_COMPLETION_GATE(gnss_region_authority);
    ASSERT_COMPLETION_GATE(normal_primary);
    ASSERT_COMPLETION_GATE(freefall_clear);
    ASSERT_COMPLETION_GATE(rx_power_qualified);
    ASSERT_COMPLETION_GATE(region_tx_legal);
#undef ASSERT_COMPLETION_GATE

    /* Any authenticated Class-A downlink, including an empty ACK-only frame,
     * is conclusive evidence even if a later local condition became ineligible. */
    lorawan_liveness_probe_result_t evidence = complete;
    evidence.authenticated_downlink = true;
    bad = q;
    bad.rx_power_qualified = false;
    assert(lorawan_liveness_complete_probe(&state, &bad, &evidence) ==
           LORAWAN_LIVENESS_SERVER_PROVEN);
    assert(state.countdown == 23u && state.qualified_miss_streak == 0u &&
           !state.probe_pending && state.server_proven &&
           state.initial_probe_attempted);

    /* CRC-protected proven state remains bound to the same imported session;
     * it does not manufacture another first-session confirmed uplink. */
    imported = state;
    assert(lorawan_liveness_normalize_after_import(&imported));
    assert(imported.server_proven && imported.initial_probe_attempted &&
           imported.countdown == 23u);

    /* A local fault can never create or preserve server proof. */
    assert(lorawan_liveness_note_local_fault(&state));
    assert(!state.server_proven && state.initial_probe_attempted &&
           state.countdown == 23u && !state.probe_pending);
    lorawan_liveness_mark_server_proven(&state);

    /* Three fully qualified empty exchanges trigger recovery. Each probe is a
     * new primary with a strictly increasing FCnt; there is no same-FCnt
     * confirmed retransmission loop. */
    uint32_t probe_fcnt[3] = {};
    for (uint8_t miss = 0; miss < 3u; ++miss) {
        advance_to_probe(&state, &q, &next_fcnt);
        assert(lorawan_liveness_arm_probe(&state, &q));
        assert(!state.server_proven && state.initial_probe_attempted);
        probe_fcnt[miss] = next_fcnt++;
        lorawan_liveness_event_t expected = miss == 2u
            ? LORAWAN_LIVENESS_RECOVERY_DUE
            : LORAWAN_LIVENESS_QUALIFIED_MISS;
        assert(lorawan_liveness_complete_probe(&state, &q, &complete) ==
               expected);
        assert(state.qualified_miss_streak == (uint8_t)(miss + 1u));
        assert(!state.server_proven && state.initial_probe_attempted);
    }
    assert(probe_fcnt[0] < probe_fcnt[1] && probe_fcnt[1] < probe_fcnt[2]);
    assert(lorawan_liveness_recovery_due(&state));
    assert(!lorawan_liveness_probe_due(&state, &q));
    assert(!lorawan_liveness_note_ordinary_primary(&state, &q, true));

    /* New-format pending intent is inconclusive across reset. Preserve earlier
     * qualified misses and the attempted bit, then resume sparse spacing. */
    state = {0u, 2u, true, false, true};
    assert(lorawan_liveness_normalize_after_import(&state));
    assert(state.countdown == 23u && state.qualified_miss_streak == 2u &&
           !state.probe_pending && !state.server_proven &&
           state.initial_probe_attempted);

    /* Pre-patch current and legacy records carry neither qualification bit.
     * They fail closed and force the first eligible primary due now. */
    state = {23u, 0u, false, false, false};
    assert(lorawan_liveness_normalize_after_import(&state));
    assert(state.countdown == 0u && !state.server_proven &&
           !state.initial_probe_attempted);
    state = {0u, 2u, true, false, false};
    assert(lorawan_liveness_normalize_after_import(&state));
    assert(state.countdown == 0u && state.qualified_miss_streak == 2u &&
           !state.probe_pending);
    state = {23u, 3u, false, false, false};
    assert(lorawan_liveness_normalize_after_import(&state));
    assert(lorawan_liveness_recovery_due(&state));

    /* Completion/save reset matrix. Before the atomic miss save, retained
     * pending miss2 can only normalize to ambiguous miss2. After the save,
     * miss3 remains recovery-due across reset; no boundary can publish a
     * completed empty exchange while silently losing the third miss. */
    lorawan_liveness_state_t retained_before_miss_save = {
        0u, 2u, true, false, true
    };
    lorawan_liveness_state_t staged_miss3 = retained_before_miss_save;
    assert(lorawan_liveness_complete_probe(&staged_miss3, &q, &complete) ==
           LORAWAN_LIVENESS_RECOVERY_DUE);
    assert(lorawan_liveness_recovery_due(&staged_miss3));

    lorawan_liveness_state_t reset_before_miss_save =
        retained_before_miss_save;
    assert(lorawan_liveness_normalize_after_import(&reset_before_miss_save));
    assert(reset_before_miss_save.qualified_miss_streak == 2u);
    assert(reset_before_miss_save.countdown == 23u);
    assert(!reset_before_miss_save.probe_pending);
    assert(!lorawan_liveness_recovery_due(&reset_before_miss_save));

    lorawan_liveness_state_t reset_after_miss_save = staged_miss3;
    assert(lorawan_liveness_normalize_after_import(&reset_after_miss_save));
    assert(reset_after_miss_save.qualified_miss_streak == 3u);
    assert(lorawan_liveness_recovery_due(&reset_after_miss_save));

    /* Invalid retained metadata is never normalized into plausible state. */
    state = {24u, 0u, false, false, false};
    assert(!lorawan_liveness_state_valid(&state));
    assert(!lorawan_liveness_normalize_after_import(&state));
    state = {0u, 4u, false, false, false};
    assert(!lorawan_liveness_state_valid(&state));
    assert(!lorawan_liveness_recovery_due(&state));
    state = {0u, 3u, true, false, true};
    assert(!lorawan_liveness_state_valid(&state));
    state = {0u, 0u, false, true, false};
    assert(!lorawan_liveness_state_valid(&state));
    state = {0u, 0u, true, true, true};
    assert(!lorawan_liveness_state_valid(&state));
    state = {23u, 1u, false, true, true};
    assert(!lorawan_liveness_state_valid(&state));

    /* Exhaust every structurally valid retained state and every local result
     * bit combination. No public transition may manufacture invalid state or
     * advance a streak unless all four local completion proofs are true. */
    for (uint8_t countdown = 0u; countdown <= 23u; ++countdown) {
        for (uint8_t misses = 0u; misses <= 3u; ++misses) {
            for (uint8_t pending = 0u; pending <= 1u; ++pending) {
                for (uint8_t proven = 0u; proven <= 1u; ++proven) {
                    for (uint8_t attempted = 0u; attempted <= 1u; ++attempted) {
                        lorawan_liveness_state_t seed = {
                            countdown, misses, pending != 0u, proven != 0u,
                            attempted != 0u
                        };
                        if (!lorawan_liveness_state_valid(&seed)) continue;

                        lorawan_liveness_state_t next = seed;
                        assert(lorawan_liveness_normalize_after_import(&next));
                        assert(lorawan_liveness_state_valid(&next));
                        next = seed;
                        (void)lorawan_liveness_note_ordinary_primary(
                            &next, &q, true);
                        assert(lorawan_liveness_state_valid(&next));
                        next = seed;
                        (void)lorawan_liveness_arm_probe(&next, &q);
                        assert(lorawan_liveness_state_valid(&next));
                        next = seed;
                        (void)lorawan_liveness_abandon_probe(&next);
                        assert(lorawan_liveness_state_valid(&next));
                        next = seed;
                        (void)lorawan_liveness_note_local_fault(&next);
                        assert(lorawan_liveness_state_valid(&next));

                        for (uint8_t mask = 0u; mask < 32u; ++mask) {
                            lorawan_liveness_probe_result_t result = {};
                            result.local_tx_succeeded = (mask & 0x01u) != 0u;
                            result.rx1_completed = (mask & 0x02u) != 0u;
                            result.rx2_completed = (mask & 0x04u) != 0u;
                            result.rx_path_healthy = (mask & 0x08u) != 0u;
                            result.authenticated_downlink =
                                (mask & 0x10u) != 0u;
                            next = seed;
                            lorawan_liveness_event_t event =
                                lorawan_liveness_complete_probe(
                                    &next, &q, &result);
                            assert(lorawan_liveness_state_valid(&next));
                            if (result.authenticated_downlink) {
                                assert(event == LORAWAN_LIVENESS_SERVER_PROVEN);
                                assert(next.qualified_miss_streak == 0u &&
                                       next.countdown == 23u &&
                                       !next.probe_pending &&
                                       next.server_proven &&
                                       next.initial_probe_attempted);
                            } else if (!seed.probe_pending) {
                                assert(event == LORAWAN_LIVENESS_NO_CHANGE);
                                assert(next.qualified_miss_streak == misses);
                            } else {
                                bool all_local_proofs =
                                    result.local_tx_succeeded &&
                                    result.rx1_completed &&
                                    result.rx2_completed &&
                                    result.rx_path_healthy;
                                if (all_local_proofs) {
                                    assert(event == (misses == 2u
                                        ? LORAWAN_LIVENESS_RECOVERY_DUE
                                        : LORAWAN_LIVENESS_QUALIFIED_MISS));
                                    assert(next.qualified_miss_streak ==
                                           (uint8_t)(misses + 1u));
                                    assert(!next.server_proven &&
                                           next.initial_probe_attempted);
                                } else {
                                    assert(event ==
                                           LORAWAN_LIVENESS_PROBE_ABANDONED);
                                    assert(next.qualified_miss_streak == misses);
                                    assert(!next.server_proven &&
                                           next.initial_probe_attempted);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    puts("LoRaWAN server-liveness policy: session proof/reset cases passed");
    return 0;
}
