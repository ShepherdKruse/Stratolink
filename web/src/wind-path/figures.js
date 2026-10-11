/* Interactive figures for "Drawing the path between packets". Same conventions as the
 * payload dev log's charts: a chart card with a heading, a canvas map on the muted
 * paper, range controls with live outputs, a readout line, keyboard access, and
 * animations that pause off-screen or under prefers-reduced-motion. Data comes from
 * the compact bundle in /assets/wind-path (see scripts in the PR description). */
import { colors, heatColor, observeChartSize } from '../payload-dev-log/charts.js';

const ASSETS = '/assets/wind-path';
const INK = '#292927', PAPER = '#eeeee9', GRID = '#d7d8d1', COAST = '#959c93', FAINT = '#b8b9b3';
const RED = colors[0], ORANGE = colors[1], GREEN = colors[3], BLUE = colors[4], INDIGO = colors[5], PURPLE = colors[6];
const MODE_COLORS = [BLUE, ORANGE, GREEN, PURPLE, INDIGO, colors[2], FAINT];
const rad = Math.PI / 180, R = 6371;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (n, p = 0) => Number(n).toLocaleString('en-US', { maximumFractionDigits: p });
const utc = ms => new Date(ms).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }) + ' UTC';
const place = (lat, lon) => `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`;
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

