import { createHmac, timingSafeEqual } from 'node:crypto';

export const payloadIdPattern = /^(?:balloon-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|(?=.{3,36}$)[a-z0-9](?:-?[a-z0-9]){2,35})$/;
export const claimTokenPattern = /^[A-Za-z0-9_-]{43}$/;
const lifetime = 30 * 60;
const cookieName = 'stratolink-payload-claim';

function key(environment) {
  const value = environment.PAYLOAD_CLAIM_COOKIE_SECRET;
  if (typeof value !== 'string' || !claimTokenPattern.test(value) || Buffer.from(value, 'base64url').length !== 32) throw new Error('Claim session unavailable');
  return Buffer.from(value, 'base64url');
}

function signature(value, environment) {
  return createHmac('sha256', key(environment)).update(`payload-claim:v1:${value}`).digest('base64url');
}

export function readClaimIntent(request, environment, now = Date.now()) {
  const cookies = (request.headers.get('cookie') || '').split(';').map(part => part.trim());
  const matches = cookies.filter(part => part.startsWith(`${cookieName}=`));
  if (matches.length !== 1) return null;
  const raw = matches[0].slice(cookieName.length + 1);
  if (raw.length > 1500) return null;
  const [value, mac, extra] = raw.split('.');
  if (!value || !claimTokenPattern.test(mac || '') || extra !== undefined) return null;
  try {
    const expected = Buffer.from(signature(value, environment));
    if (!timingSafeEqual(Buffer.from(mac), expected)) return null;
    const intent = JSON.parse(Buffer.from(value, 'base64url').toString('utf8'));
    if (intent.v !== 1 || typeof intent.deviceId !== 'string' || !payloadIdPattern.test(intent.deviceId) || !Number.isFinite(intent.expires) || intent.expires <= now || intent.expires > now + lifetime * 1000) return null;
    if (intent.tokenHash !== null && !/^[0-9a-f]{64}$/.test(intent.tokenHash)) return null;
    if (typeof intent.origin !== 'string' || new URL(intent.origin).origin !== intent.origin) return null;
    return intent;
  } catch { return null; }
}

export function writeClaimIntent(response, { deviceId, tokenHash, origin }, environment, now = Date.now()) {
  const intent = { v: 1, deviceId, tokenHash, origin, expires: now + lifetime * 1000 };
  const value = Buffer.from(JSON.stringify(intent)).toString('base64url');
  const secure = origin.startsWith('https:') ? '; Secure' : '';
  response.headers.set('Set-Cookie', `${cookieName}=${value}.${signature(value, environment)}; Path=/api/activation; HttpOnly; SameSite=Lax; Max-Age=${lifetime}${secure}`);
  return response;
}

export function clearClaimIntent(response, origin) {
  response.headers.set('Set-Cookie', `${cookieName}=; Path=/api/activation; HttpOnly; SameSite=Lax; Max-Age=0${origin?.startsWith('https:') ? '; Secure' : ''}`);
  return response;
}

export function publicClaimIntent(intent) {
  return intent ? { deviceId: intent.deviceId, requiresProof: !intent.tokenHash, expiresAt: new Date(intent.expires).toISOString() } : null;
}
