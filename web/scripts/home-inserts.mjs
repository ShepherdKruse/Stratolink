import { readFileSync, writeFileSync } from 'node:fs';
import { posts } from '../content/blog.mjs';
import { sections } from '../content/docs.mjs';

const caret = '<img src="/assets/icons/chevron-right.svg" alt="" width="8" height="12">';
const readingTime = text => Math.max(1, Math.ceil(text.replace(/<[^>]*>/g, ' ').trim().split(/\s+/).length / 220));

export function writeHomeInserts() {
  const docs = ['getting-started', 'architecture', 'dashboard'].map(slug => sections.find(section => section.slug === slug));
  const docLinks = `<section class="story-docs" aria-label="Introduction docs">
    ${docs.map(section => `<a href="/docs/${section.slug}"><span>${section.title}</span><span class="story-link-meta">${readingTime(section.intro + section.topics.map(topic => topic.html).join(' '))} min read${caret}</span></a>`).join('\n    ')}
  </section>`;
  const cards = `<section class="story-blog" aria-label="Latest from the blog">
    <div class="story-blog-grid">
      ${posts.slice(0, 3).map((post, index) => `<a class="story-blog-card${index === 0 ? ' story-blog-featured' : ''}" href="/blog/${post.slug}">
        ${index === 0 ? `<img class="story-blog-image" src="${post.image.src}" alt="" width="${post.image.width}" height="${post.image.height}"${post.image.position ? ` style="object-position:${post.image.position}"` : ''} loading="lazy">` : ''}
        <span class="story-blog-category">${post.category}</span>
        <h2>${post.title}</h2>
        <span class="story-link-meta">${readingTime(post.body)} min read${caret}</span>
      </a>`).join('\n      ')}
    </div>
  </section>`.replace(/\n[ \t]+\n/g, '\n');
  const url = new URL('../index.html', import.meta.url);
  let html = readFileSync(url, 'utf8');
  html = html.replace(/<!-- home-docs:start -->[\s\S]*?<!-- home-docs:end -->/, `<!-- home-docs:start -->\n${docLinks}\n<!-- home-docs:end -->`);
  html = html.replace(/<!-- home-blog:start -->[\s\S]*?<!-- home-blog:end -->/, `<!-- home-blog:start -->\n${cards}\n<!-- home-blog:end -->`);
  if (html !== readFileSync(url, 'utf8')) writeFileSync(url, html);
}
