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
  if (offset > 0) header.querySelector('.mobile-nav')?.removeAttribute('open');
}
function scheduleFooter() {
  if (footerFrame) return;
  footerFrame = requestAnimationFrame(() => { footerFrame = null; updateHeaderFooter(); });
}
addEventListener('scroll', scheduleFooter, {passive:true});
addEventListener('resize', scheduleFooter);
updateHeaderFooter();


document.addEventListener('click', event => {
  const menu = document.querySelector('.mobile-nav');
  if (menu?.open && (!menu.contains(event.target) || event.target.closest('a'))) menu.open = false;
});
document.addEventListener('keydown', event => {
  const menu = document.querySelector('.mobile-nav');
  if (event.key === 'Escape' && menu?.open) { menu.open = false; menu.querySelector('summary').focus(); }
});
