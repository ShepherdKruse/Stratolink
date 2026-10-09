import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { contactRanks, earthTargets, summarize } from '../src/payload-dev-log/contact-model.js';

const read = name => {
  const buffer = readFileSync(new URL(`../public/assets/payload-dev-log/${name}`, import.meta.url));
  return new Float32Array(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength));
};
const north = read('fleet-tracks.bin'), south = read('fleet-south.bin');
function worldwide(subdivisions = 1) {
  const hours = 336 * subdivisions + 1, tracks = new Float32Array(500 * hours * 2);
  for (let k = 0; k < 500; k++) for (let t = 0; t < hours; t++) {
    const source = k % 2 ? south : north, a = Math.floor(t / subdivisions), b = Math.min(336, a + 1), fraction = t / subdivisions - a;
    const base = Math.floor(k / 2) * 674, first = base + a * 2, second = base + b * 2, destination = (k * hours + t) * 2;
    tracks[destination] = source[first] + (source[second] - source[first]) * fraction;
    const delta = ((source[second + 1] - source[first + 1] + 540) % 360) - 180;
    tracks[destination + 1] = ((source[first + 1] + delta * fraction + 540) % 360) - 180;
  }
  return { tracks, hours };
}
const world = worldwide().tracks, targets = earthTargets();
const report = { weather: 'NOAA NCEP/DOE Reanalysis 2, 300 hPa, May 17–31, 2024', radiusKm: 350, arrivals: 'Hourly in first week, each with 168-hour look-ahead', fleets: {}, spatial: [], temporal: [] };
for (const [mode, tracks] of Object.entries({ north, south, world })) {
  const ranks = contactRanks(tracks, 337, targets, 350);
  report.fleets[mode] = [30, 100, 500].map(count => summarize(ranks, 337, targets, count));
}
// These are the rounded table values in the article, not a delivery forecast.
assert.deepEqual(report.fleets.world.map(row => ['reachedWeek', 'day', 'week'].map(key => Math.round(row.regions.earth[key] * 100))), [[40, 9, 39], [71, 25, 72], [99, 71, 98]]);
for (const size of [3000, 6000, 12000, 24000]) {
  const points = earthTargets(size), ranks = contactRanks(world, 337, points, 350);
  report.spatial.push({ points: size, ...summarize(ranks, 337, points, 500).regions.earth });
}
const coarse = report.spatial[1], fine = report.spatial[3];
for (const key of ['day', 'week', 'everyWeek']) assert(Math.abs(coarse[key] - fine[key]) < .002);
for (const subdivisions of [1, 2, 4]) {
  const { tracks, hours } = worldwide(subdivisions), ranks = contactRanks(tracks, hours, targets, 350);
  let day = 0, week = 0, sum = 0;
  for (let i = 0; i < targets.length; i++) {
    let next = Infinity;
    for (let t = hours - 1; t >= 0; t--) {
      if (ranks[i * hours + t] <= 500) next = t;
      if (t % subdivisions || t >= 168 * subdivisions) continue;
      const wait = (next - t) / subdivisions;
      if (wait <= 24) day++;
      if (wait <= 168) week++;
      sum += Math.min(wait, 168);
    }
  }
  const denominator = targets.length * 168;
  report.temporal.push({ minutes: 60 / subdivisions, day: day / denominator, week: week / denominator, meanCapped: sum / denominator });
}
assert(Math.abs(report.temporal[0].day - report.temporal[2].day) < .001);
assert(Math.abs(report.temporal[0].meanCapped - report.temporal[2].meanCapped) < .5);
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(report, null, 2) + '\n');
console.log('Fleet table, hemisphere denominators, spatial convergence, and contact sampling verified.');
