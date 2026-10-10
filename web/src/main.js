const launch = document.querySelector('.launch');
const viewport = document.querySelector('.launch-viewport');
const foreground = document.querySelector('.foreground-layer');
const balloon = document.querySelector('.balloon-layer');
const warmth = document.querySelector('.scene-warmth');
const story = document.querySelector('.story');
const storyWindow = document.querySelector('.story-window');
const storyItems = [...document.querySelectorAll('.essay-body > p, .essay-body > section')];
const footer = document.querySelector('.site-footer');
const header = document.querySelector('.site-header');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
// Dev diagnostics: ?perf shows a scroll-smoothness overlay; ?perf&static also freezes the scene script.
const perfFlags = new URLSearchParams(location.search);
const perfMode = perfFlags.has('perf');
const staticScene = perfMode && perfFlags.has('static');
if (perfMode) import('./scroll-perf.js').then(({ start }) => start({ staticScene }));
// Where the browser supports scroll-driven animations, the scene motion runs on the compositor in lockstep with
// the scroll (120 Hz on ProMotion, no frame of lag). Otherwise the JS path below drives it. ?jsscene forces JS.
const cssScroll = typeof CSS !== 'undefined' && CSS.supports('animation-timeline: scroll()') && !perfFlags.has('jsscene');
const clamp = (value) => Math.max(0, Math.min(1, value));
const phase = (value, start, end) => clamp((value - start) / (end - start));
const smooth = (value) => value * value * (3 - 2 * value);
let geometry;
let frame;
let firstReveal = true;
let docTop = { launch: 0, footer: 0 };
let footerHeight = 0;

// Setting an identical style value still triggers style recalculation; skip it.
const setStyle = (element, property, value) => {
  if (element.style[property] !== value) element.style[property] = value;
};
const setVar = (element, name, value) => {
  if (element.style.getPropertyValue(name) !== value) element.style.setProperty(name, value);
};

function measureScene() {
  const width = viewport.clientWidth;
  const height = reducedMotion.matches ? innerHeight : viewport.clientHeight;
  const photoHeight = Math.max(height, width * 9 / 16);
  const photoWidth = photoHeight * 16 / 9;
  const crop = (photoHeight - height) / 2;
  const anchor = photoHeight * (width >= 1024 ? .285 : .3125) - crop;
  const mobile = width < 768;
  const balloonCenter = width / 2 + .02265625 * photoWidth;
  const balloonShift = mobile
    ? Math.min(width * .82, width - 24 - .0262 * photoWidth) - balloonCenter
    : width * .09;
  const readingStart = height * .18;
  const farewell = storyItems.at(-1);
  const footerGap = Math.min(160, height * .16);
  const readingTravel = Math.max(0, anchor + farewell.offsetTop + farewell.offsetHeight - height + footerGap);
  const duration = readingStart + readingTravel;

  geometry = { width, height, anchor, readingStart, readingTravel, duration, balloonShift, mobile,
    cloudEdge: photoHeight * .52 - crop,
    cloudFeather: photoHeight * .08,
    storyLayout: storyItems.map((item) => ({ item, top: item.offsetTop, height: item.offsetHeight })),
    balloonRise: photoHeight * .567 - crop + height * .025 };
  setStyle(story, 'top', `${anchor}px`);
  setStyle(launch, 'height', reducedMotion.matches ? 'auto' : `${height + duration}px`);
  // Document-space positions, so per-frame updates need no layout reads.
  docTop = { launch: launch.getBoundingClientRect().top + scrollY, footer: footer.getBoundingClientRect().top + scrollY };
  footerHeight = footer.offsetHeight;
  if (cssScroll) writeSceneProgram();
  updateScene();
}

/* The same curves as updateScene(), compiled once into keyframes against the document scroll timeline.
 * Stops are sampled densely enough that linear interpolation between them is indistinguishable from the formulas. */
