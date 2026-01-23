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
