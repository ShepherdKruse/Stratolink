import { updateHeaderFooter } from './site-chrome.js';

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const pages = new Map();
let navigation = 0;
let transition;
let currentOrigin = history.state?.blogOrigin || 'card';
let animateHistory = true;
history.scrollRestoration = 'manual';

function savePosition(linkId) {
  history.replaceState({ ...history.state, blogPosition: {
    y: scrollY,
    rail: document.querySelector('.article-grid')?.scrollLeft || 0,
    linkId: linkId || history.state?.blogPosition?.linkId,
  } }, '');
}

async function getPage(url) {
  if (!pages.has(url)) pages.set(url, fetch(url).then(response => {
    if (!response.ok) throw new Error('Page unavailable');
    return response.text();
  }).catch(error => { pages.delete(url); throw error; }));
  return new DOMParser().parseFromString(await pages.get(url), 'text/html');
}

function nameTransition(element, kind) {
  if (!element) return;
  element.style.viewTransitionName = 'article-surface';
  element.querySelector('[data-post-title]')?.style.setProperty('view-transition-name', 'article-title');
  if (kind === 'featured') element.querySelector('[data-post-image]')?.style.setProperty('view-transition-name', 'article-image');
}

function clearTransitionNames() {
  document.querySelectorAll('[style*="view-transition-name"]').forEach(element => element.style.removeProperty('view-transition-name'));
}

function initRail() {
  const rail = document.querySelector('.article-grid');
  const controls = document.querySelector('.article-rail-controls');
  if (!rail || !controls) return;
  const previous = controls.querySelector('[data-rail-direction="-1"]');
  const next = controls.querySelector('[data-rail-direction="1"]');
  const update = () => {
    controls.hidden = rail.scrollWidth <= rail.clientWidth + 2;
    previous.disabled = rail.scrollLeft < 2;
    next.disabled = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 2;
  };
  controls.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    rail.scrollBy({left: Number(button.dataset.railDirection) * (rail.clientWidth + parseFloat(getComputedStyle(rail).gap)), behavior: reducedMotion.matches || event.detail === 0 ? 'instant' : 'smooth'});
  });
  rail.addEventListener('scroll', update, {passive:true});
  const observer = new ResizeObserver(update);
  observer.observe(rail);
  railCleanup = () => observer.disconnect();
  update();
}
let railCleanup;

async function navigate(url, { source, restore, pop = false, animate = true } = {}) {
  const currentNavigation = ++navigation;
  let nextPage;
  try { nextPage = await getPage(url); }
  catch { if (currentNavigation === navigation) location.assign(url); return; }
  if (currentNavigation !== navigation) return;
  const nextMain = nextPage.querySelector('main');
  if (!nextMain) { location.assign(url); return; }
  transition?.skipTransition();
  clearTransitionNames();
  const returning = !nextMain.dataset.post;
  const kind = source ? source.dataset.origin || 'card' : currentOrigin;
  const oldSurface = source || document.querySelector(kind === 'featured' ? '.post-hero' : '.post-heading');
  const shouldAnimate = animate && !reducedMotion.matches && document.startViewTransition;
  if (shouldAnimate) {
    nameTransition(oldSurface, kind);
    if (kind === 'featured' && returning) document.querySelector('[data-post-title]')?.style.setProperty('view-transition-name', 'article-title');
  }
  if (!pop) savePosition(source?.id);
  const update = () => {
    railCleanup?.();
    document.querySelector('main').replaceWith(nextMain);
    document.querySelector('.blog-footer').replaceWith(nextPage.querySelector('.blog-footer'));
    document.body.classList.toggle('article-page', Boolean(nextMain.dataset.post));
    document.title = nextPage.title;
    if (!pop) history.pushState({blogOrigin:kind, blogParent:!returning}, '', url);
    currentOrigin = kind;
    initRail();
    const rail = document.querySelector('.article-grid');
    if (rail && restore) rail.scrollLeft = restore.rail;
    scrollTo({top:restore?.y || 0, behavior:'instant'});
    updateHeaderFooter();
    const destination = returning
      ? document.getElementById(restore?.linkId || '')
      : document.querySelector(kind === 'featured' ? '.post-hero' : '.post-heading');
    if (shouldAnimate) {
      nameTransition(destination, kind);
      if (kind === 'featured' && !returning) document.querySelector('[data-post-title]')?.style.setProperty('view-transition-name', 'article-title');
    }
    const focus = returning ? destination || nextMain : nextMain;
    focus.setAttribute('tabindex', focus.matches('a') ? '0' : '-1');
    focus.focus({preventScroll:true});
  };
  if (!shouldAnimate) { update(); return; }
  transition = document.startViewTransition(update);
  try { await transition.finished; } catch { /* A newer navigation can interrupt the transition. */ }
  if (currentNavigation === navigation) clearTransitionNames();
}

function blogLink(event) {
  return event.target.closest('a[data-post-link], a[data-blog-back], .blog-header a[href="/blog"], .article-footer a[href="/blog"]');
}
document.addEventListener('click', event => {
  const link = blogLink(event);
  if (link) document.querySelector('.mobile-nav')?.removeAttribute('open');
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  if (link.getAttribute('href') === '/blog' && !document.querySelector('[data-post]')) return;
  event.preventDefault();
  if (link.hasAttribute('data-blog-back') && history.state?.blogParent) { animateHistory = event.detail !== 0; history.back(); return; }
  navigate(link.href, {source:link.hasAttribute('data-post-link') ? link : undefined, animate:event.detail !== 0});
});
document.addEventListener('pointerover', event => {
  const link = blogLink(event);
  if (link) getPage(link.href).catch(() => {});
});
window.addEventListener('popstate', event => {
  navigate(location.href, {pop:true, restore:event.state?.blogPosition, animate:animateHistory});
  animateHistory = true;
});
window.addEventListener('pagehide', () => savePosition());
initRail();
