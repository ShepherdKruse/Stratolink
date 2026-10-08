import { sanitizeForecast } from './locationPrivacy.js';
import { readPrivateForecast } from './forecastStorage.js';
import { createServerSupabase } from './supabaseServer.js';

async function publicDevice(device) {
  const { data, error } = await createServerSupabase().from('devices').select('device_id')
    .eq('device_id', device).eq('connection_status', 'connected').maybeSingle();
  if (error) throw error;
  return Boolean(data);
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
    if (view !== 'full' && view !== 'path') return send(400, { message: 'Invalid forecast view' });
    try {
      if (!await isPublicDevice(device)) return send(404, { message: 'Device not found' });
      const forecast = await readForecast(device);
      if (!forecast) return send(202, { status: 'pending', device });
      response.setHeader('X-Forecast-Source', 'stored');
      response.setHeader('X-Forecast-Age-Ms', String(Math.max(0, Date.now() - Date.parse(forecast.generated_at))));
      return send(200, sanitizeForecast(forecast, view));
    } catch {
      console.error('Forecast read failed');
      return send(503, { message: 'Forecast unavailable' });
    }
  };
}

export const forecastApi = createForecastApi();
