// Swap small raster frames: SVG/GIF animation is not reliable in browser tabs.
const icon = document.querySelector('#site-favicon');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const still = '/assets/favicon/globe.png';
const frames = new Map();
let timer;
let sprite;
let loading;
let context;

function draw() {
  const frame = Math.floor((Date.now() % 72000) / 750);
  if (!frames.has(frame)) {
    context.clearRect(0, 0, 32, 32);
    context.drawImage(sprite, (frame % 12) * 32, Math.floor(frame / 12) * 32, 32, 32, 0, 0, 32, 32);
    frames.set(frame, context.canvas.toDataURL('image/png'));
  }
  icon.href = frames.get(frame);
  icon.sizes = '32x32';
}

async function start() {
  if (!icon || window.self !== window.top || document.hidden || reduced.matches || timer) return;
  if (!loading) {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 32;
    context = canvas.getContext('2d');
    if (!context) return;
    sprite = new Image();
    sprite.src = '/assets/favicon/globe-frames.png';
    loading = sprite.decode();
  }
  try { await loading; } catch { return; }
  if (document.hidden || reduced.matches || timer) return;
  draw();
  timer = setInterval(draw, 750);
}

function stop() { clearInterval(timer); timer = undefined; }
document.addEventListener('visibilitychange', () => { stop(); if (!document.hidden) start(); });
addEventListener('pagehide', stop);
addEventListener('pageshow', start);
reduced.addEventListener('change', () => {
  stop();
  if (icon) { icon.href = still; icon.sizes = '64x64'; }
  start();
});
start();
