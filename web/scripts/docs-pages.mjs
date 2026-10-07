import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { sections, topicId } from '../content/docs.mjs';

const caret = '<img src="/assets/icons/chevron-right.svg" alt="" width="8" height="12">';
const topicLinks = section => section.topics.map(topic => `<a href="/docs/${section.slug}#${topicId(topic.title)}">${topic.title}</a>`).join('');

export function writeDocsPages() {
  const blog = readFileSync(new URL('../blog/index.html', import.meta.url), 'utf8');
  const header = blog.match(/<header class="blog-header">[\s\S]*?<\/header>/)[0]
    .replaceAll(' aria-current="page"', '').replaceAll('href="/docs"', 'href="/docs" aria-current="page"');
  const footer = blog.match(/<footer class="blog-footer article-footer">[\s\S]*?<\/footer>/)[0];
  const directory = new URL('../docs/pages/', import.meta.url);
  mkdirSync(directory, { recursive: true });
  const inputs = {};
  const write = (slug, title, main, className) => {
    const url = new URL(slug === 'index' ? '../index.html' : `${slug}.html`, directory);
    writeFileSync(url, `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link id="site-favicon" rel="icon" href="/assets/favicon/globe.png" type="image/png" sizes="64x64">
  <link rel="apple-touch-icon" href="/assets/favicon/apple-touch-icon.png">
  <script type="module" src="/src/favicon.js"></script>
  <meta name="theme-color" content="#f6f4ef">
  <title>${title} - Stratolink</title>
  <link rel="stylesheet" href="/src/docs.css">
  <script type="module" src="/src/docs.js"></script>
  ${slug === 'balloon-prep' ? '<script type="module" src="/src/float-calculator.js"></script>' : ''}
</head>
<body class="${className}">
  <a class="skip-link" href="#main">Skip to content</a>
  ${header}
  ${main}
  ${footer}
</body>
</html>`);
    inputs[`docs-${slug}`] = url.pathname;
  };

  const groups = sections.map(section => `<details class="docs-group" data-docs-group>
    <summary>${section.title}${caret}</summary>
    <div class="docs-group-links"><a href="/docs/${section.slug}">${section.title}</a>${topicLinks(section)}</div>
  </details>`);
  write('index', 'Docs', `<main id="main" class="docs-index" tabindex="-1">
    <div class="docs-index-heading"><h1>Docs</h1>
      <div class="docs-search" hidden><label class="sr-only" for="docs-search">Search docs</label>
        <input id="docs-search" type="search" placeholder="search docs" autocomplete="off" aria-controls="docs-directory">
      </div>
    </div>
    <div id="docs-directory" class="docs-directory">
      <div>${groups.slice(0, Math.ceil(groups.length / 2)).join('')}</div><div>${groups.slice(Math.ceil(groups.length / 2)).join('')}</div>
    </div>
    <p class="docs-empty" role="status" hidden>No matching sections.</p>
  </main>`, 'docs-index-page');

  sections.forEach((section, index) => {
    const sidebar = `<nav aria-label="Documentation">${sections.map(item => `<div class="docs-nav-section">
      <a href="/docs/${item.slug}"${item.slug === section.slug ? ' aria-current="page"' : ''}>${item.title}</a>
      ${item.slug === section.slug ? `<div class="docs-nav-topics">${topicLinks(item)}</div>` : ''}
    </div>`).join('')}</nav>`;
    const next = sections[index + 1];
    const previous = sections[index - 1];
    write(section.slug, section.title, `<main id="main" class="docs-layout" tabindex="-1">
      <aside class="docs-sidebar"><a class="docs-back" href="/docs"><img src="/assets/icons/chevron-left.svg" alt="" width="8" height="12">All docs</a>${sidebar}</aside>
      <details class="docs-mobile-sections"><summary>In this section ${caret}</summary><div><a class="docs-back" href="/docs">All docs</a>${sidebar}</div></details>
      <article class="docs-article">
        <header class="docs-article-heading"><h1>${section.title}</h1></header>
        <div class="post-body"><p class="post-intro">${section.intro}</p>
          ${section.topics.map(topic => `<section id="${topicId(topic.title)}"><h2><a href="#${topicId(topic.title)}">${topic.title}</a></h2>${topic.html.replaceAll('<a href="/dashboard', '<a target="_blank" rel="noopener" title="Opens in a new tab" href="/dashboard')}</section>`).join('')}
          ${section.sources?.length ? `<details class="docs-aside docs-sources"><summary>References</summary><ul>${section.sources.map(source => `<li><a href="${source.url}">${source.title}</a></li>`).join('')}</ul></details>` : ''}
        </div>
        <nav class="docs-pagination" aria-label="Adjacent documentation">
          ${previous ? `<a href="/docs/${previous.slug}" rel="prev"><span>Previous</span><strong><img src="/assets/icons/chevron-left.svg" alt="" width="8" height="12">${previous.title}</strong></a>` : '<span></span>'}
          ${next ? `<a href="/docs/${next.slug}" rel="next"><span>Next</span><strong>${next.title}${caret}</strong></a>` : ''}
        </nav>
      </article>
    </main>`, 'docs-article-page');
  });
  return inputs;
}
