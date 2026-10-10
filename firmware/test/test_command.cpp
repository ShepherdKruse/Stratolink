#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "command.h"
#include "config.h"

static bool retained_valid = false;
static uint8_t retained_sequence = 0;
static bool retained_relay_enabled = true;
static bool writes_succeed = true;

bool power_manager_load_command_state(uint8_t* sequence, bool* relay_enabled) {
    if (!retained_valid || !sequence || !relay_enabled) return false;
    *sequence = retained_sequence;
    *relay_enabled = retained_relay_enabled;
    return true;
}

bool power_manager_save_command_state(uint8_t sequence, bool relay_enabled) {
    if (!writes_succeed) return false;
    retained_valid = true;
    retained_sequence = sequence;
    retained_relay_enabled = relay_enabled;
    return true;
}

static lorawan_downlink_t frame(uint8_t opcode, uint8_t seq, uint8_t len = 4) {
    lorawan_downlink_t dl = {};
    dl.fport = CMD_FPORT;
    dl.len = len;
    dl.data[0] = (uint8_t)(CMD_BALLOON_ID >> 8);
    dl.data[1] = (uint8_t)(CMD_BALLOON_ID & 0xFF);
    dl.data[2] = opcode;
    dl.data[3] = seq;
    return dl;
}

static uint32_t applied(void) {
    command_stats_t s;
    command_get_stats(&s);
    return s.cmd_count;
}

int main(void) {
    command_init();
    /* Target is big-endian. A little-endian rendering of 0x0001 is not ours. */
    lorawan_downlink_t wrong_target = frame(CMD_OP_PING, 249);
    wrong_target.data[0] = 0x01;
    wrong_target.data[1] = 0x00;
    command_handle(&wrong_target);
    assert(applied() == 0);

    lorawan_downlink_t ping = frame(CMD_OP_PING, 250);
    command_handle(&ping);
    assert(applied() == 1);

    /* Duplicate and older queue residue are idempotently rejected. */
    command_handle(&ping);
    lorawan_downlink_t stale = frame(CMD_OP_PING, 249);
    command_handle(&stale);
    assert(applied() == 1);

    lorawan_downlink_t next = frame(CMD_OP_PING, 251);
    command_handle(&next);
    lorawan_downlink_t wrapped = frame(CMD_OP_PING, 0);
    command_handle(&wrapped);
    assert(applied() == 3);

    /* An unknown opcode must not consume seq=1. */
    lorawan_downlink_t unknown = frame(0x55, 1);
    command_handle(&unknown);
    assert(applied() == 3);
    lorawan_downlink_t seq1 = frame(CMD_OP_PING, 1);
    command_handle(&seq1);
    assert(applied() == 4);

    /* Exactly half the sequence space is ambiguous and must fail closed.
     * This also pins the comparison to defined uint8_t arithmetic. */
    lorawan_downlink_t half_range = frame(CMD_OP_PING, 129);
    command_handle(&half_range);
    assert(applied() == 4);

    /* A malformed relay must not consume seq=2 or change runtime state. */
    lorawan_downlink_t bad_relay = frame(CMD_OP_RELAY, 2, 4);
    command_handle(&bad_relay);
    assert(applied() == 4);
    assert(command_relay_enabled());

    lorawan_downlink_t relay_off = frame(CMD_OP_RELAY, 2, 5);
    relay_off.data[4] = 0;
    command_handle(&relay_off);
    assert(applied() == 5);
    assert(!command_relay_enabled());

    /* Non-boolean relay args and trailing garbage fail closed. */
    lorawan_downlink_t bad_bool = frame(CMD_OP_RELAY, 3, 5);
    bad_bool.data[4] = 2;
    command_handle(&bad_bool);
    lorawan_downlink_t trailing = frame(CMD_OP_PING, 3, 5);
    command_handle(&trailing);
    assert(applied() == 5);

    lorawan_downlink_t broadcast = frame(CMD_OP_RELAY, 3, 5);
    broadcast.data[0] = 0xFF;
    broadcast.data[1] = 0xFF;
    broadcast.data[4] = 1;
    command_handle(&broadcast);
    assert(applied() == 6);
    assert(command_relay_enabled());

    /* A retained write failure must have no application effect and must not
     * consume the sequence. The same sequence succeeds once storage recovers. */
    writes_succeed = false;
    lorawan_downlink_t unavailable = frame(CMD_OP_RELAY, 4, 5);
    unavailable.data[4] = 0;
    assert(!command_handle(&unavailable));
    assert(applied() == 6);
    assert(command_relay_enabled());
    writes_succeed = true;
    assert(command_handle(&unavailable));
    assert(applied() == 7);
    assert(!command_relay_enabled());

    /* Simulate a warm reset by reloading the static policy from retained
     * storage. The exact authenticated replay remains rejected. */
    command_init();
    assert(!command_handle(&unavailable));
    assert(applied() == 7);
    assert(!command_relay_enabled());
    assert(command_sequence_is_current(4));
    assert(!command_sequence_is_current(3));

    uint8_t reported_sequence = 0;
    bool reported_relay = true;
    assert(command_get_applied_state(&reported_sequence, &reported_relay));
    assert(reported_sequence == 4);
    assert(!reported_relay);

    command_stats_t stats;
    command_get_stats(&stats);
    assert(stats.last_opcode == CMD_OP_RELAY);
    assert(stats.last_seq == 4);
    assert(stats.persist_fail == 1);
    puts("command protocol: durable reservation and 15 adversarial cases passed");
    return 0;
}
