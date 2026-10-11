/* Interactive figures for "Drawing the path between packets". Same conventions as the
 * payload dev log's charts: a chart card with a heading, canvas maps on the muted
 * paper with the wind drawn across them, range controls with live outputs, a readout
 * line, keyboard access, and animations that pause off-screen or under
 * prefers-reduced-motion. Data comes from the bundle in /assets/wind-path, built by
 * scripts/blog/wind_path_figure_data.py and wind_path_background_winds.py. */
import { colors, heatColor, observeChartSize } from '../payload-dev-log/charts.js';

const ASSETS = '/assets/wind-path';
const INK = '#292927', PAPER = '#eeeee9', GRID = '#d7d8d1', COAST = '#959c93', FAINT = '#b8b9b3', CREAM = '#f6f4ef';
const RED = colors[0], ORANGE = colors[1], GREEN = colors[3], BLUE = colors[4], INDIGO = colors[5], PURPLE = colors[6];
const MODE_COLORS = [BLUE, ORANGE, GREEN, PURPLE, INDIGO, colors[2], FAINT];
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
  /* A camera for the ride-along view: a center and a longitude span; the latitude
   * span follows from the canvas aspect so the map never stretches. */
  m.look = (lat, lon, lonSpan) => {
    const latSpan = lonSpan * (m.height / m.width) * Math.cos(lat * rad);
    m.bounds = { lon0: lon - lonSpan / 2, lon1: lon + lonSpan / 2, lat0: lat - latSpan / 2, lat1: lat + latSpan / 2 };
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
  m.cross = (lat, lon, size, color) => {
    const [x, y] = m.point(lat, lon);
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    ctx.moveTo(x - size, y - size); ctx.lineTo(x + size, y + size); ctx.moveTo(x - size, y + size); ctx.lineTo(x + size, y - size); ctx.stroke();
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
const key = (text, color, shape = 'bar') => `<span class="chart-key"><i class="key-${shape}" style="${shape === 'cross' ? 'color' : 'background'}:${color}"></i>${text}</span>`;
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
  const [flight, coast, wind, cloud] = await Promise.all([load('flight.json'), load('coast-atlantic.json'), windField(), clouds()]);
  if (signal.aborted) return;
  const { t0, fixes, end } = flight, distinct = fixes.filter(f => f[3]), gaps = longGaps(fixes), segments = trackSegments(flight.track, gaps);
  const dark = gaps.reduce((s, [a, b]) => s + b - a, 0);
  host.innerHTML = `${heading('Stratolink 3, replayed', `GFS winds at ${fmt(wind.levelHpa)} hPa`)}
    <div class="fleet-metrics contact-metrics"><span><b>${fixes.length}</b>packets with a position</span><span><b>${distinct.length}</b>distinct positions</span><span><b>${fmt(dark / 60)} h</b>of ${fmt(end / 60)} without a packet for over six hours</span></div>
    <div class="chart-legend">${windKey()}${key('Received position', INK, 'dot')}${key('Where the balloon could be, 500 draws', BLUE, 'dot')}${key('The drawn line', RED)}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${footer('NOAA GFS, May 2026')}
    <canvas class="packet-strip" role="img" aria-label="Timeline of received positions over the flight, with gaps longer than six hours shaded"></canvas>
    <div class="waterfall-axis"><span>May 17</span><span>May 23</span><span>May 29</span></div>
    ${slider('Flight hour', end, 10, 'Minutes since launch')}
    <output class="chart-readout"></output>`;
  const map = createMap(ATLANTIC, 'Stratolink 3 replayed over the North Atlantic: received positions, the wind field, and the cloud of possible positions during the gaps. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const strip = host.querySelector('.packet-strip'), sctx = strip.getContext('2d');
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date');
  let cursor = 0, width = 0;
  function draw() {
    if (!width) return;
    const tMs = t0 + cursor * 60000;
    map.base(coast);
    wind.draw(map, tMs, { alpha: .34 });
    drawTrack(map, segments, cursor);
    const g = cloud.find(tMs);
    if (g) drawCloud(map, g, (tMs - g.tA) / (g.tB - g.tA) * (g.steps - 1));
    for (const [t, lat, lon, isDistinct] of fixes) if (t <= cursor) map.dot(lat, lon, isDistinct ? 2.2 : 1.5, isDistinct ? INK : '#a3a59e');
    const last = distinct.filter(f => f[0] <= cursor).at(-1);
    if (last && !g) map.dot(last[1], last[2], 6, CREAM, INK, 1.6);
    if (last && g) map.dot(last[1], last[2], 5, null, INK, 1.2);
    sctx.clearRect(0, 0, width, 30); sctx.fillStyle = '#e3e4dd'; sctx.fillRect(0, 6, width, 16);
    sctx.fillStyle = 'rgba(50,140,179,.22)';
    for (const [a, b] of gaps) sctx.fillRect(a / end * width, 6, (b - a) / end * width, 16);
    for (const [t, , , isDistinct] of fixes) { sctx.fillStyle = isDistinct ? INK : '#b3b5ae'; sctx.fillRect(t / end * width, 6, Math.max(.8, width / 1500), 16); }
    sctx.fillStyle = INK; sctx.fillRect(cursor / end * width - 1, 0, 2, 29);
    input.value = cursor; output.textContent = fmt(cursor / 60, 1); date.textContent = utc(tMs);
    const since = last ? (cursor - last[0]) / 60 : 0;
    read.textContent = g
      ? `${fmt(since)} h without a packet / ${g.n} draws from the smoother drifting with the wind; the red line is the one the dashboard draws`
      : last ? `last packet ${ago(since)} from ${place(last[1], last[2])}` : 'before launch';
  }
  const play = player(host, signal, dt => { cursor += dt * .6; if (cursor > end + 1500) cursor = 0; draw(); });
  bindSlider(input, play, value => { cursor = value; draw(); });
  keys(map.canvas, play, dir => { cursor = clamp(Math.min(cursor, end) + dir * 360, 0, end); draw(); });
  strip.onpointermove = event => { const b = strip.getBoundingClientRect(); play.set(false); cursor = clamp((event.clientX - b.left) / b.width * end, 0, end); draw(); };
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
  const [meta, buffer, coast, flight, wind, cloud] = await Promise.all([load('tube.json'), load('tube.bin'), load('coast-atlantic.json'), load('flight.json'), windField(), clouds()]);
  if (signal.aborted) return;
  const fine = new Int8Array(buffer), { slices } = meta, last = slices.length - 1, gaps = longGaps(flight.fixes), segments = trackSegments(flight.track, gaps);
  host.innerHTML = `${heading('Riding the tube', `one box of 0.25° winds per 3-hour slice`)}
    <div class="chart-legend">${key('This slice’s box', BLUE)}${windKey()}${key('Draws from the smoother', BLUE, 'dot')}${key('Reconstructed track', INK)}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${footer('')}
    ${slider('Slice', last, .1, 'Reconstruction cube time slice')}
    <output class="chart-readout"></output>`;
  const map = createMap(ATLANTIC, 'A close view that follows the balloon along the wind tube: the current slice box with its fine winds, the coarser wind around it, and the particle cloud inside. Space plays, arrow keys step.', .52);
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date'), source = host.querySelector('.fleet-source');
  let at = 0, camera, arrows = [];
  const gapHours = t => { const m = (t - flight.t0) / 60000; const g = gaps.find(([a, b]) => m >= a && m <= b); return g ? (g[1] - g[0]) / 60 : 0; };
  function target() { const s = slices[clamp(Math.round(at), 0, last)]; return { lat: s.lat0 + s.h / 2, lon: s.lon0 + s.w / 2, span: clamp(s.w * 1.45, 34, 60) }; }
  function draw(snap = false) {
    if (!map.width) return;
    const k = clamp(Math.round(at), 0, last), s = slices[k], t = s.t, want = target();
    camera = !camera || snap ? want : { lat: lerp(camera.lat, want.lat, .12), lon: lerp(camera.lon, want.lon, .12), span: lerp(camera.span, want.span, .12) };
    map.look(camera.lat, camera.lon, camera.span);
    map.base(coast, 5);
    wind.draw(map, t, { alpha: .22, scale: 2.4, max: 16 });
    for (const b of slices) if (b !== s) map.rect(b.lat0, b.lon0, b.h, b.w, { alpha: .07, width: .7 });
    map.rect(s.lat0, s.lon0, s.h, s.w, { alpha: .9, width: 1.4, fill: .05 });
    arrows = [];
    for (let i = 0; i < s.aLat; i++) for (let j = 0; j < s.aLon; j++) {
      const o = s.off + (i * s.aLon + j) * 2, u = fine[o], v = fine[o + 1], lat = s.lat0 + i * s.aStep, lon = s.lon0 + j * s.aStep;
      if (!map.inView(lat, lon)) continue;
      arrows.push({ lat, lon, u, v, speed: Math.hypot(u, v) }); map.arrow(lat, lon, u, v, { alpha: .75, width: 1.1, scale: 2.4, max: 16 });
    }
    drawTrack(map, segments, (t - flight.t0) / 60000);
    const g = cloud.find(t);
    if (g) drawCloud(map, g, (t - g.tA) / (g.tB - g.tA) * (g.steps - 1), { tail: false });
    let pos = s.pos;
    const next = slices[Math.min(last, k + 1)], f = at - k;
    if (pos && next.pos && f > 0) pos = [pos[0] + (next.pos[0] - pos[0]) * f, pos[1] + (next.pos[1] - pos[1]) * f];
    if (pos && !g) map.dot(pos[0], pos[1], 4.5, CREAM, INK, 1.8);
    input.value = at; output.textContent = fmt(k); date.textContent = utc(t); source.textContent = `box ±${(s.w / 2).toFixed(1)}°, arrows every ${s.aStep.toFixed(2)}° inside, 2.5° outside`;
    const hours = gapHours(t), half = s.w / 2;
    const why = half <= 9.05 ? 'the ±9° minimum, enough for the cloud across a gap under 60 hours' : `widened to ±${half.toFixed(1)}° because this slice sits in the ${fmt(hours)}-hour gap, where the cloud spreads further`;
    let near = '';
    if (pos && arrows.length) { const a = arrows.reduce((b, p) => km(p.lat, p.lon, pos[0], pos[1]) < km(b.lat, b.lon, pos[0], pos[1]) ? p : b, arrows[0]); near = ` / wind at the track ${fmt(a.speed)} m/s toward ${toward(a.u, a.v)}`; }
    read.textContent = `Slice ${k + 1} of ${slices.length} / ${why}${pos ? near : ' / before launch'}`;
  }
  const play = player(host, signal, dt => { at += dt * .002; if (at > last + 8) { at = 0; camera = undefined; } draw(); });
  bindSlider(input, play, value => { at = value; draw(true); });
  keys(map.canvas, play, dir => { at = clamp(Math.round(at) + dir, 0, last); draw(true); });
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event), b = map.bounds, lat = b.lat1 - y / map.height * (b.lat1 - b.lat0), lon = b.lon0 + x / map.width * (b.lon1 - b.lon0);
    const s = slices[clamp(Math.round(at), 0, last)];
    const inside = lat >= s.lat0 && lat <= s.lat0 + s.h && lon >= s.lon0 && lon <= s.lon0 + s.w;
    let u, v;
    if (inside && arrows.length) { const a = arrows.reduce((best, p) => Math.hypot(p.lat - lat, p.lon - lon) < Math.hypot(best.lat - lat, best.lon - lon) ? p : best, arrows[0]); [u, v] = [a.u, a.v]; }
    else [u, v] = wind.at(s.t, lat, lon);
    hover.hidden = false; hover.textContent = `${place(lat, lon)} / ${inside ? 'inside the box, 0.25° winds' : 'outside the box, 2.5° winds'} / ${fmt(Math.hypot(u, v))} m/s toward ${toward(u, v)}`;
  };
  map.canvas.onpointerleave = () => { hover.hidden = true; };
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(true); }, signal);
}

