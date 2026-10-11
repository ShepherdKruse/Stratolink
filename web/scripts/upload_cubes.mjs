// MANUAL dev tool — not part of the GitHub Actions workflow. Uploads the cubes
// built by scripts/gfs_ingest.py (.windcube/cubes/*.slwc|*.json) to Vercel Blob
// at cubes/{name}.gz. The production compute (scripts/compute_forecasts.ts)
// reads cubes straight off the runner's disk via WIND_CUBE_DIR, so nothing in
// production reads cubes/* any more; fetchWindCube only consults Blob when
// WIND_CUBE_DIR is unset. scripts/blob_cleanup.mjs removes stale uploads.
// Env: BLOB_READ_WRITE_TOKEN (e.g. node --env-file=.env.local scripts/upload_cubes.mjs).
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
// EXCLUDE ensemble member cubes ({device}-mNN / -aNN .slwc): those are read only
// by the runner compute (locally, via WIND_CUBE_DIR); dozens of them would be
// far too much for any Blob-reading compute.
const files = readdirSync(dir).filter(
    (f) => (f.endsWith('.slwc') || f.endsWith('.json')) && !/-[ma]\d+\.slwc$/.test(f),
);
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
