import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

/** Reports presence (not values) of the env vars the app needs.
 *  Returns booleans + lengths so we can diagnose missing/blank vs. configured
 *  without ever leaking secrets. */
export async function GET() {
    const present = (v: string | undefined) => {
        const s = (v ?? '').trim();
        return { configured: s.length > 0, length: s.length };
    };

    return NextResponse.json({
        NODE_ENV: process.env.NODE_ENV,
        VERCEL_ENV: process.env.VERCEL_ENV ?? null,
        VERCEL_URL: process.env.VERCEL_URL ?? null,
        NEXT_PUBLIC_DEV_MODE: process.env.NEXT_PUBLIC_DEV_MODE ?? null,
        env: {
            NEXT_PUBLIC_SUPABASE_URL: present(process.env.NEXT_PUBLIC_SUPABASE_URL),
            NEXT_PUBLIC_SUPABASE_ANON_KEY: present(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
            SUPABASE_SERVICE_ROLE_KEY: present(process.env.SUPABASE_SERVICE_ROLE_KEY),
            ADMIN_ACTIVATION_KEY: present(process.env.ADMIN_ACTIVATION_KEY),
            NEXT_PUBLIC_APP_URL: present(process.env.NEXT_PUBLIC_APP_URL),
            TTN_STACK_HOST: present(process.env.TTN_STACK_HOST),
            TTN_APPLICATION_ID: present(process.env.TTN_APPLICATION_ID),
            TTN_API_KEY: present(process.env.TTN_API_KEY),
            TTN_JOIN_EUI: present(process.env.TTN_JOIN_EUI),
        },
    });
}