function createMap(bounds, label) {
  const canvas = document.createElement('canvas');
  canvas.className = 'fleet-map'; canvas.tabIndex = 0; canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', label);
  const ctx = canvas.getContext('2d');
  const span = bounds.lon1 - bounds.lon0;
  const m = { canvas, ctx, bounds, width: 0, height: 0 };
  m.lon = lon => bounds.wrap ? bounds.lon0 + (((lon - bounds.lon0) % 360) + 360) % 360 : lon;
  m.x = lon => (m.lon(lon) - bounds.lon0) / span * m.width;
  m.y = lat => (bounds.lat1 - lat) / (bounds.lat1 - bounds.lat0) * m.height;
  m.point = (lat, lon) => [m.x(lon), m.y(lat)];
  m.invert = (x, y) => [bounds.lat1 - y / m.height * (bounds.lat1 - bounds.lat0), bounds.lon0 + x / m.width * span];
  m.resize = width => {
    const height = Math.round(width * (bounds.lat1 - bounds.lat0) / (span * Math.cos((bounds.lat0 + bounds.lat1) / 2 * rad)));
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
  m.cross = (lat, lon, size, color) => {
    const [x, y] = m.point(lat, lon);
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    ctx.moveTo(x - size, y - size); ctx.lineTo(x + size, y + size); ctx.moveTo(x - size, y + size); ctx.lineTo(x + size, y - size); ctx.stroke();
  };
  m.label = (lat, lon, text, dx = 8, dy = 4, color = INK) => {
    const [x, y] = m.point(lat, lon);
    ctx.fillStyle = color; ctx.font = '11px Helvetica, Arial, sans-serif'; ctx.textAlign = dx < 0 ? 'right' : 'left'; ctx.fillText(text, x + dx, y + dy);
  };
  m.base = (coast, step = 10) => {
    ctx.clearRect(0, 0, m.width, m.height); ctx.fillStyle = PAPER; ctx.fillRect(0, 0, m.width, m.height);
    for (let lat = Math.ceil(bounds.lat0 / step) * step; lat < bounds.lat1; lat += step) m.line([[lat, bounds.lon0], [lat, bounds.lon1 - 1e-6]], { color: GRID, width: .6 });
    for (let lon = Math.ceil(bounds.lon0 / step) * step; lon < bounds.lon1; lon += step) m.line([[bounds.lat0, lon], [bounds.lat1, lon]], { color: GRID, width: .6 });
    for (const c of coast) m.line(c, { color: COAST, width: .7, alpha: .8, latFirst: false });
  };
  m.pointer = event => {
    const b = canvas.getBoundingClientRect();
    return [(event.clientX - b.left) * m.width / b.width, (event.clientY - b.top) * m.height / b.height];
  };
  return m;
}

/* ── shared chrome ──────────────────────────────────────────────────────────── */
const heading = (title, subtitle, play = true) => `<div class="chart-heading fleet-heading">${title}<div class="fleet-heading-controls"><span>${subtitle}</span>${play ? '<button type="button" class="fleet-play" data-play aria-pressed="false">Play</button>' : ''}</div></div>`;
const key = (text, color, shape = 'bar') => `<span class="chart-key"><i class="key-${shape}" style="${shape === 'cross' ? 'color' : 'background'}:${color}"></i>${text}</span>`;
const slider = (label, max, step, aria) => `<div class="fleet-controls"><label class="fleet-time">${label} <output>0</output><input type="range" min="0" max="${max}" value="0" step="${step}" aria-label="${aria}"></label></div>`;

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

/* ── 1. what the balloon told us ───────────────────────────────────────────── */
async function packets(host, signal) {
  const [flight, coast] = await Promise.all([load('flight.json'), load('coast-atlantic.json')]);
  if (signal.aborted) return;
  const { t0, fixes, end } = flight;
  const distinct = fixes.filter(f => f[3]);
  const gaps = [];
  for (let i = 1; i < fixes.length; i++) if (fixes[i][0] - fixes[i - 1][0] >= 360) gaps.push([fixes[i - 1][0], fixes[i][0]]);
  const dark = gaps.reduce((s, [a, b]) => s + b - a, 0);
  host.innerHTML = `${heading('What the balloon told us', 'Stratolink 3, May 17 to 29')}
    <div class="fleet-metrics contact-metrics"><span><b>${fixes.length}</b>packets with a position</span><span><b>${distinct.length}</b>distinct positions</span><span><b>${fmt(dark / 60)} h</b>of ${fmt(end / 60)} in gaps over six hours</span></div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    <canvas class="packet-strip" role="img" aria-label="Timeline of received positions over the flight, with gaps longer than six hours shaded"></canvas>
    <div class="waterfall-axis"><span>May 17</span><span>May 23</span><span>May 29</span></div>
    ${slider('Flight hour', end, 10, 'Minutes since launch')}
    <output class="chart-readout"></output>`;
  const map = createMap(ATLANTIC, 'Received GPS positions of Stratolink 3 on a map of the North Atlantic. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const strip = host.querySelector('.packet-strip'), sctx = strip.getContext('2d');
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover');
  let cursor = 0, width = 0;
  function draw() {
    if (!width) return;
    map.base(coast);
    for (const [t, lat, lon, isDistinct] of fixes) {
      if (t > cursor) map.dot(lat, lon, 1.6, '#d2d3cc');
      else if (isDistinct) map.dot(lat, lon, 2.4, INK);
      else map.dot(lat, lon, 1.6, '#a3a59e');
    }
    const last = distinct.filter(f => f[0] <= cursor).at(-1);
    if (last) { map.dot(last[1], last[2], 6.5, '#f6f4ef', INK, 1.6); }
    for (const [a, b] of gaps) if (cursor >= a && cursor <= b) {
      const from = distinct.filter(f => f[0] <= a).at(-1);
      if (from) map.label(from[1], from[2], `${fmt((cursor - a) / 60)} h without a packet`, 11, -8, RED);
    }
    sctx.clearRect(0, 0, width, 30); sctx.fillStyle = '#e3e4dd'; sctx.fillRect(0, 6, width, 16);
    sctx.fillStyle = 'rgba(223,129,46,.28)';
    for (const [a, b] of gaps) sctx.fillRect(a / end * width, 6, (b - a) / end * width, 16);
    for (const [t, , , isDistinct] of fixes) { sctx.fillStyle = isDistinct ? INK : '#b3b5ae'; sctx.fillRect(t / end * width, 6, Math.max(.8, width / 1500), 16); }
    sctx.fillStyle = INK; sctx.fillRect(cursor / end * width - 1, 0, 2, 29);
    input.value = cursor; output.textContent = fmt(cursor / 60, 1);
    const ago = last ? (cursor - last[0]) / 60 : 0;
    read.textContent = `${utc(t0 + cursor * 60000)} / ${last ? `last position ${ago < 1 ? 'just now' : ago < 48 ? `${fmt(ago, 1)} hours ago` : `${fmt(ago / 24, 1)} days ago`}, ${place(last[1], last[2])}` : 'before launch'}`;
  }
  const play = player(host, signal, dt => { cursor += dt * .72; if (cursor > end + 1200) cursor = 0; cursor = Math.min(cursor, end + 1200); draw(); });
  bindSlider(input, play, value => { cursor = value; draw(); });
  keys(map.canvas, play, dir => { cursor = clamp(cursor + dir * 360, 0, end); draw(); });
  strip.onpointermove = event => { const b = strip.getBoundingClientRect(); play.set(false); cursor = clamp((event.clientX - b.left) / b.width * end, 0, end); draw(); };
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event);
    let best, bd = 14;
    for (const f of fixes) { if (f[0] > cursor) continue; const [fx, fy] = map.point(f[1], f[2]); const d = Math.hypot(fx - x, fy - y); if (d < bd) { bd = d; best = f; } }
    hover.hidden = !best;
    if (best) hover.textContent = `${utc(t0 + best[0] * 60000)} / ${place(best[1], best[2])}${best[3] ? '' : ' / repeated fix'}`;
  };
  map.canvas.onpointerleave = () => { hover.hidden = true; };
  observeChartSize(host, () => {
    width = host.clientWidth - 32; map.resize(width);
    const dpr = Math.min(devicePixelRatio || 1, 2);
    strip.width = width * dpr; strip.height = 30 * dpr; strip.style.width = `${width}px`; strip.style.height = '30px'; sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }, signal);
}

