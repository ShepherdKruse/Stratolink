import { COUNTS, contactRanks, earthTargets, pointRanks, summarize, waitingStats } from './contact-model.js';
const targets = earthTargets();
let tracks, hours, cache;
self.onmessage = ({ data }) => {
  if (data.type === 'init') {
    tracks = data.tracks; hours = data.hours; return;
  }
  const { id, mode, radius, count, location } = data;
  try {
    const key = `${mode}:${radius}`;
    if (cache?.key !== key) {
      const ranks = contactRanks(tracks[mode], hours, targets, radius);
      cache = { key, ranks, curves: COUNTS.map(n => summarize(ranks, hours, targets, n)) };
    }
    const selected = summarize(cache.ranks, hours, targets, count, true);
    const localRanks = pointRanks(tracks[mode], hours, location.lat, location.lon, radius);
    const local = waitingStats(localRanks, count, { hours });
    const localCurves = COUNTS.map(n => ({ count: n, ...waitingStats(localRanks, n, { hours }) }));
    const contacts = Array.from(localRanks, rank => rank <= count);
    self.postMessage({ id, selected, curves: cache.curves, local, localCurves, contacts });
  } catch {
    self.postMessage({ id, error: 'Coverage calculation could not finish.' });
  }
};
