#ifndef MESHTASTIC_RELAY_MAC_H
#define MESHTASTIC_RELAY_MAC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Pure, allocation-free Meshtastic flooding MAC used by the shared-radio
 * relay. The payload remains opaque; only the public 16-byte radio header is
 * inspected or changed.
 *
 * StratoLink is not a Meshtastic NodeNum participant. It therefore MUST NOT
 * invent a relay_node byte: doing so can teach native NextHopRouter instances
 * a route through an unrelated real node with the same low byte. Forwarded
 * frames use NO_NEXT_HOP_PREFERENCE / NO_RELAY_NODE (both zero).
 */
#define MESH_RELAY_HEADER_LEN 16u
#define MESH_RELAY_FRAME_MAX 255u
#define MESH_RELAY_PENDING_N 2u
#define MESH_RELAY_SLOT_MS 28u

typedef enum {
    MESH_RELAY_QUEUE_OK = 0,
    MESH_RELAY_DROP_SHORT,
    MESH_RELAY_DROP_TOO_LONG,
    MESH_RELAY_DROP_FROM_ZERO,
    MESH_RELAY_DROP_ID_ZERO,
    MESH_RELAY_DROP_HOP_ZERO,
    MESH_RELAY_DROP_DIRECTED_NEXT_HOP,
    MESH_RELAY_DROP_PENDING_DUPLICATE,
    MESH_RELAY_DROP_QUEUE_FULL,
} mesh_relay_queue_result_t;

typedef struct {
    bool used;
    uint8_t len;
    uint8_t frame[MESH_RELAY_FRAME_MAX];
    uint32_t from;
    uint32_t id;
    uint32_t due_ms;
    int16_t snr_db;
} mesh_relay_pending_t;

typedef struct {
    mesh_relay_pending_t pending[MESH_RELAY_PENDING_N];
} mesh_relay_mac_t;

void mesh_relay_mac_init(mesh_relay_mac_t* mac);

/*
 * Validate and queue one opaque frame. entropy is mixed with the packet key
 * and used only to select a contention slot. A successful queue operation
 * decrements hop_limit and clears next_hop/relay_node in the queued copy.
 */
mesh_relay_queue_result_t mesh_relay_mac_enqueue(
    mesh_relay_mac_t* mac, const uint8_t* frame, size_t len, int16_t snr_db,
    uint32_t now_ms, uint32_t entropy);

/* Return a due slot index, or -1. Correct across uint32_t millis() wrap. */
int8_t mesh_relay_mac_due(const mesh_relay_mac_t* mac, uint32_t now_ms);

/* True when the same (from,id) is already waiting for CAD/transmit. */
bool mesh_relay_mac_contains(
    const mesh_relay_mac_t* mac, uint32_t from, uint32_t id);

/*
 * Cancel a pending relay when the same (from,id) is heard again during our
 * ROUTER_LATE delay. That repeat is evidence another node already forwarded
 * the flood, so transmitting our queued copy would add only a collision and
 * airtime. Returns true only when a pending slot was removed.
 */
bool mesh_relay_mac_cancel(
    mesh_relay_mac_t* mac, uint32_t from, uint32_t id);

/*
 * Reschedule after a busy/failed CAD or radio hand-off. This repeats the
 * native ROUTER_LATE-style weighted contention delay from now.
 */
void mesh_relay_mac_reschedule(
    mesh_relay_mac_t* mac, uint8_t slot, uint32_t now_ms, uint32_t entropy);

void mesh_relay_mac_remove(mesh_relay_mac_t* mac, uint8_t slot);

/* Exposed for exhaustive host tests and engineering traceability. */
uint8_t mesh_relay_mac_cw_size(int16_t snr_db);
uint32_t mesh_relay_mac_delay_ms(
    int16_t snr_db, uint32_t entropy, uint32_t from, uint32_t id);

#endif
