#ifndef B2B_RF_DIAG_CONFIG_H
#define B2B_RF_DIAG_CONFIG_H

/*
 * Diagnostic-only shared key and node identities for the bounded two-board
 * B2B RF test. This key is public test material and must never be used by a
 * flight build. The PlatformIO diagnostic environments force-include this
 * header before config.h is parsed.
 */
#define B2B_FLEET_KEY "00112233445566778899AABBCCDDEEFF"

#if B2B_RF_DIAG_ROLE == 1
#define CMD_BALLOON_ID 0x0101
#elif B2B_RF_DIAG_ROLE == 2
#define CMD_BALLOON_ID 0x0102
#else
#error "B2B_RF_DIAG_ROLE must be 1 (transmitter) or 2 (receiver)"
#endif

#endif
