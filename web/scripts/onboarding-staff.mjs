#!/usr/bin/env node
import { constants } from 'node:fs';
import { mkdir, open, realpath, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import QRCode from 'qrcode';

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const devicePattern = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
const usage = `Usage: npm run onboarding:staff -- inventory|issue|connect [options]

  --origin https://stratolink.org   Website origin (required)
  --token-file /private/session    Staff Supabase access token, mode 600
  --device callsign               Existing reserved or provisioned device
  --dev-eui 0123456789ABCDEF       Verified hardware DevEUI
  --cluster nam1|eu1|au1          TTN connection only
  --application application-id   TTN connection only
  --integration integration-uuid Existing shared webhook; connection only
  --ttn-key-file /private/ttn-key TTN read key, mode 600; connection only
  --claim-origin https://stratolink.org  Expected printed URL origin
  --out /private/new-directory    New private artifact directory
  --apply                        Write changes; otherwise inspect only

Issuing a claim link does not launch the balloon. Connecting reads TTN;
it never creates, changes, or deletes TTN devices or webhooks.`;

export function parseArguments(args) {
  if (args.length === 0 || args.includes('--help')) return { help: true };
  const [command, ...rest] = args;
  if (!['inventory', 'issue', 'connect'].includes(command)) throw new Error('Choose inventory, issue, or connect');
  const values = { command, apply: false };
  const names = new Set(['origin', 'token-file', 'device', 'dev-eui', 'cluster', 'application', 'integration', 'ttn-key-file', 'claim-origin', 'out']);
  for (let i = 0; i < rest.length; i++) {
    const name = rest[i].slice(2);
    if (rest[i] === '--apply') {
      if (values.apply) throw new Error('Duplicate option');
      values.apply = true;
    } else {
      if (!rest[i].startsWith('--') || !names.has(name) || Object.hasOwn(values, name) || !rest[i + 1] || rest[i + 1].startsWith('--')) throw new Error('Invalid option');
      values[name] = rest[++i];
    }
  }
  let origin;
  try { origin = new URL(values.origin); } catch { throw new Error('Provide an exact website origin'); }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname);
  if (origin.username || origin.password || origin.search || origin.hash || origin.pathname !== '/' || !(origin.protocol === 'https:' || local && origin.protocol === 'http:')) throw new Error('Use HTTPS or a local HTTP origin, with no path or credentials');
  values.origin = origin.origin;
  if (values['claim-origin']) {
    let claimOrigin;
    try { claimOrigin = new URL(values['claim-origin']); } catch { throw new Error('Invalid claim origin'); }
    if (claimOrigin.origin !== values['claim-origin'] || claimOrigin.protocol !== 'https:' || claimOrigin.username || claimOrigin.password) throw new Error('Use an exact HTTPS claim origin');
  }
  if (!values['token-file']) throw new Error('Provide --token-file');
  if (command !== 'inventory') {
    if (!devicePattern.test(values.device || '')) throw new Error('Provide a valid existing device ID');
    values['dev-eui'] = (values['dev-eui'] || '').replace(/[\s:-]/g, '').toUpperCase();
    if (!/^[0-9A-F]{16}$/.test(values['dev-eui']) || /^0+$/.test(values['dev-eui'])) throw new Error('Provide a valid DevEUI');
    if (values.apply && !values.out) throw new Error('Provide --out for private artifacts');
  }
  if (command === 'connect') {
    if (!['nam1', 'eu1', 'au1'].includes(values.cluster) || !/^[a-z0-9](?:[a-z0-9-]{0,34}[a-z0-9])?$/.test(values.application || '')) throw new Error('Provide a TTN cluster and application');
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(values.integration || '')) throw new Error('Provide the existing shared integration ID');
    if (values.apply && !values['ttn-key-file']) throw new Error('Provide --ttn-key-file');
  }
  if (command === 'inventory' && values.apply) throw new Error('Inventory is read-only');
  return values;
}

async function privateValue(path) {
  let handle;
  try {
    handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
    const stat = await handle.stat();
    if (!stat.isFile() || (stat.mode & 0o077) !== 0 || stat.size > 16384 || (process.getuid && stat.uid !== process.getuid())) throw new Error();
    const value = (await handle.readFile('utf8')).trim();
    if (!value || /\s/.test(value)) throw new Error();
    return value;
  } catch { throw new Error('Credential file must be owned by you, mode 600, and contain only the token'); }
  finally { await handle?.close(); }
}

async function privateDirectory(path) {
  const output = resolve(path);
  let parent;
  try { parent = await realpath(dirname(output)); } catch { throw new Error('Artifact parent directory must already exist'); }
  const fromRepository = relative(await realpath(repository), parent);
  if (!(fromRepository === '..' || fromRepository.startsWith(`..${sep}`) || isAbsolute(fromRepository))) throw new Error('Save credentials outside the repository');
  try { await mkdir(output, { mode: 0o700 }); }
  catch { throw new Error('Artifact directory must be new and writable'); }
  return output;
}

