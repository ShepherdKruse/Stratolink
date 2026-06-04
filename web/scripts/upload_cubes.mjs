// Upload the GFS cubes built by scripts/gfs_ingest.py (.windcube/cubes/*.json)
// to Vercel Blob at cubes/{device}.json.gz — the production read path for
// fetchWindCube. A fine, full-mission cube is several MB raw and the compute
// reads it every run, so we gzip (~4-5x smaller) for Blob bandwidth.
// Runs after the Python ingest in the GitHub Actions workflow.
// Env: BLOB_READ_WRITE_TOKEN.
import { put } from '@vercel/blob';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join } from 'node:path';

const dir = join(process.cwd(), '.windcube', 'cubes');
if (!existsSync(dir)) {
    console.log('no .windcube/cubes — nothing to upload');
    process.exit(0);
}
// `.slwc` is the packed-binary cube (current); `.json` kept for the transition.
const files = readdirSync(dir).filter((f) => f.endsWith('.slwc') || f.endsWith('.json'));
if (!files.length) {
    console.log('no cube files to upload');
    process.exit(0);
}
let ok = 0;
for (const f of files) {
    const raw = readFileSync(join(dir, f));
    const gz = gzipSync(raw, { level: 9 });
    const r = await put(`cubes/${f}.gz`, gz, {
        access: 'private',
        addRandomSuffix: false,
        contentType: 'application/gzip',
        allowOverwrite: true,
    });
    console.log(
        `uploaded cubes/${f}.gz (${Math.round(gz.length / 1024)} KB gz / ${Math.round(raw.length / 1024)} KB raw) -> ${r.url}`,
    );
    ok++;
}
console.log(`done: ${ok}/${files.length} cubes uploaded`);
