import { mountFigures } from './figures.js';

/* Interactive figures for "Drawing the path between packets". Mirrors the payload
 * dev log's mountArticle contract: mount into the post's main element, return a
 * cleanup for the blog's client-side page transitions. */
export function mountArticle(root = document) {
  const controller = new AbortController();
  mountFigures(root, controller.signal);
  root.addEventListener('click', event => {
    const ref = event.target.closest('a[href^="#ref-"]');
    if (ref) root.querySelector('.references').open = true;
  }, { signal: controller.signal });
  return () => controller.abort();
}
