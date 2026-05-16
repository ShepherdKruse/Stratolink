/* Shared JSX for OG + Twitter raster cards (must match ImageResponse flex layout). */

export function StratolinkShareCard() {
    return (
        <div
            style={{
                height: '100%',
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                letterSpacing: '0.06em',
                background: '#eaeaeb',
                color: '#0a0a0a',
            }}
        >
            <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-end', gap: 48 }}>
                <div
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 18,
                        paddingBottom: 8,
                    }}
                >
                    <div style={{ width: 44, height: 44, background: '#0a0a0a', borderRadius: 3 }} />
                    <div style={{ width: 64, height: 14, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 84, height: 14, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 108, height: 14, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 132, height: 18, background: '#0a0a0a', borderRadius: 2 }} />
                </div>
                <div
                    style={{
                        fontSize: 108,
                        fontWeight: 800,
                        fontStyle: 'italic',
                        fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
                    }}
                >
                    STRATOLINK
                </div>
            </div>
        </div>
    );
}
