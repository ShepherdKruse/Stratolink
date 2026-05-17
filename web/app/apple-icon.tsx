import { ImageResponse } from 'next/og';

/** Apex mark · Logo 01 scaled vb 32→180 (rounded). */
export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

const ink = '#0b0e13';
const field = '#f1f3f6';
const scale = 180 / 32;

export default function AppleIcon() {
    const dot = Math.round(4 * scale);
    const hBar = Math.max(4, Math.round(1.5 * scale));
    const gap = Math.round(4.5); /* tightened stack for circular crop */
    return new ImageResponse(
        (
            <div
                style={{
                    width: '100%',
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: field,
                }}
            >
                <div
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap,
                    }}
                >
                    <div style={{ width: dot, height: dot, background: ink }} />
                    <div style={{ width: Math.round(8 * scale), height: hBar, background: ink }} />
                    <div style={{ width: Math.round(14 * scale), height: hBar, background: ink }} />
                    <div style={{ width: Math.round(20 * scale), height: hBar, background: ink }} />
                </div>
            </div>
        ),
        { ...size },
    );
}
