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
const clamp = (value) => Math.max(0, Math.min(1, value));
const phase = (value, start, end) => clamp((value - start) / (end - start));
const smooth = (value) => value * value * (3 - 2 * value);
let geometry;
let frame;
let storyReady = reducedMotion.matches;

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
  story.style.top = `${anchor}px`;
  launch.style.height = reducedMotion.matches ? 'auto' : `${height + duration}px`;
  updateScene();
}

function updateScene() {
  if (!geometry) return;
  const { width, height, readingStart, readingTravel, duration, balloonRise, balloonShift, mobile } = geometry;
  const distance = Math.max(0, -launch.getBoundingClientRect().top);
  const footerTop = footer.getBoundingClientRect().top;
  const footerHeight = footer.offsetHeight;

  if (reducedMotion.matches) {
    foreground.style.transform = '';
    balloon.style.transform = `translate3d(${balloonShift}px, 0, 0)`;
    story.style.transform = '';
    warmth.style.opacity = 0;
    footer.style.setProperty('--reveal', 1);
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

    foreground.style.transform = `translate3d(0, ${cityDrop}px, 0)`;
    balloon.style.transform = `translate3d(${right}px, ${-up}px, 0)`;
    story.style.transform = `translate3d(0, ${-readingTravel * reading}px, 0)`;
    if (cloudEdge < height) {
      storyWindow.style.maskImage = '';
      storyWindow.style.setProperty('--cloud-fade-start', `${cloudEdge}px`);
      storyWindow.style.setProperty('--cloud-fade-end', `${cloudEdge + geometry.cloudFeather}px`);
    } else {
      storyWindow.style.maskImage = 'none';
    }
    if (storyReady) {
      let stagger = 0;
      geometry.storyLayout.forEach(({ item, top, height: itemHeight }) => {
        const itemTop = storyTop + top;
        if (!item.classList.contains('is-visible') && itemTop < revealLine && itemTop + itemHeight > 0) {
          item.style.transitionDelay = `${Math.min(stagger++ * 60, 180)}ms`;
          item.classList.add('is-visible');
        }
      });
    }
    warmth.style.opacity = smooth(phase(distance, height * .4, height * .9));
    footer.style.setProperty('--reveal', smooth(clamp((innerHeight - footerTop) / Math.min(height * .5, footerHeight))));
  }

  const footerHeaderExit = smooth(clamp((height - footerTop) / Math.min(height * .4, footerHeight)));
  header.style.transform = `translateY(${-80 * footerHeaderExit}px)`;
  frame = null;
}

function scheduleScene() {
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

function revealLetters(element, delay = 0) {
  const text = element.textContent.trim();
  element.textContent = '';
  const accessibleText = document.createElement('span');
  accessibleText.className = 'sr-only';
  accessibleText.textContent = text;
  element.append(accessibleText);

  return Promise.all([...text].map((character, index) => {
    const letter = document.createElement('span');
    letter.textContent = character;
    letter.className = 'letter';
    letter.setAttribute('aria-hidden', 'true');
    element.append(letter);
    return letter.animate([{ opacity: 0 }, { opacity: 1 }], {
      duration: 650,
      delay: delay + index * 20,
      easing: 'cubic-bezier(.215, .61, .355, 1)',
      fill: 'backwards',
    }).finished;
  }));
}

function removeIntro() {
  document.querySelector('.scene-intro')?.remove();
  [foreground, balloon, story].forEach((element) => {
    element.getAnimations().forEach((animation) => animation.cancel());
  });
  launch.removeAttribute('data-loading');
}

function startStoryReveals() {
  launch.removeAttribute('data-story-pending');
  storyReady = true;
  scheduleScene();
}

if (reducedMotion.matches) {
  removeIntro();
  startStoryReveals();
} else {
  Promise.all([...document.querySelectorAll('[data-letter-reveal]')].map((element, index) =>
    revealLetters(element, index * 110)
  )).then(startStoryReveals);
  const assets = [...viewport.querySelectorAll('img')].filter(image => !image.closest('.story'));
  Promise.allSettled(assets.map(image => image.decode())).then(() => {
    const intro = document.querySelector('.scene-intro');
    if (!intro) return;
    const reveal = {
      duration: 1300,
      delay: Math.max(0, 630 - performance.now()),
      easing: 'cubic-bezier(.165, .84, .44, 1)',
      fill: 'forwards',
    };
    foreground.animate([{ opacity: 0 }, { opacity: 1 }], reveal);
    balloon.animate([{ opacity: 0 }, { opacity: 1 }], reveal);
    story.animate([{ color: '#fff' }, { color: '#29333c' }], reveal);
    intro.animate([{ opacity: 1 }, { opacity: 0 }], reveal).finished.then(removeIntro);
  });
}

addEventListener('scroll', scheduleScene, { passive: true });
addEventListener('resize', measureScene);
reducedMotion.addEventListener('change', () => {
  if (reducedMotion.matches) {
    removeIntro();
    startStoryReveals();
  }
  measureScene();
});
new ResizeObserver(measureScene).observe(viewport);
new ResizeObserver(measureScene).observe(story);
document.fonts.ready.then(measureScene);
measureScene();
launch.removeAttribute('data-title-pending');

import "./footer-globe.js";
