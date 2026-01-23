import { createClient as createSupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

export function createClient() {
    if (!supabaseUrl || !supabaseAnonKey) {
        // Return a mock client during build/development if env vars are missing
        // This prevents build-time errors
        console.warn('Missing Supabase environment variables. Using mock client.');
        return createSupabaseClient(
            'https://placeholder.supabase.co',
            'placeholder-key'
        );
    }
    return createSupabaseClient(supabaseUrl, supabaseAnonKey);
}
