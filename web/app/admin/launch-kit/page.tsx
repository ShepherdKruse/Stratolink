'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import { listLaunchKitDevices, rotateLaunchLink } from '@/lib/actions/launch-kit';

export default function LaunchKitPage() {
    const [adminKey, setAdminKey] = useState('');
    const [rows, setRows] = useState<{ device_id: string; launch_token_expires_at: string | null }[]>([]);
    const [err, setErr] = useState<string | null>(null);
    const [pending, startTransition] = useTransition();
    const [lastQr, setLastQr] = useState<{ device_id: string; url: string; dataUrl: string } | null>(null);

    function load() {
        setErr(null);
        startTransition(async () => {
            const r = await listLaunchKitDevices(adminKey);
            if (!r.ok) {
                setErr(r.error);
                setRows([]);
                return;
            }
            setRows(r.devices);
        });
    }

    function issueQr(deviceId: string) {
        setErr(null);
        setLastQr(null);
        startTransition(async () => {
            const r = await rotateLaunchLink(adminKey, deviceId);
            if (!r.ok) {
                setErr(r.error);
                return;
            }
            setLastQr({ device_id: deviceId, url: r.activateUrlWithToken, dataUrl: r.qrDataUrl });
        });
    }

    return (
        <div className="mx-auto max-w-3xl px-4 py-10 text-foreground">
            <h1 className="text-2xl font-semibold tracking-tight">Launch kit</h1>
            <p className="mt-2 text-sm text-muted-foreground">
                Devices in <code className="text-xs">storage</code>. Issue a fresh QR (invalidates any previous launch link for that device). Print the image
                for the payload label — scanning opens activate with no PIN.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
                <Link href="/admin/register-payload" className="underline">
                    Register new payload
                </Link>
            </p>

            <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-end">
                <label className="block flex-1 text-sm font-medium">
                    Admin key
                    <input
                        type="password"
                        autoComplete="off"
                        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={adminKey}
                        onChange={(e) => setAdminKey(e.target.value)}
                    />
                </label>
                <button
                    type="button"
                    disabled={pending || !adminKey}
                    onClick={load}
                    className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                    {pending ? '…' : 'Load devices'}
                </button>
            </div>

            {err && (
                <pre className="mt-6 whitespace-pre-wrap rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
                    {err}
                </pre>
            )}

            {rows.length > 0 && (
                <ul className="mt-8 divide-y divide-border rounded-md border border-border">
                    {rows.map((d) => (
                        <li key={d.device_id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                            <div>
                                <div className="font-mono text-sm font-medium">{d.device_id}</div>
                                {d.launch_token_expires_at && (
                                    <div className="text-xs text-muted-foreground">
                                        Link expires: {new Date(d.launch_token_expires_at).toLocaleString()}
                                    </div>
                                )}
                            </div>
                            <button
                                type="button"
                                disabled={pending || !adminKey}
                                onClick={() => issueQr(d.device_id)}
                                className="shrink-0 rounded-md border border-input bg-muted px-3 py-1.5 text-xs font-medium hover:bg-muted/80"
                            >
                                Issue / refresh QR
                            </button>
                        </li>
                    ))}
                </ul>
            )}

            {lastQr && (
                <div className="mt-10 rounded-md border border-border bg-muted/30 p-6">
                    <h2 className="text-sm font-semibold">QR for {lastQr.device_id}</h2>
                    <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{lastQr.url}</p>
                    <img src={lastQr.dataUrl} alt="Launch QR" className="mt-4 max-w-xs border border-border bg-white p-2" />
                    <p className="mt-3 text-xs text-muted-foreground">Right-click image → Save, or screenshot for labels.</p>
                </div>
            )}
        </div>
    );
}
