/* Interactive figures for "Drawing the path between packets". Same conventions as the
 * payload dev log's charts: a chart card with a heading, canvas maps on the muted
 * paper with the wind drawn across them, range controls with live outputs, a readout
 * line, keyboard access, and animations that pause off-screen or under
 * prefers-reduced-motion. Data comes from the bundle in /assets/wind-path, built by
 * scripts/blog/wind_path_figure_data.py and wind_path_background_winds.py. */
import { colors, heatColor, observeChartSize } from '../payload-dev-log/charts.js';

const ASSETS = '/assets/wind-path';
const INK = '#292927', PAPER = '#eeeee9', GRID = '#d7d8d1', COAST = '#959c93', CREAM = '#f6f4ef';
const RED = colors[0], BLUE = colors[4], GRAY = '#6f716b';
const rad = Math.PI / 180, R = 6371;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const fmt = (n, p = 0) => Number(n).toLocaleString('en-US', { maximumFractionDigits: p });
const utc = ms => new Date(ms).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }) + ' UTC';
const place = (lat, lon) => `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`;
const ago = hours => hours < 1 ? 'just now' : hours < 48 ? `${fmt(hours, 1)} hours ago` : `${fmt(hours / 24, 1)} days ago`;
const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
const toward = (u, v) => COMPASS[Math.round(((Math.atan2(u, v) / rad + 360) % 360) / 22.5) % 16];
function km(lat1, lon1, lat2, lon2) {
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lon2 - lon1) * rad / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

const cache = new Map();
function load(file) {
  const url = file.startsWith('/') ? file : `${ASSETS}/${file}`;
  if (!cache.has(url)) cache.set(url, fetch(url).then(response => {
    if (!response.ok) throw new Error('Figure data unavailable');
    return url.endsWith('.bin') ? response.arrayBuffer() : response.json();
  }).catch(error => { cache.delete(url); throw error; }));
  return cache.get(url);
}

/* ── map on canvas ──────────────────────────────────────────────────────────── */
const ATLANTIC = { lon0: -128, lon1: 8, lat0: 12, lat1: 58 };
const GAP_VIEW = { lon0: -112, lon1: 0, lat0: 14, lat1: 56 };
const WIDE_VIEW = { lon0: -125, lon1: 35, lat0: 8, lat1: 68 };
const WORLD = { lon0: -30, lon1: 330, lat0: -12, lat1: 78, wrap: true };

function createMap(bounds, label, aspect) {
  const canvas = document.createElement('canvas');
  canvas.className = 'fleet-map'; canvas.tabIndex = 0; canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', label);
  const ctx = canvas.getContext('2d');
  const m = { canvas, ctx, bounds: { ...bounds }, width: 0, height: 0 };
  const span = () => m.bounds.lon1 - m.bounds.lon0;
  m.lon = lon => m.bounds.wrap ? m.bounds.lon0 + (((lon - m.bounds.lon0) % 360) + 360) % 360 : lon;
  m.x = lon => (m.lon(lon) - m.bounds.lon0) / span() * m.width;
  m.y = lat => (m.bounds.lat1 - lat) / (m.bounds.lat1 - m.bounds.lat0) * m.height;
  m.point = (lat, lon) => [m.x(lon), m.y(lat)];
  m.inView = (lat, lon) => lat >= m.bounds.lat0 && lat <= m.bounds.lat1 && m.lon(lon) >= m.bounds.lon0 && m.lon(lon) <= m.bounds.lon1;
  m.resize = width => {
    const b = m.bounds, height = Math.round(width * (aspect ?? (b.lat1 - b.lat0) / ((b.lon1 - b.lon0) * Math.cos((b.lat0 + b.lat1) / 2 * rad))));
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = width * dpr; canvas.height = height * dpr; canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); m.width = width; m.height = height;
  };
  m.line = (pts, { color = INK, width = 1, alpha = 1, dash, latFirst = true, end } = {}) => {
    ctx.beginPath(); let px;
    const n = end === undefined ? pts.length : Math.min(pts.length, end);
    for (let k = 0; k < n; k++) {
      const p = pts[k], lat = latFirst ? p[0] : p[1], lon = latFirst ? p[1] : p[0], x = m.x(lon), y = m.y(lat);
      if (px === undefined || Math.abs(x - px) > m.width / 2) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      px = x;
    }
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.globalAlpha = alpha; ctx.setLineDash(dash || []); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
  };
  m.dot = (lat, lon, r, fill, stroke, lineWidth = 1.5, alpha = 1) => {
    const [x, y] = m.point(lat, lon);
    ctx.globalAlpha = alpha; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth; ctx.stroke(); }
    ctx.globalAlpha = 1;
  };
  m.label = (lat, lon, text, dx = 8, dy = 4, color = INK) => {
    const [x, y] = m.point(lat, lon);
    ctx.fillStyle = color; ctx.font = '11px Helvetica, Arial, sans-serif'; ctx.textAlign = dx < 0 ? 'right' : 'left'; ctx.fillText(text, x + dx, y + dy);
  };
  m.arrow = (lat, lon, u, v, { alpha = .36, width = 1, scale = 3.2, max = 12 } = {}) => {
    const [x, y] = m.point(lat, lon), speed = Math.hypot(u, v), len = clamp(speed / scale, 1.5, max);
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(-v, u)); ctx.strokeStyle = `rgb(${heatColor(speed / 65).join(',')})`; ctx.globalAlpha = alpha; ctx.lineWidth = width;
    ctx.beginPath(); ctx.moveTo(-len / 2, 0); ctx.lineTo(len / 2, 0); ctx.lineTo(len / 2 - 2.2, -1.9); ctx.moveTo(len / 2, 0); ctx.lineTo(len / 2 - 2.2, 1.9); ctx.stroke(); ctx.restore();
  };
  m.rect = (lat0, lon0, h, w, { color = BLUE, alpha = 1, width = 1, fill } = {}) => {
    const [x0, y1] = m.point(lat0, lon0), [x1, y0] = m.point(lat0 + h, lon0 + w);
    ctx.globalAlpha = alpha; ctx.strokeStyle = color; ctx.lineWidth = width; ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    if (fill) { ctx.globalAlpha = fill; ctx.fillStyle = color; ctx.fillRect(x0, y0, x1 - x0, y1 - y0); }
    ctx.globalAlpha = 1;
  };
  m.base = (coast, step = 10) => {
    const b = m.bounds;
    ctx.clearRect(0, 0, m.width, m.height); ctx.fillStyle = PAPER; ctx.fillRect(0, 0, m.width, m.height);
    for (let lat = Math.ceil(b.lat0 / step) * step; lat < b.lat1; lat += step) m.line([[lat, b.lon0], [lat, b.lon1 - 1e-6]], { color: GRID, width: .6 });
    for (let lon = Math.ceil(b.lon0 / step) * step; lon < b.lon1; lon += step) m.line([[b.lat0, lon], [b.lat1, lon]], { color: GRID, width: .6 });
    for (const c of coast) m.line(c, { color: COAST, width: .7, alpha: .8, latFirst: false });
  };
  m.pointer = event => {
    const b = canvas.getBoundingClientRect();
    return [(event.clientX - b.left) * m.width / b.width, (event.clientY - b.top) * m.height / b.height];
  };
  return m;
}

