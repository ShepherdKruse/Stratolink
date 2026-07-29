#include "meshtastic_relay_mac.h"

#include <string.h>

static uint32_t rd_u32le(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t mix32(uint32_t x) {
    x ^= x >> 16;
    x *= 0x7FEB352Du;
    x ^= x >> 15;
    x *= 0x846CA68Bu;
    x ^= x >> 16;
    return x;
}

void mesh_relay_mac_init(mesh_relay_mac_t* mac) {
    if (mac) memset(mac, 0, sizeof(*mac));
}

uint8_t mesh_relay_mac_cw_size(int16_t snr_db) {
    if (snr_db <= -20) return 3;
    if (snr_db >= 10) return 8;
    /* Meshtastic 2.7.3 maps -20..+10 dB linearly onto CW 3..8. */
    return (uint8_t)(3 + ((int32_t)(snr_db + 20) * 5) / 30);
}

uint32_t mesh_relay_mac_delay_ms(
    int16_t snr_db, uint32_t entropy, uint32_t from, uint32_t id) {
    uint8_t cw = mesh_relay_mac_cw_size(snr_db);
    uint32_t slots = 1u << cw;
    uint32_t r = mix32(entropy ^ mix32(from) ^ mix32(id));
    /*
     * Native ROUTER_LATE falls outside the early router/repeater window by
     * adding 2*CWmax (=16) slots, then selects within the SNR-weighted CW.
     */
    return (16u + (r & (slots - 1u))) * MESH_RELAY_SLOT_MS;
}

bool mesh_relay_mac_contains(
    const mesh_relay_mac_t* mac, uint32_t from, uint32_t id) {
    if (!mac || from == 0 || id == 0) return false;
    for (uint8_t i = 0; i < MESH_RELAY_PENDING_N; ++i) {
        const mesh_relay_pending_t* p = &mac->pending[i];
        if (p->used && p->from == from && p->id == id) return true;
    }
    return false;
}

bool mesh_relay_mac_cancel(
    mesh_relay_mac_t* mac, uint32_t from, uint32_t id) {
    if (!mac || from == 0 || id == 0) return false;
    for (uint8_t i = 0; i < MESH_RELAY_PENDING_N; ++i) {
        mesh_relay_pending_t* p = &mac->pending[i];
        if (p->used && p->from == from && p->id == id) {
            memset(p, 0, sizeof(*p));
            return true;
        }
    }
    return false;
}

mesh_relay_queue_result_t mesh_relay_mac_enqueue(
    mesh_relay_mac_t* mac, const uint8_t* frame, size_t len, int16_t snr_db,
    uint32_t now_ms, uint32_t entropy) {
    if (!mac || !frame || len < MESH_RELAY_HEADER_LEN)
        return MESH_RELAY_DROP_SHORT;
    if (len > MESH_RELAY_FRAME_MAX) return MESH_RELAY_DROP_TOO_LONG;

    uint32_t from = rd_u32le(frame + 4);
    uint32_t id = rd_u32le(frame + 8);
    uint8_t hop = frame[12] & 0x07u;
    if (from == 0) return MESH_RELAY_DROP_FROM_ZERO;
    if (id == 0) return MESH_RELAY_DROP_ID_ZERO;
    if (hop == 0) return MESH_RELAY_DROP_HOP_ZERO;
    /*
     * A non-zero next_hop asks a particular native relay ID to forward. An
     * anonymous StratoLink relay cannot prove it owns that identity.
     */
    if (frame[14] != 0) return MESH_RELAY_DROP_DIRECTED_NEXT_HOP;
    if (mesh_relay_mac_contains(mac, from, id))
        return MESH_RELAY_DROP_PENDING_DUPLICATE;

    mesh_relay_pending_t* out = NULL;
    for (uint8_t i = 0; i < MESH_RELAY_PENDING_N; ++i) {
        if (!mac->pending[i].used) {
            out = &mac->pending[i];
            break;
        }
    }
    if (!out) return MESH_RELAY_DROP_QUEUE_FULL;

    memset(out, 0, sizeof(*out));
    memcpy(out->frame, frame, len);
    out->frame[12] =
        (uint8_t)((out->frame[12] & (uint8_t)~0x07u) | (hop - 1u));
    out->frame[14] = 0; /* NO_NEXT_HOP_PREFERENCE */
    out->frame[15] = 0; /* NO_RELAY_NODE: do not impersonate a mesh node */
    out->used = true;
    out->len = (uint8_t)len;
    out->from = from;
    out->id = id;
    out->snr_db = snr_db;
    out->due_ms =
        now_ms + mesh_relay_mac_delay_ms(snr_db, entropy, from, id);
    return MESH_RELAY_QUEUE_OK;
}

int8_t mesh_relay_mac_due(const mesh_relay_mac_t* mac, uint32_t now_ms) {
    if (!mac) return -1;
    for (uint8_t i = 0; i < MESH_RELAY_PENDING_N; ++i) {
        const mesh_relay_pending_t* p = &mac->pending[i];
        if (p->used && (int32_t)(now_ms - p->due_ms) >= 0)
            return (int8_t)i;
    }
    return -1;
}

void mesh_relay_mac_reschedule(
    mesh_relay_mac_t* mac, uint8_t slot, uint32_t now_ms, uint32_t entropy) {
    if (!mac || slot >= MESH_RELAY_PENDING_N) return;
    mesh_relay_pending_t* p = &mac->pending[slot];
    if (!p->used) return;
    p->due_ms = now_ms +
        mesh_relay_mac_delay_ms(p->snr_db, entropy, p->from, p->id);
}

void mesh_relay_mac_remove(mesh_relay_mac_t* mac, uint8_t slot) {
    if (!mac || slot >= MESH_RELAY_PENDING_N) return;
    memset(&mac->pending[slot], 0, sizeof(mac->pending[slot]));
}
