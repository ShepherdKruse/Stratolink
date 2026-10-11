import test from 'node:test';
import assert from 'node:assert/strict';
import { forecastEligible, forecastViewFor } from './forecastEligibility.ts';

test('only balloons that may still be aloft get forecast layers', () => {
    for (const status of ['flying', 'Flying', 'planned', 'idle', 'storage', '', null, undefined]) {
        assert.equal(forecastEligible(status), true, String(status));
        assert.equal(forecastViewFor(status), 'full');
    }
    for (const status of ['landed', 'Recovered', 'retired', 'lost', 'MISSING', ' landed ']) {
        assert.equal(forecastEligible(status), false, status);
        assert.equal(forecastViewFor(status), 'history');
    }
});
