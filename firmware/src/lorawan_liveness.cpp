#include "lorawan_liveness.h"

static void restart_sparse_interval(lorawan_liveness_state_t* state) {
    state->countdown = LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX;
    state->probe_pending = false;
}

void lorawan_liveness_begin_session(lorawan_liveness_state_t* state) {
    if (!state) return;
    state->countdown = 0u;
    state->qualified_miss_streak = 0u;
    state->probe_pending = false;
    state->server_proven = false;
    state->initial_probe_attempted = false;
}

void lorawan_liveness_mark_server_proven(
    lorawan_liveness_state_t* state) {
    if (!state) return;
    state->qualified_miss_streak = 0u;
    state->server_proven = true;
    state->initial_probe_attempted = true;
    restart_sparse_interval(state);
}

bool lorawan_liveness_state_valid(const lorawan_liveness_state_t* state) {
    if (!state) return false;
    if (state->countdown > LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX ||
        state->qualified_miss_streak >
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY) {
        return false;
    }
    /* Proof is meaningful only after a probe/data-down opportunity.  Arming a
     * new probe revokes the older proof before the pending record is saved. */
    if (state->server_proven &&
        (!state->initial_probe_attempted || state->probe_pending ||
         state->qualified_miss_streak != 0u)) {
        return false;
    }
    /* The transition API can arm only a due probe, and it stops probing as
     * soon as the third miss makes recovery due. Reject impossible retained
     * combinations instead of normalizing corrupted bits into live state. */
    if (state->probe_pending &&
        (state->countdown != 0u ||
         state->qualified_miss_streak >=
             LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY)) {
        return false;
    }
    if (state->qualified_miss_streak >=
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY &&
        state->countdown != LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX) {
        return false;
    }
    return true;
}

bool lorawan_liveness_primary_qualified(
    const lorawan_liveness_qualification_t* qualification) {
    return qualification &&
        qualification->fresh_advancing_pvt &&
        qualification->gnss_region_authority &&
        qualification->normal_primary &&
        qualification->freefall_clear &&
        qualification->rx_power_qualified &&
        qualification->region_tx_legal;
}

bool lorawan_liveness_normalize_after_import(
    lorawan_liveness_state_t* state) {
    if (!lorawan_liveness_state_valid(state)) return false;
    if (!state->server_proven && !state->initial_probe_attempted) {
        /* Legacy/current-prequalification metadata has no trustworthy proof
         * bit.  Preserve a completed third-miss recovery state; every other
         * imported session gets one prompt first eligible probe. */
        state->probe_pending = false;
        state->countdown =
            state->qualified_miss_streak >=
                    LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY
                ? LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX
                : 0u;
        return true;
    }
    if (state->probe_pending) {
        state->server_proven = false;
        restart_sparse_interval(state);
    }
    return true;
}

bool lorawan_liveness_probe_due(
    const lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification) {
    return lorawan_liveness_state_valid(state) &&
        lorawan_liveness_primary_qualified(qualification) &&
        state->qualified_miss_streak <
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY &&
        !state->probe_pending && state->countdown == 0u;
}

bool lorawan_liveness_note_ordinary_primary(
    lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification,
    bool local_tx_succeeded) {
    if (!lorawan_liveness_state_valid(state) ||
        !lorawan_liveness_primary_qualified(qualification) ||
        !local_tx_succeeded || state->probe_pending ||
        state->qualified_miss_streak >=
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY ||
        state->countdown == 0u) {
        return false;
    }
    state->countdown--;
    return true;
}

bool lorawan_liveness_arm_probe(
    lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification) {
    if (!lorawan_liveness_probe_due(state, qualification)) return false;
    state->probe_pending = true;
    state->server_proven = false;
    state->initial_probe_attempted = true;
    return true;
}

bool lorawan_liveness_abandon_probe(lorawan_liveness_state_t* state) {
    if (!lorawan_liveness_state_valid(state) || !state->probe_pending) {
        return false;
    }
    state->server_proven = false;
    state->initial_probe_attempted = true;
    restart_sparse_interval(state);
    return true;
}

bool lorawan_liveness_note_local_fault(
    lorawan_liveness_state_t* state) {
    if (!lorawan_liveness_state_valid(state)) return false;
    state->server_proven = false;
    state->initial_probe_attempted = true;
    if (state->probe_pending) restart_sparse_interval(state);
    return true;
}

lorawan_liveness_event_t lorawan_liveness_complete_probe(
    lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification,
    const lorawan_liveness_probe_result_t* result) {
    if (!lorawan_liveness_state_valid(state) || !result) {
        return LORAWAN_LIVENESS_NO_CHANGE;
    }

    /* The ACK bit and payload are exposed by the frame layer only after the
     * address, counter, and MIC gates.  An authenticated non-ACK downlink is
     * equally strong evidence that the Network Server still owns this
     * session, so do not waste two later gateway downlinks proving it again. */
    if (result->authenticated_downlink) {
        lorawan_liveness_mark_server_proven(state);
        return LORAWAN_LIVENESS_SERVER_PROVEN;
    }

    if (!state->probe_pending) return LORAWAN_LIVENESS_NO_CHANGE;

    const bool qualified_miss =
        lorawan_liveness_primary_qualified(qualification) &&
        result->local_tx_succeeded &&
        result->rx1_completed && result->rx2_completed &&
        result->rx_path_healthy;
    if (!qualified_miss) {
        (void)lorawan_liveness_abandon_probe(state);
        return LORAWAN_LIVENESS_PROBE_ABANDONED;
    }

    state->probe_pending = false;
    state->server_proven = false;
    state->initial_probe_attempted = true;
    if (state->qualified_miss_streak <
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY) {
        state->qualified_miss_streak++;
    }
    state->countdown = LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX;
    return state->qualified_miss_streak >=
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY
        ? LORAWAN_LIVENESS_RECOVERY_DUE
        : LORAWAN_LIVENESS_QUALIFIED_MISS;
}

bool lorawan_liveness_recovery_due(
    const lorawan_liveness_state_t* state) {
    return lorawan_liveness_state_valid(state) &&
        !state->probe_pending &&
        state->qualified_miss_streak >=
            LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY;
}
