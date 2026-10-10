import { PostgrestClient } from '@supabase/postgrest-js';

let browserClient: PostgrestClient | null = null;

/** Keep the query builder, but route all reads through the public privacy filter.
 *  Only the PostgREST builder is needed here; the auth client lives in lib/community/auth and loads on demand. */
export function createClient() {
    if (browserClient) return browserClient;
    browserClient = new PostgrestClient(`${window.location.origin}/rest/v1`, {
        fetch: (input, init) => {
            const source = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
            const resource = source.pathname.split('/').at(-1);
            const query = new URLSearchParams(source.search);
            query.set('resource', resource ?? '');
            return fetch(`/api/telemetry?${query}`, { signal: init?.signal });
        },
    });
    return browserClient;
}
