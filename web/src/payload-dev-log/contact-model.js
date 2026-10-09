// Contact opportunity only: no radio, power, retry, or backhaul model.
export const EARTH_KM = 6371;
export const COUNTS = [1, 10, 30, 50, 100, 200, 300, 500];
const radians = Math.PI / 180;
const missing = 65535;

export function vector(lat, lon) {
  lat *= radians; lon *= radians;
  return [Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat)];
}

export function earthTargets(count = 6000) {
  return Array.from({ length: count }, (_, i) => {
    const z = 1 - 2 * (i + .5) / count;
    const lon = ((i * 180 * (3 - Math.sqrt(5)) + 180) % 360) - 180;
    const lat = Math.asin(z) / radians;
    return { lat, lon, xyz: vector(lat, lon) };
  });
}

// Store the first balloon in the nested fleet that reaches each target/hour.
// A latitude/longitude grid prunes candidates; the final test is spherical.
export function contactRanks(tracks, hours, targets, radius) {
  const ranks = new Uint16Array(targets.length * hours).fill(missing);
  const cells = Array.from({ length: 36 * 72 }, () => []);
  targets.forEach((p, i) => cells[Math.min(35, Math.floor((p.lat + 90) / 5)) * 72 + Math.floor((p.lon + 180) / 5)].push(i));
  const angle = radius / EARTH_KM, threshold = Math.cos(angle), latitudeSpan = angle / radians;
  const count = tracks.length / (hours * 2);
  for (let k = 0; k < count; k++) {
    for (let t = 0; t < hours; t++) {
      const offset = (k * hours + t) * 2;
      const lat = tracks[offset], lon = tracks[offset + 1], xyz = vector(lat, lon);
      const south = Math.max(0, Math.floor((lat - latitudeSpan + 90) / 5));
      const north = Math.min(35, Math.floor((lat + latitudeSpan + 90) / 5));
      const longitudeSpan = Math.abs(lat) + latitudeSpan >= 90 ? 180 : Math.asin(Math.min(1, Math.sin(angle) / Math.cos(lat * radians))) / radians;
      const west = Math.floor((lon - longitudeSpan + 180) / 5);
      const east = Math.min(west + 71, Math.floor((lon + longitudeSpan + 180) / 5));
      for (let row = south; row <= north; row++) for (let col = west; col <= east; col++) {
        for (const i of cells[row * 72 + ((col % 72) + 72) % 72]) {
          const index = i * hours + t;
          if (ranks[index] !== missing) continue;
          const p = targets[i].xyz;
          if (p[0] * xyz[0] + p[1] * xyz[1] + p[2] * xyz[2] >= threshold) ranks[index] = k + 1;
        }
      }
    }
  }
  return ranks;
}

export function pointRanks(tracks, hours, lat, lon, radius) {
  const ranks = new Uint16Array(hours).fill(missing), p = vector(lat, lon), threshold = Math.cos(radius / EARTH_KM);
  for (let k = 0; k < tracks.length / (hours * 2); k++) for (let t = 0; t < hours; t++) {
    if (ranks[t] !== missing) continue;
    const offset = (k * hours + t) * 2, b = vector(tracks[offset], tracks[offset + 1]);
    if (p[0] * b[0] + p[1] * b[1] + p[2] * b[2] >= threshold) ranks[t] = k + 1;
  }
  return ranks;
}

// Every arrival has a complete look-ahead window. Unreached arrivals stay in
// the denominator and contribute the cap to restricted mean waiting time.
export function waitingStats(ranks, count, { offset = 0, hours = 337, arrivals = 168, cap = 168 } = {}) {
  if (hours < arrivals + cap) throw new RangeError('Incomplete observation window');
  let next = Infinity, totalWait = 0, day = 0, threeDays = 0, week = 0, first = Infinity;
  const waits = new Uint16Array(arrivals);
  for (let t = hours - 1; t >= 0; t--) {
    if (ranks[offset + t] <= count) { next = t; first = t; }
    if (t >= arrivals) continue;
    const wait = next - t;
    waits[t] = wait <= cap ? wait : cap + 1;
    totalWait += Math.min(wait, cap);
    if (wait <= 24) day++;
    if (wait <= 72) threeDays++;
    if (wait <= cap) week++;
  }
  const sorted = waits.slice().sort();
  return {
    initial: ranks[offset] <= count,
    reachedWeek: first <= 168,
    reachedFortnight: Number.isFinite(first),
    day: day / arrivals, threeDays: threeDays / arrivals, week: week / arrivals,
    everyWeek: week === arrivals, meanCapped: totalWait / arrivals,
    median: sorted[Math.ceil(arrivals * .5) - 1], p90: sorted[Math.ceil(arrivals * .9) - 1],
    waits,
  };
}

const fields = ['initial', 'reachedWeek', 'reachedFortnight', 'day', 'threeDays', 'week', 'everyWeek', 'meanCapped'];
export function summarize(ranks, hours, targets, count, includeMap = false) {
  const regions = Object.fromEntries(['earth', 'north', 'south'].map(key => [key, { count: 0, ...Object.fromEntries(fields.map(k => [k, 0])) }]));
  const map = includeMap ? [] : undefined;
  targets.forEach((p, i) => {
    const s = waitingStats(ranks, count, { offset: i * hours, hours });
    for (const region of [regions.earth, p.lat >= 0 ? regions.north : regions.south]) {
      region.count++;
      fields.forEach(key => { region[key] += Number(s[key]); });
    }
    if (map) map.push([p.lat, p.lon, s.meanCapped, s.reachedFortnight ? 1 : 0]);
  });
  for (const region of Object.values(regions)) fields.forEach(key => { region[key] = region.count ? region[key] / region.count : 0; });
  return { count, regions, map };
}
