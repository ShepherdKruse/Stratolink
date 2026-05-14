'use client';

import { useEffect, useState, useTransition } from 'react';
import Link from 'next/link';
import { registerPayloadAction } from '@/lib/actions/register-payload';
import { listClaims, type ClaimedRow } from '@/lib/actions/claim';

export default function RegisterPayloadAdminPage() {
    const [adminKey, setAdminKey] = useState('');
    const [deviceId, setDeviceId] = useState('');
    const [joinEui, setJoinEui] = useState('');
    const [devEui, setDevEui] = useState('');
    const [out, setOut] = useState<string | null>(null);
    const [err, setErr] = useState<string | null>(null);
    const [pending, startTransition] = useTransition();
    const [claims, setClaims] = useState<ClaimedRow[]>([]);

    const refreshClaims = () => {
        listClaims().then((r) => {
            if (r.ok) setClaims(r.rows);
        });
    };

    useEffect(refreshClaims, []);

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
                    `Device ID: ${r.deviceId}`,
                    `PIN (backup): ${r.claimCode}`,
                    `Launch QR URL (print this):`,
                    r.activateUrlWithToken,
                    `Expires: ${r.launchTokenExpiresAt}`,
                    `TTN: ${r.ttnDeviceUrl}`,
                    '',
                    r.firmwareSnippet,
                ].join('\n')
            );
            refreshClaims();
        });
    }

    const pendingClaims = claims.filter((c) => !c.has_keys && c.status === 'storage');

    return (
        <div className="mx-auto max-w-3xl px-4 py-10 text-foreground">
            <h1 className="text-2xl font-semibold tracking-tight">Register payload</h1>
            <p className="mt-2 text-sm text-muted-foreground">
                Creates the OTAA device in TTN and updates the matching <code className="rounded bg-muted px-1 py-0.5 text-xs">devices</code> row with a one-time
                launch link. Output includes a <code className="text-xs">secrets.h</code> block to send Teddy.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
                Re-issue QR labels later via{' '}
                <Link href="/admin/launch-kit" className="underline">
                    Launch kit
                </Link>
                . Claim form for participants:{' '}
                <Link href="/claim" className="underline">
                    /claim
                </Link>
                .
            </p>

            {pendingClaims.length > 0 && (
                <div className="mt-8 rounded-md border border-yellow-700/40 bg-yellow-500/5 p-4">
                    <h2 className="text-sm font-semibold text-yellow-200">Awaiting keys</h2>
                    <p className="mt-1 text-xs text-yellow-200/70">Click a row to load it into the form, then paste the DevEUI Teddy sent.</p>
                    <ul className="mt-3 divide-y divide-yellow-700/30">
                        {pendingClaims.map((c) => (
                            <li key={c.device_id} className="flex items-center justify-between py-2 text-sm">
                                <div>
                                    <div className="font-mono">{c.device_id}</div>
                                    <div className="text-[11px] text-yellow-200/70">{c.launcher_name || 'No commander name'}</div>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setDeviceId(c.device_id)}
                                    className="rounded border border-yellow-700/40 bg-yellow-500/10 px-3 py-1.5 text-xs font-medium text-yellow-100 hover:bg-yellow-500/20"
                                >
                                    Load
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

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
                    Device ID (callsign)
                    <input
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
                        value={deviceId}
                        onChange={(e) => setDeviceId(e.target.value)}
                        placeholder="e.g. stratolink-orion (matches /claim)"
                    />
                </label>
                <label className="block text-sm font-medium">
                    Join EUI / AppEUI (optional)
                    <input
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                        value={joinEui}
                        onChange={(e) => setJoinEui(e.target.value)}
                        placeholder="16 hex — defaults to TTN_JOIN_EUI env"
                    />
                </label>
                <label className="block text-sm font-medium">
                    DevEUI (from Teddy / factory)
                    <input
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                        value={devEui}
                        onChange={(e) => setDevEui(e.target.value)}
                        placeholder="16 hex; random if empty"
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
            {out && <pre className="mt-6 whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 text-sm">{out}</pre>}

            <p className="mt-8 text-xs text-muted-foreground">
                API: <code className="rounded bg-muted px-1">POST /api/admin/register-payload</code> with{' '}
                <code className="rounded bg-muted px-1">Authorization: Bearer …</code>
            </p>
        </div>
    );
}
