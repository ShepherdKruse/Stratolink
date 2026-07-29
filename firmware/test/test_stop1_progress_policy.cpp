#include <cassert>
#include <cstdint>
#include <iostream>

#include "stop1_progress_policy.h"

static void test_mask_then_fallback(void) {
    stop1_progress_state_t state = {0u, false};
    for (uint8_t i = 1; i < STOP1_MASK_INT1_AFTER_SHORT_WAKES; ++i) {
        assert(stop1_progress_observe(&state, 10u, 28000u) ==
               STOP1_PROGRESS_CONTINUE);
        assert(!state.int1_masked);
    }
    assert(stop1_progress_observe(&state, 10u, 28000u) ==
           STOP1_PROGRESS_MASK_INT1);
    assert(state.int1_masked);

    for (uint8_t i = STOP1_MASK_INT1_AFTER_SHORT_WAKES + 1u;
         i < STOP1_SHALLOW_FALLBACK_AFTER_SHORT_WAKES; ++i) {
        assert(stop1_progress_observe(&state, 999u, 28000u) ==
               STOP1_PROGRESS_CONTINUE);
    }
    assert(stop1_progress_observe(&state, 999u, 28000u) ==
           STOP1_PROGRESS_SHALLOW_FALLBACK);
}

static void test_progress_resets_only_the_streak(void) {
    stop1_progress_state_t state = {0u, false};
    for (uint8_t i = 0; i < STOP1_MASK_INT1_AFTER_SHORT_WAKES; ++i) {
        (void)stop1_progress_observe(&state, 0u, 28000u);
    }
    assert(state.int1_masked);
    assert(stop1_progress_observe(&state, 1000u, 28000u) ==
           STOP1_PROGRESS_CONTINUE);
    assert(state.short_progress_wakes == 0u);
    assert(state.int1_masked);
    for (uint8_t i = 1; i < STOP1_SHALLOW_FALLBACK_AFTER_SHORT_WAKES; ++i) {
        assert(stop1_progress_observe(&state, 0u, 28000u) ==
               STOP1_PROGRESS_CONTINUE);
    }
    assert(stop1_progress_observe(&state, 0u, 28000u) ==
           STOP1_PROGRESS_SHALLOW_FALLBACK);
}

static void test_saturation_and_null_fail_closed(void) {
    stop1_progress_state_t state = {UINT8_MAX, true};
    assert(stop1_progress_observe(&state, 0u, 28000u) ==
           STOP1_PROGRESS_SHALLOW_FALLBACK);
    assert(state.short_progress_wakes == UINT8_MAX);
    assert(stop1_progress_observe(nullptr, 10u, 28000u) ==
           STOP1_PROGRESS_SHALLOW_FALLBACK);
    assert(stop1_progress_observe(&state, 0u, 0u) ==
           STOP1_PROGRESS_SHALLOW_FALLBACK);
}

static void test_short_residue_requires_its_complete_duration(void) {
    stop1_progress_state_t state = {0u, false};
    assert(stop1_progress_observe(&state, 499u, 500u) ==
           STOP1_PROGRESS_CONTINUE);
    assert(state.short_progress_wakes == 1u);
    assert(stop1_progress_observe(&state, 500u, 500u) ==
           STOP1_PROGRESS_CONTINUE);
    assert(state.short_progress_wakes == 0u);
}

int main(void) {
    static_assert(STOP1_MASK_INT1_AFTER_SHORT_WAKES > 0u, "mask threshold");
    static_assert(STOP1_SHALLOW_FALLBACK_AFTER_SHORT_WAKES >
                      STOP1_MASK_INT1_AFTER_SHORT_WAKES,
                  "fallback must follow masking");
    test_mask_then_fallback();
    test_progress_resets_only_the_streak();
    test_saturation_and_null_fail_closed();
    test_short_residue_requires_its_complete_duration();
    std::cout << "PASS: STOP1 short-progress mask and shallow fallback policy\n";
    return 0;
}
