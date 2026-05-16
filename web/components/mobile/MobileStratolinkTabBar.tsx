'use client';

import type { ReactElement } from 'react';

export type MobileMainTab = 'fleet' | 'map' | 'telemetry' | 'alerts' | 'more';

function IconFleet({ color }: { color: string }) {
    return (
        <svg width={22} height={22} viewBox="0 0 22 22" fill="none" aria-hidden>
            <rect x="3" y="4" width="16" height="2" fill={color} />
            <rect x="3" y="10" width="16" height="2" fill={color} />
            <rect x="3" y="16" width="16" height="2" fill={color} />
        </svg>
    );
}

function IconMapSvg({ color }: { color: string }) {
    return (
        <svg width={22} height={22} viewBox="0 0 22 22" fill="none" aria-hidden>
            <path
                d="M 4 6 L 8 4 L 14 6 L 18 4 L 18 16 L 14 18 L 8 16 L 4 18 Z"
                stroke={color}
                strokeWidth="1.5"
                fill="none"
            />
            <line x1="8" y1="4" x2="8" y2="16" stroke={color} strokeWidth="1.5" />
            <line x1="14" y1="6" x2="14" y2="18" stroke={color} strokeWidth="1.5" />
        </svg>
    );
}

function IconChartSvg({ color }: { color: string }) {
    return (
        <svg width={22} height={22} viewBox="0 0 22 22" fill="none" aria-hidden>
            <rect x="3" y="13" width="3" height="6" fill={color} />
            <rect x="9" y="8" width="3" height="11" fill={color} />
            <rect x="15" y="3" width="3" height="16" fill={color} />
        </svg>
    );
}

function IconAlertSvg({ color }: { color: string }) {
    return (
        <svg width={22} height={22} viewBox="0 0 22 22" fill="none" aria-hidden>
            <path d="M 11 3 L 19 18 L 3 18 Z" stroke={color} strokeWidth="1.5" fill="none" />
            <rect x="10" y="9" width="2" height="5" fill={color} />
            <rect x="10" y="15" width="2" height="2" fill={color} />
        </svg>
    );
}

function IconMore({ color }: { color: string }) {
    return (
        <svg width={22} height={22} viewBox="0 0 22 22" fill="none" aria-hidden>
            <rect x="4" y="10" width="3" height="3" fill={color} />
            <rect x="10" y="10" width="3" height="3" fill={color} />
            <rect x="16" y="10" width="3" height="3" fill={color} />
        </svg>
    );
}

const tabs: {
    id: MobileMainTab;
    label: string;
    Icon: ({ color }: { color: string }) => ReactElement;
}[] = [
    { id: 'fleet', label: 'Fleet', Icon: IconFleet },
    { id: 'map', label: 'Map', Icon: IconMapSvg },
    { id: 'telemetry', label: 'Telemetry', Icon: IconChartSvg },
    { id: 'alerts', label: 'Alerts', Icon: IconAlertSvg },
    { id: 'more', label: 'More', Icon: IconMore },
];

interface MobileStratolinkTabBarProps {
    active: MobileMainTab;
    onTabChange: (tab: MobileMainTab) => void;
    alertsBadge?: number;
}

export default function MobileStratolinkTabBar({ active, onTabChange, alertsBadge }: MobileStratolinkTabBarProps) {
    const ok = 'var(--ok)';
    const dim = 'var(--text-dim2)';
    const alertClr = 'var(--alert)';
    const border = 'var(--border)';
    const sand = 'var(--sans)';
    const alertNum = alertsBadge ?? 0;

    return (
        <nav
            className="fixed bottom-0 left-0 right-0 z-[100] flex border-t backdrop-blur-[20px]"
            style={{
                paddingBottom: 'max(34px, env(safe-area-inset-bottom))',
                paddingTop: 8,
                borderColor: border,
                background: 'rgba(11, 14, 19, 0.94)',
            }}>
            {tabs.map((t) => {
                const isActive = t.id === active;
                const showBadge = t.id === 'alerts' && alertNum > 0;
                const color = isActive ? ok : dim;
                const Icon = t.Icon;
                return (
                    <button
                        key={t.id}
                        type="button"
                        onClick={() => onTabChange(t.id)}
                        className="flex flex-1 flex-col items-center gap-1 bg-transparent px-2 py-1"
                        style={{ fontFamily: sand }}>
                        <div className="relative">
                            <Icon color={color} />
                            {showBadge ? (
                                <span
                                    className="absolute -right-2 -top-1 flex min-h-[14px] min-w-[14px] items-center justify-center rounded-full px-[4px] text-[9px] font-semibold tabular-nums"
                                    style={{ background: alertClr, color: '#0b0e13' }}>
                                    {alertNum > 9 ? '9+' : alertNum}
                                </span>
                            ) : null}
                        </div>
                        <span
                            style={{
                                fontSize: 9,
                                letterSpacing: '0.08em',
                                textTransform: 'uppercase',
                                fontWeight: 500,
                                color,
                            }}>
                            {t.label}
                        </span>
                    </button>
                );
            })}
        </nav>
    );
}
