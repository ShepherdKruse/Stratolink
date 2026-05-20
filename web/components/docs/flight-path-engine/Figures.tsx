export function EllipseFigure() {
    return (
        <figure className="fpe-figure">
            <div className="fig-frame">
                <svg viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Ellipse vs circle uncertainty">
                    <defs>
                        <marker id="fpe-arr" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">
                            <path d="M0,0 L7,3 L0,6 Z" fill="#97a0ac" />
                        </marker>
                    </defs>
                    <line x1="60" y1="160" x2="580" y2="70" stroke="#97a0ac" strokeWidth="1.4" strokeDasharray="5 4" markerEnd="url(#fpe-arr)" />
                    <text x="60" y="185" fontFamily="IBM Plex Mono, monospace" fontSize="11" fill="#97a0ac">
                        direction of travel
                    </text>
                    <circle cx="220" cy="135" r="46" fill="rgba(192,83,31,.08)" stroke="#c0531f" strokeWidth="1.3" strokeDasharray="4 4" />
                    <text x="220" y="139" fontFamily="IBM Plex Sans, sans-serif" fontSize="11" fill="#c0531f" textAnchor="middle">
                        circle
                    </text>
                    <text x="220" y="205" fontFamily="IBM Plex Mono, monospace" fontSize="10.5" fill="#97a0ac" textAnchor="middle">
                        overstates one axis
                    </text>
                    <g transform="translate(450,93) rotate(-9.8)">
                        <ellipse cx="0" cy="0" rx="74" ry="30" fill="rgba(15,118,110,.10)" stroke="#0f766e" strokeWidth="1.5" />
                        <line x1="-74" y1="0" x2="74" y2="0" stroke="#0f766e" strokeWidth=".8" strokeDasharray="3 3" opacity=".6" />
                        <line x1="0" y1="-30" x2="0" y2="30" stroke="#0f766e" strokeWidth=".8" strokeDasharray="3 3" opacity=".6" />
                    </g>
                    <text x="450" y="48" fontFamily="IBM Plex Sans, sans-serif" fontSize="11" fill="#0f766e" textAnchor="middle">
                        ellipse along track
                    </text>
                    <text x="528" y="96" fontFamily="IBM Plex Mono, monospace" fontSize="9.5" fill="#6b7480">
                        speed error
                    </text>
                    <text x="428" y="140" fontFamily="IBM Plex Mono, monospace" fontSize="9.5" fill="#6b7480">
                        direction error
                    </text>
                </svg>
            </div>
            <figcaption>
                Speed error stretches the region along the track; direction error stretches it across. The honest shape is an ellipse oriented to the direction of travel, not a circle.
            </figcaption>
        </figure>
    );
}

export function BridgeFigure() {
    return (
        <figure className="fpe-figure">
            <div className="fig-frame">
                <svg viewBox="0 0 640 230" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Forecast cone vs reconstruction bridge">
                    <text x="160" y="28" fontFamily="IBM Plex Sans, sans-serif" fontSize="12" fill="#9a6a16" textAnchor="middle">
                        Forecast: a cone
                    </text>
                    <circle cx="60" cy="95" r="5" fill="#c0531f" />
                    <text x="60" y="120" fontFamily="IBM Plex Mono, monospace" fontSize="9.5" fill="#97a0ac" textAnchor="middle">
                        last fix
                    </text>
                    <path d="M60,95 L280,55 L280,135 Z" fill="rgba(154,106,22,.10)" stroke="none" />
                    <path d="M60,95 L280,55" stroke="#9a6a16" strokeWidth="1" strokeDasharray="4 3" opacity=".5" />
                    <path d="M60,95 L280,135" stroke="#9a6a16" strokeWidth="1" strokeDasharray="4 3" opacity=".5" />
                    <path d="M60,95 L280,95" stroke="#9a6a16" strokeWidth="1.6" />
                    <text x="480" y="28" fontFamily="IBM Plex Sans, sans-serif" fontSize="12" fill="#0f766e" textAnchor="middle">
                        Reconstruction: a bridge
                    </text>
                    <circle cx="360" cy="150" r="5" fill="#2456c4" />
                    <circle cx="600" cy="80" r="5" fill="#2456c4" />
                    <text x="360" y="172" fontFamily="IBM Plex Mono, monospace" fontSize="9.5" fill="#97a0ac" textAnchor="middle">
                        fix A
                    </text>
                    <text x="600" y="102" fontFamily="IBM Plex Mono, monospace" fontSize="9.5" fill="#97a0ac" textAnchor="middle">
                        fix B
                    </text>
                    <path d="M360,150 Q470,40 600,80 Q470,180 360,150 Z" fill="rgba(15,118,110,.10)" stroke="none" />
                    <path d="M360,150 Q480,95 600,80" stroke="#0f766e" strokeWidth="1.6" fill="none" />
                </svg>
            </div>
            <figcaption>
                A forecast spreads outward from one known point. A reconstruction is pinned at both, so its uncertainty closes to zero at each fix and is widest halfway between.
            </figcaption>
        </figure>
    );
}

export function DirectnessFigure() {
    return (
        <figure className="fpe-figure">
            <div className="fig-frame">
                <svg viewBox="0 0 640 210" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="High vs low directness paths">
                    <circle cx="70" cy="120" r="5" fill="#2456c4" />
                    <circle cx="270" cy="70" r="5" fill="#2456c4" />
                    <path d="M70,120 Q170,88 270,70" stroke="#0f766e" strokeWidth="2" fill="none" />
                    <text x="170" y="160" fontFamily="IBM Plex Sans, sans-serif" fontSize="11.5" fill="#0f766e" textAnchor="middle">
                        high directness
                    </text>
                    <text x="170" y="178" fontFamily="IBM Plex Mono, monospace" fontSize="10" fill="#97a0ac" textAnchor="middle">
                        fast, straight, tight line
                    </text>
                    <circle cx="390" cy="120" r="5" fill="#2456c4" />
                    <circle cx="600" cy="95" r="5" fill="#2456c4" />
                    <path
                        d="M390,120 C430,40 520,40 520,95 C520,150 440,150 470,100 C495,60 560,70 600,95"
                        stroke="#c0531f"
                        strokeWidth="2"
                        fill="none"
                    />
                    <text x="495" y="178" fontFamily="IBM Plex Sans, sans-serif" fontSize="11.5" fill="#c0531f" textAnchor="middle">
                        low directness
                    </text>
                    <text x="495" y="196" fontFamily="IBM Plex Mono, monospace" fontSize="10" fill="#97a0ac" textAnchor="middle">
                        slow net travel, path may loop
                    </text>
                </svg>
            </div>
            <figcaption>
                The same pair of fixes. If the balloon covered the ground quickly, the leg stays a straight line. If its net speed was far below the wind, the engine lets the path wander and loop.
            </figcaption>
        </figure>
    );
}
