import assert from 'node:assert/strict';
import test from 'node:test';
import { telemetrySinceIso, telemetrySinceMs, fleetTelemetrySinceMs } from './missionWindow.ts';

const launch = Date.parse('2026-05-17T15:55:00Z');
const october = Date.parse('2026-10-05T12:00:00Z');
const day = 24 * 60 * 60 * 1000;

test('a completed mission remains replayable after 90 days and after a year', () => {
    for (const status of ['landed', 'recovered', 'lost', 'flying']) {
        for (const now of [october, october + 365 * day]) {
            assert.equal(
                telemetrySinceIso({ status, launchedAt: launch }, now, { fullHistory: true }),
                '2026-05-17T15:55:00.000Z',
            );
        }
    }
});

test('a selected device without usable launch metadata keeps its stored history', () => {
    for (const launchedAt of [null, Number.NaN]) {
        assert.equal(telemetrySinceMs({ launchedAt }, october, { fullHistory: true }), 0);
    }
});

test('a future launch timestamp cannot move the query window into the future', () => {
    assert.equal(
        telemetrySinceMs({ launchedAt: october + day }, october, { fullHistory: true }),
        october,
    );
});

test('fleet queries retain their recent window instead of loading historical missions', () => {
    assert.equal(telemetrySinceMs({ status: 'landed', launchedAt: launch }, october), october - day);
    assert.equal(
        fleetTelemetrySinceMs([
            { status: 'landed', launchedAt: launch },
            { status: 'flying', launchedAt: october - 3 * day },
        ], october),
        october - 3 * day,
    );
});