/* ── 3. two ways to bridge the gap ─────────────────────────────────────────── */
async function methods(host, signal) {
  const [b, coast, wind] = await Promise.all([load('bridges.json'), load('coast-atlantic.json'), windField()]);
  if (signal.aborted) return;
  host.innerHTML = `${heading('Two ways to bridge the gap', `${fmt(b.hours)} hours, New Mexico to Spain`, false)}
    <div class="capture-tabs" role="group" aria-label="Bridging method"><button type="button" data-method="forward" aria-pressed="true">Forward sampler</button><button type="button" data-method="twoFilter" aria-pressed="false">Two filters meeting in the middle</button></div>
    <div class="methods-settings"><label>Particles per run<select data-particles aria-label="Particles per run">${Object.keys(b.forward).map(n => `<option value="${n}">${fmt(n)}</option>`).join('')}</select></label><span class="methods-buttons"><button type="button" class="fleet-play" data-add>Add a rerun</button><button type="button" class="fleet-play" data-reset>Start over</button></span></div>
    <div class="fleet-map-stage"></div>
    ${footer('winds at the middle of the gap, May 24')}
    <div class="chart-legend"></div>
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Reconstructed bridges across the eight-day gap from stored reruns of each method');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const legend = host.querySelector('.chart-legend'), read = host.querySelector('.chart-readout'), select = host.querySelector('[data-particles]'), add = host.querySelector('[data-add]'), date = host.querySelector('.fleet-date');
  let method = 'forward', particles = select.value, shown = 1;
  const group = () => method === 'forward' ? b.forward[particles] : b.twoFilter;
  const A = b.drawn[0], B = b.drawn[b.drawn.length - 1], mid = (b.tA + b.tB) / 2;
  date.textContent = `${utc(b.tA)} to ${utc(b.tB)}`;
  function draw() {
    if (!map.width) return;
    const { runs, spreadKm } = group();
    map.base(coast);
    wind.draw(map, mid, { alpha: .2 });
    runs.slice(0, shown).forEach((run, k) => map.line(run, { color: colors[k % 7], width: 1.8, alpha: .9 }));
    map.dot(A[0], A[1], 5, CREAM, INK, 1.6); map.dot(B[0], B[1], 5, CREAM, INK, 1.6);
    map.label(A[0], A[1], 'May 19', 9, 14); map.label(B[0], B[1], 'May 28', -9, 14);
    legend.innerHTML = runs.slice(0, shown).map((_, k) => key(`Run ${k + 1}`, colors[k % 7])).join('') + windKey();
    select.disabled = method !== 'forward'; add.disabled = shown >= runs.length;
    read.textContent = shown < 2
      ? `One of ${runs.length} stored ${method === 'forward' ? `${fmt(particles)}-particle` : 'two-filter'} runs. Add a rerun to compare.`
      : `${shown} of ${runs.length} stored runs / the drawn line moved by a median of ${fmt(spreadKm)} km between them`;
  }
  host.querySelectorAll('[data-method]').forEach(button => button.onclick = () => {
    method = button.dataset.method; shown = 1;
    host.querySelectorAll('[data-method]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
    draw();
  });
  select.onchange = () => { particles = select.value; shown = 1; draw(); };
  add.onclick = () => { shown = Math.min(shown + 1, group().runs.length); draw(); };
  host.querySelector('[data-reset]').onclick = () => { shown = 1; draw(); };
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 4. two clouds meeting in the middle ───────────────────────────────────── */
async function meeting(host, signal) {
  const [cloud, coast, wind] = await Promise.all([clouds(), load('coast-atlantic.json'), windField()]);
  if (signal.aborted) return;
  const p = cloud.posterior, { n, steps, hours, hoursPerStep, tA } = p, mid = (steps - 1) / 2, half = hours / 2;
  host.innerHTML = `${heading('Two clouds meeting in the middle', `${n} of the ${fmt(p.nTotal)} posterior draws`)}
    <div class="chart-legend">${key('Forward half, from New Mexico', BLUE)}${key('Backward half, from Spain', ORANGE)}${key('Joined bridge', '#9a9c95')}${key('The drawn line', RED)}${windKey()}</div>
    <div class="fleet-map-stage"></div>
    ${footer('NOAA GFS at the hour shown')}
    ${slider('Gap hour', hours, .5, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Forward and backward particle clouds crossing the Atlantic and meeting at the midpoint of the gap, over the wind at that hour. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), date = host.querySelector('.fleet-date');
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
        map.line([p.at(i, sB), ...p.path(i, Math.ceil(sB), steps - 1)], { color: ORANGE, width: .8, alpha: .14 * (1 - reveal) });
      }
      for (let i = 0; i < n; i++) { const f = p.at(i, sF), bk = p.at(i, sB); map.dot(f[0], f[1], 1.7, BLUE, null, 1, .9 * (1 - reveal)); map.dot(bk[0], bk[1], 1.7, ORANGE, null, 1, .9 * (1 - reveal)); }
    }
    if (reveal > 0) {
      for (let i = 0; i < n; i++) map.line(p.path(i, 0, steps - 1), { color: '#9a9c95', width: .7, alpha: .22 * reveal });
      map.line(p.drawn, { color: RED, width: 2.4, alpha: reveal });
    }
    map.dot(A[0], A[1], 5, CREAM, INK, 1.6); map.dot(B[0], B[1], 5, CREAM, INK, 1.6);
    input.value = hour; output.textContent = fmt(hour); date.textContent = utc(tMs);
    read.textContent = hour < half - 1
      ? `forward particles ${fmt(hour)} h out of New Mexico, backward particles ${fmt(hour)} h back from Spain, neither aimed at the other end`
      : reveal <= 0
        ? 'the clouds meet: every forward particle is paired with the backward particles within reach, weighted by how closely the halves track across the overlap'
        : 'the pairs are the posterior; the drawn line is the average of the tenth of them that track the medoid most closely';
  }
  const play = player(host, signal, dt => { h += dt * .013; if (h > hours + 55) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, hours) + dir * 6, 0, hours); draw(); });
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 5. which line to draw ─────────────────────────────────────────────────── */
async function line(host, signal) {
  const [cloud, cbuffer, coast] = await Promise.all([clouds(), load('clusters.bin'), load('coast-atlantic.json')]);
  if (signal.aborted) return;
  const p = cloud.posterior, labels = new Int8Array(cbuffer), kept = new Set(p.kept), { n, steps, hours, hoursPerStep, tA } = p;
  host.innerHTML = `${heading('Which line to draw', `${n} of the ${fmt(p.nTotal)} draws at one hour`)}
    <div class="capture-tabs" role="group" aria-label="Color the draws by"><button type="button" data-color="modes" aria-pressed="true">Clusters at this hour</button><button type="button" data-color="kept" aria-pressed="false">The kept tenth</button></div>
    <div class="fleet-metrics contact-metrics"><span><b data-m1>…</b>largest cluster</span><span><b data-m2>…</b>second cluster</span><span><b data-near-mean>…</b>within 300 km of the mean</span><span><b data-near-line>…</b>within 300 km of the drawn line</span></div>
    <div class="chart-legend">${key('Posterior mean', INK, 'cross')}${key('Medoid, the most central draw', INDIGO, 'ring')}${key('The drawn line', RED)}${key('Posterior mean path', '#8a8c86', 'dash')}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${footer('')}
    ${slider('Gap hour', hours, 1, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Where the posterior draws put the balloon at one hour of the gap, with the posterior mean, the medoid and the drawn line. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date');
  const get = selector => host.querySelector(selector);
  let h = 0, mode = 'modes', dots = [];
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, hours), s = hour / hoursPerStep, si = clamp(Math.round(s), 0, steps - 1), stats = p.stats[si];
    map.base(coast);
    map.line(p.mean, { color: '#8a8c86', width: 1.3, dash: [5, 4] });
    map.line(p.drawn, { color: RED, width: 2, alpha: .9 });
    dots = [];
    for (let i = 0; i < n; i++) {
      const [lat, lon] = p.at(i, s), label = labels[i * steps + si], isKept = kept.has(i);
      const color = mode === 'modes' ? MODE_COLORS[Math.min(label, 6)] : isKept ? BLUE : FAINT;
      map.dot(lat, lon, mode === 'kept' && isKept ? 2.8 : 2.1, color, null, 1, mode === 'kept' && !isKept ? .6 : .8);
      dots.push({ lat, lon, label, isKept });
    }
    const m = p.mean[si], md = p.medoid[si], d = p.drawn[si];
    map.dot(md[0], md[1], 5, null, INDIGO, 2);
    map.cross(m[0], m[1], 5.5, INK);
    map.dot(d[0], d[1], 4.5, RED, CREAM, 1.5);
    const [m1, m2] = stats.modes;
    get('[data-m1]').textContent = m1 ? `${fmt(m1[0] * 100)}%` : '—';
    get('[data-m2]').textContent = m2 ? `${fmt(m2[0] * 100)}%` : 'none';
    get('[data-near-mean]').textContent = `${fmt(stats.within300.mean * 100)}%`;
    get('[data-near-line]').textContent = `${fmt(stats.within300.drawn * 100)}%`;
    input.value = hour; output.textContent = fmt(hour); date.textContent = utc(tA + hour * 3600000);
    read.textContent = `${stats.modes.length === 1 ? 'one cluster' : `${stats.modes.length} clusters`} / mean ${place(m[0], m[1])} / drawn line ${place(d[0], d[1])}, ${fmt(km(m[0], m[1], d[0], d[1]))} km apart`;
  }
  host.querySelectorAll('[data-color]').forEach(button => button.onclick = () => {
    mode = button.dataset.color;
    host.querySelectorAll('[data-color]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
    draw();
  });
  const play = player(host, signal, dt => { h += dt * .006; if (h > hours + 40) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, hours) + dir * 6, 0, hours); draw(); });
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event);
    const best = dots.reduce((b, q) => { const [qx, qy] = map.point(q.lat, q.lon); const dist = Math.hypot(qx - x, qy - y); return dist < b.dist ? { dist, q } : b; }, { dist: 12 });
    hover.hidden = !best.q;
    if (best.q) hover.textContent = `${place(best.q.lat, best.q.lon)} / cluster ${best.q.label + 1}${best.q.isKept ? ' / in the kept tenth' : ''}`;
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
  const svg = host.querySelector('.spread-chart'), input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), date = host.querySelector('.fleet-date');
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

const figures = { replay, tube, methods, meeting, line, forecast };

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
