#include "gps_backup_policy.h"

#include <cassert>
#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>

static std::vector<uint8_t> nav_eoe_frame() {
    std::vector<uint8_t> frame = {0xB5, 0x62, 0x01, 0x61, 4, 0};
    for (uint8_t i = 0; i < 4; ++i) frame.push_back(i);
    uint8_t a = 0;
    uint8_t b = 0;
    for (size_t i = 2; i < frame.size(); ++i) {
        a = static_cast<uint8_t>(a + frame[i]);
        b = static_cast<uint8_t>(b + a);
    }
    frame.push_back(a);
    frame.push_back(b);
    return frame;
}

int main() {
    unsigned checks = 0;

    for (uint8_t attempt = 1; attempt <= GPS_BACKUP_MAX_ATTEMPTS; ++attempt) {
        assert(gps_backup_decide(true, false, attempt) ==
               GPS_BACKUP_CONFIRMED);
        checks++;

        gps_backup_action_t expected =
            attempt < GPS_BACKUP_MAX_ATTEMPTS
                ? GPS_BACKUP_RETRY_RESET
                : GPS_BACKUP_TERMINAL_FAILURE;
        assert(gps_backup_decide(false, false, attempt) == expected);
        assert(gps_backup_decide(false, true, attempt) == expected);
        assert(gps_backup_decide(true, true, attempt) == expected);
        checks += 3;
    }

    /* Corrupt/out-of-range counters fail closed instead of wrapping into an
     * unbounded retry loop. */
    assert(gps_backup_decide(false, false, 0) == GPS_BACKUP_RETRY_RESET);
    assert(gps_backup_decide(false, false, 255) ==
           GPS_BACKUP_TERMINAL_FAILURE);
    checks += 2;

    gps_backup_marker_parser_t parser{};
    gps_backup_marker_reset(&parser);
    std::vector<uint8_t> frame = nav_eoe_frame();
    bool complete = false;
    for (uint8_t byte : frame) {
        complete = gps_backup_marker_feed(&parser, byte);
    }
    assert(complete);
    checks++;

    gps_backup_marker_reset(&parser);
    const std::array<uint8_t, 8> noise = {
        0x00, 0xB5, 0xB5, 0x61, 0x62, 0x01, 0x06, 0xFF
    };
    for (uint8_t byte : noise) {
        assert(!gps_backup_marker_feed(&parser, byte));
    }
    complete = false;
    for (uint8_t byte : frame) {
        complete = gps_backup_marker_feed(&parser, byte);
    }
    assert(complete);
    checks++;

    std::vector<uint8_t> corrupt = frame;
    corrupt[7] ^= 0x01u;
    gps_backup_marker_reset(&parser);
    complete = false;
    for (uint8_t byte : corrupt) {
        complete = gps_backup_marker_feed(&parser, byte);
    }
    assert(!complete);
    checks++;

    assert(!gps_backup_marker_feed(nullptr, 0xB5));
    gps_backup_marker_reset(nullptr);
    checks++;

    assert(!gps_backup_reset_allowed(0));
    assert(!gps_backup_reset_allowed(GPS_BACKUP_RESET_FLOOR_MV - 1u));
    assert(gps_backup_reset_allowed(GPS_BACKUP_RESET_FLOOR_MV));
    assert(gps_backup_reset_allowed(UINT16_MAX));
    checks += 4;

    std::printf("gps backup policy: %u checks passed\n", checks);
    return 0;
}
