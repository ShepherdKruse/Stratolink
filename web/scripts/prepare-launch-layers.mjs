import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Compile the existing SVG masks once instead of filtering the photograph on phones.
const assets = new URL('../public/assets/launch/', import.meta.url);
const temporary = mkdtempSync(join(tmpdir(), 'stratolink-layers-'));
const image = (name, type) => `data:image/${type};base64,${readFileSync(new URL(name, assets)).toString('base64')}`;
const photo = image('source.jpg', 'jpeg');
const city = image('city-mask.png', 'png');
const balloon = image('balloon-mask.png', 'png');
const variants = [
  { name: 'city-desktop', width: 2560, height: 1440, viewBox: '0 0 2560 1440', mask: city,
    bounds: 'x="0" y="0" width="2560" height="1440"',
    filter: '<feGaussianBlur stdDeviation="10"/>', base: '<rect y="1410" width="2560" height="30" fill="white"/>' },
  { name: 'city-mobile', width: 2560, height: 1440, viewBox: '0 0 2560 1440', mask: city,
    bounds: 'x="0" y="0" width="2560" height="1440"',
    filter: '<feComponentTransfer><feFuncA type="linear" slope="1.45" intercept="-.45"/></feComponentTransfer><feGaussianBlur stdDeviation="6"/>',
    base: '<rect y="1410" width="2560" height="30" fill="white"/>' },
  { name: 'balloon-cutout', width: 205, height: 403, viewBox: '1228 432 205 403', mask: balloon,
    bounds: 'x="1228" y="432" width="205" height="403"',
    filter: '<feMorphology operator="dilate" radius="2"/><feGaussianBlur stdDeviation=".5"/>', base: '' },
];

try {
  for (const layer of variants) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${layer.width}" height="${layer.height}" viewBox="${layer.viewBox}">
      <defs><filter id="edge" x="-5%" y="-5%" width="110%" height="110%">${layer.filter}</filter>
      <mask id="cutout" maskUnits="userSpaceOnUse" ${layer.bounds} style="mask-type:alpha">
        <image href="${layer.mask}" width="2560" height="1440" preserveAspectRatio="none" filter="url(#edge)"/>${layer.base}
      </mask></defs>
      <image href="${photo}" width="2560" height="1440" mask="url(#cutout)"/>
    </svg>`;
    const input = join(temporary, `${layer.name}.svg`);
    const raster = join(temporary, `${layer.name}.png`);
    writeFileSync(input, svg);
    execFileSync('rsvg-convert', [input, '-o', raster]);
    execFileSync('cwebp', ['-quiet', '-q', '90', '-alpha_q', '100', '-m', '6', raster,
      '-o', fileURLToPath(new URL(`${layer.name}.webp`, assets))]);
  }
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
