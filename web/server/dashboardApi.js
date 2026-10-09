import { sanitizeTelemetry, sanitizeDevice } from './locationPrivacy.js';
import { serverSupabaseConfig } from './supabaseServer.js';
const columns = {
  devices: 'device_id,launcher_name,status,launch_lat,launch_lon,launched_at,display_name,owner_github,official,connection_status,planned_launch_date',
  telemetry: 'id,device_id,time,lat,lon,altitude_m,battery_voltage,solar_voltage,temperature,pressure,rssi,snr,gps_speed,gps_heading,gps_satellites,mems_accel_x,mems_accel_y,mems_accel_z,velocity_x,velocity_y,uv_index,ambient_lux,acoustic_event,firmware_version,uptime_s,tx_count,hdop,power_mode,sleep_ms,lora_sf,lora_bw,frequency_hz,gateways,telemetry_version,power_tier,reset_cause,boot_count,gps_fix_age_min,server_proof_count_mod8,server_qualified_miss_streak,server_recovery_parity,command_ack_seq,relay_enabled,relay_fwd_delta,ctt_tags_delta',
};
export function buildQuery(params) {
  const resource = params.get('resource');
  if (!Object.hasOwn(columns, resource)) throw new Error('Invalid resource');
  const query = new URLSearchParams();
  const requested = (params.get('select') ?? '').replaceAll(' ', '').split(',');
  if (!requested.length || requested.some(field => !columns[resource].split(',').includes(field))) throw new Error('Invalid fields');
  // Always fetch both coordinates, so requesting only one cannot bypass masking.
  query.set('select', columns[resource]);
  for (const [key, value] of params) {
    if (key === 'select' || key === 'resource') continue;
    if (key === 'device_id' && /^(in\.\([a-zA-Z0-9_,"-]+\)|eq\.[a-zA-Z0-9_-]+)$/.test(value)) query.append(key, value);
    else if (key === 'time' && /^(gte|lte)\./.test(value) && Number.isFinite(Date.parse(value.slice(4)))) query.append(key, value);
    else if (['lat', 'lon'].includes(key) && value === 'not.is.null') query.append(key, value);
    else if (key === 'order' && /^(time|id|device_id)\.(asc|desc)(,(time|id|device_id)\.(asc|desc))*$/.test(value)) query.append(key, value);
    else if (['offset', 'limit'].includes(key) && /^\d{1,7}$/.test(value)) query.append(key, key === 'limit' ? String(Math.min(+value, 1000)) : value);
    else throw new Error('Unsupported query');
  }
  if (!query.has('limit')) query.set('limit', '1000');
  if (resource === 'devices') query.set('or', '(connection_status.eq.connected,and(status.in.(planned,storage),owner_id.not.is.null))');
  return { resource, query, requested };
}
export async function dashboardApi(request, response) {
  const url = new URL(request.url, 'http://localhost');
  const send = (status, data) => {
    response.statusCode = status;
    response.setHeader('Content-Type', 'application/json');
    response.setHeader('Cache-Control', 'no-store');
    response.end(JSON.stringify(data));
  };
  if (request.method !== 'GET') return send(405, { message: 'Read-only endpoint' });
  try {
    let parsed;
    try { parsed = buildQuery(url.searchParams); } catch { return send(400, { message: 'Unsupported dashboard query' }); }
    const { resource, query, requested } = parsed;
    const { url: base, key } = serverSupabaseConfig();
    const source = resource === 'telemetry' ? 'community_telemetry' : 'devices';
    const upstream = await fetch(`${base}/rest/v1/${source}?${query}`, {
      headers: { apikey: key, Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(15000),
    });
    if (!upstream.ok) return send(502, { message: 'Telemetry unavailable' });
    const raw = await upstream.json();
    if (!Array.isArray(raw)) return send(502, { message: 'Telemetry unavailable' });
    const safe = raw.map(resource === 'devices' ? sanitizeDevice : sanitizeTelemetry);
    return send(200, safe.map(row => Object.fromEntries([...new Set([...requested, 'location_approximate'])].map(field => [field, row[field]]))));
  } catch { return send(502, { message: 'Dashboard data unavailable' }); }
}