/* ── the coarse wind field drawn across the maps ────────────────────────────── */
let windPending;
function windField() {
  windPending ??= Promise.all([load('winds.json'), load('winds.bin')]).then(([meta, buffer]) => {
    const data = new Int8Array(buffer), { nLat, nLon, n } = meta, per = nLat * nLon * 2;
    const field = { ...meta,
      /* u,v at grid cell (i,j), linearly interpolated between the two slices around tMs */
      uv(tMs, i, j) {
        const s = clamp((tMs - meta.t0Ms) / meta.stepMs, 0, n - 1), a = Math.floor(s), b = Math.min(n - 1, a + 1), t = s - a;
        const ia = a * per + (i * nLon + j) * 2, ib = b * per + (i * nLon + j) * 2;
        return [data[ia] + (data[ib] - data[ia]) * t, data[ia + 1] + (data[ib + 1] - data[ia + 1]) * t];
      },
      /* u,v at a point, bilinear in the grid */
      at(tMs, lat, lon) {
        const fi = clamp((lat - meta.lat0) / meta.dLat, 0, nLat - 1), fj = clamp((lon - meta.lon0) / meta.dLon, 0, nLon - 1);
        const i0 = Math.floor(fi), j0 = Math.floor(fj), i1 = Math.min(nLat - 1, i0 + 1), j1 = Math.min(nLon - 1, j0 + 1), di = fi - i0, dj = fj - j0;
        const p00 = field.uv(tMs, i0, j0), p01 = field.uv(tMs, i0, j1), p10 = field.uv(tMs, i1, j0), p11 = field.uv(tMs, i1, j1);
        return [lerp(lerp(p00[0], p01[0], dj), lerp(p10[0], p11[0], dj), di), lerp(lerp(p00[1], p01[1], dj), lerp(p10[1], p11[1], dj), di)];
      },
      draw(map, tMs, options) {
        for (let i = 0; i < nLat; i++) for (let j = 0; j < nLon; j++) {
          const lat = meta.lat0 + i * meta.dLat, lon = meta.lon0 + j * meta.dLon;
          if (!map.inView(lat, lon)) continue;
          const [u, v] = field.uv(tMs, i, j); map.arrow(lat, lon, u, v, options);
        }
      },
    };
    return field;
  }).catch(error => { windPending = undefined; throw error; });
  return windPending;
}

/* ── the posterior draws (particle clouds) of every long gap ────────────────── */
let cloudPending;
function clouds() {
  cloudPending ??= Promise.all([load('posterior.json'), load('posterior.bin'), load('clouds.json'), load('clouds.bin')]).then(([p, pbuf, c, cbuf]) => {
    const pos = new Int16Array(pbuf), cpos = new Int16Array(cbuf);
    const accessor = (arr, off, steps) => (i, s) => {
      const a = Math.floor(s), b = Math.min(steps - 1, a + 1), t = s - a, ia = off + (i * steps + a) * 2, ib = off + (i * steps + b) * 2;
      return [(arr[ia] + (arr[ib] - arr[ia]) * t) / 100, (arr[ia + 1] + (arr[ib + 1] - arr[ia + 1]) * t) / 100];
    };
    const big = { tA: p.tA, tB: p.tA + p.hours * 3600000, hours: p.hours, n: p.n, steps: p.steps, at: accessor(pos, 0, p.steps) };
    const list = [big, ...c.gaps.map(g => ({ ...g, at: accessor(cpos, g.off, g.steps) }))].sort((a, b) => a.tA - b.tA);
    for (const g of list) { g.hoursPerStep = g.hours / (g.steps - 1); g.path = (i, from, to) => { const out = []; for (let s = from; s <= to; s++) out.push(g.at(i, s)); return out; }; }
    return { list, posterior: { ...p, at: big.at, path: big.path, hoursPerStep: big.hoursPerStep }, find: tMs => list.find(g => tMs >= g.tA && tMs <= g.tB) };
  }).catch(error => { cloudPending = undefined; throw error; });
  return cloudPending;
}

/* Draw a particle cloud at fractional step s: 12-hour tails and a dot per draw. */
function drawCloud(map, g, s, { color = BLUE, tail = true, alpha = 1 } = {}) {
  const back = Math.max(0, s - 12 / g.hoursPerStep);
  if (tail) for (let i = 0; i < g.n; i++) map.line([g.at(i, back), ...g.path(i, Math.ceil(back), Math.floor(s)), g.at(i, s)], { color, width: .8, alpha: .18 * alpha });
  for (let i = 0; i < g.n; i++) { const q = g.at(i, s); map.dot(q[0], q[1], 1.7, color, null, 1, .8 * alpha); }
}

/* ── shared chrome ──────────────────────────────────────────────────────────── */
const heading = (title, subtitle, play = true) => `<div class="chart-heading fleet-heading">${title}<div class="fleet-heading-controls"><span>${subtitle}</span>${play ? '<button type="button" class="fleet-play" data-play aria-pressed="false">Play</button>' : ''}</div></div>`;
const key = (text, color, shape = 'bar') => `<span class="chart-key"><i class="key-${shape}" style="background:${color}"></i>${text}</span>`;
const windKey = () => `<span class="chart-key"><i class="spectrum-key"></i>Wind, slow to fast</span>`;
const slider = (label, max, step, aria, value = 0) => `<div class="fleet-controls"><label class="fleet-time">${label} <output>${value}</output><input type="range" min="0" max="${max}" value="${value}" step="${step}" aria-label="${aria}"></label></div>`;
const footer = source => `<div class="fleet-map-footer"><span class="fleet-date"></span><span class="fleet-source">${source}</span></div>`;

/* Play/pause loop that only runs while the figure is on screen and the page visible;
 * autoplays unless the reader prefers reduced motion. `advance(dt)` moves the state. */
