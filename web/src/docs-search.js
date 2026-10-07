import './docs-search.css';
import { updateHeaderFooter } from './site-chrome.js';

const input = document.querySelector('#docs-search');
if (input) {
  const directory = document.querySelector('#docs-directory');
  const results = document.createElement('section');
  results.id = 'docs-search-results';
  results.className = 'docs-search-results';
  results.setAttribute('aria-label', 'Search results');
  results.hidden = true;
  const status = document.createElement('p');
  status.className = 'docs-search-status';
  status.setAttribute('role', 'status');
  const list = document.createElement('ol');
  results.append(status, list);
  directory.before(results);
  input.parentElement.hidden = false;
  input.maxLength = 300;
  input.setAttribute('aria-controls', `${results.id} docs-directory`);
  document.querySelector('.docs-empty')?.remove();
  let controller;
  let timer;

  const reset = () => {
    clearTimeout(timer);
    controller?.abort();
    results.hidden = true;
    results.removeAttribute('aria-busy');
    directory.hidden = false;
    list.replaceChildren();
    status.textContent = '';
    updateHeaderFooter();
  };

  const search = async () => {
    const query = input.value.trim();
    if (query.length < 2) return reset();
    controller?.abort();
    const request = new AbortController();
    controller = request;
    results.hidden = false;
    results.setAttribute('aria-busy', 'true');
    status.textContent = 'Searching docs…';
    try {
      const response = await fetch(`/api/docs-search?q=${encodeURIComponent(query)}`, { signal: request.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Search is unavailable. Browse the sections below.');
      if (request.signal.aborted) return;
      list.replaceChildren(...data.results.map(result => {
        const item = document.createElement('li');
        const link = document.createElement('a');
        link.href = result.url;
        const section = document.createElement('span');
        section.className = 'docs-result-section';
        section.textContent = result.section;
        const title = document.createElement('h2');
        title.textContent = result.title;
        const excerpt = document.createElement('p');
        excerpt.textContent = result.excerpt;
        link.append(section, title, excerpt);
        item.append(link);
        return item;
      }));
      status.textContent = data.results.length ? `${data.results.length} matching ${data.results.length === 1 ? 'section' : 'sections'}` : 'No close matches. Try a different question or browse the sections below.';
      directory.hidden = data.results.length > 0;
    } catch (error) {
      if (request.signal.aborted) return;
      list.replaceChildren();
      status.textContent = 'Search is unavailable. Browse the sections below.';
      directory.hidden = false;
    } finally {
      if (controller === request) {
        results.removeAttribute('aria-busy');
        updateHeaderFooter();
      }
    }
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    controller?.abort();
    if (input.value.trim().length < 2) reset();
    else timer = setTimeout(search, 300);
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') { clearTimeout(timer); search(); }
    if (event.key === 'Escape') { input.value = ''; reset(); }
  });
  addEventListener('pageshow', () => { if (input.value.trim().length >= 2) search(); });
}
