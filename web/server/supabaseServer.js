import { createClient } from '@supabase/supabase-js';

export function serverSupabaseConfig() {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVER_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error('Server database credentials are required');
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' && !(['localhost', '127.0.0.1'].includes(parsed.hostname) && parsed.protocol === 'http:')) {
    throw new Error('Invalid database URL');
  }
  if (!key.startsWith('sb_secret_')) {
    let role;
    try { role = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role; } catch { /* Rejected below. */ }
    if (role !== 'service_role') throw new Error('A server-only database key is required');
  }
  return { url: parsed.origin, key };
}

export function createServerSupabase() {
  const { url, key } = serverSupabaseConfig();
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } });
}
