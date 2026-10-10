/* Host-compilable adversarial tests for the NAV-PVT epoch freshness guard.
 *
 * Build: g++ -std=c++17 -Wall -Wextra -Werror -I include \
 *        test/test_gps_freshness.cpp src/gps_freshness.cpp \
 *        -o /tmp/test_gps_freshness
 */
#include "gps_freshness.h"

#include <cstdint>
#include <cstdio>

static int passed = 0;
static int failed = 0;

static void check(const char* name, bool condition) {
    std::printf("[%s] %s\n", condition ? "PASS" : "FAIL", name);
    condition ? ++passed : ++failed;
}

static uint32_t prng_state = 0x51A7E123u;
static uint32_t next_random(void) {
    prng_state ^= prng_state << 13;
    prng_state ^= prng_state >> 17;
    prng_state ^= prng_state << 5;
    return prng_state;
}

int main(void) {
    gps_freshness_t state{};

    gps_freshness_reset(&state);
    check("first epoch establishes anchor only",
          !gps_freshness_observe(&state, 123000u));
    check("identical cached epoch is stale",
          !gps_freshness_observe(&state, 123000u));
    check("advancing epoch is fresh",
          gps_freshness_observe(&state, 124000u));
    check("new identical epoch remains stale",
          !gps_freshness_observe(&state, 124000u));
    check("backward epoch is stale",
          !gps_freshness_observe(&state, 123000u));
    check("backward epoch does not poison anchor",
          gps_freshness_observe(&state, 125000u));

    gps_freshness_reset(&state);
    check("week-end epoch anchors",
          !gps_freshness_observe(&state, 604799000u));
    check("weekly rollover to zero advances",
          gps_freshness_observe(&state, 0u));

    gps_freshness_reset(&state);
    check("pre-reset first epoch anchors",
          !gps_freshness_observe(&state, 400000u));
    check("pre-reset second epoch advances",
          gps_freshness_observe(&state, 401000u));
    gps_freshness_reset(&state);
    check("MCU reset blocks one cached fix",
          !gps_freshness_observe(&state, 401000u));
    check("cached fix stays blocked",
          !gps_freshness_observe(&state, 401000u));
    check("post-reset advancing epoch is fresh",
          gps_freshness_observe(&state, 402000u));

    gps_freshness_reset(&state);
    check("out-of-range week epoch does not anchor",
          !gps_freshness_observe(&state, 604800000u));
    check("valid epoch anchors after invalid input",
          !gps_freshness_observe(&state, 500000u));
    check("large modular backward jump is stale",
          !gps_freshness_observe(&state, 400000u));
    check("forward epoch remains fresh after rejected jump",
          gps_freshness_observe(&state, 501000u));

    gps_freshness_reset(&state);
    check("half-week ambiguity starts from an anchor",
          !gps_freshness_observe(&state, 1000u));
    check("exact half-week jump fails closed",
          !gps_freshness_observe(&state, 302401000u));
    check("half-week rejection does not poison anchor",
          gps_freshness_observe(&state, 2000u));

    check("null state fails closed",
          !gps_freshness_observe(nullptr, 1u));

    check("no anchor below silence threshold does not reset",
          !gps_recovery_due(false, 4999u, 0u, 0u));
    check("no anchor at silence threshold resets",
          gps_recovery_due(false, 5000u, 0u, 0u));
    check("anchored epoch below frozen threshold does not reset",
          !gps_recovery_due(true, 2999u, 0u, 2500u));
    check("anchored epoch at frozen threshold resets",
          gps_recovery_due(true, 3000u, 0u, 2999u));
    check("recent advancement suppresses inline reset",
          !gps_recovery_due(true, 9000u, 8999u, 8999u));
    check("advance then freeze in the same acquisition resets",
          gps_recovery_due(true, 9000u, 6000u, 8999u));
    check("recovery timing is millis-wrap safe",
          gps_recovery_due(true, 0x00000100u,
                           0xFFFFF000u, 0x000000F0u));

    uint8_t stale_streak = 0u;
    check("first stale cycle advances legacy ladder",
          !gps_stale_ladder_step(false, false, 2u, &stale_streak) &&
          stale_streak == 1u);
    check("same-cycle reset clears ladder without a second reset",
          !gps_stale_ladder_step(false, true, 2u, &stale_streak) &&
          stale_streak == 0u);
    stale_streak = 1u;
    check("legacy ladder fires once at threshold and clears",
          gps_stale_ladder_step(false, false, 2u, &stale_streak) &&
          stale_streak == 0u);
    stale_streak = 1u;
    check("navigation progress clears legacy ladder",
          !gps_stale_ladder_step(true, false, 2u, &stale_streak) &&
          stale_streak == 0u);
    stale_streak = UINT8_MAX;
    check("saturated legacy ladder fires and clears safely",
          gps_stale_ladder_step(false, false, UINT8_MAX, &stale_streak) &&
          stale_streak == 0u);
    check("invalid legacy ladder inputs fail without mutation",
          !gps_stale_ladder_step(false, false, 1u, nullptr));

    /* Compare the production branch arithmetic against an independent
     * 64-bit-modulo oracle across anchors, week rollovers, accepted forward
     * movement, rejected backward movement, and the ambiguous half range. */
    constexpr uint32_t week_ms = 604800000u;
    constexpr uint32_t half_week_ms = week_ms / 2u;
    bool ordering_property = true;
    for (uint32_t i = 0; i < 200000u; ++i) {
        uint32_t anchor = next_random() % week_ms;
        uint32_t sample = next_random() % week_ms;
        uint64_t forward =
            ((uint64_t)sample + week_ms - anchor) % week_ms;
        bool expected = forward > 0u && forward < half_week_ms;
        gps_freshness_t trial{anchor, true};
        bool observed = gps_freshness_observe(&trial, sample);
        if (observed != expected ||
            trial.itow_ms != (expected ? sample : anchor) ||
            !trial.anchored) {
            ordering_property = false;
            break;
        }
    }
    check("200k modular-ordering property trials pass", ordering_property);

    /* Recovery timing uses unsigned elapsed arithmetic. Exercise arbitrary
     * millis() wrap positions and all combinations of the two reset causes. */
    bool recovery_property = true;
    for (uint32_t i = 0; i < 200000u; ++i) {
        uint32_t now = next_random();
        uint32_t progress_age = next_random() % 10000u;
        uint32_t pvt_age = next_random() % 10000u;
        bool anchor = (next_random() & 1u) != 0;
        uint32_t progress_at = now - progress_age;
        uint32_t pvt_at = now - pvt_age;
        bool expected =
            (anchor && progress_age >= GPS_FROZEN_EPOCH_RESET_MS) ||
            pvt_age >= GPS_PVT_SILENCE_RESET_MS;
        if (gps_recovery_due(anchor, now, progress_at, pvt_at) !=
            expected) {
            recovery_property = false;
            break;
        }
    }
    check("200k wrap-safe recovery property trials pass", recovery_property);

    std::printf("=== GPS freshness: %d passed, %d failed ===\n",
                passed, failed);
    return failed == 0 ? 0 : 1;
}
