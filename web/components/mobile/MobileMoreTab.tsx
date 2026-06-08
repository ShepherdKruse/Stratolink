'use client';

import Link from 'next/link';

import { SlHeader } from './mobileStratolinkUi';

interface MobileMoreTabProps {
    onLaunchMission: () => void;
}

export default function MobileMoreTab({ onLaunchMission }: MobileMoreTabProps) {
    const Row = ({
        label,
        right,
        onClick,
        href,
    }: {
        label: string;
        right?: string;
        href?: string;
        onClick?: () => void;
    }) =>
        href ? (
            <Link href={href} style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--text)', textDecoration: 'none' }}>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 14 }}>{label}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-dim)', display: 'flex', gap: 8, alignItems: 'center' }}>
                    {right}
                    <span style={{ opacity: 0.4 }}>›</span>
                </span>
            </Link>
        ) : (
            <button
                type="button"
                onClick={onClick}
                className="w-full cursor-pointer bg-transparent text-left"
                style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', fontFamily: 'var(--sans)', fontSize: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--text)' }}>
                <span>{label}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-dim)', display: 'flex', gap: 8, alignItems: 'center' }}>
                    {right}
                    <span style={{ opacity: 0.4 }}>›</span>
                </span>
            </button>
        );

    return (
        <div className="flex h-full flex-col overflow-hidden pb-[calc(92px+env(safe-area-inset-bottom))]" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
            <SlHeader sub="SETTINGS" title="More" />

            <div className="min-h-0 flex-1 overflow-y-auto">
                <div className="px-5 pb-2 pt-4 text-[10px]" style={{ color: 'var(--text-dim2)', letterSpacing: '0.16em', textTransform: 'uppercase', fontWeight: 500 }}>
                    Navigate
                </div>
                <Row label="Mission Control (desktop labs)" href="/dashboard" right="Labs" />
                <Row label="Documentation" href="/docs" right="Knowledge" />
                <Row label="Launch new mission" onClick={() => onLaunchMission()} right="/activate" />
            </div>
        </div>
    );
}