/* ── 2. the wind tube ──────────────────────────────────────────────────────── */
async function tube(host, signal) {
  const [meta, buffer, coast, flight] = await Promise.all([load('tube.json'), load('tube.bin'), load('coast-atlantic.json'), load('flight.json')]);
  if (signal.aborted) return;
  const winds = new Int8Array(buffer), { slices } = meta, last = slices.length - 1;
  host.innerHTML = `${heading('The wind tube', `GFS winds at ${fmt(meta.levelHpa)} hPa`)}
    <div class="chart-legend">${key('Slice boxes, one per 3 hours', BLUE)}${key('Winds in the current slice, slow to fast', 'linear-gradient(90deg,#382262,#2b90c2,#b8cb42,#d33a4d)')}${key('Reconstructed track', INK)}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    <div class="fleet-map-footer"><span class="fleet-date"></span><span class="fleet-source"></span></div>
    ${slider('Slice', last, .1, 'Reconstruction cube time slice')}
    <output class="chart-readout"></output>`;
  const map = createMap(ATLANTIC, 'Wind tube: one box of GFS winds per three-hour slice along the flight. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover'), date = host.querySelector('.fleet-date'), source = host.querySelector('.fleet-source');
  let at = 0, arrows = [];
  const windAt = (s, i, j) => { const o = s.off + (i * s.aLon + j) * 2; return [winds[o], winds[o + 1]]; };
  function draw() {
    if (!map.width) return;
    const k = clamp(Math.round(at), 0, last), s = slices[k], t = s.t;
    map.base(coast);
    const { ctx } = map;
    for (const b of slices) {
      const [x0, y1] = map.point(b.lat0, b.lon0), [x1, y0] = map.point(b.lat0 + b.h, b.lon0 + b.w);
      ctx.strokeStyle = BLUE; ctx.globalAlpha = b === s ? .9 : .1; ctx.lineWidth = b === s ? 1.4 : .7; ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
      if (b === s) { ctx.globalAlpha = .06; ctx.fillStyle = BLUE; ctx.fillRect(x0, y0, x1 - x0, y1 - y0); }
    }
    ctx.globalAlpha = 1;
    arrows = [];
    for (let i = 0; i < s.aLat; i++) for (let j = 0; j < s.aLon; j++) {
      const [u, v] = windAt(s, i, j), lat = s.lat0 + i * s.aStep, lon = s.lon0 + j * s.aStep, speed = Math.hypot(u, v);
      const [x, y] = map.point(lat, lon), len = clamp(speed / 2.6, 2, 15);
      arrows.push({ x, y, u, v, lat, lon, speed });
      ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(-v, u)); ctx.strokeStyle = `rgb(${heatColor(speed / 65).join(',')})`; ctx.globalAlpha = .6; ctx.lineWidth = 1.1;
      ctx.beginPath(); ctx.moveTo(-len / 2, 0); ctx.lineTo(len / 2, 0); ctx.lineTo(len / 2 - 2.4, -2); ctx.moveTo(len / 2, 0); ctx.lineTo(len / 2 - 2.4, 2); ctx.stroke(); ctx.restore();
    }
    const minutes = (t - flight.t0) / 60000, n = flight.track.findIndex(p => p[0] > minutes);
    map.line(flight.track, { color: INK, width: 1.4, end: n < 0 ? flight.track.length : n });
    let pos = s.pos;
    const next = slices[Math.min(last, k + 1)], f = at - k;
    if (pos && next.pos && f > 0) pos = [pos[0] + (next.pos[0] - pos[0]) * f, pos[1] + (next.pos[1] - pos[1]) * f];
    if (pos) map.dot(pos[0], pos[1], 4.5, '#f6f4ef', INK, 1.8);
    input.value = at; output.textContent = fmt(k); date.textContent = utc(t);
    source.textContent = `0.25° grid; one arrow per ${s.aStep.toFixed(2)}°`;
    let wind = '';
    if (pos) { const a = arrows.reduce((b, p) => km(p.lat, p.lon, pos[0], pos[1]) < km(b.lat, b.lon, pos[0], pos[1]) ? p : b, arrows[0]); wind = ` / wind near the balloon ${fmt(a.speed)} m/s toward ${toward(a.u, a.v)}`; }
    read.textContent = `Slice ${k + 1} of ${slices.length} / box ±${(s.w / 2).toFixed(1)}° around the track${pos ? wind : ' / before launch'}`;
  }
  const play = player(host, signal, dt => { at += dt * .0022; if (at > last + 8) at = 0; draw(); });
  bindSlider(input, play, value => { at = value; draw(); });
  keys(map.canvas, play, dir => { at = clamp(Math.round(at) + dir, 0, last); draw(); });
  map.canvas.onpointermove = event => {
    const [x, y] = map.pointer(event);
    const a = arrows.reduce((b, p) => Math.hypot(p.x - x, p.y - y) < Math.hypot(b.x - x, b.y - y) ? p : b, arrows[0]);
    const inside = a && Math.hypot(a.x - x, a.y - y) < 40;
    hover.hidden = !inside;
    if (inside) hover.textContent = `${place(a.lat, a.lon)} / ${fmt(a.speed)} m/s toward ${toward(a.u, a.v)}`;
  };
  map.canvas.onpointerleave = () => { hover.hidden = true; };
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 3. two ways to bridge the gap ─────────────────────────────────────────── */
async function methods(host, signal) {
  const [b, coast] = await Promise.all([load('bridges.json'), load('coast-atlantic.json')]);
  if (signal.aborted) return;
  host.innerHTML = `${heading('Two ways to bridge the gap', `${fmt(b.hours)} hours, New Mexico to Spain`, false)}
    <div class="capture-tabs" role="group" aria-label="Bridging method"><button type="button" data-method="forward" aria-pressed="true">Forward sampler</button><button type="button" data-method="twoFilter" aria-pressed="false">Two filters meeting in the middle</button></div>
    <div class="methods-settings"><label>Particles per run<select data-particles aria-label="Particles per run">${Object.keys(b.forward).map(n => `<option value="${n}">${fmt(n)}</option>`).join('')}</select></label><span class="methods-buttons"><button type="button" class="fleet-play" data-add>Add a rerun</button><button type="button" class="fleet-play" data-reset>Start over</button></span></div>
    <div class="fleet-map-stage"></div>
    <div class="chart-legend"></div>
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Reconstructed bridges across the eight-day gap from stored reruns of each method');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const legend = host.querySelector('.chart-legend'), read = host.querySelector('.chart-readout'), select = host.querySelector('[data-particles]'), add = host.querySelector('[data-add]');
  let method = 'forward', particles = select.value, shown = 1;
  const group = () => method === 'forward' ? b.forward[particles] : b.twoFilter;
  const A = b.drawn[0], B = b.drawn[b.drawn.length - 1];
  function draw() {
    if (!map.width) return;
    const { runs, spreadKm } = group();
    map.base(coast);
    runs.slice(0, shown).forEach((run, k) => map.line(run, { color: colors[k % 7], width: 1.7, alpha: .9 }));
    map.dot(A[0], A[1], 5, '#f6f4ef', INK, 1.6); map.dot(B[0], B[1], 5, '#f6f4ef', INK, 1.6);
    map.label(A[0], A[1], 'May 19', 9, 14); map.label(B[0], B[1], 'May 28', -9, 14);
    legend.innerHTML = runs.slice(0, shown).map((_, k) => key(`Run ${k + 1}`, colors[k % 7])).join('');
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

/* ── posterior draws shared by figures 4 and 5 ─────────────────────────────── */
async function posterior() {
  const [p, buffer] = await Promise.all([load('posterior.json'), load('posterior.bin')]);
  const pos = new Int16Array(buffer), { steps } = p;
  const at = (i, s) => {
    const a = Math.floor(s), b = Math.min(steps - 1, a + 1), t = s - a, ia = (i * steps + a) * 2, ib = (i * steps + b) * 2;
    return [(pos[ia] + (pos[ib] - pos[ia]) * t) / 100, (pos[ia + 1] + (pos[ib + 1] - pos[ia + 1]) * t) / 100];
  };
  const path = (i, from, to) => { const out = []; for (let s = from; s <= to; s++) out.push(at(i, s)); return out; };
  return { ...p, at, path, hoursPerStep: p.hours / (steps - 1) };
}

/* ── 4. two clouds meeting in the middle ───────────────────────────────────── */
async function meeting(host, signal) {
  const [p, coast] = await Promise.all([posterior(), load('coast-atlantic.json')]);
  if (signal.aborted) return;
  const { n, steps, hours, hoursPerStep, tA } = p, mid = (steps - 1) / 2, half = hours / 2;
  host.innerHTML = `${heading('Two clouds meeting in the middle', `${n} of the ${fmt(p.nTotal)} posterior draws`)}
    <div class="chart-legend">${key('Forward half, from New Mexico', BLUE)}${key('Backward half, from Spain', ORANGE)}${key('Joined bridge', '#9a9c95')}${key('The drawn line', RED)}</div>
    <div class="fleet-map-stage"></div>
    ${slider('Gap hour', hours, .5, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Forward and backward particle clouds crossing the Atlantic and meeting at the midpoint of the gap. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout');
  const A = p.drawn[0], B = p.drawn[steps - 1];
  let h = 0;
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, hours), sF = Math.min(hour / hoursPerStep, mid), sB = Math.max(steps - 1 - hour / hoursPerStep, mid);
    const reveal = clamp((hour - half) / (half * .6), 0, 1);
    map.base(coast);
    const { ctx } = map;
    if (reveal < 1) {
      for (let i = 0; i < n; i++) {
        map.line([...p.path(i, 0, Math.floor(sF)), p.at(i, sF)], { color: BLUE, width: .8, alpha: .14 * (1 - reveal) });
        map.line([p.at(i, sB), ...p.path(i, Math.ceil(sB), steps - 1)], { color: ORANGE, width: .8, alpha: .14 * (1 - reveal) });
      }
      for (let i = 0; i < n; i++) { const f = p.at(i, sF), bk = p.at(i, sB); map.dot(f[0], f[1], 1.7, BLUE, null, 1, .9 * (1 - reveal)); map.dot(bk[0], bk[1], 1.7, ORANGE, null, 1, .9 * (1 - reveal)); }
    }
    if (reveal > 0) {
      ctx.globalAlpha = 1;
      for (let i = 0; i < n; i++) map.line(p.path(i, 0, steps - 1), { color: '#9a9c95', width: .7, alpha: .22 * reveal });
      map.line(p.drawn, { color: RED, width: 2.4, alpha: reveal });
    }
    map.dot(A[0], A[1], 5, '#f6f4ef', INK, 1.6); map.dot(B[0], B[1], 5, '#f6f4ef', INK, 1.6);
    input.value = hour; output.textContent = fmt(hour);
    read.textContent = hour < half - 1
      ? `${utc(tA + hour * 3600000)} / forward particles ${fmt(hour)} h out of New Mexico, backward particles ${fmt(hour)} h back from Spain, neither aimed at the other end`
      : reveal <= 0
        ? `${utc(tA + hour * 3600000)} / the clouds meet: every forward particle is paired with the backward particles within reach, weighted by how closely the halves track across the overlap`
        : `${utc(tA + hour * 3600000)} / the pairs are the posterior; the drawn line is the average of the tenth of them that track the medoid most closely`;
  }
  const play = player(host, signal, dt => { h += dt * .013; if (h > hours + 55) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, hours) + dir * 6, 0, hours); draw(); });
  observeChartSize(host, () => { map.resize(host.clientWidth - 32); draw(); }, signal);
}

