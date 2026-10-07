import { get } from '@vercel/blob';

const MAX_FORECAST_BYTES = 8 * 1024 * 1024;

export async function readPrivateForecast(device, { getBlob = get, token = process.env.BLOB_READ_WRITE_TOKEN } = {}) {
  if (!/^[a-zA-Z0-9_-]{1,80}$/.test(device)) throw new Error('Invalid forecast device');
  if (!token) throw new Error('Forecast storage is not configured');
  const blob = await getBlob(`forecasts/${encodeURIComponent(device)}.json`, { access: 'private', useCache: false, token });
  if (!blob) return null;
  if (blob.statusCode !== 200) throw new Error('Forecast storage read failed');
  const reader = blob.stream.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_FORECAST_BYTES) throw new Error('Forecast exceeds size limit');
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally { reader.releaseLock(); }
  const forecast = JSON.parse(Buffer.concat(chunks, length).toString('utf8'));
  if (!forecast || !Number.isFinite(Date.parse(forecast.generated_at)) || !Array.isArray(forecast.nominal_path)) {
    throw new Error('Stored forecast is invalid');
  }
  return forecast;
}
