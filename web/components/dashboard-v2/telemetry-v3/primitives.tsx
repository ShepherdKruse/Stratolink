'use client';

import type { ReactNode } from 'react';
import { STATUS_LABEL, type StatusLevel, worst } from '@/lib/telemetry/telemetryV3Format';

export const DOT: Record<StatusLevel, string> = {
    nominal: 'var(--t-nominal)',
    warn: 'var(--t-warn)',
    critical: 'var(--t-critical)',
};

export function Chevron({ open }: { open: boolean }) {
    return (
        <svg
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{
                transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.22s var(--ease)',
            }}
        >
            <polyline points="9 6 15 12 9 18" />
        </svg>
    );
}

export function StatusChip({ status, label }: { status: StatusLevel; label?: string }) {
    const c = DOT[status];
    return (
        <span
            className="eyebrow"
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                padding: '2px 7px 2px 6px',
                color: c,
                background: `var(--t-${status === 'nominal' ? 'nominal' : status}-soft)`,
                border: `1px solid ${c}`,
                borderRadius: 2,
                fontSize: 9,
                whiteSpace: 'nowrap',
            }}
        >
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: c }} />
            {label || STATUS_LABEL[status]}
        </span>
    );
}

export function StatTile({ label, value, unit }: { label: string; value: string; unit?: string }) {
    return (
        <div style={{ flex: 1, minWidth: 0 }}>
            <div className="eyebrow" style={{ color: 'var(--t-text-3)', marginBottom: 5, whiteSpace: 'nowrap' }}>
                {label}
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                <span
                    className="disp mono"
                    style={{
                        fontSize: 21,
                        fontWeight: 600,
                        color: 'var(--t-text)',
                        letterSpacing: '-0.01em',
                        lineHeight: 1,
                    }}
                >
                    {value}
                </span>
                {unit && (
                    <span className="mono" style={{ fontSize: 11, color: 'var(--t-text-3)' }}>
                        {unit}
                    </span>
                )}
            </div>
        </div>
    );
}

export function Divider() {
    return <div style={{ borderTop: '1px solid var(--t-hairline)' }} />;
}

export function Group({
    index,
    title,
    statuses,
    summary,
    children,
    open,
    onToggle,
    gkey,
}: {
    index: string;
    title: string;
    statuses: StatusLevel[];
    summary?: string;
    children: ReactNode;
    open: boolean;
    onToggle: () => void;
    gkey?: string;
}) {
    const w = worst(statuses);
    return (
        <section
            id={gkey ? `grp-${gkey}` : undefined}
            style={{ borderBottom: '1px solid var(--t-border)', scrollMarginTop: 8 }}
        >
            <button
                type="button"
                onClick={onToggle}
                style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '13px 18px',
                    background: 'transparent',
                    border: 0,
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: 'var(--t-text-2)',
                }}
            >
                <Chevron open={open} />
                <span className="eyebrow" style={{ color: 'var(--t-text-4)', fontSize: 9 }}>
                    {index}
                </span>
                <span
                    className="disp"
                    style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--t-text)',
                        letterSpacing: '0.01em',
                        flex: 1,
                        minWidth: 0,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                >
                    {title}
                </span>
                {!open && summary && (
                    <span
                        className="mono"
                        style={{
                            fontSize: 10.5,
                            color: 'var(--t-text-3)',
                            marginRight: 8,
                            whiteSpace: 'nowrap',
                            flexShrink: 0,
                        }}
                    >
                        {summary}
                    </span>
                )}
                <span
                    title={STATUS_LABEL[w]}
                    style={{
                        width: 7,
                        height: 7,
                        borderRadius: '50%',
                        background: DOT[w],
                        boxShadow:
                            w !== 'nominal'
                                ? `0 0 0 3px ${w === 'critical' ? 'var(--t-critical-soft)' : 'var(--t-warn-soft)'}`
                                : 'none',
                    }}
                />
            </button>
            {open && <div style={{ padding: '0 18px 14px' }}>{children}</div>}
        </section>
    );
}

/** Stratolink apex mark (Logo 01) — theme-aware via currentColor. */
export function StratolinkMark({ size = 22 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
            <rect x="14" y="4" width="4" height="4" fill="currentColor" />
            <rect x="12" y="14" width="8" height="1.5" fill="currentColor" />
            <rect x="9" y="19" width="14" height="1.5" fill="currentColor" />
            <rect x="6" y="24" width="20" height="1.5" fill="currentColor" />
        </svg>
    );
}
