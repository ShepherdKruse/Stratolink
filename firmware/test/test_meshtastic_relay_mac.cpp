#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "meshtastic_relay_mac.h"

static uint32_t rng_state = 0xC001D00Du;

static uint32_t rnd(void) {
    uint32_t x = rng_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    rng_state = x;
    return x;
}

static void wr_u32le(uint8_t* p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static void make_frame(
    uint8_t* f, size_t len, uint32_t from, uint32_t id, uint8_t hop,
    uint8_t next_hop, uint8_t relay_node) {
    assert(len >= MESH_RELAY_HEADER_LEN);
    for (size_t i = 0; i < len; ++i) f[i] = (uint8_t)(i * 17u + 3u);
    wr_u32le(f + 0, 0xFFFFFFFFu);
    wr_u32le(f + 4, from);
    wr_u32le(f + 8, id);
    f[12] = (uint8_t)(0xA8u | (hop & 7u));
    f[14] = next_hop;
    f[15] = relay_node;
}

static void test_rejections(void) {
    mesh_relay_mac_t mac;
    mesh_relay_mac_init(&mac);
    uint8_t f[256];
    make_frame(f, sizeof(f), 1, 2, 3, 0, 9);

    assert(mesh_relay_mac_enqueue(&mac, f, 15, 0, 1, 2) ==
           MESH_RELAY_DROP_SHORT);
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 0, 1, 2) ==
           MESH_RELAY_DROP_TOO_LONG);

    make_frame(f, 32, 0, 2, 3, 0, 9);
    assert(mesh_relay_mac_enqueue(&mac, f, 32, 0, 1, 2) ==
           MESH_RELAY_DROP_FROM_ZERO);
    make_frame(f, 32, 1, 0, 3, 0, 9);
    assert(mesh_relay_mac_enqueue(&mac, f, 32, 0, 1, 2) ==
           MESH_RELAY_DROP_ID_ZERO);
    make_frame(f, 32, 1, 2, 0, 0, 9);
    assert(mesh_relay_mac_enqueue(&mac, f, 32, 0, 1, 2) ==
           MESH_RELAY_DROP_HOP_ZERO);
    make_frame(f, 32, 1, 2, 3, 0x44, 9);
    assert(mesh_relay_mac_enqueue(&mac, f, 32, 0, 1, 2) ==
           MESH_RELAY_DROP_DIRECTED_NEXT_HOP);
}

static void test_exact_mutation_and_timing(void) {
    mesh_relay_mac_t mac;
    mesh_relay_mac_init(&mac);
    uint8_t f[100];
    make_frame(f, sizeof(f), 0x11223344u, 0x55667788u, 5, 0, 0xD1);
    uint8_t original[sizeof(f)];
    memcpy(original, f, sizeof(f));

    assert(mesh_relay_mac_enqueue(
               &mac, f, sizeof(f), -20, 0xFFFFFF00u, 0x1234u) ==
           MESH_RELAY_QUEUE_OK);
    const mesh_relay_pending_t* p = &mac.pending[0];
    assert(p->used && p->len == sizeof(f));
    assert((p->frame[12] & 7u) == 4u);
    assert((p->frame[12] & 0xF8u) == (original[12] & 0xF8u));
    assert(p->frame[14] == 0);
    assert(p->frame[15] == 0);
    for (size_t i = 0; i < sizeof(f); ++i) {
        if (i == 12 || i == 14 || i == 15) continue;
        assert(p->frame[i] == original[i]);
    }
    uint32_t delay = p->due_ms - 0xFFFFFF00u;
    assert(delay >= 16u * MESH_RELAY_SLOT_MS);
    assert(delay <= 23u * MESH_RELAY_SLOT_MS);
    assert(mesh_relay_mac_due(&mac, p->due_ms - 1u) == -1);
    assert(mesh_relay_mac_due(&mac, p->due_ms) == 0);
}

