#ifndef LORAWAN_H
#define LORAWAN_H

#include <stdint.h>
#include <stdbool.h>
#include "lorawan_liveness.h"

/**
 * Maximum application uplink at the selected regional data rates. US915 DR1
 * is the tightest implemented plan at 53 bytes (no uplink FOpts are emitted);
 * enforcing that common ceiling prevents a future typed event from producing
 * a locally transmitted frame the network server must reject.
 */
#define LORAWAN_PAYLOAD_MAX 53

/**
 * LoRaWAN regional frequency plan.  Selected at runtime by
 * lorawan_set_region(), see region_manager.h for GPS-driven dispatch.
 * Ordering is stable across firmware versions so it can be persisted
 * to TAMP backup registers.
 */
typedef enum {
    LORA_REGION_US915  = 0,
    LORA_REGION_EU868  = 1,
    LORA_REGION_AS923  = 2,
    LORA_REGION_AU915  = 3,
    LORA_REGION_SILENT = 4,   /* CN470, polar, etc, no TX, no join */
    LORA_REGION_COUNT          /* sentinel, not a selectable value */
} lora_region_id_t;

/**
 * Switch active region.  Invalidates any current OTAA session, a new
 * join is required on the next TX attempt (handled by main.cpp).
 * No-op if id matches the current region.
 *
 * For LORA_REGION_SILENT the radio is left configured for whatever the
 * previous region was, but join/send_uplink return false until a real
 * region is set again.
 */
void lorawan_set_region(lora_region_id_t id);
lora_region_id_t lorawan_current_region(void);

/**
 * Per-region OTAA credentials status.  True when the active region
 * has a non-empty (DevEUI, AppKey) pair flashed in secrets.h.  False
 * means lorawan_join in this region will fail-fast.
 */
bool lorawan_creds_loaded(void);

/**
 * Copy the active 8-byte DevEUI into out.  For test introspection.
 */
void lorawan_get_dev_eui(uint8_t* out);

/**
 * Session export/import for persistence across reset (see
 * power_manager_save_session / _load_session).  Caller owns storage.
 */
typedef struct {
    uint32_t magic;         /* set by save layer */
    uint32_t version;       /* set by save layer */
    uint32_t region_id;     /* lora_region_id_t cast to u32 */
    uint32_t devAddr;
    uint32_t nwkSKey[4];    /* 16 bytes */
    uint32_t appSKey[4];    /* 16 bytes */
    uint32_t fCntUp;
    uint32_t fCntDown;      /* next downlink counter; durably reserved after
                             * MIC validation and before application dispatch */
    uint32_t rxDelaySec;     /* low nibble: RECEIVE_DELAY1 1..15 s; high
                              * CRC-protected bits: marked liveness metadata */
} lorawan_session_t;        /* total 15 words = 60 bytes */

void lorawan_export_session(lorawan_session_t* out);
bool lorawan_import_session(const lorawan_session_t* in);

/** Drop only the in-RAM OTAA session while keeping the current regional PHY.
 *  Used after durable same-region server-liveness invalidation; unlike
 *  lorawan_set_region(same), this is never a no-op. */
void lorawan_invalidate_session(void);

/**
 * Initialize LoRaWAN stack (default region US915, keys from secrets).
 * Call once from setup(). Returns true on success.
 */
bool lorawan_init(void);

/**
 * Perform OTAA join. Blocking until joined or timeout_ms.
 */
bool lorawan_join(uint32_t timeout_ms);

/**
 * Send unconfirmed uplink. payload_len must be <= LORAWAN_PAYLOAD_MAX.
 * Returns true if send was queued/successful.
 */
bool lorawan_send_uplink(const uint8_t* payload, uint8_t payload_len);

/**
 * Send an unconfirmed application uplink on an explicit non-zero FPort.
 * Used for sparse typed event packets while preserving the established
 * fPort-1 telemetry contract. Reserves and atomically persists the next
 * FCntUp before RF; a failed transmission may skip a counter but a reset
 * cannot replay one.
 */
bool lorawan_send_uplink_port(uint8_t fport, const uint8_t* payload, uint8_t payload_len);

/** Send the due fPort-1 liveness probe as ConfirmedDataUp. The pending intent
 *  is included in the same CRC-protected transaction that reserves FCntUp
 *  before RF. */
