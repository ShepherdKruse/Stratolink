import assert from 'node:assert/strict';

import { telemetryNumber } from './telemetry-values.ts';

assert.equal(telemetryNumber(null), null);
assert.equal(telemetryNumber(undefined), null);
assert.equal(telemetryNumber(''), null);
assert.equal(telemetryNumber('   '), null);
assert.equal(telemetryNumber(Number.NaN), null);
assert.equal(telemetryNumber(Number.POSITIVE_INFINITY), null);
assert.equal(telemetryNumber('not-a-reading'), null);
assert.equal(telemetryNumber(0), 0);
assert.equal(telemetryNumber('0'), 0);
assert.equal(telemetryNumber(-42.125), -42.125);
assert.equal(telemetryNumber('4616'), 4616);

console.log('telemetry value host tests passed');
