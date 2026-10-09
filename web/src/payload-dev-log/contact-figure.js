import { colors, heatColor, observeChartSize } from './charts.js';
import { loadFleet } from './fleet-data.js';

const percent = value => `${(value * 100).toFixed(1)}%`;
const duration = hours => hours > 168 ? '>7 days' : hours < 48 ? `${hours.toFixed(1)} hours` : `${(hours / 24).toFixed(1)} days`;
const coordinate = (value, positive, negative) => `${Math.abs(value).toFixed(1)}°${value >= 0 ? positive : negative}`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const NS = 'http://www.w3.org/2000/svg';
function element(name, attributes, text) {
  const node = document.createElementNS(NS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}

export async function contactFigure(host, signal) {
  const { meta, tracks, coast } = await loadFleet();
  if (signal.aborted) return;
  host.innerHTML = `<div class="chart-heading">Waiting for a balloon <span>14-day wind model</span></div>
    <div class="contact-settings">
      <label>Start<select data-mode><option value="world">Both hemispheres</option><option value="north">North</option><option value="south">South</option></select></label>
      <label>Area<select data-region><option value="earth">Whole Earth</option><option value="north">North</option><option value="south">South</option><option value="point">Selected location</option></select></label>
    </div>
    <div class="fleet-controls contact-controls">
      <label>Balloons <output>100</output><input data-count type="range" min="1" max="500" value="100" aria-label="Waiting-time balloon count"></label>
      <label>Radius <output>350 km</output><input data-radius type="range" min="200" max="500" step="25" value="350" aria-label="Waiting-time radius in kilometers"></label>
    </div>
    <div class="contact-results" aria-busy="true">
      <div class="fleet-metrics contact-metrics"><span><b data-mean>…</b>mean wait <small>(7-day cap)</small></span><span><b data-day>…</b>within 1 day</span><span><b data-week>…</b>within 7 days</span></div>
      <canvas class="fleet-map contact-map" tabindex="0" role="img" aria-label="Modeled waiting time across Earth. Select a location, or use arrow keys and Enter."></canvas>
      <div class="contact-map-key"><span>0h</span><i class="spectrum-key"></i><span>7d</span><span title="No contact in the 14-day model"><i class="contact-unreached"></i>Unreached</span></div>
      <output class="contact-location">Select a location</output>
      <div class="chart-heading contact-curve-heading">Fleet size</div>
      <div class="capture-tabs contact-chart-tabs" aria-label="Coverage comparison"><button type="button" data-comparison="deadline" aria-pressed="true">Contact by deadline</button><button type="button" data-comparison="wait" aria-pressed="false">Mean wait</button></div>
      <div class="chart-legend" data-deadline-legend><span class="chart-key"><i style="background:${colors[2]}"></i>1 day</span><span class="chart-key"><i style="background:${colors[3]}"></i>3 days</span><span class="chart-key"><i style="background:${colors[6]}"></i>7 days</span></div>
      <svg class="contact-curve" role="img" tabindex="0" aria-label="Fraction of message arrivals with a contact within one, three, or seven days. Arrow keys inspect balloon counts."></svg>
      <output class="chart-readout" data-curve-readout></output>
      <div class="contact-point" hidden><div class="chart-heading">Contact windows</div>
        <canvas class="contact-timeline" role="img" aria-label="Hours when a balloon footprint reaches the selected location, over fourteen days"></canvas>
        <div class="waterfall-axis"><span>Day 0</span><span>Day 7</span><span>Day 14</span></div>
        <label class="chart-control">Message day <output>0.0</output><input data-arrival type="range" min="0" max="167" value="0" aria-label="Message arrival hour in the first week"></label>
        <output class="chart-readout" data-arrival-readout></output>
      </div>
    </div>
    <details class="contact-details"><summary>Model details</summary><p class="contact-area"></p><p class="contact-method">Hourly arrivals in week 1, with waits capped at 7 days. Geometric range only; power and packet delivery are not modeled.</p></details>`;

  const get = selector => host.querySelector(selector);
  const map = get('.contact-map'), ctx = map.getContext('2d'), curve = get('.contact-curve');
  const timeline = get('.contact-timeline'), timeCtx = timeline.getContext('2d');
  const modeInput = get('[data-mode]'), regionInput = get('[data-region]'), countInput = get('[data-count]'), radiusInput = get('[data-radius]'), arrivalInput = get('[data-arrival]');
  const worker = new Worker(new URL('./contact-worker.js', import.meta.url), { type: 'module' });
  worker.postMessage({ type: 'init', tracks, hours: meta.steps + 1 });
  let mode = 'world', region = 'earth', count = 100, radius = 350, location = { lat: 0, lon: -140 };
  let result, width = 0, height = 0, version = 0, inFlight = false, pending = false, timer, focusCount = 4, comparison = 'deadline';

  function request() {
    version++;
    get('.contact-results').setAttribute('aria-busy', 'true');
    clearTimeout(timer);
    timer = setTimeout(send, 90);
  }
  function send() {
    if (signal.aborted) return;
    if (inFlight) { pending = true; return; }
    inFlight = true; pending = false;
    worker.postMessage({ id: version, mode, radius, count, location });
  }
  worker.onmessage = ({ data }) => {
    inFlight = false;
    if (data.id === version) {
      if (data.error) get('[data-curve-readout]').textContent = data.error;
      else { result = data; draw(); }
      get('.contact-results').setAttribute('aria-busy', 'false');
    }
    if (pending || data.id !== version) send();
  };
  worker.onerror = () => {
    get('.contact-results').setAttribute('aria-busy', 'false');
    get('[data-curve-readout]').textContent = 'Coverage calculation could not load. Reload to try again.';
  };

  function project(lat, lon) { return [(lon + 180) / 360 * width, (90 - lat) / 180 * height]; }
  function drawMap() {
    ctx.clearRect(0, 0, width, height); ctx.fillStyle = '#eeeee9'; ctx.fillRect(0, 0, width, height);
    const size = Math.max(1.25, width / 370);
    for (const [lat, lon, mean, reached] of result.selected.map) {
      const [x, y] = project(lat, lon);
      ctx.fillStyle = reached ? `rgb(${heatColor(mean / 168).join(',')})` : '#c3c6bf';
      ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI * 2); ctx.fill();
    }
    ctx.strokeStyle = '#4e574e88'; ctx.lineWidth = .7;
    for (const line of coast) {
      ctx.beginPath(); let previous;
      for (const [lon, lat] of line) {
        const [x, y] = project(lat, lon);
        if (previous === undefined || Math.abs(x - previous) > width / 2) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        previous = x;
      }
      ctx.stroke();
    }
    const [x, y] = project(location.lat, location.lon);
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fillStyle = '#f6f4ef'; ctx.fill(); ctx.strokeStyle = '#292927'; ctx.lineWidth = 2; ctx.stroke();
  }

  function curveSeries() {
    return region === 'point' ? result.localCurves : result.curves.map(row => ({ ...row.regions[region], count: row.count }));
  }
  function drawCurve() {
    const h = width < 450 ? 225 : 255, left = 36, right = 12, top = 12, bottom = 36;
    const isWait = comparison === 'wait', maximum = isWait ? 168 : 1;
    get('[data-deadline-legend]').hidden = isWait;
    curve.setAttribute('aria-label', isWait ? 'Mean waiting time capped at seven days by balloon count. Arrow keys inspect counts.' : 'Fraction of message arrivals with a contact within one, three, or seven days. Arrow keys inspect balloon counts.');
    const sx = n => left + (n - 1) / 499 * (width - left - right), sy = p => top + (1 - p / maximum) * (h - top - bottom);
    curve.setAttribute('viewBox', `0 0 ${width} ${h}`); curve.setAttribute('width', width); curve.setAttribute('height', h); curve.replaceChildren();
    for (const p of isWait ? [0, 24, 72, 120, 168] : [0, .25, .5, .75, 1]) {
      curve.append(element('line', { x1: left, x2: width - right, y1: sy(p), y2: sy(p), class: 'grid-line' }), element('text', { x: left - 7, y: sy(p) + 4, 'text-anchor': 'end', class: 'tick' }, isWait ? `${p / 24}d` : `${p * 100}%`));
    }
    for (const n of [1, 100, 200, 300, 400, 500]) curve.append(element('text', { x: sx(n), y: h - 14, 'text-anchor': 'middle', class: 'tick' }, n));
    const rows = curveSeries();
    for (const [key, color] of isWait ? [['meanCapped', colors[4]]] : [['day', colors[2]], ['threeDays', colors[3]], ['week', colors[6]]]) {
      curve.append(element('path', { d: rows.map((row, i) => `${i ? 'L' : 'M'}${sx(row.count)},${sy(row[key])}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 2.2 }));
      rows.forEach(row => curve.append(element('circle', { cx: sx(row.count), cy: sy(row[key]), r: 2.6, fill: color })));
    }
    const row = rows[focusCount];
    curve.append(element('line', { x1: sx(row.count), x2: sx(row.count), y1: top, y2: h - bottom, stroke: '#29292766', 'stroke-dasharray': '3 4' }));
    get('[data-curve-readout]').textContent = isWait
      ? `${row.count} balloons / ${duration(row.meanCapped)} mean wait`
      : `${row.count} balloons / 1 day: ${percent(row.day)} / 3 days: ${percent(row.threeDays)} / 7 days: ${percent(row.week)}`;
  }

  function drawTimeline() {
    timeCtx.clearRect(0, 0, width, 30); timeCtx.fillStyle = '#e3e4dd'; timeCtx.fillRect(0, 6, width, 16);
    timeCtx.fillStyle = colors[3];
    result.contacts.forEach((contact, hour) => { if (contact) timeCtx.fillRect(hour / 337 * width, 6, Math.max(.7, width / 337), 16); });
    const arrival = +arrivalInput.value, x = arrival / 337 * width;
    timeCtx.fillStyle = '#292927'; timeCtx.fillRect(x, 0, 2, 29);
    const wait = result.local.waits[arrival];
    arrivalInput.previousElementSibling.textContent = (arrival / 24).toFixed(2);
    get('[data-arrival-readout]').textContent = wait > 168 ? 'No contact within 7 days' : wait === 0 ? 'In range' : `Next contact in ${duration(wait)}`;
  }

  function draw() {
    if (!result || !width) return;
    const local = region === 'point', stats = local ? result.local : result.selected.regions[region];
    get('[data-mean]').textContent = duration(stats.meanCapped);
    get('[data-day]').textContent = percent(stats.day);
    get('[data-week]').textContent = percent(stats.week);
    get('.contact-location').textContent = local ? `${coordinate(location.lat, 'N', 'S')}, ${coordinate(location.lon, 'E', 'W')}` : 'Select a location';
    get('.contact-area').textContent = local
      ? `Median wait: ${duration(stats.median)}. 90th percentile: ${duration(stats.p90)}. ${stats.everyWeek ? 'Every sampled arrival found an opportunity within 7 days.' : 'Some sampled arrivals waited more than 7 days.'}`
      : `${percent(stats.reachedWeek)} of this area reached at least once in week 1; ${percent(stats.reachedFortnight)} in 14 days. ${percent(stats.everyWeek)} had a contact within 7 days of every sampled arrival.`;
    get('.contact-point').hidden = !local;
    drawMap(); drawCurve(); drawTimeline();
  }
  modeInput.onchange = () => { mode = modeInput.value; request(); };
  regionInput.onchange = () => { region = regionInput.value; draw(); };
  countInput.oninput = () => {
    count = +countInput.value; countInput.previousElementSibling.textContent = count;
    if (result) focusCount = result.curves.reduce((best, row, i) => Math.abs(row.count - count) < Math.abs(result.curves[best].count - count) ? i : best, 0);
    request();
  };
  radiusInput.oninput = () => { radius = +radiusInput.value; radiusInput.previousElementSibling.textContent = `${radius} km`; request(); };
  arrivalInput.oninput = drawTimeline;
  host.querySelectorAll('[data-comparison]').forEach(button => {
    button.onclick = () => {
      comparison = button.dataset.comparison;
      host.querySelectorAll('[data-comparison]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
      if (result) drawCurve();
    };
  });
  function chooseLocation() { region = 'point'; regionInput.value = region; request(); }
  map.onclick = event => {
    const bounds = map.getBoundingClientRect();
    location = { lat: clamp(90 - (event.clientY - bounds.top) / bounds.height * 180, -90, 90), lon: clamp((event.clientX - bounds.left) / bounds.width * 360 - 180, -180, 180) };
    chooseLocation();
  };
  map.onkeydown = event => {
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter'].includes(event.key)) return;
    event.preventDefault();
    location.lat = clamp(location.lat + (event.key === 'ArrowUp' ? 1 : event.key === 'ArrowDown' ? -1 : 0), -90, 90);
    location.lon = ((location.lon + (event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0) + 540) % 360) - 180;
    chooseLocation();
  };
  curve.onpointermove = event => {
    if (!result) return;
    const bounds = curve.getBoundingClientRect(), n = 1 + ((event.clientX - bounds.left) / bounds.width * width - 36) / (width - 48) * 499;
    const rows = curveSeries(); focusCount = rows.reduce((best, row, i) => Math.abs(row.count - n) < Math.abs(rows[best].count - n) ? i : best, 0); drawCurve();
  };
  curve.onkeydown = event => {
    if (!result || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); focusCount = event.key === 'Home' ? 0 : event.key === 'End' ? 7 : clamp(focusCount + (event.key === 'ArrowRight' ? 1 : -1), 0, 7); drawCurve();
  };
  observeChartSize(host, () => {
    width = host.clientWidth - 32; height = width / 2;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    for (const [canvas, context, h] of [[map, ctx, height], [timeline, timeCtx, 30]]) {
      canvas.width = width * ratio; canvas.height = h * ratio; canvas.style.width = `${width}px`; canvas.style.height = `${h}px`; context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    draw();
  }, signal);
  signal.addEventListener('abort', () => { clearTimeout(timer); worker.terminate(); }, { once: true });
  request();
}
