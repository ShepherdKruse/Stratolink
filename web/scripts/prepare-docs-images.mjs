import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Run after changing a preparation illustration; the generated files are committed.
const directory = new URL('../public/assets/docs/prep/', import.meta.url);
for (let step = 1; step <= 5; step++) {
  for (const width of [480, 960]) {
    execFileSync('cwebp', [
      '-quiet', '-q', '90', '-alpha_q', '100', '-m', '6',
      '-resize', String(width), '0',
      fileURLToPath(new URL(`step-${step}.webp`, directory)),
      '-o', fileURLToPath(new URL(`step-${step}-${width}.webp`, directory)),
    ], { stdio: 'inherit' });
  }
}
