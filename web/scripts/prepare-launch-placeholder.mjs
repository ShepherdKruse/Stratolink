import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Render a tiny, heavily compressed copy of the launch photograph and inline it into index.html.
// It paints behind the hero (blurred by CSS) while the full-size layers are still downloading.
// Regenerate with: node scripts/prepare-launch-placeholder.mjs   (requires ImageMagick `magick`)
const source = fileURLToPath(new URL('../public/assets/launch/source.jpg', import.meta.url));
const page = new URL('../index.html', import.meta.url);
const webp = execFileSync('magick', [source, '-resize', '32x18!', '-strip', '-quality', '45', '-define', 'webp:method=6', 'webp:-']);
const style = `<style data-launch-placeholder>.scene-placeholder{background-image:url(data:image/webp;base64,${webp.toString('base64')})}</style>`;
const html = readFileSync(page, 'utf8');
const next = html.replace(/<!-- home-placeholder:start -->[\s\S]*?<!-- home-placeholder:end -->/,
  `<!-- home-placeholder:start -->\n  ${style}\n  <!-- home-placeholder:end -->`);
if (!next.includes('data-launch-placeholder')) throw new Error('index.html is missing the home-placeholder markers');
if (next !== html) writeFileSync(page, next);
console.log(`placeholder: ${webp.length} bytes`);
