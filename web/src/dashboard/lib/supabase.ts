import { createClient as createSupabaseClient, type SupabaseClient } from '@supabase/supabase-js';

let browserClient: SupabaseClient | null = null;

/** Keep the query builder, but route all reads through the public privacy filter. */
export function createClient() {
    if (browserClient) return browserClient;
    browserClient = createSupabaseClient(window.location.origin, 'public-dashboard', {
        auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
        global: {
            fetch: (input, init) => {
                const source = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
                const resource = source.pathname.split('/').at(-1);
                const query = new URLSearchParams(source.search);
                query.set('resource', resource ?? '');
                return fetch(`/api/telemetry?${query}`, { signal: init?.signal });
            },
        },
    });
    return browserClient;
}
