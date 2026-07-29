#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "tmp117_conversion.h"

int main(void) {
    int16_t temperature_dc = 1234;

    assert(!tmp117_raw_to_decidegrees(0, nullptr));

    /* Datasheet power-on sentinel must never masquerade as -256 C. */
    assert(!tmp117_raw_to_decidegrees(INT16_MIN, &temperature_dc));
    assert(temperature_dc == 1234);

    /* TI datasheet examples; the wire field is 0.1 C per LSB. */
    assert(tmp117_raw_to_decidegrees((int16_t)0x0C80, &temperature_dc));
    assert(temperature_dc == 250);
    assert(tmp117_raw_to_decidegrees((int16_t)0xF380, &temperature_dc));
    assert(temperature_dc == -250);

    assert(tmp117_raw_to_decidegrees(0, &temperature_dc));
    assert(temperature_dc == 0);
    assert(tmp117_raw_to_decidegrees(128, &temperature_dc));
    assert(temperature_dc == 10);
    assert(tmp117_raw_to_decidegrees(12800, &temperature_dc));
    assert(temperature_dc == 1000);

    /* Nearest-decidegree rounding is symmetric around zero. */
    assert(tmp117_raw_to_decidegrees(6, &temperature_dc));
    assert(temperature_dc == 0);
    assert(tmp117_raw_to_decidegrees(7, &temperature_dc));
    assert(temperature_dc == 1);
    assert(tmp117_raw_to_decidegrees(-6, &temperature_dc));
    assert(temperature_dc == 0);
    assert(tmp117_raw_to_decidegrees(-7, &temperature_dc));
    assert(temperature_dc == -1);

    assert(tmp117_raw_to_decidegrees(INT16_MAX, &temperature_dc));
    assert(temperature_dc == 2560);
    assert(tmp117_raw_to_decidegrees((int16_t)(INT16_MIN + 1),
                                    &temperature_dc));
    assert(temperature_dc == -2560);

    puts("TMP117 datasheet-to-wire conversion and reset-sentinel checks passed");
    return 0;
}
