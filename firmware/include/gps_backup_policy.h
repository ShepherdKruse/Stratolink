#ifndef GPS_BACKUP_POLICY_H
#define GPS_BACKUP_POLICY_H

#include <stdbool.h>
#include <stdint.h>

/* Immediately before PMREQ the receiver is temporarily configured for a
 * RAM-only 10 Hz NAV-EOE marker. A complete marker establishes the frame
 * boundary; 350 ms then spans more than three expected marker periods. */
#define GPS_BACKUP_MARKER_WAIT_MS 500u
#define GPS_BACKUP_CONFIRM_MS 350u
#define GPS_BACKUP_MAX_ATTEMPTS 3u
#define GPS_BACKUP_RETRY_SLEEP_MS 5000u

/* A complete failed-confirmation path can include two MAX-M10S hardware
 * resets, cold-boot waits, library re-syncs, and AIRBORNE_4G readback.  The
 * conservative source bound is 16.84 s. The exact capacitor is specified at
 * 0.8 F minimum, not exactly 1 F. At that limit, the energy between the
 * ordinary 3.6 V GPS-acquisition floor and the conservative 3.32 V Flight-3
 * reported plateau (not measured BOR/VSTOR in dropout) is
 * only 0.775 J. At 4.4 V it holds 3.335 J to that conservative endpoint,
 * leaving 0.720 J / 27.5%
 * margin over a deliberately conservative 2.615 J path bound (30 mA GNSS +
 * 10 mA active/control allowance, 3.3 V, 85% power conversion efficiency).
 *
 * A low-rail receiver still gets one marker/PMREQ shutdown attempt.  This
 * threshold suppresses only the expensive RESET_N escalation; main then keeps
 * auxiliary radio windows closed and retries after five seconds. */
#define GPS_BACKUP_RESET_FLOOR_MV 4400u

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
 * Silence is meaningful only after UART UBX output, a 10 Hz measurement rate,
 * and periodic NAV-EOE were positively configured in volatile receiver RAM,
 * then one complete checksum-valid NAV-EOE frame was observed. */
gps_backup_action_t gps_backup_decide(
    bool marker_armed,
    bool uart_activity_seen,
    uint8_t attempts_completed);

bool gps_backup_reset_allowed(uint16_t vstor_mv);

#endif /* GPS_BACKUP_POLICY_H */