bool lorawan_send_confirmed_uplink(
    const uint8_t* payload,
    uint8_t payload_len,
    const lorawan_liveness_qualification_t* qualification);

/** Publish the current joined session through the same checked transaction used
 *  by counter/liveness reservations.  A failed transaction revokes server proof
 *  by invalidating the complete RAM session, closing every optional service. */
bool lorawan_persist_session(void);

/**
 * Return true if we are joined and can send.
 */
bool lorawan_joined(void);

/** Stage-by-stage Class-A receive diagnostics for J-Link/HIL validation. */
typedef struct {
    uint32_t calls;
    uint32_t rx1_armed;
    uint32_t rx2_armed;
    uint32_t irq_count;
    uint32_t frame_count;
    int32_t  last_rx1_start_offset_ms; /* actual arm time minus TX end */
    int32_t  last_rx2_start_offset_ms;
    int16_t  last_rx1_start_state;     /* RadioLib return code */
    int16_t  last_rx2_start_state;
    uint8_t  last_window;              /* 0 none, 1 RX1, 2 RX2 */
    uint8_t  last_len;
    uint8_t  last_mhdr;
    uint8_t  last_reject;              /* 0 accepted; 1-7 frame, 8 PHY config */
    uint32_t authenticated_frames;
    uint32_t ack_frames;
    uint32_t complete_no_evidence;
    uint32_t mission_aborts;
    uint32_t local_faults;
} lorawan_downlink_stats_t;

void lorawan_downlink_get_stats(lorawan_downlink_stats_t* out);

/**
 * Put the SX1262 SubGHz radio into SLEEP retention mode (~3 µA, config kept).
 * MUST be called before MCU STOP1 entry, otherwise the radio sits in
 * STDBY_RC drawing ~600 µA, which both wrecks the night-survival energy
 * budget and (on the RAK3172 module) appears to leave pending interrupts
 * that previously hard-reset the chip when STOP2 attempted to enter or exit.
 * An unready/unknown PHY is not assumed quiescent: the implementation performs
 * one bounded radio reinitialization and demands a confirmed sleep, resetting
 * the MCU if it still cannot prove the modem is safe for the long idle window.
 *
 * Subsequent transmit() calls wake the radio implicitly via SetStandby.
 */
void lorawan_sleep(void);

/* ===== Meshtastic open-relay (mission-subordinate, power-gated) ===== */

/** Cumulative relay diagnostics (J-Link readable; not in telemetry). */
typedef struct {
    uint32_t rx_count;    /* LongFast frames received */
    uint32_t fwd;         /* frames forwarded (hop-1, opaque) */
    uint32_t dedup;       /* duplicates suppressed */
    uint32_t hop0;        /* hop-exhausted frames dropped */
    uint32_t cap_skip;    /* forwards skipped by the airtime cap */
    uint32_t rx_arm_fail; /* initial/re-arm receive failures */
    uint32_t last_from;   /* NodeNum of the last received frame */
    int16_t  last_rssi;   /* RSSI of the last received frame (dBm) */
    uint16_t reserved;    /* keeps appended counters word-aligned */
    uint32_t queued;      /* valid frames admitted to delayed TX queue */
    uint32_t pending_dup; /* pending ROUTER_LATE forward canceled by duplicate */
    uint32_t next_hop_skip; /* directed next-hop not owned by this relay */
    uint32_t queue_full;  /* valid frame dropped: bounded queue occupied */
    uint32_t invalid;     /* zero source/id or other malformed header */
    uint32_t cad_busy;    /* LoRa activity detected; randomized retry */
    uint32_t cad_error;   /* CAD failed for a reason other than activity */
    uint32_t tx_error;    /* post-CAD radio transmit failure */
    uint32_t window_skip; /* queued frame expired at relay-window boundary */
} lorawan_relay_stats_t;

/**
 * Run the shared LongFast service window on the SX1262 for up to max_ms, then
 * restore the exact post-init LoRaWAN TX PHY. Authenticated B2B traffic is
 * always serviced; meshtastic_enabled controls only the public, keyless
 * Meshtastic repeater (dedup + hop-decrement + airtime cap). Uses the active
 * region's LongFast frequency (US915/EU868/AU915; returns 0 otherwise).
 *
 * MISSION-SUBORDINATE: the CALLER gates entry on power/region/schedule; this
 * function additionally self-aborts the instant VSTOR < floor_mv.  The LoRaWAN
 * session (DevAddr/keys/FCnt) is never touched.  Returns ms actually spent.
 */
