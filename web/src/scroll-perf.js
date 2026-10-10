// Dev-only scroll smoothness overlay. Opt in with ?perf on the homepage; add &static to freeze the
// scroll-driven scene script so compositor-only scrolling can be compared against the JS-driven scene.
const FLAG_CSS = {
  // Each flag removes one suspect so the judder can be bisected on a real device.
  noimages: '.scene-layer img, .scene-placeholder { visibility: hidden !important }',
  nolayers: '.foreground-layer, .balloon-layer, .story, .scene-warmth { will-change: auto !important }',
  nomask: '.story-window { mask-image: none !important; -webkit-mask-image: none !important }',
  nowarmth: '.scene-warmth { display: none !important }',
  nofooter: '.site-footer, .footer-globe-portal { display: none !important }',
  noshadow: '.story-blog-card { box-shadow: none !important }',
  noglobe: '', // handled in footer-globe.js: the dashboard iframe is never created
};
export function start({ staticScene }) {
  const params = new URLSearchParams(location.search);
  const flags = Object.keys(FLAG_CSS).filter(flag => params.has(flag));
  const css = flags.map(flag => FLAG_CSS[flag]).filter(Boolean).join('\n');
  if (css) { const style = document.createElement('style'); style.textContent = css; document.head.append(style); }
  const box = document.createElement('div');
  box.id = 'scroll-perf';
  box.style.cssText = 'position:fixed;left:8px;right:8px;bottom:8px;z-index:99999;padding:8px 10px;border-radius:8px;' +
    'background:rgba(0,0,0,.8);color:#fff;font:12px/1.4 ui-monospace,Menlo,monospace;white-space:pre-wrap;pointer-events:auto';
  document.body.append(box);

  const scene = (window.__scenePerf ??= { ms: [] });
  let lastFrame = 0, lastScroll = -1e9, minDelta = Infinity;
  const stats = { frames: 0, sum: 0, worst: 0, dropped: 0, long: 0, deltas: [] };
  const reset = () => { stats.frames = 0; stats.sum = 0; stats.worst = 0; stats.dropped = 0; stats.long = 0; stats.deltas = []; scene.ms = []; };

  addEventListener('scroll', () => { lastScroll = performance.now(); }, { passive: true });
  function tick(now) {
    if (lastFrame) {
      const delta = now - lastFrame;
      if (delta < minDelta && delta > 4) minDelta = delta;
      if (now - lastScroll < 120) { // only count frames while the page is actually scrolling
        stats.frames++; stats.sum += delta; stats.deltas.push(delta);
        if (delta > stats.worst) stats.worst = delta;
      }
    }
    lastFrame = now;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  function render() {
    const expected = minDelta < 12 ? 1000 / 120 : 1000 / 60; // rAF cadence this browser is actually giving us
    stats.dropped = stats.deltas.filter(d => d > expected * 1.5).length;
    stats.long = stats.deltas.filter(d => d > 50).length;
    const fps = stats.frames ? 1000 / (stats.sum / stats.frames) : 0;
    const sceneAvg = scene.ms.length ? scene.ms.reduce((a, b) => a + b, 0) / scene.ms.length : 0;
    const sceneMax = scene.ms.length ? Math.max(...scene.ms) : 0;
    box.textContent =
      `mode ${staticScene ? 'STATIC (scene script off)' : 'JS scene'}${flags.length ? ' + ' + flags.join(',') : ''}   rAF ${Math.round(1000 / expected)} Hz   ${innerWidth}×${innerHeight} @${devicePixelRatio}x\n` +
      `scrolling: ${fps.toFixed(0)} fps over ${stats.frames} frames   dropped ${stats.dropped}   >50ms ${stats.long}   worst ${stats.worst.toFixed(0)} ms\n` +
      `scene script per frame: avg ${sceneAvg.toFixed(2)} ms  max ${sceneMax.toFixed(1)} ms\n` +
      `${timingLine()}\n` +
      `tap = reset   ·   ${staticScene ? '[switch to JS]' : '[switch to STATIC]'}`;
  }
  setInterval(render, 300);
  // Also report to a local collector (a dev machine on the LAN listening on :5174), so the numbers can be
  // read without transcribing them off the phone. Opaque no-cors POST: fire and forget.
  let reported = -1;
  setInterval(() => {
    if (stats.frames === reported || stats.frames === 0) return;
    reported = stats.frames;
    const expected = minDelta < 12 ? 1000 / 120 : 1000 / 60;
    const body = JSON.stringify({
      at: new Date().toISOString(), mode: staticScene ? 'static' : 'js', flags, ua: navigator.userAgent,
      viewport: `${innerWidth}x${innerHeight}@${devicePixelRatio}`, rafHz: Math.round(1000 / expected),
      frames: stats.frames, fps: +(stats.frames ? 1000 / (stats.sum / stats.frames) : 0).toFixed(1),
      dropped: stats.dropped, over50ms: stats.long, worstMs: +stats.worst.toFixed(1),
      sceneAvgMs: +(scene.ms.length ? scene.ms.reduce((a, b) => a + b, 0) / scene.ms.length : 0).toFixed(3),
      sceneMaxMs: +(scene.ms.length ? Math.max(...scene.ms) : 0).toFixed(2),
      histogram: histogram(stats.deltas, expected),
      heroReadyMs: Math.round(window.__heroReadyAt ?? -1), globeStartMs: Math.round(window.__globeTiming?.loadAt ?? -1), globeReadyMs: Math.round(window.__globeTiming?.readyAt ?? -1),
      portal: portalState(),
    });
    fetch(`http://${location.hostname}:5174/perf`, { method: 'POST', mode: 'no-cors', body, headers: { 'Content-Type': 'text/plain' }, keepalive: true }).catch(() => {});
  }, 2000);
  // Once the globe reports ready, post the iframe's resource waterfall (same origin, so its timing is readable).
  let waterfallSent = false;
  setInterval(() => {
    const g = window.__globeTiming ?? {};
    if (waterfallSent || g.readyAt == null) return;
    waterfallSent = true;
    const frame = document.querySelector('.footer-globe-portal iframe');
    const perf = frame?.contentWindow?.performance;
    if (!perf) return;
    const nav = perf.getEntriesByType('navigation')[0];
    const label = u => u.replace(/^https?:\/\/[^/]+/, '').replace(/\?.*$/, '').replace(/^\/assets\//, '').replace(/-[\w-]{8,}\.js$/, '.js');
    const rows = perf.getEntriesByType('resource').map(r => ({ n: label(r.name) + (/api\/telemetry/.test(r.name) ? ' (' + (r.name.includes('limit=') ? 'latest' : 'q') + ')' : ''), s: Math.round(r.startTime), e: Math.round(r.responseEnd), kb: Math.round((r.transferSize || r.encodedBodySize || 0) / 1024), host: new URL(r.name).host }))
      .filter(r => r.e - r.s > 0 || r.kb > 0);
    const body = JSON.stringify({ at: new Date().toISOString(), kind: 'waterfall', ua: navigator.userAgent,
      iframeStartMs: Math.round(g.loadAt ?? -1), bootedMs: Math.round(g.bootedAt ?? -1), globeReadyMs: Math.round(g.readyAt ?? -1),
      iframeNav: nav ? { responseEnd: Math.round(nav.responseEnd), domInteractive: Math.round(nav.domInteractive) } : null,
      mapTiming: frame.contentWindow.__mapTiming ?? null, rows });
    fetch(`http://${location.hostname}:5174/perf`, { method: 'POST', mode: 'no-cors', body, headers: { 'Content-Type': 'text/plain' }, keepalive: true }).catch(() => {});
  }, 500);
  function portalState() {
    try {
      const p = document.querySelector('.footer-globe-portal'); const f = p?.querySelector('iframe'); const w = f?.contentWindow; const d = f?.contentDocument;
      const c = d?.querySelector('.mapboxgl-canvas');
      return { visible: !!p?.classList.contains('is-visible'), reveal: p ? getComputedStyle(p).getPropertyValue('--globe-reveal').trim() : null,
        frameVisibility: f ? getComputedStyle(f).visibility : null, clip: p?.style.clipPath || null, stage: d?.documentElement?.dataset?.globePortal ?? null,
        canvas: c ? [c.width, c.height, c.clientWidth, c.clientHeight] : null, mapTiming: w?.__mapTiming ?? null, mapErrors: w?.__mapErrors ?? null,
        darkScheme: matchMedia('(prefers-color-scheme: dark)').matches, scrollY: Math.round(scrollY), pageHeight: document.documentElement.scrollHeight };
    } catch (error) { return { error: String(error) }; }
  }
  function timingLine() {
    const g = window.__globeTiming ?? {};
    const ms = v => (v == null ? '—' : `${Math.round(v)} ms`);
    return `hero ready ${ms(window.__heroReadyAt)}   globe start ${ms(g.loadAt)}   globe ready ${ms(g.readyAt)}`;
  }
  function histogram(deltas, expected) {
    const buckets = { onTime: 0, x2: 0, x3: 0, x4plus: 0 };
    for (const d of deltas) {
      const n = Math.round(d / expected);
      if (n <= 1) buckets.onTime++; else if (n === 2) buckets.x2++; else if (n === 3) buckets.x3++; else buckets.x4plus++;
    }
    return buckets;
  }
  box.addEventListener('click', (event) => {
    const url = new URL(location.href);
    if (/switch to/.test(box.textContent) && event.offsetY > box.clientHeight * .7) {
      if (staticScene) url.searchParams.delete('static'); else url.searchParams.set('static', '');
      location.href = url.toString();
      return;
    }
    reset();
  });
}
