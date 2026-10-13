#!/usr/bin/env python3
"""Exercise the actual DNP driver, sensor initializer and telemetry serializer."""
from pathlib import Path
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SCRATCH = Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/as7331/firmware')

ARDUINO = r'''
#pragma once
#include <stdint.h>
extern unsigned delay_calls;
inline void delay(unsigned long) { ++delay_calls; }
'''
WIRE = r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
extern unsigned bus_begins, bus_ends, transactions;
struct TwoWire {
    void begin() { ++bus_begins; }
    void end() { ++bus_ends; }
    void beginTransmission(uint8_t) { ++transactions; }
    size_t write(uint8_t) { return 1; }
    uint8_t endTransmission() { return 2; } // Every optical address NACKs.
    uint8_t requestFrom(int, int) { ++transactions; return 0; }
    int read() { ++transactions; return -1; }
};
extern TwoWire Wire;
'''
HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <Wire.h>
#include "sensors.h"
#include "sensor_ltr390.h"
#include "telemetry.h"
unsigned delay_calls = 0, bus_begins = 0, bus_ends = 0, transactions = 0;
unsigned temp_inits = 0, baro_inits = 0, accel_inits = 0;
bool other_sensors_ok = true;
TwoWire Wire;
bool sensor_tmp117_init(void) { ++temp_inits; return other_sensors_ok; }
bool sensor_ms5611_init(void) { ++baro_inits; return other_sensors_ok; }
bool sensor_lis2dh12_init(void) { ++accel_inits; return other_sensors_ok; }
int main() {
    // An intentionally empty U6 is not a failed initialization and adds no
    // startup delay/probe. The common bus and fitted sensors still initialize.
    assert(sensors_init());
    assert(bus_begins == 1 && bus_ends == 0);
    assert(temp_inits == 1 && baro_inits == 1 && accel_inits == 1);
    assert(transactions == 0 && delay_calls == 0);
    assert(sensor_ltr390_quiesce());
    assert(!sensor_ltr390_read_uv_index(nullptr));
    assert(!sensor_ltr390_read_ambient_lux(nullptr));

    // Repeated normal wake cycles cannot create UV/lux samples or an optical
    // fault. Seed previously valid readings to exercise telemetry reset.
    telemetry_input_t ti;
    for (unsigned cycle = 0; cycle < 20000; ++cycle) {
        ti.uv_index = 12; ti.ambient_lux = 345;
        telemetry_input_init(&ti);
        const bool uv_ok = sensor_ltr390_read_uv_index(&ti.uv_index);
        const bool lux_ok = sensor_ltr390_read_ambient_lux(&ti.ambient_lux);
        assert(!uv_ok && !lux_ok);
        assert(ti.uv_index == TELEMETRY_UV_INVALID);
        assert(ti.ambient_lux == TELEMETRY_LUX_INVALID);
        assert(sensor_ltr390_quiesce());
        uint8_t packet[TELEMETRY_PAYLOAD_SIZE] = {};
        telemetry_pack(&ti, packet);
        assert(packet[31] == 0xFE);
        assert(packet[32] == 0xFF && packet[33] == 0xFE);
    }
    assert(transactions == 0 && delay_calls == 0);

    // An actual failure of all fitted sensors still reports failure and
    // performs their bounded retries. DNP must not add its own retries.
    other_sensors_ok = false;
    assert(!sensors_init());
    assert(temp_inits == 4 && baro_inits == 4 && accel_inits == 4);
    assert(delay_calls == 9 && transactions == 0);
    sensors_recover_i2c_bus();
    assert(bus_begins == 3 && bus_ends == 1 && delay_calls == 10);
    assert(sensor_ltr390_init() && sensor_ltr390_quiesce());
    assert(transactions == 0 && delay_calls == 10);
    puts("PASS: 20,000 DNP cycles, zero optical I2C/waits, invalid wire data; fitted-sensor failure/recovery preserved");
}
'''

def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='host-', dir=SCRATCH) as temp:
        temp = Path(temp)
        (temp/'Arduino.h').write_text(ARDUINO)
        (temp/'Wire.h').write_text(WIRE)
        (temp/'harness.cpp').write_text(HARNESS)
        common = ['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                  '-I'+str(temp), '-I'+str(ROOT/'firmware/include')]
        sources = [str(temp/'harness.cpp'), str(ROOT/'firmware/src/sensors.cpp'),
                   str(ROOT/'firmware/src/sensor_ltr390.cpp'),
                   str(ROOT/'firmware/src/telemetry.cpp')]
        subprocess.run(common+['-DSTRATOLINK_UV_SENSOR=0']+sources+['-o',str(temp/'test')], check=True)
        result = subprocess.check_output([str(temp/'test')], text=True)
        # An unsupported populated AS7331 must not be silently treated as
        # LTR390 or DNP just by setting the population value to 2.
        unsupported = subprocess.run(common+['-DSTRATOLINK_UV_SENSOR=2','-c',
              str(ROOT/'firmware/src/sensor_ltr390.cpp'),'-o',str(temp/'bad.o')],
              text=True,capture_output=True)
        assert unsupported.returncode != 0
        assert 'Unsupported UV population' in unsupported.stderr
        # Verify both legacy entry routes still compile the complete driver.
        for flags in ([], ['-DSTRATOLINK_UV_SENSOR=1']):
            subprocess.run(common+flags+['-c', str(ROOT/'firmware/src/sensor_ltr390.cpp'),
                           '-o',str(temp/'legacy.o')],check=True)
        report = {'dnp_cycles':20000,'optical_i2c_transactions':0,
                  'optical_delay_calls':0,'wire_uv_invalid':'0xfe',
                  'wire_lux_invalid':'0xfffe','fitted_sensor_recovery_preserved':True,
                  'unsupported_population_compile_rejected':True,
                  'legacy_default_and_explicit_compile':True,
                  'stdout':result.strip(),
                  'limitations':'Host mocks; no physical DNP board, flight or AS7331 driver test.'}
        (HERE/'host-test.json').write_text(json.dumps(report,indent=2)+'\n')
        print(result.strip())

if __name__ == '__main__':
    main()
