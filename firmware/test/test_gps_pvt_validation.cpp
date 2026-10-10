#include "gps_pvt_validation.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static gps_pvt_values_t valid_pvt(void) {
    gps_pvt_values_t value = {};
    value.lat_e7 = 377749000;
    value.lon_e7 = -1224194000;
    value.altitude_mm = 30123456;
    value.ground_speed_mm_s = 55123;
    value.heading_e5 = 35999999;
    value.satellites = 8;
    return value;
}

static void rejects_without_writing(gps_pvt_values_t value) {
    gps_wire_fix_t out = {
        1, 2, 3, 4, 5, 6,
    };
    assert(!gps_pvt_to_wire_fix(&value, &out));
    assert(out.lat_e7 == 1);
    assert(out.lon_e7 == 2);
    assert(out.altitude_m == 3);
    assert(out.speed_cm_s == 4);
    assert(out.heading_cdeg == 5);
    assert(out.satellites == 6);
}

int main(void) {
    gps_wire_fix_t out = {};
    gps_pvt_values_t value = valid_pvt();
    assert(gps_pvt_to_wire_fix(&value, &out));
    assert(out.lat_e7 == value.lat_e7);
    assert(out.lon_e7 == value.lon_e7);
    assert(out.altitude_m == 30123);
    assert(out.speed_cm_s == 5512);
    assert(out.heading_cdeg == 35999);
    assert(out.satellites == 8);

    assert(!gps_pvt_to_wire_fix(nullptr, &out));
    assert(!gps_pvt_to_wire_fix(&value, nullptr));

    /* Geographic boundaries, including legitimate equator/prime meridian. */
    value = valid_pvt(); value.lat_e7 = -900000000;
    assert(gps_pvt_to_wire_fix(&value, &out));
    value.lat_e7 = 900000000;
    assert(gps_pvt_to_wire_fix(&value, &out));
    value.lon_e7 = -1800000000;
    assert(gps_pvt_to_wire_fix(&value, &out));
    value.lon_e7 = 1800000000;
    assert(gps_pvt_to_wire_fix(&value, &out));
    value.lat_e7 = 0; value.lon_e7 = 0;
    assert(gps_pvt_to_wire_fix(&value, &out));

    value = valid_pvt(); value.lat_e7 = -900000001;
    rejects_without_writing(value);
    value = valid_pvt(); value.lat_e7 = 900000001;
    rejects_without_writing(value);
    value = valid_pvt(); value.lon_e7 = -1800000001;
    rejects_without_writing(value);
    value = valid_pvt(); value.lon_e7 = 1800000001;
    rejects_without_writing(value);

    value = valid_pvt(); value.altitude_mm = -500000;
    assert(gps_pvt_to_wire_fix(&value, &out) && out.altitude_m == -500);
    value.altitude_mm = 60000000;
    assert(gps_pvt_to_wire_fix(&value, &out) && out.altitude_m == 60000);
    value.altitude_mm = -500001;
    rejects_without_writing(value);
    value = valid_pvt(); value.altitude_mm = 60000001;
    rejects_without_writing(value);

    value = valid_pvt(); value.ground_speed_mm_s = 0;
    assert(gps_pvt_to_wire_fix(&value, &out) && out.speed_cm_s == 0);
    value.ground_speed_mm_s = 500000;
    assert(gps_pvt_to_wire_fix(&value, &out) && out.speed_cm_s == 50000);
    value.ground_speed_mm_s = -1;
    rejects_without_writing(value);
    value = valid_pvt(); value.ground_speed_mm_s = 500001;
    rejects_without_writing(value);

    value = valid_pvt(); value.heading_e5 = 0;
    assert(gps_pvt_to_wire_fix(&value, &out) && out.heading_cdeg == 0);
    value.heading_e5 = 35999999;
    assert(gps_pvt_to_wire_fix(&value, &out) &&
           out.heading_cdeg == 35999);
    value.heading_e5 = -1;
    rejects_without_writing(value);
    value = valid_pvt(); value.heading_e5 = 36000000;
    rejects_without_writing(value);

    value = valid_pvt(); value.satellites = 3;
    rejects_without_writing(value);
    value = valid_pvt(); value.satellites = 65;
    rejects_without_writing(value);

    puts("GPS PVT value ranges and telemetry conversion pass");
    return 0;
}
