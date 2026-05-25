'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import {
    listFlightDevices,
    setFlightStatus,
    type FlightRow,
    type FlightStatus,
} from '@/lib/actions/flight-status';

const STATUS_STYLES: Record<string, string> = {
    flying: 'bg-emerald-500/15 text-emerald-600 border-emerald-500/40',
    landed: 'bg-amber-500/15 text-amber-600 border-amber-500/40',
    retired: 'bg-muted text-muted-foreground border-border',
};

export default function FlightStatusPage() {
    const [adminKey, setAdminKey] = useState('');
    const [rows, setRows] = useState<FlightRow[]>([]);
    const [loaded, setLoaded] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    const [note, setNote] = useState<string | null>(null);
    const [pending, startTransition] = useTransition();

    function load() {
        setErr(null);
        setNote(null);
        startTransition(async () => {
            const r = await listFlightDevices(adminKey);
            if (!r.ok) {
                setErr(r.error);
                setRows([]);
                setLoaded(false);
                return;
            }
            setRows(r.devices);
            setLoaded(true);
        });
    }

    function changeStatus(deviceId: string, status: FlightStatus) {
        setErr(null);
        setNote(null);
        startTransition(async () => {
            const r = await setFlightStatus(adminKey, deviceId, status);
            if (!r.ok) {
                setErr(r.error);
                return;
            }
            setNote(`${deviceId} → ${status}`);
            /* Reflect the new status without a manual reload. */
            setRows((prev) => prev.map((d) => (d.device_id === deviceId ? { ...d, status } : d)));
        });
    }

    return (
        <div className="mx-auto max-w-3xl px-4 py-10 text-foreground">
            <h1 className="text-2xl font-semibold tracking-tight">Flight status</h1>
            <p className="mt-2 text-sm text-muted-foreground">
                Move launched devices through their lifecycle. <code className="text-xs">flying</code> devices appear
                in Mission Control; <code className="text-xs">landed</code> / <code className="text-xs">retired</code>{' '}
                devices appear in the{' '}
                <Link href="/dashboard-v2/archive" className="underline">
                    Mission Archive
                </Link>
                . Mark a flight <strong>landed</strong> when its mission ends so it moves into the archive.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
                <Link href="/admin/launch-kit" className="underline">
                    Launch kit
                </Link>{' '}
                ·{' '}
                <Link href="/admin/register-payload" className="underline">
                    Register payload
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
                    {pending ? '…' : 'Load flights'}
                </button>
            </div>

            {err && (
                <pre className="mt-6 whitespace-pre-wrap rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
                    {err}
                </pre>
            )}
            {note && (
                <p className="mt-6 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-700">
                    {note}
                </p>
            )}

            {loaded && rows.length === 0 && (
                <p className="mt-8 text-sm text-muted-foreground">No launched devices yet.</p>
            )}

            {rows.length > 0 && (
                <ul className="mt-8 divide-y divide-border rounded-md border border-border">
                    {rows.map((d) => (
                        <li
                            key={d.device_id}
                            className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                        >
                            <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="font-mono text-sm font-medium">{d.device_id}</span>
                                    <span
                                        className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                                            STATUS_STYLES[d.status] ?? STATUS_STYLES.retired
                                        }`}
                                    >
                                        {d.status}
                                    </span>
                                </div>
                                <div className="mt-1 text-xs text-muted-foreground">
                                    {d.launcher_name ? `${d.launcher_name} · ` : ''}
                                    {d.launched_at
                                        ? `launched ${new Date(d.launched_at).toLocaleString()}`
                                        : 'no launch time'}
                                </div>
                            </div>

                            <div className="flex shrink-0 flex-wrap gap-2">
                                {d.status !== 'landed' && (
                                    <ActionButton
                                        label="Mark landed"
                                        onClick={() => changeStatus(d.device_id, 'landed')}
                                        disabled={pending || !adminKey}
                                    />
                                )}
                                {d.status !== 'flying' && (
                                    <ActionButton
                                        label="Reopen flight"
                                        onClick={() => changeStatus(d.device_id, 'flying')}
                                        disabled={pending || !adminKey}
                                    />
                                )}
                                {d.status !== 'retired' && (
                                    <ActionButton
                                        label="Retire"
                                        onClick={() => changeStatus(d.device_id, 'retired')}
                                        disabled={pending || !adminKey}
                                    />
                                )}
                                {(d.status === 'landed' || d.status === 'retired') && (
                                    <Link
                                        href={`/dashboard-v2/archive/${encodeURIComponent(d.device_id)}`}
                                        className="rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted/60"
                                    >
                                        View replay →
                                    </Link>
                                )}
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function ActionButton({
    label,
    onClick,
    disabled,
}: {
    label: string;
    onClick: () => void;
    disabled: boolean;
}) {
    return (
        <button
            type="button"
            disabled={disabled}
            onClick={onClick}
            className="rounded-md border border-input bg-muted px-3 py-1.5 text-xs font-medium hover:bg-muted/80 disabled:opacity-50"
        >
            {label}
        </button>
    );
}
