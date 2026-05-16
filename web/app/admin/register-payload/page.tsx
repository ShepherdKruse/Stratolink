'use client';

import { useEffect, useState, useTransition } from 'react';
import Link from 'next/link';
import { ArrowRight, Check, Copy, ExternalLink, KeyRound, Loader2, Mail, ShieldCheck, X } from 'lucide-react';
import { registerPayloadAction } from '@/lib/actions/register-payload';
import { listClaims, type ClaimedRow } from '@/lib/actions/claim';

type SuccessOutput = {
    deviceId: string;
    claimCode: string;
    activateUrlWithToken: string;
    launchTokenExpiresAt: string;
    ttnDeviceUrl: string;
    firmwareSnippet: string;
};

export default function RegisterPayloadAdminPage() {
    const [adminKey, setAdminKey] = useState('');
    const [deviceId, setDeviceId] = useState('');
    const [joinEui, setJoinEui] = useState('');
    const [devEui, setDevEui] = useState('');
    const [out, setOut] = useState<SuccessOutput | null>(null);
    const [err, setErr] = useState<string | null>(null);
    const [pending, startTransition] = useTransition();
    const [claims, setClaims] = useState<ClaimedRow[]>([]);
    const [copied, setCopied] = useState<string | null>(null);

    const refreshClaims = () => {
        listClaims().then((r) => {
            if (r.ok) setClaims(r.rows);
        });
    };

    useEffect(refreshClaims, []);

    function copy(label: string, text: string) {
        navigator.clipboard.writeText(text).then(() => {
            setCopied(label);
            setTimeout(() => setCopied((c) => (c === label ? null : c)), 1500);
        });
    }

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
            setOut({
                deviceId: r.deviceId,
                claimCode: r.claimCode,
                activateUrlWithToken: r.activateUrlWithToken,
                launchTokenExpiresAt: r.launchTokenExpiresAt,
                ttnDeviceUrl: r.ttnDeviceUrl,
                firmwareSnippet: r.firmwareSnippet,
            });
            refreshClaims();
        });
    }

    const pendingClaims = claims.filter((c) => !c.has_keys && c.status === 'storage');
    const formReady = adminKey.trim().length > 0;
    const launchExpiresPretty = out
        ? new Date(out.launchTokenExpiresAt).toLocaleString(undefined, {
              dateStyle: 'medium',
              timeStyle: 'short',
          })
        : '';

    return (
        <div className="min-h-screen bg-slate-50">
            <div className="mx-auto max-w-3xl px-4 py-10">
                <header>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                        Stratolink admin
                    </p>
                    <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">
                        Register payload
                    </h1>
                    <p className="mt-3 text-sm leading-relaxed text-slate-600">
                        Creates the OTAA device in TTN and updates the matching{' '}
                        <code className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-xs text-slate-800">
                            devices
                        </code>{' '}
                        row with a one-time launch link. Output includes a{' '}
                        <code className="font-mono text-xs">secrets.h</code> block ready to send to whoever is
                        flashing the firmware.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                        <Link href="/admin/launch-kit" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                            Re-issue QR labels via Launch kit
                        </Link>
                        <Link href="/claim" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                            Claim form (/claim)
                        </Link>
                    </div>
                </header>

                {/* How-this-works callout */}
                <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h2 className="text-sm font-semibold text-slate-900">How this works</h2>
                    <ol className="mt-3 grid gap-2 text-sm text-slate-700 sm:grid-cols-4">
                        <Step n={1} label="Pick a pending claim" sub="(or type a fresh device id)" />
                        <Step n={2} label="Paste admin key" />
                        <Step n={3} label="Click Register" sub="generates DevEUI + AppKey" />
                        <Step n={4} label="Copy + send" sub="three #define lines to Teddy" />
                    </ol>
                </section>

                {/* Awaiting keys */}
                {pendingClaims.length > 0 && (
                    <section className="mt-6 rounded-xl border border-amber-300 bg-amber-50 p-5 shadow-sm">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-amber-900">
                                Awaiting keys · {pendingClaims.length}
                            </h2>
                            <span className="text-[11px] font-medium uppercase tracking-wider text-amber-800/70">
                                claimed but not yet provisioned
                            </span>
                        </div>
                        <p className="mt-1 text-xs text-amber-900/80">
                            Click <span className="font-semibold">Use this</span> to load the call-sign into the form below.
                        </p>
                        <ul className="mt-4 grid gap-2">
                            {pendingClaims.map((c) => {
                                const selected = c.device_id === deviceId.trim().toLowerCase();
                                return (
                                    <li
                                        key={c.device_id}
                                        className={`flex items-center justify-between gap-3 rounded-lg border bg-white px-4 py-3 shadow-sm transition-colors ${
                                            selected
                                                ? 'border-primary ring-2 ring-primary/20'
                                                : 'border-amber-200 hover:border-amber-400'
                                        }`}
                                    >
                                        <div className="min-w-0">
                                            <div className="truncate font-mono text-sm font-semibold text-slate-900">
                                                {c.device_id}
                                            </div>
                                            <div className="truncate text-xs text-slate-600">
                                                {c.launcher_name || 'No commander name'}
                                            </div>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => setDeviceId(c.device_id)}
                                            className={`shrink-0 rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                                                selected
                                                    ? 'bg-primary text-primary-foreground'
                                                    : 'bg-slate-900 text-white hover:bg-slate-700'
                                            }`}
                                        >
                                            {selected ? (
                                                <span className="inline-flex items-center gap-1">
                                                    <Check className="h-3.5 w-3.5" />
                                                    Loaded
                                                </span>
                                            ) : (
                                                'Use this'
                                            )}
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </section>
                )}

                {/* Form */}
                <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h2 className="text-sm font-semibold text-slate-900">Registration details</h2>
                    <div className="mt-4 space-y-4">
                        <Field
                            label="Admin key"
                            hint="From your Vercel env (ADMIN_ACTIVATION_KEY). Required."
                            required
                        >
                            <input
                                type="password"
                                autoComplete="off"
                                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm placeholder:text-slate-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                value={adminKey}
                                onChange={(e) => setAdminKey(e.target.value)}
                                placeholder="ADMIN_ACTIVATION_KEY"
                            />
                        </Field>

                        <Field
                            label="Device ID (callsign)"
                            hint="Lowercase letters, digits, hyphens. Match the value on /claim."
                        >
                            <input
                                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 font-mono text-sm shadow-sm placeholder:text-slate-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                value={deviceId}
                                onChange={(e) => setDeviceId(e.target.value)}
                                placeholder="e.g. moneybird"
                            />
                        </Field>

                        <Field
                            label="Join EUI / AppEUI"
                            hint="Optional. Defaults to TTN_JOIN_EUI from server env."
                        >
                            <input
                                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 font-mono text-xs shadow-sm placeholder:text-slate-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                value={joinEui}
                                onChange={(e) => setJoinEui(e.target.value)}
                                placeholder="16 hex — leave blank to use TTN_JOIN_EUI"
                            />
                        </Field>

                        <Field
                            label="DevEUI"
                            hint="Optional. Leave blank to auto-generate a random 8-byte EUI."
                        >
                            <input
                                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 font-mono text-xs shadow-sm placeholder:text-slate-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                value={devEui}
                                onChange={(e) => setDevEui(e.target.value)}
                                placeholder="16 hex; random if empty"
                            />
                        </Field>

                        <button
                            type="button"
                            disabled={pending || !formReady}
                            onClick={run}
                            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-md transition-all hover:bg-primary/90 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
                        >
                            {pending ? (
                                <>
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Registering on TTN + Supabase…
                                </>
                            ) : (
                                <>
                                    <KeyRound className="h-4 w-4" />
                                    Register on TTN + Supabase
                                    <ArrowRight className="h-4 w-4" />
                                </>
                            )}
                        </button>
                        {!formReady && !pending && (
                            <p className="text-xs text-slate-500">
                                Paste your admin key to enable registration.
                            </p>
                        )}
                    </div>
                </section>

                {/* Error */}
                {err && (
                    <section className="mt-6 rounded-xl border border-destructive/40 bg-destructive/5 p-5">
                        <div className="flex items-start gap-3">
                            <X className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                            <div className="min-w-0 flex-1">
                                <h2 className="text-sm font-semibold text-destructive">Registration failed</h2>
                                <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-xs text-destructive/90">
                                    {err}
                                </pre>
                            </div>
                        </div>
                    </section>
                )}

                {/* Success output */}
                {out && (
                    <section className="mt-6 space-y-4">
                        <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-5 shadow-sm">
                            <div className="flex items-start gap-3">
                                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
                                <div className="min-w-0 flex-1">
                                    <h2 className="text-sm font-semibold text-emerald-900">
                                        {out.deviceId} registered
                                    </h2>
                                    <p className="mt-1 text-xs text-emerald-900/80">
                                        OTAA device created in TTN, claim row updated, launch link minted.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <CopyCard
                            title="Send these three lines to Teddy"
                            subtitle="Paste into firmware/include/secrets.h, replacing the placeholders. Use a secure channel (Signal / 1Password) — these are root keys."
                            text={out.firmwareSnippet}
                            tone="primary"
                            copiedKey={copied === 'snippet'}
                            onCopy={() => copy('snippet', out.firmwareSnippet)}
                            icon={<Mail className="h-4 w-4" />}
                        />

                        <CopyCard
                            title="Launch link (print as QR)"
                            subtitle={`One-time activation URL — expires ${launchExpiresPretty}.`}
                            text={out.activateUrlWithToken}
                            tone="muted"
                            copiedKey={copied === 'url'}
                            onCopy={() => copy('url', out.activateUrlWithToken)}
                        />

                        <div className="grid gap-4 sm:grid-cols-2">
                            <CopyCard
                                title="Backup PIN"
                                subtitle="Manual fallback at /activate"
                                text={out.claimCode}
                                tone="muted"
                                copiedKey={copied === 'pin'}
                                onCopy={() => copy('pin', out.claimCode)}
                                compact
                            />
                            <a
                                href={out.ttnDeviceUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="group flex flex-col justify-center rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
                            >
                                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                    TTN console
                                </span>
                                <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-slate-900">
                                    Open device page
                                    <ExternalLink className="h-3.5 w-3.5 text-slate-500 transition-transform group-hover:translate-x-0.5" />
                                </span>
                            </a>
                        </div>
                    </section>
                )}

                <p className="mt-10 text-xs text-slate-400">
                    API:{' '}
                    <code className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[11px] text-slate-700">
                        POST /api/admin/register-payload
                    </code>{' '}
                    with{' '}
                    <code className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[11px] text-slate-700">
                        Authorization: Bearer …
                    </code>
                </p>
            </div>
        </div>
    );
}

function Step({ n, label, sub }: { n: number; label: string; sub?: string }) {
    return (
        <li className="flex flex-col gap-1 rounded-lg border border-slate-200 bg-slate-50/50 p-3">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
                {n}
            </span>
            <span className="text-sm font-medium text-slate-900">{label}</span>
            {sub && <span className="text-xs text-slate-500">{sub}</span>}
        </li>
    );
}

function Field({
    label,
    hint,
    required,
    children,
}: {
    label: string;
    hint?: string;
    required?: boolean;
    children: React.ReactNode;
}) {
    return (
        <div>
            <label className="block text-sm font-medium text-slate-900">
                {label}
                {required && <span className="ml-1 text-destructive">*</span>}
            </label>
            {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
            <div className="mt-1.5">{children}</div>
        </div>
    );
}

function CopyCard({
    title,
    subtitle,
    text,
    tone,
    copiedKey,
    onCopy,
    compact,
    icon,
}: {
    title: string;
    subtitle?: string;
    text: string;
    tone: 'primary' | 'muted';
    copiedKey: boolean;
    onCopy: () => void;
    compact?: boolean;
    icon?: React.ReactNode;
}) {
    const accent = tone === 'primary' ? 'border-primary/30 bg-primary/5' : 'border-slate-200 bg-white';
    return (
        <div className={`rounded-xl border ${accent} p-4 shadow-sm`}>
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <h3 className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                        {icon}
                        {title}
                    </h3>
                    {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{subtitle}</p>}
                </div>
                <button
                    type="button"
                    onClick={onCopy}
                    className={`inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                        copiedKey
                            ? 'bg-emerald-600 text-white'
                            : 'bg-slate-900 text-white hover:bg-slate-700'
                    }`}
                >
                    {copiedKey ? (
                        <>
                            <Check className="h-3.5 w-3.5" />
                            Copied
                        </>
                    ) : (
                        <>
                            <Copy className="h-3.5 w-3.5" />
                            Copy
                        </>
                    )}
                </button>
            </div>
            <pre
                className={`mt-3 ${
                    compact ? 'text-base font-semibold' : 'text-xs'
                } overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-slate-200 bg-white px-3 py-2.5 font-mono text-slate-900`}
            >
                {text}
            </pre>
        </div>
    );
}