function player(host, signal, advance) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const button = host.querySelector('[data-play]');
  let playing = false, visible = false, raf = 0, last = 0;
  function tick(t) { raf = 0; if (!playing || !visible || document.hidden) return; if (last) advance(Math.min(t - last, 100)); last = t; raf = requestAnimationFrame(tick); }
  function update() {
    last = 0;
    if (playing && visible && !document.hidden && !raf) raf = requestAnimationFrame(tick);
    if (!playing && raf) { cancelAnimationFrame(raf); raf = 0; }
    if (button) { button.textContent = playing ? 'Pause' : 'Play'; button.setAttribute('aria-pressed', String(playing)); }
  }
  const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; if (!visible && raf) { cancelAnimationFrame(raf); raf = 0; } update(); }, { threshold: .1 });
  observer.observe(host);
  document.addEventListener('visibilitychange', update, { signal });
  reduced.addEventListener('change', () => { if (reduced.matches) { playing = false; update(); } }, { signal });
  signal.addEventListener('abort', () => { observer.disconnect(); cancelAnimationFrame(raf); }, { once: true });
  const api = { get playing() { return playing; }, set(value) { playing = value; update(); }, toggle() { playing = !playing; update(); } };
  if (button) button.onclick = () => api.toggle();
  api.set(!reduced.matches);
  return api;
}

/* A range input that pauses the player while it is dragged and resumes afterwards. */
function bindSlider(input, play, onInput) {
  let resume = false;
  input.oninput = () => { if (play.playing) { resume = true; play.set(false); } onInput(+input.value); };
  input.onchange = () => { if (resume) play.set(true); resume = false; };
}
function keys(canvas, play, step) {
  canvas.onkeydown = event => {
    if (event.key === ' ') { event.preventDefault(); play.toggle(); }
    else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); play.set(false); step(event.key === 'ArrowRight' ? 1 : -1); }
  };
}
function sizeCanvas(canvas, ctx, width, height) {
  const dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.width = width * dpr; canvas.height = height * dpr; canvas.style.width = `${width}px`; canvas.style.height = `${height}px`; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

/* The flight's long gaps (over six hours) from the fixes, in minutes since launch. */
function longGaps(fixes) {
  const gaps = [];
  for (let i = 1; i < fixes.length; i++) if (fixes[i][0] - fixes[i - 1][0] >= 360) gaps.push([fixes[i - 1][0], fixes[i][0]]);
  return gaps;
}
/* The track split into the stretches between packets (ink) and the long gaps (red),
 * each as its minutes-since-launch and its [lat, lon] points. */
function trackSegments(track, gaps) {
  const segments = []; let current;
  for (const [t, lat, lon] of track) {
    const dark = gaps.some(([a, b]) => t > a && t < b);
    if (!current || current.dark !== dark) {
      current = { dark, times: current ? [current.times.at(-1)] : [], pts: current ? [current.pts.at(-1)] : [] };
      segments.push(current);
    }
    current.times.push(t); current.pts.push([lat, lon]);
  }
  return segments;
}
/* Draw the track up to `minutes` since launch. */
function drawTrack(map, segments, minutes) {
  for (const seg of segments) {
    const n = seg.times.findIndex(t => t > minutes);
    if (n === 0) continue;
    map.line(seg.pts, { color: seg.dark ? RED : INK, width: seg.dark ? 1.8 : 1.4, alpha: seg.dark ? .85 : 1, end: n < 0 ? undefined : n });
  }
}

/* ── 1. the flight, replayed ───────────────────────────────────────────────── */
async function replay(host, signal) {
  const [flight, coast, wind] = await Promise.all([load('flight.json'), load('coast-atlantic.json'), windField()]);
  if (signal.aborted) return;
  const { t0, fixes, end } = flight, distinct = fixes.filter(f => f[3]), gaps = longGaps(fixes), segments = trackSegments(flight.track, gaps);
  const dark = gaps.reduce((s, [a, b]) => s + b - a, 0);
  host.innerHTML = `${heading('Stratolink 3, replayed', `GFS winds at ${fmt(wind.levelHpa)} hPa`)}
    <div class="fleet-metrics contact-metrics"><span><b>${fixes.length}</b>packets with a position</span><span><b>${distinct.length}</b>distinct positions</span><span><b>${fmt(dark / 60)} h</b>of ${fmt(end / 60)} without a packet for over six hours</span></div>
    <div class="chart-legend">${windKey()}${key('Received position', INK, 'dot')}${key('The drawn line through the gaps', RED)}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${footer('NOAA GFS, May 2026')}
    <canvas class="packet-strip" role="img" aria-label="Timeline of received positions over the flight, with gaps longer than six hours shaded"></canvas>
    <div class="waterfall-axis"><span>May 17</span><span>May 23</span><span>May 29</span></div>
    ${slider('Flight hour', end, 10, 'Minutes since launch')}
    <output class="chart-readout"></output>`;
  const map = createMap(ATLANTIC, 'Stratolink 3 replayed over the North Atlantic: received positions, the wind field, and the reconstructed line through the gaps. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const strip = host.querySelector('.packet-strip'), sctx = strip.getContext('2d');
  const input = host.querySelector('input'), output = host.querySelector('.fleet-time output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date');
  let cursor = 0, width = 0;
  function draw() {
    if (!width) return;
    const tMs = t0 + cursor * 60000;
    map.base(coast);
    wind.draw(map, tMs, { alpha: .34 });
    drawTrack(map, segments, cursor);
    const g = gaps.find(([a, b]) => cursor > a && cursor < b);
    for (const [t, lat, lon, isDistinct] of fixes) if (t <= cursor) map.dot(lat, lon, isDistinct ? 2.2 : 1.5, isDistinct ? INK : '#a3a59e');
    const last = distinct.filter(f => f[0] <= cursor).at(-1);
    if (last) map.dot(last[1], last[2], g ? 5 : 6, g ? null : CREAM, INK, g ? 1.2 : 1.6);
    sctx.clearRect(0, 0, width, 30); sctx.fillStyle = '#e3e4dd'; sctx.fillRect(0, 6, width, 16);
    sctx.fillStyle = 'rgba(50,140,179,.22)';
    for (const [a, b] of gaps) sctx.fillRect(a / end * width, 6, (b - a) / end * width, 16);
    for (const [t, , , isDistinct] of fixes) { sctx.fillStyle = isDistinct ? INK : '#b3b5ae'; sctx.fillRect(t / end * width, 6, Math.max(.8, width / 1500), 16); }
    sctx.fillStyle = INK; sctx.fillRect(cursor / end * width - 1, 0, 2, 29);
    input.value = cursor; output.textContent = fmt(cursor / 60, 1); date.textContent = utc(tMs);
    const since = last ? (cursor - last[0]) / 60 : 0;
    read.textContent = g
      ? `${fmt(since)} h without a packet / the red line is the reconstruction the dashboard draws`
      : last ? `last packet ${ago(since)} from ${place(last[1], last[2])}` : 'before launch';
  }
  const play = player(host, signal, dt => { cursor += dt * .6; if (cursor > end + 1500) cursor = 0; draw(); });
  bindSlider(input, play, value => { cursor = value; draw(); });
  keys(map.canvas, play, dir => { cursor = clamp(Math.min(cursor, end) + dir * 360, 0, end); draw(); });
  /* Scrub by pressing on the timeline and dragging; hovering does nothing. */
  const scrub = event => { const b = strip.getBoundingClientRect(); cursor = clamp((event.clientX - b.left) / b.width * end, 0, end); draw(); };
  strip.onpointerdown = event => { strip.setPointerCapture(event.pointerId); play.set(false); scrub(event); };
  strip.onpointermove = event => { if (strip.hasPointerCapture(event.pointerId)) scrub(event); };
  strip.onpointerup = strip.onpointercancel = event => { if (strip.hasPointerCapture(event.pointerId)) strip.releasePointerCapture(event.pointerId); };
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event), tMs = t0 + Math.min(cursor, end) * 60000;
    const b = map.bounds, lat = b.lat1 - y / map.height * (b.lat1 - b.lat0), lon = b.lon0 + x / map.width * (b.lon1 - b.lon0);
    const [u, v] = wind.at(tMs, lat, lon);
    hover.hidden = false; hover.textContent = `${place(lat, lon)} / wind ${fmt(Math.hypot(u, v))} m/s toward ${toward(u, v)}`;
  };
  map.canvas.onpointerleave = () => { hover.hidden = true; };
  observeChartSize(host, () => { width = host.clientWidth - 32; map.resize(width); sizeCanvas(strip, sctx, width, 30); draw(); }, signal);
}

