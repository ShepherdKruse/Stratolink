export function publicBuildDefines(environment, local = {}) {
  const read = name => environment[name] || local[name] || '';
  const production = read('VERCEL_ENV') === 'production';
  const url = read('VITE_SUPABASE_URL') || read('NEXT_PUBLIC_SUPABASE_URL');
  const key = read('VITE_SUPABASE_PUBLISHABLE_KEY') || read('NEXT_PUBLIC_SUPABASE_ANON_KEY');
  const mapbox = read('NEXT_PUBLIC_MAPBOX_TOKEN');

  if (production && (!url || !key || !mapbox)) {
    throw new Error('Production requires a public Supabase URL, public Supabase key and Mapbox token');
  }
  if (url) {
    let parsed;
    try { parsed = new URL(url); } catch { /* Rejected below. */ }
    const loopback = parsed && !production && ['localhost', '127.0.0.1'].includes(parsed.hostname) && parsed.protocol === 'http:';
    if (!parsed || (parsed.protocol !== 'https:' && !loopback) || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) {
      throw new Error('The public Supabase URL must be an HTTPS origin');
    }
  }
  if (key) {
    let anonymous = false;
    if (/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(key)) {
      try { anonymous = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString('utf8')).role === 'anon'; } catch { /* Rejected below. */ }
    }
    if (!anonymous && !/^sb_publishable_[A-Za-z0-9_-]{20,}$/.test(key)) {
      throw new Error('The browser Supabase key must be a publishable or anon key');
    }
  }
  if (mapbox && !/^pk\.[A-Za-z0-9._-]+$/.test(mapbox)) throw new Error('The browser Mapbox token must be public');

  return {
    'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(url),
    'import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY': JSON.stringify(key),
    'process.env.NEXT_PUBLIC_MAPBOX_TOKEN': JSON.stringify(mapbox),
  };
}
