#ifndef COMMAND_H
#define COMMAND_H

#include <stdint.h>
#include <stdbool.h>
#include "lorawan.h"

/* Cumulative command diagnostics (J-Link readable; not in telemetry). */
typedef struct {
    uint32_t rx_count;     /* downlinks received + decrypted */
    uint32_t cmd_count;    /* valid commands dispatched */
    uint8_t  last_opcode;
    uint8_t  last_seq;
    uint8_t  last_fport;
    uint8_t  last_len;
} command_stats_t;

/* Parse + dispatch a received downlink (fPort CMD_FPORT, addressed to us or broadcast).
 * Payload layout: [target:2 LE][opcode:1][seq:1][args:0..N]. Unknown fPort/target/
 * opcode are ignored (fail-closed). A repeated seq is ignored (idempotent). */
void command_handle(const lorawan_downlink_t* dl);

/* Runtime relay enable, gated by the relay command (default on). */
bool command_relay_enabled(void);

void command_get_stats(command_stats_t* out);

#endif /* COMMAND_H */
