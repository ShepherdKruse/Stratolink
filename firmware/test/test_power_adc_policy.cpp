#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "power_adc.h"

int main(void) {
    assert(power_adc_validated_vdda_mv(0) == 0);
    assert(power_adc_validated_vdda_mv(1799) == 0);
    assert(power_adc_validated_vdda_mv(1800) == 1800);
    assert(power_adc_validated_vdda_mv(3300) == 3300);
    assert(power_adc_validated_vdda_mv(3600) == 3600);
    assert(power_adc_validated_vdda_mv(3601) == 0);
    assert(power_adc_validated_vdda_mv(UINT16_MAX) == 0);

    /* Representative STM32WL factory/live samples. */
    assert(power_adc_vdda_from_vrefint(1500, 1500, 3300) == 3300);
    assert(power_adc_vdda_from_vrefint(1500, 1375, 3300) == 3600);
    assert(power_adc_vdda_from_vrefint(1500, 2750, 3300) == 1800);
    assert(power_adc_vdda_from_vrefint(1500, 1374, 3300) == 0);
    assert(power_adc_vdda_from_vrefint(1500, 2751, 3300) == 0);
    assert(power_adc_vdda_from_vrefint(0, 1500, 3300) == 0);
    assert(power_adc_vdda_from_vrefint(UINT16_MAX, 1500, 3300) == 0);
    assert(power_adc_vdda_from_vrefint(1500, 0, 3300) == 0);

    /* Before the full-width check, 396000 mV narrowed to 2784 mV and passed
     * the policy. The corrupt sample must now stay fail-closed. */
    assert((uint16_t)((3300u * 1200u) / 10u) == 2784u);
    assert(power_adc_vdda_from_vrefint(1200, 10, 3300) == 0);
    puts("Power ADC reference policy: invalid VDDA fails closed");
    return 0;
}
