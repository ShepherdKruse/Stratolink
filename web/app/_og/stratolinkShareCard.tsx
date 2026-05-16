/* Shared OG / Twitter raster — Logo 01 · Apex + wordmark lockup.

   Apex geometry matches `Stratolink Logo Exploration.html`: viewBox 32×32,
   rect (14,4) w4 h4, then bars at y14 w8 h1.5 · y19 w14 h1.5 · y24 w20 h1.5.

   Wordmark: exploration horizontal lockup — Inter-weight sans, uppercase, 0.20em tracking. */

const ink = '#0b0e13';
const field = '#f1f3f6';

const S = 10; /* Scale vb grid to pixels */

export function StratolinkShareCard() {
    const dot = 4 * S;
    /* Bar height ≈ 1.5 vb */
    const barH = Math.max(12, Math.round(1.5 * S));
    /* vb gaps: dot bottom→first bar = 6; between stacked bars ≈ 3.5 each */
    const gapAfterDot = Math.round(6 * S);
    const gapBetweenBars = Math.round(3.5 * S);
    return (
        <div
            style={{
                height: '100%',
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: field,
                color: ink,
            }}
        >
            <div
                style={{
                    display: 'flex',
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 48,
                }}
            >
                <div
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                    }}
                >
                    <div style={{ width: dot, height: dot, background: ink }} />
                    <div style={{ height: gapAfterDot }} />
                    <div style={{ width: 8 * S, height: barH, background: ink }} />
                    <div style={{ height: gapBetweenBars }} />
                    <div style={{ width: 14 * S, height: barH, background: ink }} />
                    <div style={{ height: gapBetweenBars }} />
                    <div style={{ width: 20 * S, height: barH, background: ink }} />
                </div>
                <span
                    style={{
                        fontSize: 88,
                        fontWeight: 500,
                        letterSpacing: '0.20em',
                        fontFamily:
                            '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
                        color: ink,
                        textTransform: 'uppercase',
                    }}
                >
                    STRATOLINK
                </span>
            </div>
        </div>
    );
}
