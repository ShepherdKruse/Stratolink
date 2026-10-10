#ifndef COMMAND_H
#define COMMAND_H

#include <stdint.h>
#include <stdbool.h>
#include "device_identity.h"
#include "lorawan.h"

/* Cumulative command diagnostics (J-Link readable; not in telemetry). */
typedef struct {
    uint32_t rx_count;     /* downlinks received + decrypted */
    uint32_t cmd_count;    /* valid commands dispatched */
    uint8_t  last_opcode;
    uint8_t  last_seq;
    uint8_t  last_fport;
    uint8_t  last_len;
    uint32_t persist_fail; /* sequence reservation failed; command not applied */
} command_stats_t;

/* Restore the retained application sequence before any radio receive window.
 * Missing/corrupt state means no prior sequence; subsequent commands still
 * reserve their sequence durably before dispatch. Safe to call again after a
 * simulated reset in host/HIL tests. */
void command_init(void);

/* Parse + dispatch a received downlink (fPort CMD_FPORT, addressed to us or broadcast).
 * Payload layout: [target:2 BE][opcode:1][seq:1][args:0..N], matching the B2B
 * carrier and the rest of the wire protocol. Unknown fPort/target/opcode, bad
 * lengths/arguments, duplicates, older sequence numbers, and failed durable
 * sequence reservations are ignored fail-closed. */
bool command_handle(const lorawan_downlink_t* dl);

/* Validate fPort, exact opcode length, and bounded arguments without applying
 * target or sequence policy. Used before securely wrapping a LoRaWAN command
 * for another balloon in the B2B carrier. */
bool command_validate_wire(const lorawan_downlink_t* dl);

/* Runtime relay enable, gated by the relay command (default on). */
bool command_relay_enabled(void);

/* True only when sequence is the durably reserved current command. Used by
 * B2B to re-ACK an exact authenticated retry without reapplying it. */
bool command_sequence_is_current(uint8_t sequence);

/* Report the last durably applied state for primary telemetry. A valid result
 * survives warm resets together with the bounded relay behavior, so the
 * acknowledgement cannot contradict the state the firmware actually uses. */
bool command_get_applied_state(uint8_t* sequence, bool* relay_enabled);

void command_get_stats(command_stats_t* out);

#endif /* COMMAND_H */
