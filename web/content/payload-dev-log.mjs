import { readFileSync } from 'node:fs';
import katex from 'katex';

const source = readFileSync(new URL('./articles/building-towards-stratolink-v1.html', import.meta.url), 'utf8');
const body = source.replace(/<(div|span)([^>]*?) data-math="([^"]*)"><\/\1>/g,
  (_, tag, attrs, expression) => `<${tag}${attrs}>${katex.renderToString(expression, { displayMode: tag === 'div', throwOnError: true, output: 'htmlAndMathml' })}</${tag}>`);

export const payloadArticle = {
  slug: 'building-towards-stratolink-v1',
  title: 'Building towards Stratolink v1',
  category: 'Dev log',
  excerpt: 'Antenna models, radio tests, sensor choices, and the power budget for the next payload.',
  published: '2026-10',
  publishedLabel: 'October 2026',
  author: { name: 'Teddy Warner', github: 'https://github.com/twarner491' },
  image: {
    src: '/assets/payload-dev-log/payload.jpg',
    alt: 'The complete Stratolink payload and solar panels suspended above Dolores Park.',
    width: 1707,
    height: 2560,
    position: '65% 46%',
    caption: 'The Stratolink payload.',
  },
  interactive: true,
  heroPosition: 'center 58%',
  featuredClass: 'featured-payload',
  body,
};
