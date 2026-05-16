import { ImageResponse } from 'next/og';

/**
 * Apex mark at favicon density (Logo Exploration Logo 01), scale vb 32→64.
 * Light field #f1f3f6, ink #0b0e13 — matches `.ctx.light` in exploration.
 */
export const size = { width: 64, height: 64 };
export const contentType = 'image/png';

const ink = '#0b0e13';
const field = '#f1f3f6';

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
                    background: field,
                }}
            >
                <div
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 10,
                    }}
                >
                    <div style={{ width: 8, height: 8, background: ink }} />
                    <div style={{ width: 16, height: 3, background: ink }} />
                    <div style={{ width: 28, height: 3, background: ink }} />
                    <div style={{ width: 40, height: 3, background: ink }} />
                </div>
            </div>
        ),
        { ...size },
    );
}