static void test_duplicate_queue_and_reschedule(void) {
    mesh_relay_mac_t mac;
    mesh_relay_mac_init(&mac);
    uint8_t f[20];
    make_frame(f, sizeof(f), 1, 2, 3, 0, 8);
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 10, 100, 1) ==
           MESH_RELAY_QUEUE_OK);
    assert(mesh_relay_mac_contains(&mac, 1, 2));
    uint32_t old_due = mac.pending[0].due_ms;
    mesh_relay_mac_reschedule(&mac, 0, old_due, 3);
    uint32_t retry_delay = mac.pending[0].due_ms - old_due;
    assert(retry_delay >= 16u * MESH_RELAY_SLOT_MS);
    assert(retry_delay <= 271u * MESH_RELAY_SLOT_MS);

    assert(!mesh_relay_mac_cancel(&mac, 1, 99));
    assert(mesh_relay_mac_cancel(&mac, 1, 2));
    assert(!mesh_relay_mac_contains(&mac, 1, 2));
    assert(!mesh_relay_mac_cancel(&mac, 1, 2));

    make_frame(f, sizeof(f), 1, 2, 3, 0, 8);
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 10, 200, 2) ==
           MESH_RELAY_QUEUE_OK);
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 10, 200, 2) ==
           MESH_RELAY_DROP_PENDING_DUPLICATE);

    make_frame(f, sizeof(f), 3, 4, 3, 0, 8);
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 0, 100, 1) ==
           MESH_RELAY_QUEUE_OK);
    make_frame(f, sizeof(f), 5, 6, 3, 0, 8);
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 0, 100, 1) ==
           MESH_RELAY_DROP_QUEUE_FULL);
    mesh_relay_mac_remove(&mac, 0);
    assert(!mesh_relay_mac_contains(&mac, 1, 2));
    assert(mesh_relay_mac_enqueue(&mac, f, sizeof(f), 0, 100, 1) ==
           MESH_RELAY_QUEUE_OK);
}

static void test_properties(void) {
    for (unsigned n = 0; n < 100000; ++n) {
        mesh_relay_mac_t mac;
        mesh_relay_mac_init(&mac);
        uint8_t f[MESH_RELAY_FRAME_MAX];
        size_t len = MESH_RELAY_HEADER_LEN +
            (rnd() % (MESH_RELAY_FRAME_MAX - MESH_RELAY_HEADER_LEN + 1u));
        uint32_t from = rnd() | 1u;
        uint32_t id = rnd() | 1u;
        uint8_t hop = (uint8_t)(1u + rnd() % 7u);
        int16_t snr = (int16_t)((int32_t)(rnd() % 101u) - 50);
        make_frame(f, len, from, id, hop, 0, (uint8_t)rnd());
        uint8_t before[MESH_RELAY_FRAME_MAX];
        memcpy(before, f, len);
        uint32_t now = rnd();
        assert(mesh_relay_mac_enqueue(&mac, f, len, snr, now, rnd()) ==
               MESH_RELAY_QUEUE_OK);
        const mesh_relay_pending_t* p = &mac.pending[0];
        assert(p->due_ms - now >= 16u * MESH_RELAY_SLOT_MS);
        assert(p->due_ms - now <= 271u * MESH_RELAY_SLOT_MS);
        assert((p->frame[12] & 7u) == hop - 1u);
        assert(p->frame[14] == 0 && p->frame[15] == 0);
        for (size_t i = 0; i < len; ++i) {
            if (i == 12 || i == 14 || i == 15) continue;
            assert(p->frame[i] == before[i]);
        }
    }
}

int main(void) {
    assert(mesh_relay_mac_cw_size(-100) == 3);
    assert(mesh_relay_mac_cw_size(-20) == 3);
    assert(mesh_relay_mac_cw_size(10) == 8);
    assert(mesh_relay_mac_cw_size(100) == 8);
    test_rejections();
    test_exact_mutation_and_timing();
    test_duplicate_queue_and_reschedule();
    test_properties();
    puts("test_meshtastic_relay_mac: PASS");
    return 0;
}
