#ifndef LORAWAN_H
#define LORAWAN_H

#include <stdint.h>
#include <stdbool.h>

/** Maximum uplink payload size (LoRaWAN allows up to 222 at SF7; we use 38). */
#define LORAWAN_PAYLOAD_MAX 64

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
} lorawan_session_t;        /* total 13 words = 52 bytes */

void lorawan_export_session(lorawan_session_t* out);
bool lorawan_import_session(const lorawan_session_t* in);

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
 * Return true if we are joined and can send.
 */
bool lorawan_joined(void);

/**
 * Put the SX1262 SubGHz radio into SLEEP retention mode (~3 µA, config kept).
 * MUST be called before MCU STOP2 entry, otherwise the radio sits in
 * STDBY_RC drawing ~600 µA, which both wrecks the night-survival energy
 * budget and (on the RAK3172 module) appears to leave pending interrupts
 * that hard-reset the chip when STOP2 attempts to enter or exit.
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
    uint32_t last_from;   /* NodeNum of the last received frame */
    int16_t  last_rssi;   /* RSSI of the last received frame (dBm) */
} lorawan_relay_stats_t;

/**
 * Run a header-only, KEYLESS Meshtastic LongFast repeater on the shared SX1262
 * for up to max_ms, then restore the exact post-init LoRaWAN TX PHY.  Forwards
 * real traffic (dedup + hop-decrement + airtime cap) on the active region's
 * LongFast frequency (US915/EU868 only; returns 0 otherwise).
 *
 * MISSION-SUBORDINATE: the CALLER gates entry on power/region/schedule; this
 * function additionally self-aborts the instant VSTOR < floor_mv.  The LoRaWAN
 * session (DevAddr/keys/FCnt) is never touched.  Returns ms actually spent.
 */
uint32_t lorawan_relay_window(uint32_t max_ms, uint16_t floor_mv);

/** Copy cumulative relay diagnostics into out. */
void lorawan_relay_get_stats(lorawan_relay_stats_t* out);

#endif /* LORAWAN_H */