uint32_t lorawan_relay_window(
    uint32_t max_ms, uint16_t floor_mv, bool meshtastic_enabled);

/** Copy cumulative relay diagnostics into out. */
void lorawan_relay_get_stats(lorawan_relay_stats_t* out);

/* ===== CTT wildlife-tag listener (434 MHz FSK, mission-subordinate) ===== */

/** One logged tag detection (aggregated per listen window). */
typedef struct {
    uint32_t id_raw;      /* raw 32-bit tag id (rtl_433 convention) */
    uint32_t id_motus;    /* 20-bit Motus dictionary id (0 if not dictionary-valid) */
    int16_t  rssi_best;   /* strongest reception this window (dBm) */
    uint8_t  hits;        /* beeps heard this window (saturating) */
    uint8_t  motus_valid; /* all 4 id bytes were dictionary members */
    uint16_t window_idx;  /* which listen window logged it (recency ordering) */
    uint32_t queued_min;  /* local RTC minute of first detection; not raw RF */
} ctt_detection_t;

/** Cumulative listener diagnostics (J-Link readable; not yet in telemetry). */
typedef struct {
    uint32_t frames_rx;   /* 5-byte frames pulled from the FSK modem */
    uint32_t crc_fail;    /* frames failing the CRC-8 */
    uint32_t tags_seen;   /* distinct (per-window) tag detections logged */
    uint32_t windows;     /* listen windows run */
    uint32_t rx_arm_fail; /* initial/re-arm receive failures */
    uint32_t last_id;     /* raw id of the most recent good frame */
    int16_t  last_rssi;   /* RSSI of the most recent good frame */
    uint32_t pending_drop;/* distinct detections lost because event queue was full */
} lorawan_ctt_stats_t;

#define CTT_LOG_N 16      /* detection ring size */

/**
 * Listen for CTT wildlife-tag beacons (434.0 MHz, 2-FSK 25 kbps, +-25 kHz)
 * on the shared SX1262 for up to max_ms, logging decoded tag ids, then
 * restore the exact post-init LoRaWAN TX PHY.  RX-only, transmits nothing.
 * Same subordination contract as the relay window: caller gates entry,
 * self-aborts below floor_mv, on solar loss, or on a pending freefall.
 * Returns ms actually spent.
 */
uint32_t lorawan_ctt_window(uint32_t max_ms, uint16_t floor_mv);

/** Copy cumulative CTT diagnostics into out. */
void lorawan_ctt_get_stats(lorawan_ctt_stats_t* out);

/** Copy the detection ring into out[CTT_LOG_N]; returns entries used. */
uint8_t lorawan_ctt_get_log(ctt_detection_t* out);

/**
 * Transactional event queue. peek leaves the oldest detection queued; ack
 * removes it only after the caller has successfully transmitted and persisted
 * the resulting LoRaWAN frame counter.
 */
bool lorawan_ctt_peek_pending(ctt_detection_t* out);
void lorawan_ctt_ack_pending(void);
uint8_t lorawan_ctt_pending_count(void);

/* ===== Balloon-to-balloon store-and-forward (inside relay window) ===== */

/** Offer the newest fresh local fix for the next due hourly B2B crumb. */
void lorawan_b2b_set_local_crumb(int32_t lat_e7, int32_t lon_e7, int32_t altitude_m);

/**
 * Oldest fresh remote B2B frame awaiting a TTN tunnel on fPort 12.
 * The returned bytes are the exact versioned B2B wire frame. `capacity` must
 * be at least B2B_FRAME_MAX; a smaller destination fails without consuming or
 * corrupting the pending event. As with CTT, peek is non-destructive and ack
 * follows only a successful, persisted uplink.
 */
bool lorawan_b2b_peek_pending_uplink(
    uint8_t* out, uint8_t capacity, uint8_t* len);
void lorawan_b2b_ack_pending_uplink(void);
uint8_t lorawan_b2b_pending_uplink_count(void);

/* ===== Class-A downlink (command channel) ===== */

