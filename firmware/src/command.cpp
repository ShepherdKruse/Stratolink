/**
 * Class-A downlink command dispatcher. Stage 1: receive + parse + a few safe,
 * immediate opcodes (ping, relay toggle). Telemetry v2 echoes the durably applied
 * sequence and actual retained relay state. Stage 2 adds the
 * commit-confirm behaviour-changers (cadence, SF), GPS reset, safe-mode, rejoin,
 * persistent cadence/SF controls, dead-man revert, and commit-confirm flow.
 */
#include "command.h"
#include "power_manager.h"

static command_stats_t s_stats = {};
static bool s_relay_enabled = true;     /* runtime relay toggle, default on */
static uint8_t s_last_seq = 0;
static bool s_have_seq = false;

void command_init(void) {
    uint8_t sequence = 0;
    bool relay_enabled = true;
    s_have_seq = power_manager_load_command_state(&sequence, &relay_enabled);
    s_last_seq = sequence;
    if (s_have_seq) {
        s_relay_enabled = relay_enabled;
        s_stats.last_seq = sequence;
    } else {
        s_relay_enabled = true;
    }
}

static bool command_shape_ok(uint8_t opcode, const lorawan_downlink_t* dl) {
    switch (opcode) {
        case CMD_OP_PING:
        case CMD_OP_EASTER:
            return dl->len == 4;
        case CMD_OP_RELAY:
            return dl->len == 5 && dl->data[4] <= 1;
        default:
            return false;
    }
}

bool command_validate_wire(const lorawan_downlink_t* dl) {
    if (!dl || dl->fport != CMD_FPORT || dl->len < 4) return false;
    return command_shape_ok(dl->data[2], dl);
}

bool command_handle(const lorawan_downlink_t* dl) {
    if (!dl) return false;
    s_stats.rx_count++;
    s_stats.last_fport = dl->fport;
    s_stats.last_len = dl->len;

    if (!command_validate_wire(dl)) return false; /* [target:2][opcode][seq] */
    uint16_t target = (uint16_t)(((uint16_t)dl->data[0] << 8) | dl->data[1]);
    if (target != CMD_BALLOON_ID && target != CMD_BROADCAST) return false;

    uint8_t opcode = dl->data[2];
    uint8_t seq    = dl->data[3];
    /* Validate the complete command before consuming its sequence number.
     * Otherwise a malformed/unknown frame can advance last_seq and suppress a
     * later corrected command carrying the same seq. */
    /* Modulo-256 half-range comparison. Deltas 1..127 are newer, zero is a
     * duplicate, and 128..255 are stale/reordered. Keep the subtraction
     * explicitly unsigned: narrowing a negative int to int8_t is
     * implementation-defined and made replay policy depend on the compiler. */
    if (s_have_seq) {
        const uint8_t delta = (uint8_t)(seq - s_last_seq);
        if (delta == 0 || delta > 127u) return false;
    }
    /* Reserve before effect. A reset after this write but before dispatch can
     * lose a command (the sender retries with a newer sequence), but can never
     * re-apply the same authenticated B2B command after a warm reset. */
    bool next_relay_enabled = s_relay_enabled;
    if (opcode == CMD_OP_RELAY) next_relay_enabled = dl->data[4] != 0;
    if (!power_manager_save_command_state(seq, next_relay_enabled)) {
        s_stats.persist_fail++;
        return false;
    }
    s_have_seq = true; s_last_seq = seq;
    s_stats.last_opcode = opcode; s_stats.last_seq = seq; s_stats.cmd_count++;

    switch (opcode) {
        case CMD_OP_PING:                                       /* ACKed in next primary */
            break;
        case CMD_OP_RELAY:
            s_relay_enabled = next_relay_enabled;
            break;
        case CMD_OP_EASTER:
            break;
    }
    return true;
}

bool command_relay_enabled(void) { return s_relay_enabled; }
bool command_sequence_is_current(uint8_t sequence) {
    return s_have_seq && sequence == s_last_seq;
}
bool command_get_applied_state(uint8_t* sequence, bool* relay_enabled) {
    if (relay_enabled) *relay_enabled = s_relay_enabled;
    if (!s_have_seq) return false;
    if (sequence) *sequence = s_last_seq;
    return true;
}
void command_get_stats(command_stats_t* out) { if (out) *out = s_stats; }
