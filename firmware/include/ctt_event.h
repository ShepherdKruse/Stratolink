#ifndef CTT_EVENT_H
#define CTT_EVENT_H

#include <stdint.h>
#include "lorawan.h"

/* Dedicated fPort-11 event payload. Magic + version make a wrong-port or
 * future-format packet fail loudly instead of becoming plausible telemetry.
 *
 * [0..1]  ASCII "CT"
 * [2]     version (2)
 * [3]     flags: bit0 Motus dictionary-valid; bits1..7 zero
 * [4..7]  raw CTT tag id, big-endian
 * [8..11] 20-bit Motus dictionary id in uint32, big-endian (0 if invalid)
 * [12..13] best RSSI, signed int16 dBm, big-endian
 * [14]    hit count in the listen window
 * [15..16] whole minutes since first detection, uint16 big-endian,
 *          saturating at 65,535
 */
#define CTT_EVENT_PAYLOAD_SIZE 17
#define CTT_EVENT_VERSION 2

void ctt_event_pack(const ctt_detection_t* in,
                    uint32_t now_min,
                    uint8_t out[CTT_EVENT_PAYLOAD_SIZE]);

#endif
