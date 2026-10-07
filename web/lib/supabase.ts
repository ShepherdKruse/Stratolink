import { createClient } from '@supabase/supabase-js';

export function createServiceRoleClient() {
    const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVER_KEY;
    if (!url || !key) throw new Error('Forecast database is not configured');
    return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}
