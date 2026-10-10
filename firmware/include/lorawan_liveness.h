#ifndef LORAWAN_LIVENESS_H
#define LORAWAN_LIVENESS_H

#include <stdbool.h>
#include <stdint.h>

/* A healthy session asks the network for proof only once per 24 qualified
 * primary cycles.  At the normal 1200 s cadence this is at most three
 * confirmed-uplink ACK downlinks per day, leaving the Class-A command budget
 * mostly untouched. */
#define LORAWAN_LIVENESS_PROBE_INTERVAL 24u
#define LORAWAN_LIVENESS_PROBE_COUNTDOWN_MAX \
    (LORAWAN_LIVENESS_PROBE_INTERVAL - 1u)
#define LORAWAN_LIVENESS_MISSES_BEFORE_RECOVERY 3u

/**
 * Compact state persisted with the retained LoRaWAN session.
 *
 * countdown is the number of additional qualified ordinary primaries before
 * the next primary is made confirmed.  A value of zero means "probe due".
 * probe_pending and initial_probe_attempted are set before the confirmed frame
 * is handed to the radio so a reset cannot make an interrupted probe look
 * completed or repeatedly schedule a new first-session probe.  server_proven
 * is set only after an authenticated data downlink / ACK and its advanced
 * FCntDown have been durably committed with this state.
 */
typedef struct {
    uint8_t countdown;             /* 0..23 */
    uint8_t qualified_miss_streak; /* 0..3, saturated */
    bool probe_pending;
    bool server_proven;            /* authenticated proof for this session */
    bool initial_probe_attempted;  /* persisted anti-reset amplification bit */
} lorawan_liveness_state_t;

/** Mission gates required for a primary to participate in liveness policy. */
typedef struct {
    bool fresh_advancing_pvt;
    bool gnss_region_authority; /* explicit launch authority is not enough */
    bool normal_primary;        /* excludes burst and auxiliary uplinks */
    bool freefall_clear;
    bool rx_power_qualified;
    bool region_tx_legal;
} lorawan_liveness_qualification_t;

/** Local facts about the confirmed primary and its Class-A exchange. */
typedef struct {
    bool local_tx_succeeded;
    bool rx1_completed;
    bool rx2_completed;
    bool rx_path_healthy;       /* no config, arm, read, or restore fault */
    bool authenticated_downlink;
} lorawan_liveness_probe_result_t;

typedef enum {
    LORAWAN_LIVENESS_NO_CHANGE = 0,
    LORAWAN_LIVENESS_PROBE_ABANDONED,
    LORAWAN_LIVENESS_SERVER_PROVEN,
    LORAWAN_LIVENESS_QUALIFIED_MISS,
    LORAWAN_LIVENESS_RECOVERY_DUE,
} lorawan_liveness_event_t;

/** Start a new OTAA session unproven; its first eligible primary is due now. */
void lorawan_liveness_begin_session(lorawan_liveness_state_t* state);

/** Publish authenticated server proof and restart the sparse probe interval. */
void lorawan_liveness_mark_server_proven(
    lorawan_liveness_state_t* state);

/** Reject structurally impossible state before using retained metadata. */
bool lorawan_liveness_state_valid(const lorawan_liveness_state_t* state);

/** True only when all mission gates permit a meaningful confirmed probe. */
bool lorawan_liveness_primary_qualified(
    const lorawan_liveness_qualification_t* qualification);

/**
 * Normalize CRC-protected state after import.  A pre-upgrade record with both
 * qualification bits clear is unproven and due immediately.  A new record
 * whose first probe was already attempted retains the existing sparse cadence;
 * pending intent is abandoned without manufacturing a miss.  Proven state
 * remains bound to the imported session.
 */
bool lorawan_liveness_normalize_after_import(
    lorawan_liveness_state_t* state);

/** True when this qualified primary should use ConfirmedDataUp. */
bool lorawan_liveness_probe_due(
    const lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification);

/**
 * Count one successfully transmitted, qualified ordinary primary.  A due,
 * pending, invalid, or recovery state is unchanged rather than postponing the
 * required action.
 */
bool lorawan_liveness_note_ordinary_primary(
    lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification,
    bool local_tx_succeeded);

/** Mark a due probe pending immediately before its durable FCnt reservation. */
bool lorawan_liveness_arm_probe(
    lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification);

/**
 * Resolve a pending probe whose outcome is inconclusive.  This is shared by
 * local TX failure, freefall/preemption, low rail, incomplete RX windows, and
 * local PHY/RX faults.  It never advances the miss streak.
 */
bool lorawan_liveness_abandon_probe(lorawan_liveness_state_t* state);

/**
 * A local persistence/RX fault cannot create or retain server proof.  Preserve
 * the established countdown/miss policy, except that a pending probe is
 * abandoned into the normal sparse interval.
 */
bool lorawan_liveness_note_local_fault(
    lorawan_liveness_state_t* state);

/**
 * Complete the Class-A exchange.  Any authenticated downlink is conclusive
 * server/session evidence and resets the state, including an ACK-only frame.
 * A miss advances only after a locally successful confirmed TX and two fully
 * completed, healthy RX windows under every original mission qualification.
 * All other pending outcomes are abandoned as ambiguous.
 */
lorawan_liveness_event_t lorawan_liveness_complete_probe(
    lorawan_liveness_state_t* state,
    const lorawan_liveness_qualification_t* qualification,
    const lorawan_liveness_probe_result_t* result);

/** Three qualified misses require bounded same-region OTAA recovery. */
bool lorawan_liveness_recovery_due(
    const lorawan_liveness_state_t* state);

#endif /* LORAWAN_LIVENESS_H */
