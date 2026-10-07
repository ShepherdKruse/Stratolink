import { updateHeaderFooter } from './site-chrome.js';

import './docs-search.js';
import './docs-reading.js';

document.querySelectorAll('.docs-group').forEach(group => group.addEventListener('toggle', updateHeaderFooter));
document.querySelector('.docs-mobile-sections')?.addEventListener('click', event => {
  if (event.target.closest('a')) event.currentTarget.open = false;
});
function updateTopic() {
  document.querySelectorAll('.docs-nav-topics a').forEach(link => {
    if (link.hash === location.hash) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
}
addEventListener('hashchange', updateTopic);
updateTopic();

const readingArea = document.querySelector('.docs-layout');
if (readingArea) new ResizeObserver(updateHeaderFooter).observe(readingArea);
