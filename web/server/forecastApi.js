import { sanitizeForecast } from './locationPrivacy.js';
import { readPrivateForecast } from './forecastStorage.js';
import { createServerSupabase } from './supabaseServer.js';

/* A stored forecast changes at most a few times a day (one GitHub Actions run per
 * NOAA cycle), so a successful read may sit in the shared CDN cache for five
 * minutes and be served stale for up to an hour while it revalidates. Pending
 * (202), unknown-device (404) and failed (503) answers stay uncacheable so a
 * balloon that just got its first forecast, or a transient outage, is never
 * pinned. */
const CACHEABLE = 'public, s-maxage=300, stale-while-revalidate=3600';
const VIEWS = new Set(['full', 'path', 'history']);

async function publicDevice(device) {
  const { data, error } = await createServerSupabase().from('devices').select('device_id')
    .eq('device_id', device).eq('connection_status', 'connected').maybeSingle();
  if (error) throw error;
  return Boolean(data);
}

/** Weak entity tag for a stored forecast: its generation time is the only thing
 *  that changes between runs, and each view has its own body. Weak because the
 *  CDN may re-encode the bytes. */
export function forecastEtag(forecast, view) {
  return `W/"${view}-${Date.parse(forecast.generated_at)}"`;
}

/** RFC 7232 If-None-Match: a list of tags (or `*`), compared weakly. */
function etagMatches(header, etag) {
  if (typeof header !== 'string') return false;
  const opaque = etag.replace(/^W\//, '');
  return header.split(',').some(candidate => {
    const tag = candidate.trim().replace(/^W\//, '');
    return tag === '*' || tag === opaque;
  });
}

export function createForecastApi({ readForecast = readPrivateForecast, isPublicDevice = publicDevice } = {}) {
  return async function forecastApi(request, response) {
    response.setHeader('Content-Type', 'application/json; charset=utf-8');
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    const send = (status, body) => { response.statusCode = status; response.end(JSON.stringify(body)); };
    if (request.method !== 'GET') {
      response.setHeader('Allow', 'GET');
      return send(405, { message: 'Use GET to read a forecast.' });
    }
    const params = new URL(request.url, 'http://localhost').searchParams;
    const device = params.get('device');
    const view = params.get('view') ?? 'full';
    if (!device || !/^[a-zA-Z0-9_-]{1,80}$/.test(device)) return send(400, { message: 'Invalid device' });
    if (!VIEWS.has(view)) return send(400, { message: 'Invalid forecast view' });
    try {
      if (!await isPublicDevice(device)) return send(404, { message: 'Device not found' });
      const forecast = await readForecast(device);
      if (!forecast) return send(202, { status: 'pending', device });
      const etag = forecastEtag(forecast, view);
      response.setHeader('Cache-Control', CACHEABLE);
      response.setHeader('ETag', etag);
      response.setHeader('X-Forecast-Source', 'stored');
      response.setHeader('X-Forecast-Age-Ms', String(Math.max(0, Date.now() - Date.parse(forecast.generated_at))));
      if (etagMatches(request.headers?.['if-none-match'], etag)) {
        response.statusCode = 304;
        response.end();
        return;
      }
      return send(200, sanitizeForecast(forecast, view));
    } catch {
      console.error('Forecast read failed');
      return send(503, { message: 'Forecast unavailable' });
    }
  };
}

export const forecastApi = createForecastApi();
