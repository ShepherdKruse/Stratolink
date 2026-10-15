import { initHomeMenu } from './home-menu.js';
const pageMenu = initHomeMenu(document.querySelector('.blog-header'));
let footerFrame;
export function updateHeaderFooter() {
  const header = document.querySelector('.blog-header');
  const footer = document.querySelector('.article-footer');
  if (!footer) {
    header.style.removeProperty('--header-offset');
    header.inert = false;
    return;
  }
  const offset = Math.max(0, Math.min(header.offsetHeight + 16, innerHeight - footer.getBoundingClientRect().top));
  header.style.setProperty('--header-offset', `${offset}px`);
  header.inert = offset >= header.offsetHeight;
  if (offset > 0) pageMenu.close();
}
function scheduleFooter() {
  if (footerFrame) return;
  footerFrame = requestAnimationFrame(() => { footerFrame = null; updateHeaderFooter(); });
}
addEventListener('scroll', scheduleFooter, {passive:true});
addEventListener('resize', scheduleFooter);
updateHeaderFooter();
