import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { posts, readingTime } from '../content/blog.mjs';
import { socialMetadata } from './social-metadata.mjs';

const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const image = (post, attributes = '') => `<img data-post-image src="${escape(post.image.src)}" alt="${escape(post.image.alt)}" width="${post.image.width}" height="${post.image.height}"${post.image.position ? ` style="object-position:${escape(post.image.position)}"` : ''} ${attributes}>`;
const card = (post, type) => `<a class="${type}" href="/blog/${post.slug}" data-post-link id="${type}-${post.slug}">
  <span class="category">${escape(post.category)}</span>
  <h3 data-post-title>${escape(post.title)}</h3>
  <p>${escape(post.excerpt)}</p>
</a>`;

function indexMain() {
  const [featured, ...recent] = posts;
  return `<main id="main" class="blog-main" tabindex="-1">
    <h1 class="sr-only">Blog</h1>
    ${featured ? `<div class="blog-lead${recent.length ? '' : ' blog-lead--single'}">
      <a class="featured" href="/blog/${featured.slug}" data-post-link data-origin="featured" id="featured-${featured.slug}" aria-labelledby="featured-title">
        ${image(featured, 'fetchpriority="high"')}
        <div class="featured-copy">
          <span class="category">${escape(featured.category)}</span>
          <h2 id="featured-title" data-post-title>${escape(featured.title)}</h2>
          <p class="featured-excerpt">${escape(featured.excerpt)}</p>
        </div>
        <span class="articles-link">Read more</span>
      </a>
      ${recent.length ? `<section class="latest" aria-labelledby="latest-title">
        <h2 id="latest-title" class="section-label">Latest</h2>
        ${recent.slice(0, 2).map(post => card(post, 'latest-entry')).join('\n')}
      </section>` : ''}
    </div>` : ''}
    ${posts.length > 3 ? `<section id="articles" class="article-section" aria-labelledby="articles-title">
      <div class="article-section-header"><h2 id="articles-title" class="section-label">All articles</h2>
        <div class="article-rail-controls" hidden><button type="button" data-rail-direction="-1" aria-label="Previous articles"><img src="/assets/icons/chevron-left.svg" alt="" width="9" height="12"></button><button type="button" data-rail-direction="1" aria-label="Next articles"><img src="/assets/icons/chevron-right.svg" alt="" width="9" height="12"></button></div>
      </div>
      <div class="article-grid" tabindex="0" role="region" aria-label="All articles, scroll horizontally">
        ${posts.map(post => card(post, 'article-card')).join('\n')}
      </div>
    </section>` : ''}
  </main>`.replace(/\n[ \t]+\n/g, '\n');
}

export function writeBlogPages() {
  const indexUrl = new URL('../blog/index.html', import.meta.url);
  const index = readFileSync(indexUrl, 'utf8');
  const header = index.match(/<header class="blog-header">[\s\S]*?<\/header>/)[0];
  const home = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const footer = home.match(/<footer class="site-footer">[\s\S]*?<\/footer>/)[0].replace('class="site-footer"', 'class="blog-footer article-footer"');
  const nextIndex = index.replace(/<main\b[\s\S]*?<\/main>/, indexMain()).replace(/<footer\b[\s\S]*?<\/footer>/, footer);
  if (index !== nextIndex) writeFileSync(indexUrl, nextIndex);
  const directory = new URL('../blog/posts/', import.meta.url);
  mkdirSync(directory, { recursive: true });
  return Object.fromEntries(posts.map(post => {
    const url = new URL(`${post.slug}.html`, directory);
    writeFileSync(url, `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link id="site-favicon" rel="icon" href="/assets/favicon/globe.png" type="image/png" sizes="64x64">
  <link rel="apple-touch-icon" href="/assets/favicon/apple-touch-icon.png">
  <script type="module" src="/src/favicon.js"></script>
  <meta name="theme-color" content="#f6f4ef">
  <meta name="description" content="${escape(post.excerpt)}">
  <title>${escape(post.title)} - Stratolink</title>
${socialMetadata({ title: `${post.title} - Stratolink`, path: `/blog/${post.slug}`, description: post.excerpt, image: post.image, type: 'article' })}
  <link rel="stylesheet" href="/src/blog.css">
  <script type="module" src="/src/blog-navigation.js"></script>
</head>
<body class="article-page">
  <a class="skip-link" href="#main">Skip to content</a>
  ${header}
  <main id="main" class="post-main" data-post="${post.slug}" tabindex="-1">
    <article>
      <header class="post-heading">
        <a class="post-back" href="/blog" data-blog-back><img src="/assets/icons/chevron-left.svg" alt="" width="9" height="12">All articles</a>
        <h1 data-post-title>${escape(post.title)}</h1>
        <div class="post-meta">
          <a href="${escape(post.author.github)}" target="_blank" rel="noreferrer">${escape(post.author.name)}</a>
          <time datetime="${post.published}">${escape(post.publishedLabel)}</time>
          <span>${readingTime(post)} min read</span>
        </div>
      </header>
      <figure class="post-hero">${image(post, 'fetchpriority="high"')}<figcaption>${escape(post.image.caption)}</figcaption></figure>
      <div class="post-body">${post.body}</div>
    </article>
  </main>
  ${footer}
</body>
</html>`);
    return [`post-${post.slug}`, url.pathname];
  }));
}
