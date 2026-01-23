import { NextResponse } from 'next/server';

export async function GET() {
    return NextResponse.json({
        NODE_ENV: process.env.NODE_ENV,
        NEXT_PUBLIC_DEV_MODE: process.env.NEXT_PUBLIC_DEV_MODE,
        isDevelopment: process.env.NODE_ENV === 'development' || process.env.NEXT_PUBLIC_DEV_MODE === 'true',
    });
}