/* ── 2. riding the tube ────────────────────────────────────────────────────── */
async function tube(host, signal) {
  const [meta, buffer, coast, flight, cloud, fmeta, fbuf, obuf, pbuf] = await Promise.all([load('tube.json'), load('tube.bin'), load('coast-atlantic.json'), load('flight.json'), clouds(), load('filters.json'), load('filters.bin'), load('tube-outer.bin'), load('tube-patch.bin')]);
  if (signal.aborted) return;
  const fpos = new Int16Array(fbuf), coarse = new Int8Array(obuf), patches = new Int8Array(pbuf);
  /* The filters' own clouds (every 3 h): the forward one from the fix before a
   * long gap, the backward one from the fix after it. The box is sized for them. */
  const filterAt = (t, dir) => { let best = null; for (const sn of fmeta.snaps) if (sn.dir === dir && Math.abs(sn.t - t) <= 1.6 * 3600000 && (!best || Math.abs(sn.t - t) < Math.abs(best.t - t))) best = sn; return best; };
  const fine = new Int8Array(buffer), gaps = longGaps(flight.fixes), segments = trackSegments(flight.track, gaps);
  /* Ride from launch to the last fix: the slices the reconstruction actually reads
   * (the cube also holds a lead-in slice and the pre-launch days on the ground). */
  const first = meta.slices.findIndex(b => b.pos), lastIdx = meta.slices.findLastIndex(b => b.pos);
  const ride = meta.slices.slice(Math.max(0, first), lastIdx + 1), last = ride.length - 1, stepMs = ride[1].t - ride[0].t;
  /* One fixed view that holds every box on the ride: nothing zooms or pans. */
  const view = ride.reduce((v, b) => ({ lat0: Math.min(v.lat0, b.lat0 - 2), lat1: Math.max(v.lat1, b.lat0 + b.h + 2), lon0: Math.min(v.lon0, b.lon0 - 2), lon1: Math.max(v.lon1, b.lon0 + b.w + 2) }), { lat0: 90, lat1: -90, lon0: 360, lon1: -360 });
  host.innerHTML = `${heading('Riding the tube', 'one box of 0.25° winds per 3-hour slice')}
    <div class="chart-legend">${key('This slice’s box', BLUE)}${windKey()}<span class="chart-key"><i class="spectrum-key" style="opacity:.35"></i>Coarse 1.5° winds around it</span>${key('Forward particles', BLUE, 'dot')}${key('Backward particles', RED, 'dot')}${key('Bridges', INK, 'dot')}${key('Reconstructed track', INK)}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${footer('')}
    <div class="tube-inset">
      <figure><canvas data-inset="fine" role="img" aria-label="Every 0.25° wind vector the box stores in a 3° square around the balloon"></canvas><figcaption>In the box: 0.25° winds, 3° around the balloon</figcaption></figure>
      <figure><canvas data-inset="coarse" role="img" aria-label="The same square read from the coarse 1.5° field"></canvas><figcaption>The same square in the coarse field: 1.5° winds</figcaption></figure>
    </div>
    ${slider('Slice', last, .05, 'Reconstruction cube time slice')}
    <output class="chart-readout"></output>`;
  const insets = [...host.querySelectorAll('[data-inset]')].map(c => ({ canvas: c, ctx: c.getContext('2d'), kind: c.dataset.inset, size: 0 }));
  /* One inset: a 3° square around the balloon at each field's REAL density — the
   * box's every 0.25° vector (13 × 13), or the coarse field's own 1.5° grid points
   * (a handful) — with one length scale; the balloon is the ring. */
  function drawInset(inset, sl, pos) {
    const { ctx, size, kind } = inset;
    if (!size) return;
    ctx.clearRect(0, 0, size, size); ctx.fillStyle = PAPER; ctx.fillRect(0, 0, size, size);
    const pt = sl && sl.patch;
    if (!pt || (kind === 'coarse' && !pt.coarse)) { ctx.fillStyle = '#8a8c86'; ctx.font = '12px Helvetica, Arial, sans-serif'; ctx.textAlign = 'center'; ctx.fillText('before launch', size / 2, size / 2); return; }
    const n = pt.n, cell = size / n, span = (n - 1) * pt.step;
    const px = (lat, lon) => [((lon - pt.lon0) / span) * (size - cell) + cell / 2, size - (((lat - pt.lat0) / span) * (size - cell) + cell / 2)];
    const arrow = (lat, lon, u, v) => {
      const [x, y] = px(lat, lon), speed = Math.hypot(u, v), len = clamp(speed / 50 * cell * 1.1, 2, cell * 1.1);
      ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(-v, u)); ctx.strokeStyle = `rgb(${heatColor(speed / 65).join(',')})`; ctx.lineWidth = kind === 'fine' ? 1.2 : 1.8;
      ctx.beginPath(); ctx.moveTo(-len / 2, 0); ctx.lineTo(len / 2, 0); ctx.lineTo(len / 2 - 2.6, -2.2); ctx.moveTo(len / 2, 0); ctx.lineTo(len / 2 - 2.6, 2.2); ctx.stroke(); ctx.restore();
      ctx.beginPath(); ctx.arc(x, y, kind === 'fine' ? .9 : 2, 0, Math.PI * 2); ctx.fillStyle = '#8a8c86'; ctx.fill();   // the grid point
    };
    if (kind === 'fine') {
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const o = pt.off + (i * n + j) * 2; arrow(pt.lat0 + i * pt.step, pt.lon0 + j * pt.step, patches[o], patches[o + 1]); }
    } else {
      for (const [lat, lon, u, v] of pt.coarse) arrow(lat, lon, u, v);
    }
    if (pos) {
      const [x, y] = px(pos[0], pos[1]);
      ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.strokeStyle = INK; ctx.lineWidth = 1.8; ctx.stroke();
    }
  }
  const map = createMap(view, 'The flight with the reconstruction’s wind box for each three-hour slice moving along it, the winds inside the box, and the possible positions during the gaps. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('.fleet-time output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date'), source = host.querySelector('.fleet-source');
  let at = 0, shown = [], coarseShown = [];
  const gapHours = t => { const m = (t - flight.t0) / 60000; const g = gaps.find(([a, b]) => m >= a && m <= b); return g ? (g[1] - g[0]) / 60 : 0; };
  /* The winds of one slice, thinned to at least 1.25° and ~8 px apart so small
   * and large boxes, and phone and desktop widths, read alike (the coarse field
   * around the box is drawn sparser and paler). */
  function sliceArrows(b) {
    const minDeg = Math.max(1.25, 8 / (map.width / (view.lon1 - view.lon0)));
    const out = [], skip = Math.max(1, Math.ceil(minDeg / b.aStep - 1e-9));
    /* Start on the global lattice of multiples of the drawn spacing, so arrows
     * stay put from frame to frame instead of shifting with each box's origin. */
    const first = (o) => ((Math.round(-o / b.aStep) % skip) + skip) % skip;
    const iS = first(b.aLat0 ?? b.lat0), jS = first(b.aLon0 ?? b.lon0);
    for (let i = iS; i < b.aLat; i += skip) for (let j = jS; j < b.aLon; j += skip) {
      const o = b.off + (i * b.aLon + j) * 2, u = fine[o], v = fine[o + 1];
      out.push({ lat: (b.aLat0 ?? b.lat0) + i * b.aStep, lon: (b.aLon0 ?? b.lon0) + j * b.aStep, u, v, speed: Math.hypot(u, v) });
    }
    return out;
  }
  /* The coarse outer field of one slice (stored thinned to ~3°). */
  function coarseArrows(b) {
    const o = b.outer, out = [];
    if (!o) return out;
    const minDeg = Math.max(3, 18 / (map.width / (view.lon1 - view.lon0))), skip = Math.max(1, Math.ceil(minDeg / o.aStep - 1e-9));
    const first = (v) => ((Math.round(-v / o.aStep) % skip) + skip) % skip;   // stay on a fixed global lattice
    for (let i = first(o.lat0); i < o.aLat; i += skip) for (let j = first(o.lon0); j < o.aLon; j += skip) {
      const k = o.off + (i * o.aLon + j) * 2, u = coarse[k], v = coarse[k + 1];
      out.push({ lat: o.lat0 + i * o.aStep, lon: o.lon0 + j * o.aStep, u, v, speed: Math.hypot(u, v) });
    }
    return out;
  }
  const inBox = (b, lat, lon) => lat >= b.lat0 && lat <= b.lat0 + b.h && lon >= b.lon0 && lon <= b.lon0 + b.w;
  function draw() {
    if (!map.width) return;
    const k = clamp(Math.floor(at), 0, last), f = k < last ? at - k : 0, a = ride[k], b = ride[Math.min(last, k + 1)];
    const t = a.t + f * stepMs, minutes = (t - flight.t0) / 60000;
    /* The box glides between slices; its winds cross-fade from one slice to the next. */
    const box = { lat0: lerp(a.lat0, b.lat0, f), lon0: lerp(a.lon0, b.lon0, f), h: lerp(a.h, b.h, f), w: lerp(a.w, b.w, f) };
    map.base(coast, 10);
    /* Around the box: the cube's coarse 1.5° winds, pale and sparse, cross-faded like the box's. */
    const fadeC = clamp((f - .7) / .3, 0, 1);
    for (const [sl, al] of [[a, 1 - fadeC], [b, fadeC]]) {
      if (al <= 0) continue;
      for (const q of coarseArrows(sl)) if (map.inView(q.lat, q.lon) && !inBox(box, q.lat, q.lon)) map.arrow(q.lat, q.lon, q.u, q.v, { alpha: .3 * al, width: .8, scale: 3.4, max: 10 });
    }
    coarseShown = coarseArrows(fadeC < .5 ? a : b);
    for (let back = 4; back >= 1; back--) { const g = ride[k - back]; if (g) map.rect(g.lat0, g.lon0, g.h, g.w, { alpha: .05 * (5 - back), width: .8 }); }
    map.rect(box.lat0, box.lon0, box.h, box.w, { alpha: .9, width: 1.5, fill: .05 });
    /* Hold each slice's winds, then fade to the next over the last 30 % of the step. */
    const fade = clamp((f - .7) / .3, 0, 1);
    const arrowsA = sliceArrows(a), arrowsB = fade > 0 ? sliceArrows(b) : [];
    for (const q of arrowsA) if (inBox(box, q.lat, q.lon)) map.arrow(q.lat, q.lon, q.u, q.v, { alpha: .85 * (1 - fade), width: 1.1, scale: 3, max: 11 });
    for (const q of arrowsB) if (inBox(box, q.lat, q.lon)) map.arrow(q.lat, q.lon, q.u, q.v, { alpha: .85 * fade, width: 1.1, scale: 3, max: 11 });
    shown = fade < .5 ? arrowsA : arrowsB;
    drawTrack(map, segments, minutes);
    for (const [dir, color] of [[1, BLUE], [-1, RED]]) {
      const sn = filterAt(t, dir);
      if (sn) for (let i = 0; i < sn.n; i++) { const o = sn.off + i * 2; map.dot(fpos[o] / 100, fpos[o + 1] / 100, 2.2, color, null, 1, .6); }
    }
    const g = cloud.find(t);
    if (g) drawCloud(map, g, (t - g.tA) / (g.tB - g.tA) * (g.steps - 1), { tail: false, color: INK, alpha: .45 });
    let pos = a.pos;
    if (pos && b.pos && f > 0) pos = [lerp(a.pos[0], b.pos[0], f), lerp(a.pos[1], b.pos[1], f)];
    if (pos && !g) map.dot(pos[0], pos[1], 4.5, CREAM, INK, 1.8);
    const ps = fadeC < .5 ? a : b;
    for (const inset of insets) drawInset(inset, ps, ps.pos);
    input.value = at; output.textContent = fmt(k + 1); date.textContent = utc(t);
    const s = f < .5 ? a : b;
    source.textContent = `box ${fmt(s.h)}° × ${fmt(s.w)}° at 0.25°, coarser 1.5° winds around it`;
    const hours = gapHours(t);
    read.textContent = `Slice ${k + 1} of ${ride.length} / ${s.wind
      ? `inside the ${fmt(hours)}-hour gap: sized by a pilot run of both clouds over this slice’s six hours; particles that stray outside ride the coarser winds`
      : 'covers the track, ±9°'}`;
  }
  const play = player(host, signal, dt => { at += dt * .005; if (at > last + 10) at = 0; draw(); });
  bindSlider(input, play, value => { at = value; draw(); });
  keys(map.canvas, play, dir => { at = clamp(Math.round(at) + dir, 0, last); draw(); });
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event), bd = map.bounds, lat = bd.lat1 - y / map.height * (bd.lat1 - bd.lat0), lon = bd.lon0 + x / map.width * (bd.lon1 - bd.lon0);
    const s = ride[clamp(Math.round(at), 0, last)];
    hover.hidden = false;
    if (!inBox(s, lat, lon) || !shown.length) {
      if (!coarseShown.length) { hover.textContent = `${place(lat, lon)} / outside the box`; return; }
      const c = coarseShown.reduce((best, p) => Math.hypot(p.lat - lat, p.lon - lon) < Math.hypot(best.lat - lat, best.lon - lon) ? p : best, coarseShown[0]);
      hover.textContent = `${place(lat, lon)} / outside the box, coarse 1.5° winds: ${fmt(c.speed)} m/s toward ${toward(c.u, c.v)}`; return;
    }
    const q = shown.reduce((best, p) => Math.hypot(p.lat - lat, p.lon - lon) < Math.hypot(best.lat - lat, best.lon - lon) ? p : best, shown[0]);
    hover.textContent = `${place(lat, lon)} / ${fmt(q.speed)} m/s toward ${toward(q.u, q.v)}`;
  };
  map.canvas.onpointerleave = () => { hover.hidden = true; };
  observeChartSize(host, () => {
    map.resize(host.clientWidth - 32);
    for (const inset of insets) { const w = Math.min(220, Math.floor((host.clientWidth - 32 - 16) / 2)); inset.size = w; sizeCanvas(inset.canvas, inset.ctx, w, w); }
    draw();
  }, signal);
}

