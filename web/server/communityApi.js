import { createHash, randomBytes } from 'node:crypto';
import { createServerSupabase } from './supabaseServer.js';
import { payloadIdPattern, claimTokenPattern, readClaimIntent, writeClaimIntent, clearClaimIntent, publicClaimIntent } from './payloadClaim.js';

const idPattern = payloadIdPattern;
const ttnIdPattern = /^[a-z0-9](?:[a-z0-9-]{0,34}[a-z0-9])?$/;
const loginPattern = /^[a-z\d](?:[a-z\d-]{0,37}[a-z\d])?$/i;
const statuses = new Set(['planned', 'flying', 'landed', 'missing', 'retired']);
class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }
const fail = (status, message) => { throw new ApiError(status, message); };
const reply = (status, body) => Response.json(body, { status, headers: {
  'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Vary': 'Authorization, Origin',
} });

export function githubAccount(user) {
  if (!user?.id || user.is_anonymous) return null;
  const identity = user.identities?.find(item => item.provider === 'github');
  const id = identity?.identity_data?.sub ?? identity?.identity_data?.provider_id;
  const login = identity?.identity_data?.user_name ?? identity?.identity_data?.preferred_username;
  if (!/^\d{1,20}$/.test(String(id)) || typeof login !== 'string' || !loginPattern.test(login)) return null;
  return { id: user.id, login, avatarUrl: `https://avatars.githubusercontent.com/u/${id}` };
}

export function normalizeEui(value) {
  if (typeof value !== 'string' || value.length > 32) return null;
  const normalized = value.replace(/[\s:-]/g, '').toUpperCase();
  return /^[0-9A-F]{16}$/.test(normalized) && !/^0+$/.test(normalized) ? normalized : null;
}

function exactFields(body, expected) {
  if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length !== expected.length || expected.some(key => !Object.hasOwn(body, key))) fail(400, 'Invalid fields');
}
async function boundedJson(input, maxBytes) {
  const reader = input.body?.getReader();
  if (!reader) fail(400, 'JSON body required');
  const chunks = []; let length = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      length += chunk.value.byteLength;
      if (length > maxBytes) { await reader.cancel(); fail(413, 'Request body too large'); }
      chunks.push(chunk.value);
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch (error) {
    if (error instanceof ApiError) throw error;
    fail(400, 'Invalid JSON');
  }
}

