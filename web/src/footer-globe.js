import { faCircleInfo } from '@fortawesome/free-solid-svg-icons';

const footer = document.querySelector('.site-footer');
const home = document.querySelector('main');
const header = document.querySelector('.site-header');
const scene = document.querySelector('.launch-viewport');
const warmth = document.querySelector('.scene-warmth');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const portal = document.createElement('div');
portal.className = 'footer-globe-portal';
portal.innerHTML = `<iframe title="Stratolink fleet globe" tabindex="-1" aria-hidden="true"></iframe>
  <a class="footer-globe-trigger" href="/dashboard" aria-label="Explore the balloon dashboard" title="Explore dashboard"></a>
  <div class="footer-globe-credit"><a href="https://www.mapbox.com/" aria-label="Mapbox"><img src="/assets/mapbox-attribution.svg" width="62" height="17" alt="Mapbox"></a><details class="footer-globe-attribution"><summary aria-label="Map attribution"><svg viewBox="0 0 ${faCircleInfo.icon[0]} ${faCircleInfo.icon[1]}" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="${faCircleInfo.icon[4]}"/></svg></summary><div><a href="https://www.mapbox.com/about/maps/">© Mapbox</a><a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a><a href="https://apps.mapbox.com/feedback/">Improve this map</a></div></details></div>`;
document.body.append(portal);
const frame = portal.querySelector('iframe');
const trigger = portal.querySelector('.footer-globe-trigger');
const credit = portal.querySelector('.footer-globe-credit');
frame.inert = true;
let loaded = false, ready = false, stage = 'footer';
let animation, navigationTimer, motionFrame;
let footerScroll = 0, previewVisible = null;
const send = (next) => frame.contentWindow?.postMessage({ channel:'stratolink-globe', stage:next }, location.origin);