let program;
function writeSceneProgram() {
  program ??= document.head.appendChild(Object.assign(document.createElement('style'), { id: 'scene-program' }));
  if (reducedMotion.matches) { program.textContent = ''; return; }
  const { width, height, duration, readingStart, readingTravel, balloonRise, balloonShift, mobile, cloudEdge, cloudFeather } = geometry;
  const px = (value) => `${value.toFixed(2)}px`;
  const stops = (count, frame) => Array.from({ length: count + 1 }, (_, i) => `${(100 * i / count).toFixed(3)}% { ${frame(i / count)} }`).join('\n');
  const timeline = 'animation-timeline: scroll(root block);';
  const range = (from, to) => `animation-range: ${px(docTop.launch + from)} ${px(docTop.launch + to)};`;
  const cityEnd = height * .6;
  const footerStart = docTop.footer - height; // the footer's top reaches the bottom of the viewport
  program.textContent = `
@property --cloud-fade-start { syntax: '<length>'; inherits: true; initial-value: 100000px; }
@property --cloud-fade-end { syntax: '<length>'; inherits: true; initial-value: 100000px; }
@keyframes sl-city { ${stops(24, x => `transform: translate3d(0, ${px(height * 1.12 * smooth(x))}, 0)`)} }
@keyframes sl-balloon { ${stops(60, f => {
    const sway = Math.sin(f * Math.PI * 2) * Math.sin(f * Math.PI);
    const right = balloonShift + width * (.03 * f + (mobile ? .42 : .24) * f ** 2 + .014 * sway);
    const up = balloonRise * (.9 * f + .1 * f ** 2);
    return `transform: translate3d(${px(right)}, ${px(-up)}, 0)`;
  })} }
@keyframes sl-story { ${stops(1, x => `transform: translate3d(0, ${px(-readingTravel * x)}, 0)`)} }
@keyframes sl-warmth { ${stops(12, x => `opacity: ${smooth(x).toFixed(4)}`)} }
@keyframes sl-cloud { ${stops(24, x => { const edge = cloudEdge + height * 1.12 * smooth(x); return `--cloud-fade-start: ${px(edge)}; --cloud-fade-end: ${px(edge + cloudFeather)}`; })} }
@keyframes sl-footer { ${stops(12, x => `opacity: ${smooth(x).toFixed(4)}; transform: translateY(${px(32 * (1 - smooth(x)))})`)} }
@keyframes sl-header { ${stops(12, x => `transform: translateY(${px(-80 * smooth(x))})`)} }
.foreground-layer { animation: sl-city linear both; ${timeline} ${range(0, cityEnd)} }
.balloon-layer { animation: sl-balloon linear both; ${timeline} ${range(0, duration)} }
.story { animation: sl-story linear both; ${timeline} ${range(readingStart, duration)} }
.scene-warmth { animation: sl-warmth linear both; ${timeline} ${range(height * .4, height * .9)} }
.story-window { animation: sl-cloud linear both; ${timeline} ${range(0, cityEnd)} }
.footer-row { animation: sl-footer linear both; ${timeline} animation-range: ${px(footerStart)} ${px(footerStart + Math.min(height * .5, footerHeight))}; }
.site-header { animation: sl-header linear both; ${timeline} animation-range: ${px(footerStart)} ${px(footerStart + Math.min(height * .4, footerHeight))}; }
`;
}

function updateScene() {
  if (!geometry) return;
  const perfStart = perfMode ? performance.now() : 0;
  const { width, height, readingStart, readingTravel, duration, balloonRise, balloonShift, mobile } = geometry;
  const distance = Math.max(0, scrollY - docTop.launch);
  const footerTop = docTop.footer - scrollY;

  if (reducedMotion.matches) {
    setStyle(foreground, 'transform', '');
    setStyle(balloon, 'transform', `translate3d(${balloonShift}px, 0, 0)`);
    setStyle(story, 'transform', '');
    setStyle(warmth, 'opacity', '0');
    setVar(footer, '--reveal', '1');
  } else if (cssScroll) {
    // Motion is on the compositor (see writeSceneProgram); JS only reveals paragraphs as they enter view.
    const cityDrop = height * 1.12 * smooth(phase(distance, 0, height * .6));
    const cloudEdge = geometry.cloudEdge + cityDrop;
    const viewportTop = Math.min(0, duration - distance);
    const revealLine = Math.min(height * .82, viewportTop + Math.min(height, cloudEdge)) + Math.min(80, height * .1);
    revealStory(geometry.anchor - Math.max(0, distance - readingStart), revealLine);
  } else {
    const city = smooth(phase(distance, 0, height * .6));
    const reading = phase(distance, readingStart, duration);
    const flight = clamp(distance / duration);
    const sway = Math.sin(flight * Math.PI * 2) * Math.sin(flight * Math.PI);
    const right = balloonShift + width * (.03 * flight + (mobile ? .42 : .24) * flight ** 2 + .014 * sway);
    const up = balloonRise * (.9 * flight + .1 * flight ** 2);

    const cityDrop = height * 1.12 * city;
    const cloudEdge = geometry.cloudEdge + cityDrop;
    const viewportTop = Math.min(0, duration - distance);
    const revealLine = Math.min(height * .82, viewportTop + Math.min(height, cloudEdge)) + Math.min(80, height * .1);
    const storyTop = geometry.anchor - Math.max(0, distance - readingStart);

    setStyle(foreground, 'transform', `translate3d(0, ${cityDrop}px, 0)`);
    setStyle(balloon, 'transform', `translate3d(${right}px, ${-up}px, 0)`);
    setStyle(story, 'transform', `translate3d(0, ${-readingTravel * reading}px, 0)`);
    if (cloudEdge < height) {
      setStyle(storyWindow, 'maskImage', '');
      setVar(storyWindow, '--cloud-fade-start', `${cloudEdge}px`);
      setVar(storyWindow, '--cloud-fade-end', `${cloudEdge + geometry.cloudFeather}px`);
    } else {
      setStyle(storyWindow, 'maskImage', 'none');
    }
    revealStory(storyTop, revealLine);
    setStyle(warmth, 'opacity', String(smooth(phase(distance, height * .4, height * .9))));
    setVar(footer, '--reveal', String(smooth(clamp((innerHeight - footerTop) / Math.min(height * .5, footerHeight)))));
  }

  if (!cssScroll) {
    const footerHeaderExit = smooth(clamp((height - footerTop) / Math.min(height * .4, footerHeight)));
    setStyle(header, 'transform', `translateY(${-80 * footerHeaderExit}px)`);
  }
  frame = null;
  if (perfMode) (window.__scenePerf ??= { ms: [] }).ms.push(performance.now() - perfStart);
}

