import { updateHeaderFooter } from './site-chrome.js';

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const pages = new Map();
let navigation = 0;
let transition;
let currentOrigin = history.state?.blogOrigin || (document.querySelector('.post-hero') ? 'featured' : 'card');
let animateHistory = true;
let currentPath = location.pathname;
let articleCleanup;
let fallbackCleanup;
history.scrollRestoration = 'manual';

async function prepareArticle(page) {
  const styles = await Promise.all([...page.querySelectorAll('link[data-article-style]')].map(async source => {
    let style = [...document.querySelectorAll('link[data-article-style]')].find(link => link.href === source.href);
    if (!style) {
      style = source.cloneNode();
      style.media = 'not all';
      const loaded = new Promise((resolve, reject) => { style.onload = resolve; style.onerror = reject; });
      document.head.append(style);
      await loaded;
    }
    return style;
  }));
  const module = page.querySelector('[data-interactive-article]')
    ? await import('./payload-dev-log/article.js') : null;
  return main => {
    document.querySelectorAll('link[data-article-style]').forEach(style => { style.media = styles.includes(style) ? 'all' : 'not all'; });
    return module?.mountArticle(main);
  };
}

async function animatePage(update, oldSurface, kind) {
  const oldMain = document.querySelector('main');
  const oldImage = kind === 'featured' ? oldSurface?.querySelector('[data-post-image]') : null;
  const from = oldImage?.getBoundingClientRect();
  const imageStyle = oldImage && getComputedStyle(oldImage);
  const oldStyle = imageStyle && {objectPosition:imageStyle.objectPosition, borderRadius:imageStyle.borderRadius};
  const image = from?.width && from.bottom > 0 && from.top < innerHeight ? oldImage.cloneNode() : null;
  let destination;
  const animations = [];
  const cleanup = () => {
    animations.forEach(animation => animation.cancel());
    image?.remove();
    destination?.style.removeProperty('visibility');
  };
  fallbackCleanup = cleanup;
  if (image) {
    image.removeAttribute('data-post-image');
    image.setAttribute('aria-hidden', 'true');
    image.className = 'article-transition-image';
    Object.assign(image.style, { left:`${from.left}px`, top:`${from.top}px`, width:`${from.width}px`, height:`${from.height}px`, objectPosition:oldStyle.objectPosition, borderRadius:oldStyle.borderRadius, opacity:'0' });
    document.body.append(image);
  }
  animations.push(oldMain.animate([{opacity:1},{opacity:0}], {duration:120,fill:'forwards',easing:'ease-out'}));
  if (image) animations.push(image.animate([{opacity:0},{opacity:1}], {duration:120,fill:'forwards',easing:'ease-out'}));
  try {
    await animations[0].finished;
    const surface = update();
    const main = document.querySelector('main');
    destination = image && surface?.querySelector('[data-post-image]');
    if (destination) {
      const to = destination.getBoundingClientRect(), style = getComputedStyle(destination);
      destination.style.visibility = 'hidden';
      animations.push(image.animate([
        {left:`${from.left}px`,top:`${from.top}px`,width:`${from.width}px`,height:`${from.height}px`,borderRadius:oldStyle.borderRadius,objectPosition:oldStyle.objectPosition},
        {left:`${to.left}px`,top:`${to.top}px`,width:`${to.width}px`,height:`${to.height}px`,borderRadius:style.borderRadius,objectPosition:style.objectPosition},
      ], {duration:300,fill:'forwards',easing:'cubic-bezier(.22,1,.36,1)'}));
    } else image?.remove();
    animations.push(main.animate([{opacity:0},{opacity:1}], {duration:220,fill:'both',easing:'ease-out'}));
    await Promise.all(animations.map(animation => animation.finished));
  } catch { /* Superseded by another navigation. */ }
  finally { cleanup(); if (fallbackCleanup === cleanup) fallbackCleanup = undefined; }
}

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
  transition?.skipTransition();
  fallbackCleanup?.();
  let nextPage, mount;
  try {
    nextPage = await getPage(url);
    mount = await prepareArticle(nextPage);
    const hero = nextPage.querySelector('.post-hero img, .featured > img');
    if (hero) { const image = new Image(); image.src = hero.src; await image.decode().catch(() => {}); }
  }
  catch { if (currentNavigation === navigation) location.assign(url); return; }
  if (currentNavigation !== navigation) return;
  const nextMain = nextPage.querySelector('main');
  if (!nextMain) { location.assign(url); return; }
  clearTransitionNames();
  const returning = !nextMain.dataset.post;
  const kind = source ? source.dataset.origin || 'card' : currentOrigin;
  const oldSurface = source || document.querySelector(kind === 'featured' ? '.post-hero' : '.post-heading');
  const shouldAnimate = animate && !reducedMotion.matches;
  const nativeTransition = shouldAnimate && document.startViewTransition;
  if (nativeTransition) {
    nameTransition(oldSurface, kind);
    if (kind === 'featured' && returning) document.querySelector('[data-post-title]')?.style.setProperty('view-transition-name', 'article-title');
  }
  if (!pop) savePosition(source?.id);
  const update = () => {
    railCleanup?.();
    articleCleanup?.();
    document.querySelector('main').replaceWith(nextMain);
    document.querySelector('.blog-footer').replaceWith(nextPage.querySelector('.blog-footer'));
    document.body.classList.toggle('article-page', Boolean(nextMain.dataset.post));
    document.title = nextPage.title;
    articleCleanup = mount(nextMain);
    if (!pop) history.pushState({blogOrigin:kind, blogParent:!returning}, '', url);
    currentPath = location.pathname;
    currentOrigin = kind;
    initRail();
    const rail = document.querySelector('.article-grid');
    if (rail && restore) rail.scrollLeft = restore.rail;
    scrollTo({top:restore?.y || 0, behavior:'instant'});
    updateHeaderFooter();
    const destination = returning
      ? document.getElementById(restore?.linkId || '') || document.querySelector('.featured')
      : document.querySelector(kind === 'featured' ? '.post-hero' : '.post-heading');
    if (nativeTransition) {
      nameTransition(destination, kind);
      if (kind === 'featured' && !returning) document.querySelector('[data-post-title]')?.style.setProperty('view-transition-name', 'article-title');
    }
    const focus = returning ? destination || nextMain : nextMain;
    focus.setAttribute('tabindex', focus.matches('a') ? '0' : '-1');
    focus.focus({preventScroll:true});
    return destination;
  };
  if (!shouldAnimate) { update(); return; }
  if (!nativeTransition) { await animatePage(update, oldSurface, kind); return; }
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
  if (location.pathname === currentPath) return;
  navigate(location.href, {pop:true, restore:event.state?.blogPosition, animate:animateHistory});
  animateHistory = true;
});
window.addEventListener('pagehide', () => savePosition());
initRail();
const initialMain = document.querySelector('main');
prepareArticle(document).then(mount => { if (initialMain.isConnected && !articleCleanup) articleCleanup = mount(initialMain); });
