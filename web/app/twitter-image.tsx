import { ImageResponse } from 'next/og';
import { StratolinkShareCard } from './_og/stratolinkShareCard';

export const runtime = 'edge';

export const alt = 'Stratolink';

export const size = {
    width: 1200,
    height: 630,
};

export const contentType = 'image/png';

export default function TwitterImage() {
    return new ImageResponse(<StratolinkShareCard />, { ...size });
}
