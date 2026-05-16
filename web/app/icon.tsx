import { ImageResponse } from 'next/og';

/** Small raster favicon (64×64) — transmission mark only. Avoids stale / favicon.jpg. */
export const size = { width: 64, height: 64 };
export const contentType = 'image/png';

export default function Icon() {
    return new ImageResponse(
        (
            <div
                style={{
                    width: '100%',
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#eaeaeb',
                }}
            >
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7 }}>
                    <div style={{ width: 17, height: 17, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 24, height: 6, background: '#0a0a0a', borderRadius: 1 }} />
                    <div style={{ width: 32, height: 6, background: '#0a0a0a', borderRadius: 1 }} />
                    <div style={{ width: 40, height: 6, background: '#0a0a0a', borderRadius: 1 }} />
                    <div style={{ width: 50, height: 7, background: '#0a0a0a', borderRadius: 1 }} />
                </div>
            </div>
        ),
        { ...size },
    );
}
