// Upload the GFS cubes built by scripts/gfs_ingest.py (.windcube/cubes/*.json)
// to Vercel Blob at cubes/{device}.json — the production read path for
// fetchWindCube. Runs after the Python ingest in the GitHub Actions workflow.
// Env: BLOB_READ_WRITE_TOKEN.
import { put } from '@vercel/blob';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const dir = join(process.cwd(), '.windcube', 'cubes');
if (!existsSync(dir)) {
    console.log('no .windcube/cubes — nothing to upload');
    process.exit(0);
}
const files = readdirSync(dir).filter((f) => f.endsWith('.json'));
if (!files.length) {
    console.log('no cube files to upload');
    process.exit(0);
}
let ok = 0;
for (const f of files) {
    const body = readFileSync(join(dir, f), 'utf8');
    const r = await put(`cubes/${f}`, body, {
        access: 'private',
        addRandomSuffix: false,
        contentType: 'application/json',
        allowOverwrite: true,
    });
    console.log(`uploaded cubes/${f} (${Math.round(body.length / 1024)} KB) -> ${r.url}`);
    ok++;
}
console.log(`done: ${ok}/${files.length} cubes uploaded`);
