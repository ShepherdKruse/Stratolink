import { readFileSync } from 'node:fs';
try {
    const raw = readFileSync(new URL('../.env.local', import.meta.url), 'utf8');
    for (const line of raw.split('\n')) {
        const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$/);
        if (m) process.env[m[1]] = process.env[m[1]] || m[2];
    }
} catch {}
const URL_BASE = process.env.NEXT_PUBLIC_SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const r = await fetch(`${URL_BASE}/rest/v1/telemetry?select=*&order=time.desc&limit=5`, {
    headers: { apikey: KEY, Authorization: `Bearer ${KEY}` },
});
const rows = await r.json();
console.log(JSON.stringify(rows, null, 2));