/* ── 5. which line to draw ─────────────────────────────────────────────────── */
async function line(host, signal) {
  const [p, cbuffer, coast] = await Promise.all([posterior(), load('clusters.bin'), load('coast-atlantic.json')]);
  if (signal.aborted) return;
  const labels = new Int8Array(cbuffer), kept = new Set(p.kept), { n, steps, hours, hoursPerStep, tA } = p;
  host.innerHTML = `${heading('Which line to draw', `${n} of the ${fmt(p.nTotal)} draws at one hour`)}
    <div class="capture-tabs" role="group" aria-label="Color the draws by"><button type="button" data-color="modes" aria-pressed="true">Clusters at this hour</button><button type="button" data-color="kept" aria-pressed="false">The kept tenth</button></div>
    <div class="fleet-metrics contact-metrics"><span><b data-m1>…</b>largest cluster</span><span><b data-m2>…</b>second cluster</span><span><b data-near-mean>…</b>within 300 km of the mean</span><span><b data-near-line>…</b>within 300 km of the drawn line</span></div>
    <div class="chart-legend">${key('Posterior mean', INK, 'cross')}${key('Medoid, the most central draw', INDIGO, 'ring')}${key('The drawn line', RED)}${key('Posterior mean path', '#8a8c86', 'dash')}</div>
    <div class="fleet-map-stage"><output class="fleet-hover" hidden></output></div>
    ${slider('Gap hour', hours, 1, 'Hours into the gap')}
    <output class="chart-readout"></output>`;
  const map = createMap(GAP_VIEW, 'Where the posterior draws put the balloon at one hour of the gap, with the posterior mean, the medoid and the drawn line. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout'), hover = host.querySelector('.fleet-hover');
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
      const [lat, lon] = p.at(i, s), label = labels[i * steps + si];
      const isKept = kept.has(i);
      const color = mode === 'modes' ? MODE_COLORS[Math.min(label, 6)] : isKept ? BLUE : FAINT;
      map.dot(lat, lon, mode === 'kept' && isKept ? 2.8 : 2.1, color, null, 1, mode === 'kept' && !isKept ? .6 : .8);
      dots.push({ lat, lon, label, isKept });
    }
    const m = p.mean[si], md = p.medoid[si], d = p.drawn[si];
    map.dot(md[0], md[1], 5, null, INDIGO, 2);
    map.cross(m[0], m[1], 5.5, INK);
    map.dot(d[0], d[1], 4.5, RED, '#f6f4ef', 1.5);
    const [m1, m2] = stats.modes;
    get('[data-m1]').textContent = m1 ? `${fmt(m1[0] * 100)}%` : '—';
    get('[data-m2]').textContent = m2 ? `${fmt(m2[0] * 100)}%` : 'none';
    get('[data-near-mean]').textContent = `${fmt(stats.within300.mean * 100)}%`;
    get('[data-near-line]').textContent = `${fmt(stats.within300.drawn * 100)}%`;
    input.value = hour; output.textContent = fmt(hour);
    read.textContent = `${utc(tA + hour * 3600000)} / ${stats.modes.length === 1 ? 'one cluster' : `${stats.modes.length} clusters`} / mean ${place(m[0], m[1])} / drawn line ${place(d[0], d[1])}, ${fmt(km(m[0], m[1], d[0], d[1]))} km apart`;
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
    <div class="chart-stage"><svg class="spread-chart" role="img" aria-label="Ensemble spread against forecast day, with the 2,000 km stopping threshold"></svg></div>
    ${slider('Forecast hour', total, 1, 'Hours after the last fix')}
    <output class="chart-readout"></output>`;
  const map = createMap(WORLD, 'Sixty-two ensemble trajectories from the last fix in Spain eastward around the world. Space plays, arrow keys step.');
  host.querySelector('.fleet-map-stage').prepend(map.canvas);
  const svg = host.querySelector('.spread-chart'), input = host.querySelector('input'), output = host.querySelector('output'), read = host.querySelector('.chart-readout');
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
    svg.append(el('circle', { cx: sx(hour), cy: sy(spread), r: 4, fill: BLUE, stroke: '#f6f4ef', 'stroke-width': 2 }));
  }
  function draw() {
    if (!map.width) return;
    const hour = Math.min(h, total), s = hour / stepH, done = hour >= total - 1e-9;
    map.base(coast, 30);
    const { ctx } = map;
    ctx.globalAlpha = 1;
    for (let m = 0; m < members; m++) {
      const pts = []; for (let k = 0; k <= Math.floor(s); k++) pts.push(at(m, k)); pts.push(at(m, s));
      map.line(pts, { color: BLUE, width: .8, alpha: .32 });
    }
    for (let m = 0; m < members; m++) { const q = at(m, s); map.dot(q[0], q[1], 1.6, BLUE, null, 1, .8); }
    const med = median.slice(0, Math.floor(s) + 1); const ms = median[Math.min(steps - 1, Math.ceil(s))], mf = median[Math.floor(s)];
    med.push([mf[0] + (ms[0] - mf[0]) * (s - Math.floor(s)), mf[1] + (ms[1] - mf[1]) * (s - Math.floor(s))]);
    map.line(med, { color: INK, width: 2 });
    map.dot(f.lastFix[0], f.lastFix[1], 5, '#f6f4ef', INK, 1.6);
    map.label(f.lastFix[0], f.lastFix[1], 'last fix, May 29', 9, 16);
    if (done) {
      const [x, y] = map.point(f.divergence.lat, f.divergence.lon);
      ctx.fillStyle = RED; ctx.beginPath(); ctx.moveTo(x, y - 7); ctx.lineTo(x + 7, y); ctx.lineTo(x, y + 7); ctx.lineTo(x - 7, y); ctx.closePath(); ctx.fill();
      map.label(f.divergence.lat, f.divergence.lon, `forecast ends: spread ${fmt(f.divergence.spreadKm)} km`, -11, -10, RED);
    }
    const spread = spreadAt(s);
    host.querySelector('[data-day]').textContent = fmt(hour / 24, 1);
    host.querySelector('[data-spread]').textContent = `${fmt(spread)} km`;
    drawChart(hour, spread);
    input.value = hour; output.textContent = fmt(hour);
    read.textContent = `${utc(start + hour * 3600000)} / 75% of the members within ${fmt(spread)} km of the median${done ? ` / past ${fmt(thresholdKm)} km the median is not predicting anything, so the line stops here` : ''}`;
  }
  const play = player(host, signal, dt => { h += dt * .016; if (h > total + 70) h = 0; draw(); });
  bindSlider(input, play, value => { h = value; draw(); });
  keys(map.canvas, play, dir => { h = clamp(Math.min(h, total) + dir * 12, 0, total); draw(); });
  observeChartSize(host, () => { width = host.clientWidth - 32; map.resize(width); draw(); }, signal);
}

const figures = { packets, tube, methods, meeting, line, forecast };

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
