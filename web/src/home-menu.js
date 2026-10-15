export function initHomeMenu(header) {
  if (!document.querySelector('.home-menu-backdrop')) {
    const backdrop = document.createElement('div');
    backdrop.className = 'home-menu-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.prepend(backdrop);
  }
  const toggle = header.querySelector('.home-menu-toggle');
  const navigation = header.querySelector('#home-menu-links');
  const mobile = matchMedia('(max-width: 700px)');
  let open = false;
  let background = [];

  function setOpen(next, restoreFocus = false) {
    next = next && mobile.matches;
    if (next === open) return;
    open = next;
    if (open) {
      document.addEventListener('wheel', blockBackgroundScroll, { passive: false });
      document.addEventListener('touchmove', blockBackgroundScroll, { passive: false });
      background = [...document.querySelectorAll('main, .site-footer, .article-footer, .skip-link, .footer-globe-portal')].map(element => [element, element.inert]);
      background.forEach(([element]) => { element.inert = true; });
    } else {
      document.removeEventListener('wheel', blockBackgroundScroll);
      document.removeEventListener('touchmove', blockBackgroundScroll);
      background.forEach(([element, inert]) => { element.inert = inert; });
    }
    document.documentElement.classList.toggle('home-menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    navigation.inert = !open;
    if (!open && restoreFocus) toggle.focus({ preventScroll: true });
  }

  toggle.addEventListener('click', () => setOpen(!open));
  header.addEventListener('click', event => {
    if (event.target.closest('a')) setOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (!open) return;
    if (event.key === 'Escape') { event.preventDefault(); setOpen(false, true); }
    if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', ' '].includes(event.key) && event.target !== toggle) event.preventDefault();
    if (event.key !== 'Tab') return;
    const targets = [header.querySelector(':scope > a'), toggle, ...navigation.querySelectorAll('a')];
    const first = targets[0];
    const last = targets.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  // Keep viewport geometry and scroll-driven scene animations unchanged while open.
  function blockBackgroundScroll(event) {
    if (!open) return;
    if (navigation.contains(event.target) && navigation.scrollHeight > navigation.clientHeight) return;
    event.preventDefault();
  }
  mobile.addEventListener('change', () => { if (!mobile.matches) setOpen(false); });
  addEventListener('pagehide', () => setOpen(false));
  return { close: () => setOpen(false), get isOpen() { return open; } };
}
