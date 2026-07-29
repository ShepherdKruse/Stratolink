#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "ltr390_conversion.h"

int main(void) {
    static_assert(LTR390_UV_COUNTS_PER_UVI_18X_18BIT == 350u,
                  "Rev. 1.7 flight-setting sensitivity must remain explicit");

    assert(ltr390_uv_index_from_raw(0u) == 0u);
    assert(ltr390_uv_index_from_raw(349u) == 0u);
    assert(ltr390_uv_index_from_raw(350u) == 1u);
    assert(ltr390_uv_index_from_raw(3500u) == 10u);
    assert(ltr390_uv_index_from_raw(88899u) == 253u);
    assert(ltr390_uv_index_from_raw(88900u) == 255u);
    assert(ltr390_uv_index_from_raw(89249u) == 255u);
    assert(ltr390_uv_index_from_raw(89250u) == 255u);
    assert(ltr390_uv_index_from_raw(UINT32_MAX) == 255u);

    assert(ltr390_lux_from_raw_1x_18bit(0u) == 0u);
    assert(ltr390_lux_from_raw_1x_18bit(1u) == 0u);
    assert(ltr390_lux_from_raw_1x_18bit(10u) == 6u);
    assert(ltr390_lux_from_raw_1x_18bit(100000u) == 60000u);
    assert(ltr390_lux_from_raw_1x_18bit(109223u) == 65533u);
    assert(ltr390_lux_from_raw_1x_18bit(109224u) == 65535u);
    assert(ltr390_lux_from_raw_1x_18bit(109225u) == 65535u);
    assert(ltr390_lux_from_raw_1x_18bit(109226u) == 65535u);
    assert(ltr390_lux_from_raw_1x_18bit(UINT32_MAX) == 65535u);

    puts("LTR390 Rev. 1.7 UV and ALS conversions passed");
    return 0;
}
