#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "telemetry.h"
#include "tmp117_conversion.h"

static int16_t read_be_i16(const uint8_t* bytes) {
    return (int16_t)(((uint16_t)bytes[0] << 8) | bytes[1]);
}

static void require_wire_temperature(int16_t tmp117_raw,
                                     int16_t expected_decidegrees) {
    int16_t temperature_dc = 0;
    assert(tmp117_raw_to_decidegrees(tmp117_raw, &temperature_dc));
    assert(temperature_dc == expected_decidegrees);

    telemetry_input_t telemetry = {};
    telemetry.temperature_dc = temperature_dc;
    uint8_t payload[TELEMETRY_PAYLOAD_SIZE] = {};
    telemetry_pack(&telemetry, payload);

    /* Bytes 12-13 are decoded by TTN as signed big-endian / 10. */
    assert(read_be_i16(payload + 12) == expected_decidegrees);
}

int main(void) {
    require_wire_temperature((int16_t)0x0C80, 250); /* +25.0 C */
    require_wire_temperature((int16_t)0xF380, -250); /* -25.0 C */

    puts("TMP117-to-40-byte-wire temperature unit checks passed");
    return 0;
}
