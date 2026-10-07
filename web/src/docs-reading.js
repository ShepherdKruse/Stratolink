import { icon } from '@fortawesome/fontawesome-svg-core';
import { faCopy, faCheck, faXmark } from '@fortawesome/free-solid-svg-icons';

const svg = glyph => icon(glyph, { attributes: { 'aria-hidden': 'true' } }).html.join('');
const copyStatus = document.createElement('span');
copyStatus.className = 'sr-only';
copyStatus.setAttribute('role', 'status');
document.body.append(copyStatus);

document.querySelectorAll('.docs-article a[download][href="/assets/docs/ttn-uplink-formatter.js"]').forEach(link => {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'docs-inline-copy';
  button.title = 'Copy to your clipboard';
  button.setAttribute('aria-label', 'Copy uplink decoder to your clipboard');
  button.innerHTML = svg(faCopy);
  link.after(button);
  let reset;
  button.addEventListener('click', async () => {
    try {
      const contents = fetch(link.href).then(response => {
        if (!response.ok) throw new Error('Decoder unavailable');
        return response.text();
      });
      // Keep clipboard permission tied to the click while the file loads.
      if (window.ClipboardItem && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({
          'text/plain': contents.then(text => new Blob([text], { type: 'text/plain' })),
        })]);
      } else {
        await navigator.clipboard.writeText(await contents);
      }
      button.innerHTML = svg(faCheck);
      button.title = 'Copied';
      button.setAttribute('aria-label', 'Decoder copied');
      copyStatus.textContent = 'Uplink decoder copied to your clipboard.';
      clearTimeout(reset);
      reset = setTimeout(() => {
        button.innerHTML = svg(faCopy);
        button.title = 'Copy to your clipboard';
        button.setAttribute('aria-label', 'Copy uplink decoder to your clipboard');
        copyStatus.textContent = '';
      }, 1800);
    } catch {
      copyStatus.textContent = 'Could not copy. Download the decoder instead.';
    }
  });
});

document.querySelectorAll('.docs-article pre').forEach(pre => {
  const code = pre.querySelector('code') || pre;
  const text = code.textContent;
  const wrap = document.createElement('div');
  wrap.className = 'docs-code';
  pre.before(wrap);
  wrap.append(pre);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'docs-copy';
  button.setAttribute('aria-label', 'Copy code');
  button.innerHTML = svg(faCopy);
  wrap.append(button);
  let reset;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.innerHTML = svg(faCheck);
      button.setAttribute('aria-label', 'Copied');
      copyStatus.textContent = 'Code copied.';
      clearTimeout(reset);
      reset = setTimeout(() => {
        button.innerHTML = svg(faCopy);
        button.setAttribute('aria-label', 'Copy code');
        copyStatus.textContent = '';
      }, 1800);
    } catch {
      copyStatus.textContent = 'Could not copy. Select the code and copy it manually.';
    }
  };
  button.addEventListener('click', copy);
  pre.addEventListener('click', () => { if (!getSelection()?.toString()) void copy(); });
});

const figures = document.querySelectorAll('.docs-figure img');
if (figures.length) {
  const dialog = document.createElement('dialog');
  dialog.className = 'docs-lightbox';
  dialog.setAttribute('aria-label', 'Expanded image');
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'docs-lightbox-close';
  close.setAttribute('aria-label', 'Close image');
  close.innerHTML = svg(faXmark);
  const image = document.createElement('img');
  const caption = document.createElement('p');
  dialog.append(close, image, caption);
  document.body.append(dialog);
  let returnFocus;
  figures.forEach(img => {
    const figure = img.closest('figure');
    let trigger = img.closest('a');
    if (!trigger) {
      trigger = document.createElement('a');
      trigger.href = img.src;
      img.before(trigger);
      trigger.append(img);
    }
    trigger.classList.add('docs-image-open');
    trigger.setAttribute('aria-label', `Enlarge image: ${img.alt}`);
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      returnFocus = trigger;
      image.src = img.currentSrc || img.src;
      image.alt = img.alt;
      caption.textContent = figure?.querySelector('figcaption')?.textContent || '';
      caption.hidden = !caption.textContent;
      dialog.classList.toggle('is-illustration', Boolean(figure?.classList.contains('docs-illustration')));
      dialog.showModal();
      document.documentElement.classList.add('docs-image-expanded');
    });
  });
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => {
    document.documentElement.classList.remove('docs-image-expanded');
    returnFocus?.focus({ preventScroll: true });
  });
}
