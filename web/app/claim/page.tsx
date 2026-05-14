'use client';

import { useEffect, useState, useTransition } from 'react';
import { claimCallsign, listClaims, type ClaimedRow } from '@/lib/actions/claim';

export default function ClaimPage() {
    const [name, setName] = useState('');
    const [callsign, setCallsign] = useState('');
    const [eventCode, setEventCode] = useState('');
    const [result, setResult] = useState<{ deviceId: string; launcherName: string } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [claims, setClaims] = useState<ClaimedRow[]>([]);
    const [pending, startTransition] = useTransition();

    const refresh = () => {
        listClaims().then((r) => {
            if (r.ok) setClaims(r.rows);
        });
    };

    useEffect(refresh, []);

    function submit() {
        setError(null);
        setResult(null);
        startTransition(async () => {
            const r = await claimCallsign(callsign, name, eventCode || undefined);
            if (!r.ok) {
                setError(r.error);
                return;
            }
            setResult({ deviceId: r.deviceId, launcherName: r.launcherName });
            setCallsign('');
            refresh();
        });
    }

    return (
        <div className="min-h-screen bg-[#1a1a1a] text-[#e5e5e5]">
            <div className="mx-auto max-w-2xl px-4 py-12">
                <h1 className="text-2xl font-semibold tracking-tight">Name your balloon</h1>
                <p className="mt-2 text-sm text-[#999]">
                    Pick a callsign and your name. The launch organizer will use this list to mint flight keys and your launch QR.
                </p>

                <div className="mt-8 space-y-4 rounded-md border border-[#333] bg-[#141414] p-4">
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-[#666]">
                        Your name
                        <input
                            type="text"
                            className="mt-1 w-full rounded border border-[#333] bg-[#1a1a1a] px-3 py-2 text-[14px] text-[#e5e5e5] focus:border-[#4a90d9] focus:outline-none"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Shepherd"
                            maxLength={80}
                        />
                    </label>

                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-[#666]">
                        Callsign
                        <input
                            type="text"
                            className="mt-1 w-full rounded border border-[#333] bg-[#1a1a1a] px-3 py-2 font-mono text-[14px] tracking-wide text-[#e5e5e5] focus:border-[#4a90d9] focus:outline-none"
                            value={callsign}
                            onChange={(e) => setCallsign(e.target.value.toLowerCase().replace(/\s+/g, '-'))}
                            placeholder="stratolink-orion"
                            maxLength={36}
                        />
                        <span className="mt-1 block text-[10px] text-[#666]">
                            Lowercase letters, digits, hyphens. 3–36 chars (TTN device-id rules).
                        </span>
                    </label>

                    {process.env.NEXT_PUBLIC_CLAIM_GATED === 'true' && (
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-[#666]">
                            Event code
                            <input
                                type="password"
                                autoComplete="off"
                                className="mt-1 w-full rounded border border-[#333] bg-[#1a1a1a] px-3 py-2 text-[14px] text-[#e5e5e5] focus:border-[#4a90d9] focus:outline-none"
                                value={eventCode}
                                onChange={(e) => setEventCode(e.target.value)}
                                placeholder="Shared event code"
                            />
                        </label>
                    )}

                    <button
                        type="button"
                        onClick={submit}
                        disabled={pending || !name.trim() || !callsign.trim()}
                        className="w-full rounded bg-[#4a90d9] py-3 text-[12px] font-mono font-semibold uppercase tracking-wider text-[#e5e5e5] disabled:cursor-not-allowed disabled:bg-[#333] disabled:text-[#666]"
                    >
                        {pending ? 'Claiming…' : 'Claim callsign'}
                    </button>

                    {error && (
                        <pre className="whitespace-pre-wrap rounded border border-[#c44]/60 bg-[#c44]/10 px-3 py-2 text-[12px] text-[#fbb]">
                            {error}
                        </pre>
                    )}

                    {result && (
                        <div className="rounded border border-emerald-700/60 bg-emerald-950/40 px-3 py-2 text-[12px] text-emerald-200">
                            <div className="font-semibold">Callsign reserved</div>
                            <div className="font-mono">{result.deviceId}</div>
                            <div className="text-emerald-300/80">Commander: {result.launcherName}</div>
                            <div className="mt-2 text-emerald-300/80">
                                The launch organizer will register this on TTN and send you the QR / launch link.
                            </div>
                        </div>
                    )}
                </div>

                {claims.length > 0 && (
                    <div className="mt-8">
                        <h2 className="text-sm font-semibold">Claimed so far</h2>
                        <ul className="mt-3 divide-y divide-[#333] rounded-md border border-[#333] bg-[#141414]">
                            {claims.map((c) => (
                                <li key={c.device_id} className="flex items-center justify-between px-4 py-3 text-sm">
                                    <div>
                                        <div className="font-mono text-[#e5e5e5]">{c.device_id}</div>
                                        <div className="text-[11px] text-[#666]">
                                            {c.launcher_name || 'Unclaimed'} · {c.status}
                                        </div>
                                    </div>
                                    <span
                                        className={
                                            c.has_keys
                                                ? 'rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] uppercase tracking-wider text-emerald-300'
                                                : 'rounded-full bg-yellow-500/20 px-2 py-0.5 text-[10px] uppercase tracking-wider text-yellow-300'
                                        }
                                    >
                                        {c.has_keys ? 'Keys minted' : 'Awaiting keys'}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </div>
    );
}
