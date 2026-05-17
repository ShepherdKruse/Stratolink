'use client';

import type { ReactNode } from 'react';

type NumericRow = { t: number };

interface StackedLineChartProps<T extends NumericRow> {
    title: string;
    valueDisplay: ReactNode;
    unitSuffix?: ReactNode;
    data: T[];
    getY: (row: T) => number | null;
    color?: string;
    min?: number;
    max?: number;
}

export function StackedLineChart<T extends NumericRow>({
    title,
    valueDisplay,
    unitSuffix,
    data,
    getY,
    color = 'var(--ok-mute)',
    min: minFixed,
    max: maxFixed,
}: StackedLineChartProps<T>) {
    const W = 360;
    const H = 60;
    const padT = 4;
    const padB = 4;

    const valid = data.map(getY).filter((v): v is number => v !== null && !Number.isNaN(v));
    if (!valid.length) return null;

    const lo = minFixed !== undefined ? minFixed : Math.min(...valid);
    const hi = maxFixed !== undefined ? maxFixed : Math.max(...valid);
    const r = hi - lo || 1;
    const t0 = data[0].t;
    const t1 = data[data.length - 1].t;
    const span = t1 - t0 || 1;

    const xOf = (t: number) => ((t - t0) / span) * W;
    const yOf = (v: number) => padT + (H - padT - padB) - ((v - lo) / r) * (H - padT - padB);

    let d = '';
    let started = false;
    data.forEach((row) => {
        const v = getY(row);
        if (v === null || Number.isNaN(v)) {
            started = false;
            return;
        }
        d += (started ? 'L' : 'M') + xOf(row.t).toFixed(1) + ' ' + yOf(v).toFixed(1) + ' ';
        started = true;
    });

    return (
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontFamily: 'var(--sans)' }}>
            <div className="mb-2 flex items-baseline justify-between">
                <div
                    style={{
                        fontFamily: 'var(--sans)',
                        fontSize: 10,
                        letterSpacing: '0.14em',
                        textTransform: 'uppercase',
                        color: 'var(--text-dim)',
                        fontWeight: 500,
                    }}>
                    {title}
                </div>
                <div
                    style={{
                        fontFamily: 'var(--mono)',
                        fontSize: 16,
                        color: 'var(--text-hi)',
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 500,
                    }}>
                    {valueDisplay}
                    {unitSuffix ? (
                        <span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 3 }}>{unitSuffix}</span>
                    ) : null}
                </div>
            </div>
            <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
                <path d={d} stroke={color} strokeWidth="1.4" fill="none" vectorEffect="nonScalingStroke" />
            </svg>
            <div
                className="mt-1 flex justify-between"
                style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-dim3)', marginTop: 4 }}>
                <span>
                    {lo.toFixed(lo < 10 && Math.abs(lo) < 100 ? 1 : Math.abs(lo) < 1 ? 2 : 0)}
                </span>
                <span>
                    {hi.toFixed(hi < 10 && Math.abs(hi) < 100 ? 1 : Math.abs(hi) < 1 ? 2 : 0)}
                </span>
            </div>
        </div>
    );
}

interface SlHeaderProps {
    sub?: string;
    title: string;
    right?: ReactNode;
    back?: boolean;
    onBack?: () => void;
    dense?: boolean;
}

export function SlHeader({ sub, title, right, back, onBack, dense }: SlHeaderProps) {
    return (
        <header
            className="flex shrink-0 items-center gap-[14px] bg-[var(--bg)] pb-[18px] pl-5 pr-5 pt-[56px]"
            style={{ borderBottom: '1px solid var(--border)' }}>
            {back ? (
                <button
                    type="button"
                    aria-label="Back"
                    onClick={onBack}
                    className="-ml-2 flex h-8 w-8 shrink-0 items-center justify-center bg-transparent">
                    <svg width={20} height={20} viewBox="0 0 20 20" fill="none" aria-hidden>
                        <path d="M 13 4 L 6 10 L 13 16" stroke="var(--text)" strokeWidth="1.5" />
                    </svg>
                </button>
            ) : null}
            <div className="min-w-0 flex-1">
                {sub ? (
                    <div
                        style={{
                            fontFamily: 'var(--sans)',
                            fontSize: 10,
                            letterSpacing: '0.14em',
                            textTransform: 'uppercase',
                            color: 'var(--text-dim2)',
                            fontWeight: 500,
                            marginBottom: 2,
                        }}>
                        {sub}
                    </div>
                ) : null}
                <h1
                    className="truncate"
                    style={{
                        fontFamily: 'var(--sans)',
                        fontSize: dense ? 16 : 18,
                        color: 'var(--text-hi)',
                        fontWeight: 500,
                    }}>
                    {title}
                </h1>
            </div>
            {right ? <div className="flex shrink-0 flex-col items-end gap-[2px]">{right}</div> : null}
        </header>
    );
}

export function SectionLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
    return (
        <div
            className="flex items-baseline justify-between px-5 pb-2.5 pt-6"
            style={{ fontFamily: 'var(--sans)' }}>
            <div style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>
                {children}
            </div>
            {right}
        </div>
    );
}
