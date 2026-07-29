#include "gps_backup_policy.h"

static void checksum_add(gps_backup_marker_parser_t* parser, uint8_t byte) {
    parser->checksum_a = (uint8_t)(parser->checksum_a + byte);
    parser->checksum_b = (uint8_t)(parser->checksum_b + parser->checksum_a);
}

void gps_backup_marker_reset(gps_backup_marker_parser_t* parser) {
    if (!parser) return;
    parser->payload_remaining = 0;
    parser->state = 0;
    parser->checksum_a = 0;
    parser->checksum_b = 0;
}

bool gps_backup_marker_feed(gps_backup_marker_parser_t* parser, uint8_t byte) {
    if (!parser) return false;

    switch (parser->state) {
        case 0: /* UBX sync 1 */
            if (byte == 0xB5u) parser->state = 1;
            break;
        case 1: /* UBX sync 2 */
            if (byte == 0x62u) {
                parser->state = 2;
                parser->checksum_a = 0;
                parser->checksum_b = 0;
            } else {
                parser->state = (byte == 0xB5u) ? 1u : 0u;
            }
            break;
        case 2: /* NAV class */
            if (byte != 0x01u) {
                gps_backup_marker_reset(parser);
                break;
            }
            checksum_add(parser, byte);
            parser->state = 3;
            break;
        case 3: /* EOE id */
            if (byte != 0x61u) {
                gps_backup_marker_reset(parser);
                break;
            }
            checksum_add(parser, byte);
            parser->state = 4;
            break;
        case 4: /* payload length LSB = 4 */
            if (byte != 4u) {
                gps_backup_marker_reset(parser);
                break;
            }
            checksum_add(parser, byte);
            parser->state = 5;
            break;
        case 5: /* payload length MSB = 0 */
            if (byte != 0u) {
                gps_backup_marker_reset(parser);
                break;
            }
            checksum_add(parser, byte);
            parser->payload_remaining = 4u;
            parser->state = 6;
            break;
        case 6: /* payload */
            checksum_add(parser, byte);
            if (--parser->payload_remaining == 0u) parser->state = 7;
            break;
        case 7: /* checksum A */
            if (byte != parser->checksum_a) {
                gps_backup_marker_reset(parser);
                break;
            }
            parser->state = 8;
            break;
        case 8: { /* checksum B */
            bool valid = byte == parser->checksum_b;
            gps_backup_marker_reset(parser);
            return valid;
        }
        default:
            gps_backup_marker_reset(parser);
            break;
    }
    return false;
}

gps_backup_action_t gps_backup_decide(
    bool marker_armed,
    bool uart_activity_seen,
    uint8_t attempts_completed) {
    if (marker_armed && !uart_activity_seen) {
        return GPS_BACKUP_CONFIRMED;
    }
    if (attempts_completed < GPS_BACKUP_MAX_ATTEMPTS) {
        return GPS_BACKUP_RETRY_RESET;
    }
    return GPS_BACKUP_TERMINAL_FAILURE;
}

bool gps_backup_reset_allowed(uint16_t vstor_mv) {
    return vstor_mv >= GPS_BACKUP_RESET_FLOOR_MV;
}
