'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import { registerPayloadAction } from '@/lib/actions/register-payload';

export default function RegisterPayloadAdminPage() {
    const [adminKey, setAdminKey] = useState('');
    const [deviceId, setDeviceId] = useState('');
    const [joinEui, setJoinEui] = useState('');
    const [devEui, setDevEui] = useState('');
    const [out, setOut] = useState<string | null>(null);
    const [err, setErr] = useState<string | null>(null);
    const [pending, startTransition] = useTransition();

    function run() {
        setErr(null);
        setOut(null);
        startTransition(async () => {
            const r = await registerPayloadAction(adminKey, {
                deviceId: deviceId.trim() || undefined,
                joinEui: joinEui.trim() || undefined,
                devEui: devEui.trim() || undefined,
            });
            if (!r.ok) {
                setErr([r.error, r.details].filter(Boolean).join('\n'));
                return;
            }
            setOut(
                [
                    `Device ID (TTN + map): ${r.deviceId}`,
                    `Launch PIN: ${r.claimCode}`,
                    `TTN console: ${r.ttnDeviceUrl}`,
                    '',
                    r.firmwareSnippet,
                ].join('\n')
            );
        });
    }

    return (
        <div className="mx-auto max-w-2xl px-4 py-10 text-foreground">
            <h1 className="text-2xl font-semibold tracking-tight">Register payload</h1>
            <p className="mt-2 text-sm text-muted-foreground">
                Creates an OTAA device in your TTN application and a matching row in Supabase. After you flash keys,
                uplinks must hit your production{' '}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">/api/ttn-webhook</code> integration so telemetry
                appears on the map. RSSI/SNR come from whichever gateway TTN lists for each packet.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
                <Link href="/activate" className="underline">
                    Launch day
                </Link>
                : operator enters this device ID and the PIN below to set status to <code className="text-xs">flying</code>.
            </p>

            <div className="mt-8 space-y-4">
                <label className="block text-sm font-medium">
                    Admin key
                    <input
                        type="password"
                        autoComplete="off"
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={adminKey}
                        onChange={(e) => setAdminKey(e.target.value)}
                        placeholder="ADMIN_ACTIVATION_KEY"
                    />
                </label>
                <label className="block text-sm font-medium">
                    Device ID (optional)
                    <input
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={deviceId}
                        onChange={(e) => setDeviceId(e.target.value)}
                        placeholder="e.g. stratolink-001 (lowercase; auto if empty)"
                    />
                </label>
                <label className="block text-sm font-medium">
                    Join EUI / AppEUI (optional)
                    <input
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono text-xs"
                        value={joinEui}
                        onChange={(e) => setJoinEui(e.target.value)}
                        placeholder="16 hex — defaults to TTN_JOIN_EUI env"
                    />
                </label>
                <label className="block text-sm font-medium">
                    DevEUI (optional)
                    <input
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono text-xs"
                        value={devEui}
                        onChange={(e) => setDevEui(e.target.value)}
                        placeholder="16 hex — random if empty (then flash generated EUI)"
                    />
                </label>
                <button
                    type="button"
                    disabled={pending || !adminKey}
                    onClick={run}
                    className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                    {pending ? 'Registering…' : 'Register on TTN + Supabase'}
                </button>
            </div>

            {err && (
                <pre className="mt-6 whitespace-pre-wrap rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
                    {err}
                </pre>
            )}
            {out && (
                <pre className="mt-6 whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 text-sm">{out}</pre>
            )}

            <p className="mt-8 text-xs text-muted-foreground">
                API: <code className="rounded bg-muted px-1">POST /api/admin/register-payload</code> with{' '}
                <code className="rounded bg-muted px-1">Authorization: Bearer …</code>
            </p>
        </div>
    );
}