const timing = (window.__globeTiming ??= {});
function load() {
  if (loaded || new URLSearchParams(location.search).has('noglobe')) return; // ?perf&noglobe diagnostic
  loaded = true;
  timing.loadAt = performance.now();
  frame.src = '/dashboard?portal=footer';
  // Watchdog: if the dashboard shell never reports in (an import failed mid-boot, say), reload the iframe once.
  setTimeout(() => {
    if (!timing.bootedAt && !document.hidden && !watchdogReloaded && stage === 'footer') { watchdogReloaded = true; frame.src = frame.src; }
  }, 20000);
}
let watchdogReloaded = false;
// Where scroll-driven animations exist, the globe's position, reveal and clip are compiled into keyframes against
// the document scroll (see writeGlobeProgram) and run on the compositor in lockstep with the scroll. Positioning a
// fixed element from scroll events instead trails the page by a frame, which on a 120 Hz phone reads as rubber-banding.
const cssScroll = typeof CSS !== 'undefined' && CSS.supports('animation-timeline: scroll()') && !new URLSearchParams(location.search).has('jsglobe');
const smooth = (value) => value * value * (3 - 2 * value);
const clamp01 = (value) => Math.max(0, Math.min(1, value));
function globeGeometry() {
  const W = innerWidth, H = innerHeight, mobile = W < 768;
  const diameter = mobile ? Math.min(440, W * 1.1) * 1.035 : (Math.min(680, W * .55, H * .92) + Math.max(0, W - 1440) * .55) * 1.065;
  const x = W - diameter * (mobile ? -.02 : .18);
  const footerBottom = footer.getBoundingClientRect().bottom + scrollY; // document space
  return { W, H, mobile, diameter, x, footerBottom, maxScroll: Math.max(1, document.documentElement.scrollHeight - H) };
}
// Everything the footer globe needs at a given document scroll offset.
function globeAt(g, scroll) {
  const y = g.footerBottom - scroll - g.diameter * .24;
  const progress = clamp01((g.H - (y - g.diameter * .55)) / (g.diameter * .45));
  const reveal = reduced.matches ? 1 : smooth(progress);
  const lift = reduced.matches ? 0 : (1 - reveal) * 18;
  const scale = g.diameter / (Math.min(g.W, g.H) * .82) * (.985 + reveal * .015);
  return { y, progress, reveal, lift, scale, clip: Math.max(0, Math.min(g.H, y - g.diameter * .65)), credit: Math.max(0, g.footerBottom - scroll - g.H) };
}
let program, programKey = '', geometry;
function writeGlobeProgram() {
  if (!cssScroll) return;
  geometry = globeGeometry();
  const g = geometry;
  const key = JSON.stringify([g.W, g.H, g.footerBottom, g.maxScroll, reduced.matches, stage]);
  if (key === programKey) return;
  programKey = key;
  program ??= document.head.appendChild(Object.assign(document.createElement('style'), { id: 'globe-program' }));
  if (stage !== 'footer') { program.textContent = ''; return; }
  // Sample densely across the reveal (where opacity, lift and scale curve) and at the clip clamps; linear elsewhere.
  const revealStart = g.footerBottom - g.H - g.diameter * .79, revealEnd = revealStart + g.diameter * .45;
  const clipTopStart = g.footerBottom - g.diameter * .89 - g.H, clipTopEnd = g.footerBottom - g.diameter * .89;
  const samples = new Set([0, g.maxScroll, clipTopStart, clipTopEnd, g.footerBottom - g.H]);
  for (let i = 0; i <= 16; i++) samples.add(revealStart + (revealEnd - revealStart) * i / 16);
  const scrolls = [...samples].map(v => Math.max(0, Math.min(g.maxScroll, v))).sort((a, b) => a - b);
  const px = (v) => `${v.toFixed(2)}px`;
  const frames = (body) => scrolls.map(scroll => `${(100 * scroll / g.maxScroll).toFixed(4)}% { ${body(globeAt(g, scroll))} }`).join('\n');
  const timeline = `animation-timeline: scroll(root block); animation-range: 0px ${px(g.maxScroll)};`;
  program.textContent = `
@keyframes globe-frame { ${frames(a => `transform: translate3d(${px(g.x - g.W / 2)}, ${px(a.y + a.lift - g.H / 2)}, 0) scale(${a.scale.toFixed(5)}) scale(var(--globe-hover-scale)); opacity: ${a.reveal.toFixed(4)}`)} }
@keyframes globe-clip { ${frames(a => `clip-path: inset(${px(a.clip)} 0px 0px 0px)`)} }
@keyframes globe-trigger { ${frames(a => `transform: translate3d(${px(g.x - g.diameter / 2)}, ${px(a.y - g.diameter / 2)}, 0)`)} }
@keyframes globe-credit { ${frames(a => `transform: translateY(${px(a.credit)})`)} }
.footer-globe-portal iframe { animation: globe-frame linear both; ${timeline} }
.footer-globe-portal { animation: globe-clip linear both; ${timeline} }
.footer-globe-trigger { animation: globe-trigger linear both; ${timeline} }
.footer-globe-credit { animation: globe-credit linear both; ${timeline} }
`;
  trigger.style.cssText = `width:${g.diameter}px;height:${g.diameter}px;left:0;top:0`;
}
let parked = false;
function place() {
  if (stage !== 'footer') return;
  // Fallback if the page booted hidden (background tab) or on a save-data connection: load once the footer is in view.
  if (!loaded && footer.getBoundingClientRect().top < innerHeight) load();
  if (cssScroll) {
    // Motion lives in the program; per scroll frame only the visibility flags need updating.
    writeGlobeProgram();
    const a = globeAt(geometry, scrollY);
    if (!geometry.mobile) { // Only the desktop warmth gradient reads these.
      const sceneTop = scene.getBoundingClientRect().top;
      warmth.style.setProperty('--globe-x', `${geometry.x}px`);
      warmth.style.setProperty('--globe-y', `${a.y - sceneTop}px`);
      warmth.style.setProperty('--globe-radius', `${geometry.diameter * .55}px`);
    }
    const visible = ready && a.progress > 0;
    portal.classList.toggle('is-visible', visible);
    if (previewVisible !== visible) {
      previewVisible = visible;
      frame.contentWindow?.postMessage({ channel:'stratolink-globe', previewVisible:visible }, location.origin);
    }
    return;
  }
  const bounds = footer.getBoundingClientRect();
  const mobile = innerWidth < 768;
  const diameter = mobile ? Math.min(440, innerWidth * 1.1) * 1.035 : (Math.min(680, innerWidth * .55, innerHeight * .92) + Math.max(0, innerWidth - 1440) * .55) * 1.065;
  // While the globe is well below the fold nothing it positions can be seen; skip the style writes.
  const far = bounds.top - diameter > innerHeight * 1.5;
  if (far && parked) return;
  parked = far;
  const sceneTop = scene.getBoundingClientRect().top;
  const x = innerWidth - diameter * (mobile ? -.02 : .18);
  const y = bounds.bottom - diameter * .24;
  const progress = Math.max(0, Math.min(1, (innerHeight - (y - diameter * .55)) / (diameter * .45)));
  const reveal = reduced.matches ? 1 : progress * progress * (3 - 2 * progress);
  const lift = reduced.matches ? 0 : (1 - reveal) * 18;
  const scale = diameter / (Math.min(innerWidth, innerHeight) * .82) * (.985 + reveal * .015);
  frame.style.transform = `translate3d(${x - innerWidth / 2}px, ${y + lift - innerHeight / 2}px, 0) scale(${scale}) scale(var(--globe-hover-scale))`;
  portal.style.setProperty('--globe-reveal', reveal);
  if (!mobile) { // Only the desktop warmth gradient reads these.
    warmth.style.setProperty('--globe-x', `${x}px`);
    warmth.style.setProperty('--globe-y', `${y - sceneTop}px`);
    warmth.style.setProperty('--globe-radius', `${diameter * .55}px`);
  }
  portal.style.clipPath = `inset(${Math.max(0, Math.min(innerHeight, y - diameter * .65))}px 0 0 0)`;
  trigger.style.cssText = `width:${diameter}px;height:${diameter}px;left:${x - diameter / 2}px;top:${y - diameter / 2}px`;
  credit.style.transform = `translateY(${Math.max(0, bounds.bottom - innerHeight)}px)`;
  const visible = ready && progress > 0;
  portal.classList.toggle('is-visible', visible);
  if (previewVisible !== visible) {
    previewVisible = visible;
    frame.contentWindow?.postMessage({ channel:'stratolink-globe', previewVisible:visible }, location.origin);
  }
}
function schedule() {
  if (!motionFrame) motionFrame = requestAnimationFrame(() => { motionFrame = null; place(); });
}
function enter(event) {
  if (event && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0)) return;
  if (stage !== 'footer') { event?.preventDefault(); return; }
  if (!ready) return; // The real dashboard link remains a usable fallback.
  event?.preventDefault();
  footerScroll = scrollY;
  const start = getComputedStyle(frame).transform;
  stage = 'entering';
  portal.dataset.stage = stage;
  writeGlobeProgram(); // stage left 'footer': removes the scroll-timeline keyframes so inline styles and the animation below apply
  portal.style.clipPath = 'none';
  document.documentElement.classList.add('globe-navigation');
  home.inert = true; footer.inert = true; header.inert = true;
  frame.style.transform = 'none';
  animation = frame.animate([{transform:start},{transform:'translate3d(0,0,0) scale(1)'}], {
    duration:reduced.matches ? 180 : 1600, easing:'cubic-bezier(.65,0,.35,1)', fill:'forwards',
  });
  if (reduced.matches) animation.effect.setKeyframes([{opacity:0},{opacity:1}]);
  history.pushState({ globeDashboard:true, footerScroll }, '', '/dashboard');
  document.title = 'Dashboard - Stratolink';
  send('entering');
  // If rendering was interrupted, finish navigation rather than trapping input.
  navigationTimer = setTimeout(finish, reduced.matches ? 700 : 2600);
}
function finish() {
  if (stage !== 'entering') return;
  clearTimeout(navigationTimer);
  stage = 'dashboard';
  document.title = 'Dashboard - Stratolink';
  portal.dataset.stage = stage;
  animation?.cancel();
  frame.style.transform = 'none';
  frame.removeAttribute('aria-hidden');
  frame.inert = false;
  frame.tabIndex = 0;
  send('dashboard');
  frame.focus({ preventScroll:true });
}
function returnHome() {
  clearTimeout(navigationTimer);
  animation?.cancel();
  stage = 'footer';
  ready = false;
  frame.style.visibility = 'hidden';
  portal.dataset.stage = stage;
  frame.setAttribute('aria-hidden','true'); frame.inert = true; frame.tabIndex = -1;
  document.documentElement.classList.remove('globe-navigation');
  home.inert = false; footer.inert = false; header.inert = false;
  document.title = 'Stratolink';
  send('footer');
  scrollTo(0, footerScroll);
  place();
  trigger.focus({preventScroll:true});
}
window.addEventListener('message', event => {
  if (event.origin !== location.origin || event.source !== frame.contentWindow || event.data?.channel !== 'stratolink-globe') return;
  if (event.data.type === 'booted') timing.bootedAt ??= performance.now();
  if (event.data.type === 'ready') { ready = true; timing.readyAt ??= performance.now(); frame.style.visibility = ''; previewVisible = null; place(); }
  if (event.data.type === 'arrived') finish();
  if (event.data.type === 'theme' && ['light','dark'].includes(event.data.theme)) portal.style.setProperty('--portal-bg', event.data.theme === 'dark' ? '#0b1017' : '#eaebed');
  if (event.data.type === 'route' && stage === 'dashboard' && /^\/dashboard(?:\?device=[\w%-]+)?$/.test(event.data.path)) history.replaceState(history.state, '', event.data.path);
});
trigger.addEventListener('click', enter);
window.addEventListener('scroll', schedule, {passive:true});
window.addEventListener('resize', () => { programKey = ''; schedule(); });
window.addEventListener('popstate', () => {
  if (location.pathname === '/') returnHome();
  else if (history.state?.globeDashboard) { stage = 'entering'; document.documentElement.classList.add('globe-navigation'); home.inert = footer.inert = header.inert = true; portal.style.clipPath = 'none'; finish(); }
});
window.addEventListener('keydown', event => {
  if (event.key === 'Escape' && stage === 'entering') { history.back(); return; }
});
new ResizeObserver(() => { programKey = ''; schedule(); }).observe(footer);
// Start the globe with the page, not after the hero: its bytes and boot overlap the hero's own image decode.
// (The scene motion is compositor-driven, so a booting map no longer stutters the scroll.)
if (!navigator.connection?.saveData) {
  if (document.hidden) document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); }, { once: true });
  else load();
}
place();
