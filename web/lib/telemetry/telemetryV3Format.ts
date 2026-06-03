export type StatusLevel = 'nominal' | 'warn' | 'critical';

export const STATUS_LABEL: Record<StatusLevel, string> = {
    nominal: 'Nominal',
    warn: 'Warning',
    critical: 'Critical',
};

type StatusSpec = { warn: number; crit: number; dir: 'high' | 'low' | 'band' };

export function evalStatus(v: number | null, spec: StatusSpec): StatusLevel {
    if (v == null) return 'critical';
    const { warn, crit, dir } = spec;
    if (dir === 'high') {
        if (v <= crit) return 'critical';
        if (v <= warn) return 'warn';
        return 'nominal';
    }
    if (dir === 'low') {
        if (v >= crit) return 'critical';
        if (v >= warn) return 'warn';
        return 'nominal';
    }
    return 'nominal';
}

export const tlmFmt = {
    int: (v: number | null) => (v == null ? '—' : Math.round(v).toLocaleString('en-US')),
    d1: (v: number | null) => (v == null ? '—' : v.toFixed(1)),
    d2: (v: number | null) => (v == null ? '—' : v.toFixed(2)),
};

export function relTime(ms: number): string {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ${s % 60}s`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ${m % 60}m`;
    const d = Math.floor(h / 24);
    return `${d}d ${h % 24}h`;
}

export function stamp(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getUTCMonth() + 1}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

export function worst(statuses: StatusLevel[]): StatusLevel {
    const rank: Record<StatusLevel, number> = { nominal: 0, warn: 1, critical: 2 };
    return statuses.reduce((a, s) => (rank[s] > rank[a] ? s : a), 'nominal');
}