/* ── 3. forecasting versus bridging ────────────────────────────────────────── */
async function compare(host, signal) {
  const [cloud, fo, fbuf, coast, wind] = await Promise.all([clouds(), load('forecast-only.json'), load('forecast-only.bin'), load('coast-atlantic.json'), windField()]);
  if (signal.aborted) return;
  const p = cloud.posterior, { n, steps, hours, hoursPerStep, tA } = p, fpos = new Int16Array(fbuf);
  const fat = (i, s) => {
    const a = Math.floor(s), b = Math.min(steps - 1, a + 1), t = s - a, ia = (i * steps + a) * 2, ib = (i * steps + b) * 2;
    return [(fpos[ia] + (fpos[ib] - fpos[ia]) * t) / 100, (fpos[ia + 1] + (fpos[ib + 1] - fpos[ia + 1]) * t) / 100];
  };
  host.innerHTML = `${heading('Forecasting versus bridging', `${fmt(hours)} hours, the same particles and winds`)}
    <div class="capture-tabs" role="group" aria-label="Show"><button type="button" data-show="both" aria-pressed="true">Both</button><button type="button" data-show="forecast" aria-pressed="false">Forecast from New Mexico</button><button type="button" data-show="bridge" aria-pressed="false">Bridge between the fixes</button></div>
    <div class="fleet-metrics contact-metrics"><span><b data-f>…</b>forecast: holds 90% of its particles</span><span><b data-b>…</b>bridge: holds 90% of its particles</span><span><b data-h>…</b>hours into the gap</span></div>
    <div class="chart-legend">${key('Forecast, knowing only the start', GRAY, 'dot')}${key('Bridge, knowing both ends', BLUE, 'dot')}${key('The fixes', INK, 'dot')}${windKey()}</div>
    <div class="fleet-map-stage"></div>
    ${footer('NOAA GFS at the hour shown')}
    ${slider('Gap hour', hours, .5, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(WIDE_VIEW, 'Two clouds of particles over the eight-day gap: one forecast forward from New Mexico that spreads across the Atlantic, and the bridge that also knows the fix in Spain. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('.fleet-time output'), read = host.querySelector('.chart-readout'), date = host.querySelector('.fleet-date');
  const A = p.drawn[0], B = p.drawn[steps - 1];
  let h = 0, show = 'both';
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, hours), s = hour / hoursPerStep, si = clamp(Math.round(s), 0, steps - 1), tMs = tA + hour * 3600000;
    map.base(coast);
    wind.draw(map, tMs, { alpha: .14 });
    if (show !== 'bridge') for (let i = 0; i < fo.n; i++) { const q = fat(i, s); map.dot(q[0], q[1], 2.3, GRAY, null, 1, .85); }
    if (show !== 'forecast') for (let i = 0; i < n; i++) { const q = p.at(i, s); map.dot(q[0], q[1], 2.3, BLUE, null, 1, .9); }
    map.dot(A[0], A[1], 5, CREAM, INK, 1.6); map.dot(B[0], B[1], 5, CREAM, INK, 1.6);
    map.label(A[0], A[1], 'May 19', 9, 14); map.label(B[0], B[1], 'May 28', -9, 14);
    host.querySelector('[data-f]').textContent = `${fmt(fo.stats[si].r90)} km`;
    host.querySelector('[data-b]').textContent = `${fmt(p.stats[si].r90)} km`;
    host.querySelector('[data-h]').textContent = fmt(hour);
    input.value = hour; output.textContent = fmt(hour); date.textContent = utc(tMs);
    read.textContent = hour >= hours - .5
      ? `at the end the forecast’s particles are a median ${fmt(fo.endToB.median)} km from where the balloon was, and ${fmt(fo.endToB.within300 * 100, 1)}% are within 300 km; every bridge ends on the fix`
      : 'the forecast only knows where the balloon started; the bridge also knows where it was 201 hours later';
  }
  host.querySelectorAll('[data-show]').forEach(button => button.onclick = () => {
    show = button.dataset.show;
    host.querySelectorAll('[data-show]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
    draw();
  });
  const play = player(host, signal, dt => { h += dt * .013; if (h > hours + 55) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, hours) + dir * 6, 0, hours); draw(); });
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 4. two clouds meeting in the middle ───────────────────────────────────── */
async function meeting(host, signal) {
  const [cloud, coast, wind] = await Promise.all([clouds(), load('coast-atlantic.json'), windField()]);
  if (signal.aborted) return;
  const p = cloud.posterior, { n, steps, hours, hoursPerStep, tA } = p, mid = (steps - 1) / 2, half = hours / 2;
  host.innerHTML = `${heading('Two clouds meeting in the middle', `${n} of the ${fmt(p.nTotal)} bridges`)}
    <div class="chart-legend">${key('Forward, from New Mexico', BLUE)}${key('Backward, from Spain', RED)}${key('Joined bridge', '#9a9c95')}${key('The drawn line', INK)}${windKey()}</div>
    <div class="fleet-map-stage"></div>
    ${footer('NOAA GFS at the hour shown')}
    ${slider('Gap hour', hours, .5, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Forward and backward particle clouds crossing the Atlantic and meeting at the midpoint of the gap, over the wind at that hour. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('.fleet-time output'), read = host.querySelector('.chart-readout'), date = host.querySelector('.fleet-date');
  const A = p.drawn[0], B = p.drawn[steps - 1];
  let h = 0;
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, hours), tMs = tA + hour * 3600000, sF = Math.min(hour / hoursPerStep, mid), sB = Math.max(steps - 1 - hour / hoursPerStep, mid);
    const reveal = clamp((hour - half) / (half * .6), 0, 1);
    map.base(coast);
    wind.draw(map, tMs, { alpha: .26 });
    if (reveal < 1) {
      for (let i = 0; i < n; i++) {
        map.line([...p.path(i, 0, Math.floor(sF)), p.at(i, sF)], { color: BLUE, width: .8, alpha: .14 * (1 - reveal) });
        map.line([p.at(i, sB), ...p.path(i, Math.ceil(sB), steps - 1)], { color: RED, width: .8, alpha: .14 * (1 - reveal) });
      }
      for (let i = 0; i < n; i++) { const f = p.at(i, sF), bk = p.at(i, sB); map.dot(f[0], f[1], 1.7, BLUE, null, 1, .9 * (1 - reveal)); map.dot(bk[0], bk[1], 1.7, RED, null, 1, .9 * (1 - reveal)); }
    }
    if (reveal > 0) {
      for (let i = 0; i < n; i++) map.line(p.path(i, 0, steps - 1), { color: '#9a9c95', width: .7, alpha: .22 * reveal });
      map.line(p.drawn, { color: INK, width: 2.4, alpha: reveal });
    }
    map.dot(A[0], A[1], 5, CREAM, INK, 1.6); map.dot(B[0], B[1], 5, CREAM, INK, 1.6);
    input.value = hour; output.textContent = fmt(hour); date.textContent = utc(tMs);
    read.textContent = hour < half - 1
      ? `forward particles ${fmt(hour)} h out of New Mexico, backward particles ${fmt(hour)} h back from Spain, neither aimed at the other end`
      : reveal <= 0
        ? 'the clouds meet: every forward particle is paired with the backward particles within reach, weighted by how closely the halves track across the overlap'
        : 'the joined bridges are the answer, each weighted by how plausible it is; the drawn line is their average';
  }
  const play = player(host, signal, dt => { h += dt * .013; if (h > hours + 55) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, hours) + dir * 6, 0, hours); draw(); });
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 5. how sure the line is ───────────────────────────────────────────────── */
async function line(host, signal) {
  const [cloud, coast] = await Promise.all([clouds(), load('coast-atlantic.json')]);
  if (signal.aborted) return;
  const p = cloud.posterior, { n, steps, hours, hoursPerStep, tA } = p;
  host.innerHTML = `${heading('How sure the line is', `${n} of the ${fmt(p.nTotal)} bridges at one hour`)}
    <div class="fleet-metrics contact-metrics"><span><b data-near>…</b>of bridges within 300 km of the line</span><span><b data-r90>…</b>holds 90% of the bridges</span><span><b data-hour>…</b>hours into the gap</span></div>
    <div class="chart-legend">${key('Possible positions', BLUE, 'dot')}${key('The drawn line', RED)}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${footer('')}
    ${slider('Gap hour', hours, 1, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Where the posterior draws put the balloon at one hour of the gap, around the drawn line. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('.fleet-time output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date');
  const get = selector => host.querySelector(selector);
  let h = 0, dots = [];
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, hours), s = hour / hoursPerStep, si = clamp(Math.round(s), 0, steps - 1), stats = p.stats[si];
    map.base(coast);
    map.line(p.drawn, { color: RED, width: 2, alpha: .9 });
    dots = [];
    for (let i = 0; i < n; i++) {
      const [lat, lon] = p.at(i, s);
      map.dot(lat, lon, 2.1, BLUE, null, 1, .8);
      dots.push({ lat, lon });
    }
    const d = p.drawn[si];
    map.dot(d[0], d[1], 4.5, RED, CREAM, 1.5);
    get('[data-near]').textContent = `${fmt(stats.within300 * 100)}%`;
    get('[data-r90]').textContent = `${fmt(stats.r90)} km`;
    get('[data-hour]').textContent = fmt(hour);
    input.value = hour; output.textContent = fmt(hour); date.textContent = utc(tA + hour * 3600000);
    read.textContent = `drawn line at ${place(d[0], d[1])} / a circle of ${fmt(stats.r90)} km around it holds 90% of the bridges`;
  }
  const play = player(host, signal, dt => { h += dt * .006; if (h > hours + 40) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, hours) + dir * 6, 0, hours); draw(); });
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event);
    const best = dots.reduce((b, q) => { const [qx, qy] = map.point(q.lat, q.lon); const dist = Math.hypot(qx - x, qy - y); return dist < b.dist ? { dist, q } : b; }, { dist: 12 });
    hover.hidden = !best.q;
    if (best.q) hover.textContent = place(best.q.lat, best.q.lon);
  };
  map.canvas.onpointerleave = () => { hover.hidden = true; };
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 6. where it goes next ─────────────────────────────────────────────────── */
async function forecast(host, signal) {
  const [f, buffer, coast] = await Promise.all([load('forecast.json'), load('forecast.bin'), load('/assets/payload-dev-log/coastlines.json')]);
  if (signal.aborted) return;
  const pos = new Int16Array(buffer), { members, steps, hours, spreadKm, median, thresholdKm } = f, total = hours[steps - 1], stepH = hours[1] - hours[0];
  const start = Date.parse(f.start);
  const at = (m, s) => {
    const a = Math.floor(s), b = Math.min(steps - 1, a + 1), t = s - a, ia = (m * steps + a) * 2, ib = (m * steps + b) * 2;
    let dl = pos[ib + 1] - pos[ia + 1]; if (dl > 18000) dl -= 36000; if (dl < -18000) dl += 36000;
    return [(pos[ia] + (pos[ib] - pos[ia]) * t) / 100, (pos[ia + 1] + dl * t) / 100];
  };
  const spreadAt = s => { const a = Math.floor(s), b = Math.min(steps - 1, a + 1); return spreadKm[a] + (spreadKm[b] - spreadKm[a]) * (s - a); };
  host.innerHTML = `${heading('Where it goes next', `${members} members: ${f.gefs} GEFS, ${f.aigefs} AIGEFS`)}
    <div class="fleet-metrics contact-metrics"><span><b data-day>…</b>days after the last fix</span><span><b data-spread>…</b>75% of members within this distance of the median</span><span><b>${fmt(thresholdKm)} km</b>where the forecast stops</span></div>
    <div class="chart-legend">${key('Ensemble members', BLUE)}${key('Median path, the drawn forecast', INK)}${key('Forecast ends', RED, 'diamond')}</div>
    <div class="fleet-map-stage"></div>
    ${footer('GEFS and AIGEFS members from the May 29 cycle')}
    <div class="chart-stage"><svg class="spread-chart" role="img" aria-label="Ensemble spread against forecast day, with the 2,000 km stopping threshold"></svg></div>
    ${slider('Forecast hour', total, 1, 'Hours after the last fix')}
    <output class="chart-readout"></output>`;
  const map = createMap(WORLD, 'Sixty-two ensemble trajectories from the last fix in Spain eastward around the world. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const svg = host.querySelector('.spread-chart'), input = host.querySelector('input'), output = host.querySelector('.fleet-time output'), read = host.querySelector('.chart-readout'), date = host.querySelector('.fleet-date');
  const ns = 'http://www.w3.org/2000/svg', el = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; return e; };
  let h = 0, width = 0;
  function drawChart(hour, spread) {
    const w = width, ht = 150, L = 46, Rm = 12, T = 14, B = 30, ymax = Math.max(2400, ...spreadKm) * 1.05;
    const sx = x => L + x / total * (w - L - Rm), sy = y => T + (1 - y / ymax) * (ht - T - B);
    svg.setAttribute('viewBox', `0 0 ${w} ${ht}`); svg.setAttribute('width', w); svg.setAttribute('height', ht); svg.replaceChildren();
    for (const v of [0, 1000, 2000]) svg.append(el('line', { x1: L, x2: w - Rm, y1: sy(v), y2: sy(v), class: 'grid-line' }), el('text', { x: L - 7, y: sy(v) + 4, 'text-anchor': 'end', class: 'tick' }, `${fmt(v / 1000, 0)}k`));
    for (let d = 0; d <= total / 24; d += 2) svg.append(el('text', { x: sx(d * 24), y: ht - 10, 'text-anchor': 'middle', class: 'tick' }, `day ${d}`));
    svg.append(el('text', { x: L, y: 10, class: 'axis-label' }, 'Spread (km)'));
    svg.append(el('line', { x1: L, x2: w - Rm, y1: sy(thresholdKm), y2: sy(thresholdKm), stroke: RED, 'stroke-dasharray': '4 4' }));
    svg.append(el('path', { d: spreadKm.map((v, k) => `${k ? 'L' : 'M'}${sx(hours[k])},${sy(v)}`).join(' '), fill: 'none', stroke: BLUE, 'stroke-width': 2.2 }));
    svg.append(el('line', { x1: sx(hour), x2: sx(hour), y1: T, y2: ht - B, stroke: '#29292766', 'stroke-dasharray': '3 4' }));
    svg.append(el('circle', { cx: sx(hour), cy: sy(spread), r: 4, fill: BLUE, stroke: CREAM, 'stroke-width': 2 }));
  }
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, total), s = hour / stepH, done = hour >= total - 1e-9;
    map.base(coast, 30);
    const { ctx } = map;
    for (let m = 0; m < members; m++) {
      const pts = []; for (let k = 0; k <= Math.floor(s); k++) pts.push(at(m, k)); pts.push(at(m, s));
      map.line(pts, { color: BLUE, width: .8, alpha: .32 });
    }
    for (let m = 0; m < members; m++) { const q = at(m, s); map.dot(q[0], q[1], 1.6, BLUE, null, 1, .8); }
    const med = median.slice(0, Math.floor(s) + 1); const ms = median[Math.min(steps - 1, Math.ceil(s))], mf = median[Math.floor(s)];
    med.push([mf[0] + (ms[0] - mf[0]) * (s - Math.floor(s)), mf[1] + (ms[1] - mf[1]) * (s - Math.floor(s))]);
    map.line(med, { color: INK, width: 2 });
    map.dot(f.lastFix[0], f.lastFix[1], 5, CREAM, INK, 1.6);
    map.label(f.lastFix[0], f.lastFix[1], 'last fix, May 29', 9, 16);
    if (done) {
      const [x, y] = map.point(f.divergence.lat, f.divergence.lon);
      ctx.fillStyle = RED; ctx.beginPath(); ctx.moveTo(x, y - 7); ctx.lineTo(x + 7, y); ctx.lineTo(x, y + 7); ctx.lineTo(x - 7, y); ctx.closePath(); ctx.fill();
      map.label(f.divergence.lat, f.divergence.lon, `forecast ends: spread ${fmt(spreadKm[steps - 1])} km`, -11, -10, RED);
    }
    const spread = spreadAt(s);
    host.querySelector('[data-day]').textContent = fmt(hour / 24, 1);
    host.querySelector('[data-spread]').textContent = `${fmt(spread)} km`;
    drawChart(hour, spread);
    input.value = hour; output.textContent = fmt(hour); date.textContent = utc(start + hour * 3600000);
    read.textContent = `75% of the members within ${fmt(spread)} km of the median${done ? ` / past ${fmt(thresholdKm)} km the median is not predicting anything, so the line stops here` : ''}`;
  }
  const play = player(host, signal, dt => { h += dt * .016; if (h > total + 70) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, total) + dir * 12, 0, total); draw(); });
  observeChartSize(host, () => { width = host.clientWidth - 32; map.resize(width); draw(); }, signal);
}

const figures = { replay, tube, compare, meeting, line, forecast };

export function mountFigures(root, signal) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting || signal.aborted) continue;
      observer.unobserve(entry.target);
      const host = entry.target, mount = figures[host.dataset.chart];
      if (!mount) continue;
      mount(host, signal).catch(() => { if (!signal.aborted) host.textContent = 'Figure could not load. Reload to try again.'; });
    }
  }, { rootMargin: '450px' });
  root.querySelectorAll('[data-chart]').forEach(host => observer.observe(host));
  signal.addEventListener('abort', () => observer.disconnect(), { once: true });
}
