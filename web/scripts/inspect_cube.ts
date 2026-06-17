/* Dev: decode a .slwc cube and summarize geometry. For the tube (v2) it prints
 * how the per-slice box origin walks across time — a quick check that the cube
 * follows a trajectory and decodes correctly. Usage:
 *   npx tsx scripts/inspect_cube.ts .windcube/cubes/stratolink-3-fc.slwc */
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';

async function main() {
    const path = process.argv[2];
    if (!path) throw new Error('usage: inspect_cube.ts <path-to-.slwc[.gz]>');
    let buf = await readFile(path);
    if (path.endsWith('.gz')) buf = gunzipSync(buf);
    const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
    const dv = new DataView(ab);
    const headerLen = dv.getUint32(0, true);
    const h = JSON.parse(Buffer.from(ab, 4, headerLen).toString('utf8'));
    console.log('header keys:', Object.keys(h).join(', '));
    console.log(`v=${h.v} nGrids=${h.nGrids} dims=${h.nLat}x${h.nLon} step=${h.gridStep}° level=${h.levelHpa}hPa`);
    const t0 = new Date(h.t0Ms).toISOString();
    const tEnd = new Date(h.t0Ms + (h.nGrids - 1) * h.stepMs).toISOString();
    console.log(`time: ${t0} → ${tEnd}  (${(h.stepMs / 3.6e6)}h step)`);
    console.log(`union bounds: lat ${h.bounds.latMin.toFixed(1)}..${h.bounds.latMax.toFixed(1)}  lon ${h.bounds.lonMin.toFixed(1)}..${h.bounds.lonMax.toFixed(1)}`);
    if (h.origins) {
        const o = h.origins;
        const half = ((h.nLat - 1) * h.dLat) / 2;
        console.log(`tube centers (lat0+${half}°, lon0+${half}°), sampled every ~${Math.ceil(o.length / 12)} slices:`);
        for (let i = 0; i < o.length; i += Math.max(1, Math.ceil(o.length / 12))) {
            const t = new Date(h.t0Ms + i * h.stepMs).toISOString().slice(5, 16);
            console.log(`  [${String(i).padStart(3)}] ${t}  center lat ${(o[i][0] + half).toFixed(2)}  lon ${(o[i][1] + half).toFixed(2)}`);
        }
        const last = o.length - 1;
        console.log(`  [${last}] center lat ${(o[last][0] + half).toFixed(2)}  lon ${(o[last][1] + half).toFixed(2)} (final)`);
    } else {
        console.log('static cube (v1): single box, no per-slice origins');
    }
}
main().catch((e) => { console.error(e); process.exit(1); });
