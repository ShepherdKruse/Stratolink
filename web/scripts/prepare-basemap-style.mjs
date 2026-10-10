import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Build the dashboard's basemap from the stock Mapbox light/dark styles, keeping only the layers a world-scale
// balloon tracker needs: land, water, rivers, borders and place names. The stock styles carry 50 layers (roads,
// buildings, land use, POIs, ...) that cost style setup, tile parsing and shader compiles on every boot and were
// mostly hidden anyway. One style serves both the homepage footer globe and the dashboard, so entering the
// dashboard never swaps styles. Code-added relief and bathymetry (baseStyle.ts, bathymetry.ts) layer on top.
// Regenerate with: NEXT_PUBLIC_MAPBOX_TOKEN=... node scripts/prepare-basemap-style.mjs
const KEEP = [
  'land', 'water', 'waterway',
  'admin-1-boundary-bg', 'admin-0-boundary-bg', 'admin-1-boundary', 'admin-0-boundary', 'admin-0-boundary-disputed',
  'natural-line-label', 'natural-point-label', 'water-line-label', 'water-point-label',
  'settlement-minor-label', 'settlement-major-label', 'country-label', 'continent-label',
];
const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
if (!token) throw new Error('NEXT_PUBLIC_MAPBOX_TOKEN is required');
for (const scheme of ['light', 'dark']) {
  const response = await fetch(`https://api.mapbox.com/styles/v1/mapbox/${scheme}-v11?access_token=${token}`);
  if (!response.ok) throw new Error(`${scheme}-v11: ${response.status}`);
  const stock = await response.json();
  const missing = KEEP.filter(id => !stock.layers.some(layer => layer.id === id));
  if (missing.length) throw new Error(`${scheme}-v11 lacks ${missing.join(', ')}`);
  const style = {
    version: 8,
    name: `stratolink-${scheme}`,
    sources: stock.sources,
    sprite: stock.sprite,
    glyphs: stock.glyphs,
    projection: { name: 'globe' },
    layers: stock.layers.filter(layer => KEEP.includes(layer.id)).map(({ metadata, ...layer }) => layer),
  };
  const out = fileURLToPath(new URL(`../src/dashboard/components/maps/basemap.${scheme}.json`, import.meta.url));
  writeFileSync(out, JSON.stringify(style, null, 1) + '\n');
  console.log(`${scheme}: ${style.layers.length} layers (${style.layers.filter(l => l.type === 'symbol').length} symbol), ${JSON.stringify(style).length} bytes`);
}
