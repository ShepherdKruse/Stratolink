'use client';

import type { ReactNode } from 'react';

import { SlHeader } from './mobileStratolinkUi';
import type { DerivedAlert } from './mobileStratolinkUtils';

interface MobileAlertsTabProps {
    activeAlerts: DerivedAlert[];
}

export default function MobileAlertsTab({ activeAlerts }: MobileAlertsTabProps) {
    return (
        <div className="flex h-full flex-col overflow-hidden pb-[calc(92px+env(safe-area-inset-bottom))]" style={{ background: 'var(--bg)' }}>
            <SlHeader title="Alerts" sub="LAST 24H" right={<span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: activeAlerts.length ? 'var(--alert)' : 'var(--text-dim2)', fontWeight: 500 }}>{activeAlerts.length} active</span>} />

            <div className="min-h-0 flex-1 overflow-y-auto" style={{ fontFamily: 'var(--sans)', color: 'var(--text)' }}>
                <MobileSectionHeading>ACTIVE</MobileSectionHeading>
                {activeAlerts.length === 0 ? (
                    <div className="px-5 py-10 text-[13px]" style={{ color: 'var(--text-dim2)' }}>
                        Nice—nothing tripped heuristic checks on your fleet.
                    </div>
                ) : (
                    activeAlerts.map((a) => <MobileAlertCard key={a.id} {...a} />)
                )}
                <MobileSectionHeading>RESOLVED · TODAY</MobileSectionHeading>
                <div className="border-b px-5 py-8 text-[13px]" style={{ borderColor: 'var(--border)', color: 'var(--text-dim2)' }}>
                    Server-side alerting and resolved history ships next—we only show live heuristics for now.
                </div>
            </div>
        </div>
    );
}

function MobileSectionHeading({ children }: { children: ReactNode }) {
    return (
        <div className="px-5 pb-2.5 pt-6" style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', fontWeight: 500, color: 'var(--text-dim2)' }}>
            {children}
        </div>
    );
}

function MobileAlertCard(a: DerivedAlert) {
    const color = a.severity === 'WARN' ? 'var(--alert)' : 'var(--ok)';
    return (
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', borderLeft: `2px solid ${a.severity === 'WARN' ? color : 'transparent'}` }}>
            <div className="mb-1 flex items-baseline justify-between gap-2">
                <div className="flex items-center gap-2">
                    <span style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 500, color }}>{a.severity}</span>
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-dim)' }}>
                        {a.device}
                    </span>
                </div>
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-dim3)' }}>
                    {a.time}
                </span>
            </div>
            <div className="mb-2 text-[14px] font-medium" style={{ color: 'var(--text-hi)' }}>
                {a.title}
            </div>
            <div className="text-[12px]" style={{ color: 'var(--text-dim)' }}>
                {a.message}
            </div>
        </div>
    );
}