function revealStory(storyTop, revealLine) {
  geometry.storyLayout.forEach(({ item, top, height: itemHeight }) => {
    const itemTop = storyTop + top;
    if (!item.classList.contains('is-visible') && itemTop < revealLine && itemTop + itemHeight > 0) {
      // Text in view on first paint appears instantly; later paragraphs fade in as they scroll up.
      if (firstReveal) item.style.transition = 'none';
      item.classList.add('is-visible');
    }
  });
  firstReveal = false;
}

function scheduleScene() {
  if (staticScene) return; // ?perf&static: leave the scene exactly as laid out on load
  if (!frame) frame = requestAnimationFrame(updateScene);
}

story.addEventListener('focusin', event => {
  const link = event.target.closest('a');
  if (!link || !link.matches(':focus-visible') || !geometry || reducedMotion.matches) return;
  // Keep keyboard scrolling on the page, rather than inside the masked scene.
  document.querySelector('.story-window').scrollTop = 0;
  viewport.scrollTop = 0;
  const item = link.closest('.essay-body > p, .essay-body > section');
  if (item) {
    item.style.transitionDuration = '0ms';
    item.style.transitionDelay = '0ms';
    item.classList.add('is-visible');
  }
  const rect = link.getBoundingClientRect();
  if (rect.top < header.offsetHeight + 16 || rect.bottom > geometry.height * .85) {
    const offset = rect.top - story.getBoundingClientRect().top;
    scrollTo({ top: launch.offsetTop + geometry.readingStart + geometry.anchor + offset - geometry.height * .35, behavior: 'instant' });
    updateScene();
  }
});

// Hold the whole hero (scene imagery and story text) until every image has decoded, then show it
// all in one frame. A short cap keeps a slow network from blanking the page for long.
const sceneAssets = [...viewport.querySelectorAll('img:not([loading="lazy"])')];
const assetsDecoded = Promise.allSettled(sceneAssets.map(image => image.decode()));
const readyCap = new Promise(resolve => setTimeout(resolve, 2500));
Promise.race([assetsDecoded, readyCap]).then(() => {
  measureScene();
  launch.removeAttribute('data-pending');
  window.__heroReadyAt = performance.now();
  window.dispatchEvent(new Event('launch:ready'));
  // The blurred placeholder is fully covered now; stop compositing a blurred full-screen layer.
  setTimeout(() => document.querySelector('.scene-placeholder')?.remove(), 400);
});

addEventListener('scroll', scheduleScene, { passive: true });
addEventListener('resize', measureScene);
reducedMotion.addEventListener('change', measureScene);
new ResizeObserver(measureScene).observe(viewport);
new ResizeObserver(measureScene).observe(story);
document.fonts.ready.then(measureScene);
measureScene();

import "./footer-globe.js";