export async function runStaff(args, { fetcher = fetch, log = console.log } = {}) {
  const options = parseArguments(args);
  if (options.help) { log(usage); return; }
  const token = await privateValue(options['token-file']);
  if (!/^[A-Za-z0-9_.-]{20,10000}$/.test(token)) throw new Error('Invalid staff access token');
  const request = async (path, body) => {
    let response;
    try {
      response = await fetcher(`${options.origin}${path}`, {
        method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(20_000),
        headers: { Authorization: `Bearer ${token}`, Origin: options.origin, Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } catch { throw new Error('Request failed. No automatic retry was made. Inspect inventory before retrying a write.'); }
    if (!response.ok) throw new Error(`Staff API returned HTTP ${response.status}. Check sign-in, staff access, and rollout settings.`);
    try { return await response.json(); } catch { throw new Error('Invalid staff API response'); }
  };
  const inventory = await request('/api/staff/payloads');
  if (!Array.isArray(inventory?.payloads)) throw new Error('Invalid staff inventory response');
  if (options.command === 'inventory') {
    for (const payload of inventory.payloads) log(JSON.stringify({ deviceId: payload.deviceId, status: payload.status, owned: payload.owned, launcherName: payload.launcherName, devEui: payload.devEui }));
    for (const integration of inventory.integrations || []) log(JSON.stringify({ integrationId: integration.id, cluster: integration.cluster, applicationId: integration.applicationId }));
    if (!inventory.payloads.length) log('No payloads');
    return;
  }
  const payload = inventory.payloads.find(item => item.deviceId === options.device);
  if (!payload) throw new Error('Device is not in the staff inventory. Preserve its existing registration.');
  if (options.command === 'issue') {
    if (payload.owned) throw new Error('This payload already has an owner');
    if (payload.devEui && payload.devEui !== options['dev-eui']) throw new Error('DevEUI differs from the existing registration');
  } else if (!inventory.integrations?.some(item => item.id === options.integration && item.cluster === options.cluster && item.applicationId === options.application)) {
    throw new Error('Shared integration does not match this TTN application and cluster');
  }
  if (!options.apply) {
    log(JSON.stringify({ dryRun: true, action: options.command, deviceId: options.device, devEui: options['dev-eui'], ...(options.command === 'connect' ? { cluster: options.cluster, applicationId: options.application, integrationId: options.integration } : {}) }));
    log('No changes made. Use --apply and --out to continue.');
    return;
  }
  const apiKey = options.command === 'connect' ? await privateValue(options['ttn-key-file']) : undefined;
  const output = await privateDirectory(options.out);
  const endpoint = options.command === 'issue' ? 'claim-link' : 'connections';
  const result = await request(`/api/staff/payloads/${encodeURIComponent(options.device)}/${endpoint}`, options.command === 'issue'
    ? { devEui: options['dev-eui'] }
    : { cluster: options.cluster, applicationId: options.application, deviceEui: options['dev-eui'], apiKey, integrationId: options.integration });
  const save = (name, content) => writeFile(resolve(output, name), content, { encoding: 'utf8', mode: 0o600, flag: 'wx' });
  // Persist a successful write before rendering; a rendering failure must not lose the credential.
  await save('result.json', `${JSON.stringify(result, null, 2)}\n`);
  if (options.command === 'issue') {
    let activation;
    try { activation = new URL(result.url); } catch { throw new Error('Claim saved privately; API returned an invalid activation URL'); }
    const proof = new URLSearchParams(activation.hash.slice(1));
    if (result.deviceId !== options.device || activation.origin !== (options['claim-origin'] || options.origin) || activation.pathname !== `/activate/${options.device}` || activation.search || activation.username || activation.password || [...proof.keys()].join() !== 'k' || !/^[A-Za-z0-9_-]{43}$/.test(proof.get('k') || '') || !Number.isFinite(Date.parse(result.expiresAt))) throw new Error('Claim saved privately; check the activation URL before printing');
    const expiry = new Date(result.expiresAt).toISOString().slice(0, 10);
    await save('claim-qr.svg', await QRCode.toString(result.url, { type: 'svg', margin: 4, errorCorrectionLevel: 'M' }));
    await save('label.html', `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>${options.device}</title><style>body{font:16px Helvetica,Arial,sans-serif;margin:32px;width:320px}img{width:256px;display:block}p{margin:12px 0}</style><p>stratolink</p><img src="claim-qr.svg" alt="Claim this payload"><p>${options.device}</p><p>Scan to add this payload to your account.</p><p>Expires ${expiry} (UTC)</p></html>\n`);
  }
  log(`Saved private ${options.command === 'issue' ? 'claim link and printable QR' : 'verified connection receipt'} to ${output}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  runStaff(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });
}
