'use client';

/** Abstract map teaser matching prototype POSITION block (SVG, not Mapbox). */
export default function SlMapMini({ accent = 'var(--ok)' }: { accent?: string }) {
    const W = 400;
    const H = 200;
    return (
        <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" style={{ display: 'block', background: 'var(--bg-1)' }} aria-hidden>
            {Array.from({ length: 8 }, (_, i) => (
                <line key={`v${i}`} x1={(i / 8) * W} y1={0} x2={(i / 8) * W} y2={H} stroke="var(--grid)" strokeWidth={1} />
            ))}
            {Array.from({ length: 5 }, (_, i) => (
                <line key={`h${i}`} x1={0} y1={(i / 5) * H} x2={W} y2={(i / 5) * H} stroke="var(--grid)" strokeWidth={1} />
            ))}
            <path
                d={`M 0 ${H * 0.62} Q ${W * 0.25} ${H * 0.55}, ${W * 0.5} ${H * 0.58} T ${W + 10} ${H * 0.65}`}
                stroke="var(--border-hi)"
                fill="none"
            />
            <g transform={`translate(${W / 2}, ${H / 2})`}>
                <line x1={-14} y1={0} x2={-6} y2={0} stroke={accent} strokeWidth={1.2} />
                <line x1={6} y1={0} x2={14} y2={0} stroke={accent} strokeWidth={1.2} />
                <line x1={0} y1={-14} x2={0} y2={-6} stroke={accent} strokeWidth={1.2} />
                <line x1={0} y1={6} x2={0} y2={14} stroke={accent} strokeWidth={1.2} />
                <rect x={-3} y={-3} width={6} height={6} fill={accent} />
            </g>
        </svg>
    );
}
