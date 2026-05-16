import { ImageResponse } from 'next/og';

/** iOS home screen / rich link thumbnails often prefer PNG apple icons. */
export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

export default function AppleIcon() {
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
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
                    <div style={{ width: 48, height: 48, background: '#0a0a0a', borderRadius: 4 }} />
                    <div style={{ width: 68, height: 14, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 90, height: 14, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 118, height: 14, background: '#0a0a0a', borderRadius: 2 }} />
                    <div style={{ width: 144, height: 18, background: '#0a0a0a', borderRadius: 2 }} />
                </div>
            </div>
        ),
        { ...size },
    );
}
