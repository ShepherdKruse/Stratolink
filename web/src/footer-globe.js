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

function load() {
  if (loaded) return;
  loaded = true;
  frame.src = '/dashboard?portal=footer';
}
function place() {
  if (stage !== 'footer') return;
  const bounds = footer.getBoundingClientRect();
  // Warm the map a few screens ahead once the reader starts scrolling.
  // Leave the initial homepage load alone, and keep rotation paused offscreen.
  if (!loaded && (bounds.top < innerHeight || (scrollY > 120 && bounds.top < innerHeight * 4))) load();
  const sceneTop = scene.getBoundingClientRect().top;
  const mobile = innerWidth < 768;
  const diameter = mobile ? Math.min(440, innerWidth * 1.1) * 1.035 : (Math.min(680, innerWidth * .55, innerHeight * .92) + Math.max(0, innerWidth - 1440) * .55) * 1.065;
  const x = innerWidth - diameter * (mobile ? -.02 : .18);
  const y = bounds.bottom - diameter * .24;
  const progress = Math.max(0, Math.min(1, (innerHeight - (y - diameter * .55)) / (diameter * .45)));
  const reveal = reduced.matches ? 1 : progress * progress * (3 - 2 * progress);
  const lift = reduced.matches ? 0 : (1 - reveal) * 18;
  const scale = diameter / (Math.min(innerWidth, innerHeight) * .82) * (.985 + reveal * .015);
  frame.style.transform = `translate3d(${x - innerWidth / 2}px, ${y + lift - innerHeight / 2}px, 0) scale(${scale}) scale(var(--globe-hover-scale))`;
  portal.style.setProperty('--globe-reveal', reveal);
  warmth.style.setProperty('--globe-x', `${x}px`);
  warmth.style.setProperty('--globe-y', `${y - sceneTop}px`);
  warmth.style.setProperty('--globe-radius', `${diameter * .55}px`);
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
  if (event.data.type === 'ready') { ready = true; frame.style.visibility = ''; previewVisible = null; place(); }
  if (event.data.type === 'arrived') finish();
  if (event.data.type === 'theme' && ['light','dark'].includes(event.data.theme)) portal.style.setProperty('--portal-bg', event.data.theme === 'dark' ? '#0b1017' : '#eaebed');
  if (event.data.type === 'route' && stage === 'dashboard' && /^\/dashboard(?:\?device=[\w%-]+)?$/.test(event.data.path)) history.replaceState(history.state, '', event.data.path);
});
trigger.addEventListener('click', enter);
window.addEventListener('scroll', schedule, {passive:true});
window.addEventListener('resize', schedule);
window.addEventListener('popstate', () => {
  if (location.pathname === '/') returnHome();
  else if (history.state?.globeDashboard) { stage = 'entering'; document.documentElement.classList.add('globe-navigation'); home.inert = footer.inert = header.inert = true; portal.style.clipPath = 'none'; finish(); }
});
window.addEventListener('keydown', event => {
  if (event.key === 'Escape' && stage === 'entering') { history.back(); return; }
});
new ResizeObserver(schedule).observe(footer);
place();
