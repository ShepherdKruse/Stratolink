import test from 'node:test';
import assert from 'node:assert/strict';
import { publicBuildDefines } from '../scripts/public-config.mjs';

const jwt = role => `eyJhbGciOiJIUzI1NiJ9.${Buffer.from(JSON.stringify({ role })).toString('base64url')}.synthetic-signature`;
const old = { NEXT_PUBLIC_SUPABASE_URL: 'https://shared.supabase.co', NEXT_PUBLIC_SUPABASE_ANON_KEY: jwt('anon'), NEXT_PUBLIC_MAPBOX_TOKEN: 'pk.synthetic-public-token' };
const key = 'sb_publishable_' + 'a'.repeat(32);
const decode = definitions => Object.fromEntries(Object.entries(definitions).map(([name, value]) => [name, JSON.parse(value)]));

test('existing public configuration builds auth without exposing server or arbitrary prefixed values', () => {
  const definitions = decode(publicBuildDefines({ ...old, VERCEL_ENV: 'production', SUPABASE_SERVICE_ROLE_KEY: 'private-service-key', SUPABASE_SERVER_KEY: 'private-server-key', VITE_PRIVATE_KEY: 'private-prefixed-key', NEXT_PUBLIC_OTHER: 'unrelated-value' }));
  assert.deepEqual(definitions, {
    'import.meta.env.VITE_SUPABASE_URL': old.NEXT_PUBLIC_SUPABASE_URL,
    'import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY': old.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    'process.env.NEXT_PUBLIC_MAPBOX_TOKEN': old.NEXT_PUBLIC_MAPBOX_TOKEN,
  });
  assert.doesNotMatch(JSON.stringify(definitions), /private|unrelated/);
});

test('modern public settings take precedence, with process values ahead of local files', () => {
  const definitions = decode(publicBuildDefines({ ...old, VITE_SUPABASE_URL: 'https://new.supabase.co', VITE_SUPABASE_PUBLISHABLE_KEY: key }, { VITE_SUPABASE_URL: 'https://local.supabase.co', VITE_SUPABASE_PUBLISHABLE_KEY: jwt('anon') }));
  assert.equal(definitions['import.meta.env.VITE_SUPABASE_URL'], 'https://new.supabase.co');
  assert.equal(definitions['import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY'], key);
  assert.deepEqual(publicBuildDefines({}, old), publicBuildDefines(old));
});

test('private or malformed keys fail before reaching browser definitions and are absent from errors', () => {
  for (const unsafe of [jwt('service_role'), jwt('authenticated'), 'sb_secret_' + 's'.repeat(32), 'not-a-key', 'e30.invalid.signature']) {
    for (const name of ['VITE_SUPABASE_PUBLISHABLE_KEY', 'NEXT_PUBLIC_SUPABASE_ANON_KEY']) {
      assert.throws(() => publicBuildDefines({ ...old, [name]: unsafe }), error => {
        assert.equal(error.message, 'The browser Supabase key must be a publishable or anon key');
        assert.ok(!error.message.includes(unsafe));
        return true;
      });
    }
  }
  assert.throws(() => publicBuildDefines({ ...old, NEXT_PUBLIC_MAPBOX_TOKEN: 'sk.private-token' }), /must be public/);
});

test('production refuses missing settings and never substitutes private or request-derived values', () => {
  for (const name of Object.keys(old)) assert.throws(() => publicBuildDefines({ ...old, [name]: '', VERCEL_ENV: 'production' }), /Production requires/);
  assert.throws(() => publicBuildDefines({ VERCEL_ENV: 'production', SUPABASE_URL: old.NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY: jwt('service_role'), VERCEL_URL: 'preview.example' }), /Production requires/);
  assert.ok(Object.values(decode(publicBuildDefines({}))).every(value => value === ''));
});

test('database URLs must be origins, with HTTP confined to local development', () => {
  for (const url of ['http://remote.supabase.co', 'https://user:password@shared.supabase.co', 'https://shared.supabase.co/path', 'https://shared.supabase.co?key=private', 'https://shared.supabase.co#private', 'file:///tmp/db', 'not-a-url']) {
    assert.throws(() => publicBuildDefines({ ...old, NEXT_PUBLIC_SUPABASE_URL: url }), /must be an HTTPS origin/);
  }
  assert.doesNotThrow(() => publicBuildDefines({ ...old, NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:54321' }));
  assert.throws(() => publicBuildDefines({ ...old, NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:54321', VERCEL_ENV: 'production' }), /must be an HTTPS origin/);
});
