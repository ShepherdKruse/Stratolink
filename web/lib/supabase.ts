import { createClient as createSupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

export function createClient() {
    if (!supabaseUrl || !supabaseAnonKey || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
        throw new Error('Supabase not configured. Please set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in .env.local');
    }
    
    // Validate URL format
    if (!supabaseUrl.startsWith('http://') && !supabaseUrl.startsWith('https://')) {
        throw new Error(`Invalid Supabase URL format: ${supabaseUrl}`);
    }
    
    return createSupabaseClient(supabaseUrl, supabaseAnonKey);
}

/**
 * Create a Supabase client with service role key for server-side operations
 * that require elevated permissions (e.g., webhook writes).
 * 
 * WARNING: Never use this in client-side code. Service role key bypasses RLS.
 */
export function createServiceRoleClient() {
    const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    
    if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
        throw new Error('Supabase URL not configured. Please set NEXT_PUBLIC_SUPABASE_URL in .env.local');
    }
    
    if (!serviceRoleKey) {
        throw new Error('SUPABASE_SERVICE_ROLE_KEY not configured. Required for webhook operations.');
    }
    
    // Validate URL format
    if (!supabaseUrl.startsWith('http://') && !supabaseUrl.startsWith('https://')) {
        throw new Error(`Invalid Supabase URL format: ${supabaseUrl}`);
    }
    
    return createSupabaseClient(supabaseUrl, serviceRoleKey, {
        auth: {
            autoRefreshToken: false,
            persistSession: false
        }
    });
}
