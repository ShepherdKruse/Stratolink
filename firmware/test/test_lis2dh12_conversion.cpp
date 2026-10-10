#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "lis2dh12_conversion.h"

int main(void) {
    assert(lis2dh12_low_power_to_cm_s2(0) == 0);
    assert(lis2dh12_low_power_to_cm_s2(1) == 15);
    assert(lis2dh12_low_power_to_cm_s2(-1) == -15);
    assert(lis2dh12_low_power_to_cm_s2(64) == 1004);
    assert(lis2dh12_low_power_to_cm_s2(-64) == -1004);
    assert(lis2dh12_low_power_to_cm_s2(INT8_MAX) == 1992);
    assert(lis2dh12_low_power_to_cm_s2(INT8_MIN) == -2008);

    assert(!lis2dh12_int1_active(0x00));
    assert(!lis2dh12_int1_active(0x01)); /* XL alone is normal on a flat board. */
    assert(!lis2dh12_int1_active(0x15)); /* XL|YL|ZL bits without aggregate IA. */
    assert(!lis2dh12_int1_active(0x3F)); /* Every per-axis source bit, still no IA. */
    assert(lis2dh12_int1_active(0x40));
    assert(lis2dh12_int1_active(0x55));
    assert(lis2dh12_int1_active(0xFF));

    assert(!lis2dh12_freefall_is_cleared(false, false));
    assert(!lis2dh12_freefall_is_cleared(false, true));
    assert(!lis2dh12_freefall_is_cleared(true, false));
    assert(lis2dh12_freefall_is_cleared(true, true));

    int16_t prior = lis2dh12_low_power_to_cm_s2(INT8_MIN);
    for (int raw = INT8_MIN + 1; raw <= INT8_MAX; ++raw) {
        int16_t current = lis2dh12_low_power_to_cm_s2((int8_t)raw);
        assert(current > prior);
        prior = current;
    }

    puts("LIS2DH12 conversion, aggregate INT1, and fail-closed clear passed");
    return 0;
}
