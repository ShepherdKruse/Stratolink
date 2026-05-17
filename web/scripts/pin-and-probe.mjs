import { readFileSync } from 'node:fs';

const raw = readFileSync(new URL('../.env.local', import.meta.url), 'utf8');
for (const line of raw.split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$/);
    if (m) process.env[m[1]] = process.env[m[1]] || m[2];
}

const URL_BASE = process.env.NEXT_PUBLIC_SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

const pinR = await fetch(
    `${URL_BASE}/rest/v1/devices?device_id=in.(stratolink-1,stratolink-2,stratolink-3)`,
    {
        method: 'PATCH',
        headers: {
            apikey: KEY,
            Authorization: `Bearer ${KEY}`,
            'Content-Type': 'application/json',
            Prefer: 'return=representation',
        },
        body: JSON.stringify({ launch_lat: 37.7749, launch_lon: -122.4194 }),
    },
);
const pinned = await pinR.json();
console.log('Pin status:', pinR.status, '→', pinned.map((r) => r.device_id).join(', '));

const buf = Buffer.alloc(35);
buf.writeInt16BE(225, 12);
buf.writeUInt16BE(1013, 14);
buf.writeUInt16BE(420, 16);
buf.writeUInt16BE(3940, 18);
buf.writeUInt8(0, 31);
buf.writeUInt16BE(45, 32);
buf.writeUInt8(0, 34);

const wh = await fetch('https://stratolink.org/api/ttn-webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        end_device_ids: { device_id: 'stratolink-3' },
        received_at: new Date().toISOString(),
        uplink_message: {
            frm_payload: buf.toString('base64'),
            rx_metadata: [{ rssi: -92, snr: 8.1 }],
        },
    }),
});
console.log('Webhook status:', wh.status);
console.log('Webhook body:', await wh.json());
