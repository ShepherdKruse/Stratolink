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
    src: '/assets/blog/wind-path-hero.png',
    alt: 'A map of the North Atlantic showing Stratolink 3’s track from San Francisco to Spain. The eight-day section with no GPS fixes is drawn as a dashed line.',
    width: 1200,
    height: 675,
    caption: 'Stratolink 3, May 2026. The dashed section is eight days without a packet.',
  },
  interactive: 'wind-path',
  styles: ['/payload-dev-log/article.css', '/wind-path/figures.css'],
  body,
};
