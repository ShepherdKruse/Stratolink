#ifndef GPS_BACKUP_POLICY_H
#define GPS_BACKUP_POLICY_H

#include <stdbool.h>
#include <stdint.h>

/* Immediately before PMREQ the receiver is temporarily requested to produce
 * a RAM-only 10 Hz NAV-EOE marker. A complete marker establishes a frame
 * boundary, but a CFG ACK does not prove achieved cadence. The current 350 ms
 * silence window remains unqualified for the default three-constellation
 * configuration; see the Board1 readiness report and physical shutdown test. */
/* This reserve is added to the CFG budget for one combined first-marker
 * deadline, anchored before CFG. Unused CFG time remains available to observe
 * a complete marker; it is not a new 500 ms timer after configuration. */
#define GPS_BACKUP_MARKER_WAIT_MS 500u
#define GPS_BACKUP_CONFIRM_MS 350u
#define GPS_BACKUP_MAX_ATTEMPTS 3u

/* Share the former five 300 ms waits; a delayed ACK must not force a reset
 * merely because it exceeds one slice. UART/execution overhead is separate. */
#define GPS_BACKUP_CONFIG_BUDGET_MS 1500u

/* A complete failed-confirmation path can include two MAX-M10S hardware
 * resets, cold-boot waits, library re-syncs, and AIRBORNE_4G readback.  The
 * configured-wait/delay subtotal is 19.32 s, including all three library
 * begin() connection polls and a shared 1.8 s model gate per reset. UART and
 * execution overhead are not included, so this is not a complete time or energy
 * upper bound. The exact capacitor is specified at 0.8 F minimum, not exactly
 * 1 F. At that limit, the energy between the ordinary 3.6 V GPS-acquisition
 * floor and the conservative 3.32 V Flight-3 reported plateau (not measured
 * BOR/VSTOR in dropout) is only 0.775 J. At 4.4 V it holds 3.335 J to that
 * conservative endpoint,
 * leaving 0.3348 J / 11.16% over the 3.0003 J subtotal (30 mA GNSS +
 * 10 mA active/control allowance, 3.3 V, 85% power conversion efficiency).
 * That arithmetic margin does not qualify the excluded overhead or terminal
 * reset-held current. The existing 4.4 V threshold remains unqualified pending
 * exact-assembly measurements; see gps_backup_energy_audit.py.
 * The shared model budget lowers the former aggregate maximum, but its
 * never-ACK SET path increases from 0.96 s to 1.8 s per model gate.
 *
 * A low-rail receiver still gets one marker/PMREQ shutdown attempt.  This
 * threshold suppresses only the expensive RESET_N escalation; main then keeps
 * auxiliary radio windows closed and retries at the next normal scheduled
 * cycle. */
#define GPS_BACKUP_RESET_FLOOR_MV 4400u

/* A terminal PMREQ failure leaves RESET_N actively held. Releasing that hold
 * creates a cold-start/re-sync load, so it uses the same conservative 4.4 V
 * admission threshold as an in-ladder hardware reset, not the lower ordinary
 * acquisition floor. */
#define GPS_CONTAINMENT_RELEASE_FLOOR_MV GPS_BACKUP_RESET_FLOOR_MV

typedef struct {
    uint16_t payload_remaining;
    uint8_t state;
    uint8_t checksum_a;
    uint8_t checksum_b;
} gps_backup_marker_parser_t;

void gps_backup_marker_reset(gps_backup_marker_parser_t* parser);

/* Consume one UART byte. Returns true only after a complete checksum-valid
 * UBX-NAV-EOE frame (class 0x01, id 0x61, payload length 4). */
bool gps_backup_marker_feed(gps_backup_marker_parser_t* parser, uint8_t byte);

typedef enum {
    GPS_BACKUP_CONFIRMED = 0,
    GPS_BACKUP_RETRY_RESET = 1,
    GPS_BACKUP_TERMINAL_FAILURE = 2,
} gps_backup_action_t;

/* Pure, host-testable decision used after each passive confirmation window.
 * The caller requires ACKed volatile marker configuration and one complete
 * checksum-valid NAV-EOE frame. This Boolean policy cannot establish an upper
 * bound on the actual marker spacing; that physical assumption is unqualified. */
gps_backup_action_t gps_backup_decide(
    bool marker_armed,
    bool uart_activity_seen,
    uint8_t attempts_completed);

bool gps_backup_reset_allowed(uint16_t vstor_mv);

bool gps_backup_containment_release_allowed(uint16_t vstor_mv);

#endif /* GPS_BACKUP_POLICY_H */