export async function verifyTTNDevice({ cluster, applicationId, deviceEui, apiKey, requireComplete = false }, fetcher = fetch) {
  if (!['nam1','eu1','au1'].includes(cluster) || typeof applicationId !== 'string' || !ttnIdPattern.test(applicationId) || typeof deviceEui !== 'string' || !/^[0-9A-F]{16}$/.test(deviceEui)) fail(400, 'Invalid network identity');
  if (typeof apiKey !== 'string' || apiKey.length < 24 || apiKey.length > 512 || /[\s\x00-\x1F]/.test(apiKey)) fail(400, 'Invalid TTN API key');
  const signal = AbortSignal.timeout(12_000);
  const read = async url => {
    let response;
    try { response = await fetcher(url, { headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' }, redirect: 'error', signal, cache: 'no-store' }); }
    catch { fail(502, 'The Things Network is unavailable'); }
    if ([401,403].includes(response.status)) fail(403, 'The TTN key needs permission to read this application’s end devices');
    if (response.status === 404) fail(404, 'Application or device not found in this TTN cluster');
    if (!response.ok) fail(502, 'The Things Network is unavailable');
    try { return await boundedJson(response, 1024 * 1024); } catch { fail(502, 'Invalid response from The Things Network'); }
  };
  const base = `https://${cluster}.cloud.thethings.network/api/v3`;
  // TTN has one central Identity Server, independent of the radio's routing cluster.
  const registry = 'https://eu1.cloud.thethings.network/api/v3';
  let match;
  for (let page = 1; page <= 20; page++) {
    const data = await read(`${registry}/applications/${applicationId}/devices?field_mask=${requireComplete ? 'ids,join_server_address' : 'ids'}&limit=100&page=${page}`);
    if (!data || typeof data !== 'object' || Array.isArray(data) || (data.end_devices !== undefined && !Array.isArray(data.end_devices))) fail(502, 'Invalid response from The Things Network');
    const devices = data.end_devices ?? [];
    match = devices.find(device => normalizeEui(device?.ids?.dev_eui) === deviceEui && device?.ids?.application_ids?.application_id === applicationId);
    if (match || devices.length < 100) break;
  }
  const deviceId = match?.ids?.device_id;
  if (!deviceId || !ttnIdPattern.test(deviceId)) fail(404, 'This DevEUI was not found in your TTN application');
  const network = await read(`${base}/ns/applications/${applicationId}/devices/${deviceId}?field_mask=ids,frequency_plan_id${requireComplete ? ',supports_join' : ''}`);
  if (network?.ids?.device_id !== deviceId || network?.ids?.application_ids?.application_id !== applicationId || normalizeEui(network?.ids?.dev_eui) !== deviceEui) fail(409, 'The TTN registries disagree about this device. Check its network settings.');
  const plan = network.frequency_plan_id;
  if (typeof plan !== 'string' || !/^[A-Z0-9_-]{1,80}$/.test(plan)) fail(400, 'The TTN device needs a frequency plan');
  if (requireComplete) {
    if (network.supports_join !== true) fail(409, 'This payload needs an OTAA registration');
    if (!/^[0-9A-Fa-f]{16}$/.test(match.ids.join_eui || '') || network.ids.join_eui !== match.ids.join_eui) fail(409, 'Check the TTN JoinEUI in each registry');
    const joinHost = match.join_server_address;
    if (typeof joinHost !== 'string' || !/^(nam1|eu1|au1)\.cloud\.thethings\.network(?::443)?$/.test(joinHost)) fail(409, 'Check the TTN Join Server address');
    for (const address of [`${base}/as`, `https://${joinHost}/api/v3/js`]) {
      const registered = await read(`${address}/applications/${applicationId}/devices/${deviceId}?field_mask=ids`);
      if (registered?.ids?.device_id !== deviceId || registered?.ids?.application_ids?.application_id !== applicationId || normalizeEui(registered?.ids?.dev_eui) !== deviceEui || registered?.ids?.join_eui !== match.ids.join_eui) fail(409, 'The TTN registries disagree about this device. Check its network settings.');
    }
  }
  return { cluster, applicationId, deviceEui, deviceId, region: plan };
}

export function createCommunityApi({ createDb = createServerSupabase, verifyDevice = verifyTTNDevice, environment = process.env } = {}) {
  return async function community(request) {
    try {
      const url = new URL(request.url);
      const accountRoute = url.pathname === '/api/account';
      const registerRoute = url.pathname === '/api/balloons';
      const reserveRoute = url.pathname === '/api/balloons/reserve';
      const intentRoute = url.pathname === '/api/activation/intent';
      const claimRoute = url.pathname === '/api/activation/claim';
      const staffInventory = url.pathname === '/api/staff/payloads';
      const staffDetail = url.pathname.match(/^\/api\/staff\/payloads\/([^/]+)\/(claim-link|connections)$/);
      const detail = !reserveRoute && url.pathname.match(/^\/api\/balloons\/([^/]+)(\/connections)?$/);
      if (!accountRoute && !registerRoute && !reserveRoute && !intentRoute && !claimRoute && !staffInventory && !staffDetail && !detail) return reply(404, { error: 'Not found' });
      const methods = intentRoute ? ['GET','POST','DELETE'] : [accountRoute || staffInventory ? 'GET' : registerRoute || reserveRoute || claimRoute || staffDetail || detail?.[2] ? 'POST' : 'PATCH'];
      if (!methods.includes(request.method)) return reply(405, { error: 'Method not allowed' });
      const bearer = request.headers.get('authorization')?.match(/^Bearer ([A-Za-z0-9_.-]{20,10000})$/)?.[1];
      if (!intentRoute && !bearer) return reply(401, { error: 'Sign in with GitHub to continue' });
      const origin = request.headers.get('origin');
      if (request.method !== 'GET') {
        const allowed = [environment.SITE_URL, ...(environment.AUTH_ALLOWED_ORIGINS || '').split(',')].filter(Boolean).map(value => new URL(value.trim()).origin);
        if (!origin || !allowed.includes(origin) || request.headers.get('sec-fetch-site') === 'cross-site') return reply(403, { error: 'Request origin not allowed' });
        if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type') || '')) return reply(415, { error: 'Use application/json' });
      }
      if (intentRoute && request.method === 'DELETE') return clearClaimIntent(reply(200, { intent: null }), origin);
      if (intentRoute && request.method === 'GET') return reply(200, { intent: publicClaimIntent(readClaimIntent(request, environment)) });
      if ((registerRoute || reserveRoute || claimRoute || intentRoute || staffDetail || detail?.[2]) && environment.COMMUNITY_REGISTRATION_ENABLED !== 'true') {
        return reply(503, { error: 'Registration unavailable' });
      }
      if (intentRoute) {
        const body = await boundedJson(request, 2048);
        exactFields(body, Object.hasOwn(body ?? {}, 'claimToken') ? ['deviceId','claimToken'] : ['deviceId']);
        if (typeof body.deviceId !== 'string' || !idPattern.test(body.deviceId) || (body.claimToken !== undefined && (typeof body.claimToken !== 'string' || body.claimToken.length > 256))) return reply(400, { error: 'Invalid payload link' });
        // Old PINs and short legacy codes retain context but are never proof.
        const tokenHash = claimTokenPattern.test(body.claimToken || '') ? createHash('sha256').update(body.claimToken).digest('hex') : null;
        const now = Date.now();
        const response = reply(200, { intent: publicClaimIntent({ deviceId: body.deviceId, tokenHash, expires: now + 30 * 60_000 }) });
        return writeClaimIntent(response, { deviceId: body.deviceId, tokenHash, origin }, environment, now);
      }
      const db = createDb();
      const auth = await db.auth.getUser(bearer);
      if (auth.error || !auth.data?.user) return reply(401, { error: 'Sign in with GitHub to continue' });
      const user = githubAccount(auth.data.user);
      if (!user) return reply(403, { error: 'Sign in with GitHub to continue' });
      const isStaff = (environment.PAYLOAD_STAFF_USER_IDS || '').split(',').map(value => value.trim()).includes(user.id);
      if ((staffInventory || staffDetail) && !isStaff) return reply(403, { error: 'Staff access required' });
      const rpc = async (name, args) => {
        const result = await db.rpc(name, args);
        if (result.error) {
          if (result.error.code === '23505') fail(409, 'This device is already registered or connected');
          if (result.error.code === 'P0001') fail(409, 'The account or device connection limit has been reached');
          if (result.error.code === '55000') fail(409, name === 'connect_community_radio' ? 'This connection is managed by Stratolink' : 'Verify the payload and shared TTN integration before continuing');
          if (result.error.code === '22023') fail(400, 'Invalid payload or network identity');
          fail(503, 'Unable to save this change');
        }
        return result.data;
      };
      const balloons = async () => await rpc('community_account', { p_owner_id: user.id });
      if (accountRoute) return reply(200, { user, balloons: await balloons() });
      if (staffInventory) return reply(200, await rpc('staff_payload_inventory', {}));
      const action = registerRoute ? 'register' : reserveRoute ? 'reserve' : claimRoute ? 'claim' : staffDetail ? staffDetail[2] === 'claim-link' ? 'issue' : 'connect' : detail[2] ? 'connect' : 'update';
      if (!await rpc('community_rate_limit', { p_owner_id: user.id, p_action: action })) return reply(429, { error: 'Too many changes. Try again in a minute.' });
      const body = await boundedJson(request, 8192);
      if (claimRoute) {
        exactFields(body, Object.hasOwn(body ?? {}, 'claimToken') ? ['deviceId','claimToken'] : ['deviceId']);
        const intent = readClaimIntent(request, environment);
        if (!intent || intent.origin !== origin) return reply(409, { error: 'Open your payload link again to continue' });
        if (body.deviceId !== intent.deviceId) return reply(409, { error: 'This payload link changed. Open it again.' });
        if (body.claimToken !== undefined && (typeof body.claimToken !== 'string' || !claimTokenPattern.test(body.claimToken))) return reply(400, { error: 'Enter a valid claim code' });
        const tokenHash = body.claimToken ? createHash('sha256').update(body.claimToken).digest('hex') : intent.tokenHash;
        if (!tokenHash) return reply(400, { error: 'Enter the claim code supplied with your payload' });
        const balloon = await rpc('claim_existing_payload', { p_owner_id: user.id, p_github_login: user.login, p_device_id: intent.deviceId, p_token_hash: tokenHash });
        if (!balloon) return writeClaimIntent(reply(409, { error: 'This claim code is invalid, expired, or already used' }), { ...intent, tokenHash: null }, environment);
        return clearClaimIntent(reply(200, { balloon }), origin);
      }
      if (reserveRoute) {
        exactFields(body, ['callsign']);
        const callsign = typeof body.callsign === 'string' ? body.callsign.trim().toLowerCase() : '';
        if (callsign.length > 36 || !/^[a-z0-9](?:-?[a-z0-9]){2,35}$/.test(callsign)) return reply(400, { error: 'Use 3 to 36 lowercase letters, numbers, or single hyphens' });
        const balloon = await rpc('reserve_community_payload', { p_owner_id: user.id, p_github_login: user.login, p_callsign: callsign });
        return reply(201, { balloon });
      }
      if (staffDetail) {
        const deviceId = staffDetail[1];
        if (!idPattern.test(deviceId)) return reply(404, { error: 'Payload not found' });
        const inventory = await rpc('staff_payload_inventory', {});
        const payload = inventory.payloads.find(item => item.deviceId === deviceId);
        if (!payload) return reply(404, { error: 'Payload not found' });
        if (action === 'issue') {
          exactFields(body, ['devEui']);
          const devEui = normalizeEui(body.devEui);
          if (!devEui) return reply(400, { error: 'Enter a valid 16-character DevEUI' });
          if (payload.owned) return reply(409, { error: 'This payload already has an owner' });
          const site = new URL(environment.SITE_URL);
          if (site.protocol !== 'https:' || site.username || site.password || site.pathname !== '/' || site.search || site.hash) return reply(503, { error: 'Payload URL is not configured' });
          const secret = randomBytes(32).toString('base64url');
          const result = await rpc('issue_payload_claim', { p_issuer_id: user.id, p_device_id: deviceId, p_dev_eui: devEui, p_token_hash: createHash('sha256').update(secret).digest('hex') });
          if (!result) return reply(409, { error: 'Verify this payload before issuing a claim link' });
          return reply(201, { deviceId, url: `${site.origin}/activate/${encodeURIComponent(deviceId)}#k=${secret}`, expiresAt: result.expiresAt });
        }
        exactFields(body, ['integrationId','cluster','applicationId','deviceEui','apiKey']);
        const integration = inventory.integrations.find(item => item.id === body.integrationId && item.cluster === body.cluster && item.applicationId === body.applicationId);
        const deviceEui = normalizeEui(body.deviceEui);
        if (!integration || !deviceEui) return reply(400, { error: 'Choose a matching shared TTN integration' });
        const connection = await verifyDevice({ ...body, deviceEui, requireComplete: true });
        const balloon = await rpc('bind_staff_payload_radio', { p_device_id: deviceId, p_integration_id: integration.id, p_cluster: connection.cluster, p_application_id: connection.applicationId, p_ttn_device_id: connection.deviceId, p_dev_eui: connection.deviceEui, p_region: connection.region });
        return balloon ? reply(200, { balloon }) : reply(409, { error: 'Unable to connect this payload' });
      }
      if (registerRoute) {
        exactFields(body, ['callsign','devEui']);
        const callsign = typeof body.callsign === 'string' ? body.callsign.trim() : '';
        const devEui = normalizeEui(body.devEui);
        if (!/^[A-Za-z0-9][A-Za-z0-9 ._-]{1,39}$/.test(callsign) || !devEui) return reply(400, { error: 'Enter a callsign and a valid 16-character DevEUI' });
        const balloon = await rpc('register_community_balloon', { p_owner_id: user.id, p_github_login: user.login, p_callsign: callsign, p_dev_eui: devEui });
        return reply(201, { balloon });
      }
      const deviceId = detail[1];
      if (!idPattern.test(deviceId)) return reply(404, { error: 'Balloon not found' });
      const owned = (await balloons()).find(balloon => balloon.id === deviceId);
      if (!owned) return reply(404, { error: 'Balloon not found' });
      if (action === 'update') {
        exactFields(body, ['status']);
        if (!statuses.has(body.status)) return reply(400, { error: 'Invalid status' });
        const balloon = await rpc('update_community_balloon', { p_owner_id: user.id, p_device_id: deviceId, p_status: body.status });
        return balloon ? reply(200, { balloon }) : reply(404, { error: 'Balloon not found' });
      }
      exactFields(body, ['cluster','applicationId','deviceEui','apiKey']);
      const deviceEui = normalizeEui(body.deviceEui);
      if (!deviceEui || typeof body.applicationId !== 'string') return reply(400, { error: 'Invalid network identity' });
      const connection = await verifyDevice({ ...body, deviceEui });
      const site = new URL(environment.SITE_URL);
      if (site.protocol !== 'https:' || site.username || site.password || site.pathname !== '/' || site.search || site.hash) return reply(503, { error: 'Webhook URL is not configured' });
      const secret = randomBytes(32).toString('base64url');
      const tokenHash = createHash('sha256').update(secret).digest('hex');
      const balloon = await rpc('connect_community_radio', { p_owner_id: user.id, p_device_id: deviceId, p_cluster: connection.cluster, p_application_id: connection.applicationId, p_ttn_device_id: connection.deviceId, p_dev_eui: connection.deviceEui, p_region: connection.region, p_token_hash: tokenHash });
      if (!balloon) return reply(404, { error: 'Balloon not found' });
      return reply(200, { balloon, webhook: { url: `${site.origin}/api/ttn-webhook`, secret } });
    } catch (error) {
      if (error instanceof ApiError) return reply(error.status, { error: error.message });
      return reply(503, { error: 'Account service unavailable' });
    }
  };
}
export const communityApi = createCommunityApi();

export default communityApi;