/** A received, decrypted downlink. */
typedef struct {
    uint8_t fport;
    uint8_t len;
    bool ack;            /* authenticated LoRaWAN FCtrl.ACK */
    uint8_t data[64];     /* decrypted FRMPayload */
} lorawan_downlink_t;

typedef enum {
    LORAWAN_CLASS_A_AMBIGUOUS = 0,
    LORAWAN_CLASS_A_AUTHENTICATED,
    LORAWAN_CLASS_A_COMPLETE_NO_EVIDENCE,
    LORAWAN_CLASS_A_PERSISTENCE_FAULT,
} lorawan_class_a_result_t;

/**
 * Called synchronously after both healthy Class-A windows finish empty, before
 * lorawan_receive_downlink_result() is allowed to return.  Probe callers use
 * this boundary to re-check live mission gates and durably commit the miss, so
 * a reset cannot turn a conclusive third miss back into interrupted ambiguity.
 * Return false when that durable completion fails; the receive result then
 * fails closed as PERSISTENCE_FAULT.
 */
typedef bool (*lorawan_probe_completion_fn)(
    const lorawan_liveness_probe_result_t* result,
    void* context);

/**
 * Detailed Class-A result for server-liveness qualification. COMPLETE means
 * both windows reached their deadlines with successful arm/read/standby/PHY
 * handling and no freefall preemption. Ordinary local faults are AMBIGUOUS;
 * a failed durable state transaction is the distinct PERSISTENCE_FAULT.
 * Optional rx_path_healthy_out reports this exchange's local health separately
 * from durable server proof. It stays false on incomplete/faulted exchanges,
 * including an authenticated frame whose PHY restore failed. Such a frame is
 * still committed and returned for at-most-once command delivery.
 */
lorawan_class_a_result_t lorawan_receive_downlink_result(
    lorawan_downlink_t* out,
    lorawan_probe_completion_fn probe_completion = nullptr,
    void* probe_context = nullptr,
    bool* rx_path_healthy_out = nullptr);

/**
 * Securely originate a valid LoRaWAN command for a different balloon (or
 * broadcast) onto the B2B store-and-forward queue. Returns false for local
 * targets, malformed commands, a missing/invalid fleet key, or a full queue.
 */
bool lorawan_b2b_queue_command(const lorawan_downlink_t* command);

/**
 * Open the RX1 then RX2 window after the most recent uplink. If a valid downlink for
 * our DevAddr arrives, verify its MIC + frame counter (replay guard), decrypt it, and
 * return true with the FPort + plaintext in out. The accepted counter is
 * atomically persisted before the command becomes visible, so a reset cannot
 * replay an already authenticated frame. Restores the TX PHY on every exit so
 * the next uplink is unaffected. Call right after a successful
 * lorawan_send_uplink().
 */
bool lorawan_receive_downlink(lorawan_downlink_t* out);

/** Persisted server-liveness state transitions used by the primary scheduler. */
bool lorawan_server_probe_due(
    const lorawan_liveness_qualification_t* qualification);
bool lorawan_server_note_ordinary_primary(
    const lorawan_liveness_qualification_t* qualification,
    bool local_tx_succeeded);
/* Completes only miss/ambiguous outcomes. Authenticated results are committed
 * by lorawan_receive_downlink() with the matching durable FCntDown advance. */
lorawan_liveness_event_t lorawan_server_complete_probe(
    const lorawan_liveness_qualification_t* qualification,
    const lorawan_liveness_probe_result_t* result,
    bool* durable = nullptr);
bool lorawan_server_abandon_probe(void);
bool lorawan_server_recovery_due(void);
/** True only for a joined session carrying durably authenticated server proof. */
bool lorawan_server_session_proven(void);
void lorawan_server_liveness_get_state(lorawan_liveness_state_t* out);

typedef struct {
    uint32_t confirmed_probe_tx;
    uint32_t authenticated_downlinks;
    uint32_t ack_downlinks;
    uint32_t qualified_misses;
    uint32_t recoveries;
    uint32_t abandoned_probes;
    uint32_t persistence_failures;
} lorawan_liveness_diag_t;

void lorawan_server_liveness_get_diag(lorawan_liveness_diag_t* out);
void lorawan_server_liveness_note_recovery(bool durable_success);

#endif /* LORAWAN_H */
