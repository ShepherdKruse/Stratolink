/**
 * Class-A downlink command dispatcher. Stage 1: receive + parse + a few safe,
 * immediate, observable opcodes (ping, relay toggle). Stage 2 adds the commit-confirm
 * behaviour-changers (cadence, SF), GPS reset, safe-mode, rejoin, and persistence.
 */
#include "command.h"
#include "config.h"

static command_stats_t s_stats = {0};
static bool s_relay_enabled = true;     /* runtime relay toggle, default on */
static uint8_t s_last_seq = 0;
static bool s_have_seq = false;

void command_handle(const lorawan_downlink_t* dl) {
    if (!dl) return;
    s_stats.rx_count++;
    s_stats.last_fport = dl->fport;
    s_stats.last_len = dl->len;

    if (dl->fport != CMD_FPORT || dl->len < 4) return;          /* [target:2][opcode][seq] */
    uint16_t target = (uint16_t)(dl->data[0] | (dl->data[1] << 8));
    if (target != CMD_BALLOON_ID && target != CMD_BROADCAST) return;

    uint8_t opcode = dl->data[2];
    uint8_t seq    = dl->data[3];
    if (s_have_seq && seq == s_last_seq) return;                /* idempotent: ignore a repeat */
    s_have_seq = true; s_last_seq = seq;
    s_stats.last_opcode = opcode; s_stats.last_seq = seq; s_stats.cmd_count++;

    switch (opcode) {
        case CMD_OP_PING:                                       /* acked via stats / next uplink */
            break;
        case CMD_OP_RELAY:
            if (dl->len >= 5) s_relay_enabled = (dl->data[4] != 0);
            break;
        case CMD_OP_EASTER:
            break;
        default:
            break;
    }
}

bool command_relay_enabled(void) { return s_relay_enabled; }
void command_get_stats(command_stats_t* out) { if (out) *out = s_stats; }
