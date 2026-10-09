import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { contactRanks, earthTargets, pointRanks, summarize, vector, waitingStats } from './contact-model.js';

const empty = () => new Uint16Array(337).fill(65535);

test('both deployed trajectory assets match their provenance and contain 500 complete tracks', () => {
  // Resolve from the web root, independent of the command's working directory.
  const root = new URL('../../public/assets/payload-dev-log/', import.meta.url);
  const meta = JSON.parse(readFileSync(new URL('fleet.json', root)));
  for (const [file, hash] of Object.entries(meta.track_hashes)) {
    const bytes = readFileSync(new URL(file, root));
    assert.equal(bytes.byteLength, 500 * 337 * 2 * 4);
    assert.equal(createHash('sha256').update(bytes).digest('hex'), hash);
  }
});

test('unreached locations remain in the denominator and do not get a zero wait', () => {
  const s = waitingStats(empty(), 500);
  assert.equal(s.meanCapped, 168);
  assert.equal(s.week, 0);
  assert.equal(s.median, 169);
  assert.equal(s.reachedFortnight, false);
});

test('continuous coverage gives zero wait and complete weekly contact', () => {
  const s = waitingStats(new Uint16Array(337).fill(1), 1);
  assert.equal(s.meanCapped, 0);
  assert.equal(s.day, 1);
  assert.equal(s.everyWeek, true);
});

test('look-ahead includes the second week without wrapping the end to the start', () => {
  const ranks = empty(); ranks[200] = 1;
  const s = waitingStats(ranks, 1);
  assert.equal(s.reachedWeek, false);
  assert.equal(s.reachedFortnight, true);
  assert.equal(s.waits[32], 168);
  assert.equal(s.waits[31], 169);
  assert.equal(s.week, 136 / 168);
  ranks.fill(65535); ranks[0] = 1;
  assert.equal(waitingStats(ranks, 1).week, 1 / 168);
  assert.throws(() => waitingStats(ranks, 1, { hours: 200 }), /Incomplete/);
});

test('arrival weighting includes current contact and long waits, not just completed gaps', () => {
  const ranks = empty(); ranks[24] = 1; ranks[168] = 1;
  const s = waitingStats(ranks, 1);
  assert.equal(s.day, 49 / 168);
  assert.equal(s.everyWeek, true);
  assert.equal(s.meanCapped, (24 * 25 / 2 + 143 * 144 / 2) / 168);
});

test('hemisphere statistics use their own area denominators', () => {
  const targets = [{ lat: 40 }, { lat: -40 }], ranks = new Uint16Array(674).fill(65535);
  ranks.fill(1, 0, 337);
  const { regions } = summarize(ranks, 337, targets, 1);
  assert.equal(regions.earth.week, .5);
  assert.equal(regions.north.week, 1);
  assert.equal(regions.south.week, 0);
});

test('spatial grid agrees with independent great-circle calculation at poles and dateline', () => {
  const targets = earthTargets(2000);
  const positions = [[89.5, 179.9], [-89.5, -179.9], [0, 179.9], [0, -179.9], [30, 40], [-30, -70]];
  const tracks = new Float32Array(positions.flat()), radius = 500;
  const ranks = contactRanks(tracks, 1, targets, radius);
  targets.forEach((p, i) => {
    const expected = positions.findIndex(([lat, lon]) => {
      const phi = Math.PI / 180;
      const a = Math.sin((lat - p.lat) * phi / 2) ** 2 + Math.cos(lat * phi) * Math.cos(p.lat * phi) * Math.sin((lon - p.lon) * phi / 2) ** 2;
      return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(a))) <= radius;
    });
    assert.equal(ranks[i], expected < 0 ? 65535 : expected + 1);
  });
});

test('more balloons and larger footprints cannot delay a contact', () => {
  const tracks = new Float32Array(2 * 337 * 2);
  for (let k = 0; k < 2; k++) for (let t = 0; t < 337; t++) {
    tracks[(k * 337 + t) * 2] = k ? -30 : 30;
    tracks[(k * 337 + t) * 2 + 1] = (t * 2 + 180) % 360 - 180;
  }
  const small = pointRanks(tracks, 337, -30, 0, 250), big = pointRanks(tracks, 337, -30, 0, 500);
  assert(waitingStats(small, 2).meanCapped <= waitingStats(small, 1).meanCapped);
  assert(waitingStats(big, 2).meanCapped <= waitingStats(small, 2).meanCapped);
  assert.equal(vector(0, 0)[0], 1);
});
