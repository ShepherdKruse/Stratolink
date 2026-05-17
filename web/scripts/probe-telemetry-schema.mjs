import 'dotenv/config';
import { readFileSync } from 'node:fs';

/* Tiny .env.local reader (dotenv/config doesn't auto-load .env.local) */
try {
    const raw = readFileSync(new URL('../.env.local', import.meta.url), 'utf8');
    for (const line of raw.split('\n')) {
        const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$/);
        if (m) process.env[m[1]] = process.env[m[1]] || m[2];
    }
} catch {}

const URL_BASE = process.env.NEXT_PUBLIC_SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!URL_BASE || !KEY) {
    console.error('Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
    process.exit(1);
}

async function main() {
    const sel = await fetch(`${URL_BASE}/rest/v1/telemetry?select=*&limit=1`, {
        headers: { apikey: KEY, Authorization: `Bearer ${KEY}` },
    });
    const rows = await sel.json();

    if (Array.isArray(rows) && rows.length) {
        console.log('Columns present (from existing row):');
        Object.keys(rows[0]).sort().forEach((k) => console.log('  -', k));
        return;
    }

    console.log('Table empty — probing via dry-run insert…');
    const probe = await fetch(`${URL_BASE}/rest/v1/telemetry`, {
        method: 'POST',
        headers: {
            apikey: KEY,
            Authorization: `Bearer ${KEY}`,
            'Content-Type': 'application/json',
            Prefer: 'return=representation',
        },
        body: JSON.stringify({ device_id: '__schema_probe__' }),
    });
    const inserted = await probe.json();
    if (Array.isArray(inserted) && inserted.length) {
        console.log('Columns present:');
        Object.keys(inserted[0]).sort().forEach((k) => console.log('  -', k));
        await fetch(`${URL_BASE}/rest/v1/telemetry?device_id=eq.__schema_probe__`, {
            method: 'DELETE',
            headers: { apikey: KEY, Authorization: `Bearer ${KEY}` },
        });
    } else {
        console.error('Probe insert failed:', inserted);
    }
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
