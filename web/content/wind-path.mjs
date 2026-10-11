import { readFileSync } from 'node:fs';

const body = readFileSync(new URL('./articles/drawing-the-path-between-packets.html', import.meta.url), 'utf8');

export const windPathArticle = {
  slug: 'drawing-the-path-between-packets',
  title: 'Drawing the path between packets',
  category: 'Dev log',
  excerpt: 'Stratolink 3 flew for twelve days and reported where it was for about one of them. How the dashboard fills in the rest from the wind, and what I changed to make that line trustworthy.',
  published: '2026-10',
  publishedLabel: 'October 2026',
  author: { name: 'Caleb Kruse', github: 'https://github.com/clkruse' },
  image: {
    src: '/assets/blog/wind-path-hero.jpg',
    alt: 'A map of the North Atlantic with Stratolink 3’s track from San Francisco to Spain. Across the eight-day gap, two thousand faint blue possible routes fan over the ocean and the red line the dashboard draws runs through the densest part of them.',
    width: 2400,
    height: 1230,
    caption: 'Stratolink 3, May 2026: the 2,000 routes the smoother considers across eight days without a packet, and the one the dashboard draws.',
  },
  interactive: 'wind-path',
  styles: ['/payload-dev-log/article.css', '/wind-path/figures.css'],
  body,
};
