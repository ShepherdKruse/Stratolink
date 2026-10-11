// A city-wide area, deliberately unrelated to any private street address.
export const SAN_FRANCISCO = { lat: 37.76, lon: -122.44, label: 'San Francisco' };
export function isPrivateLocation(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) && lat >= 37.70 && lat <= 37.84 && lon >= -122.53 && lon <= -122.35;
}
export function publicPosition(lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return { lat: null, lon: null };
  return isPrivateLocation(lat, lon) ? { lat: SAN_FRANCISCO.lat, lon: SAN_FRANCISCO.lon, location_approximate: true } : { lat, lon };
}
export function sanitizeTelemetry(row) {
  const result = { ...row, ...publicPosition(row.lat, row.lon) };
  // A coarse point cannot support a precise receiver link or a street-level heading.
  if (result.location_approximate) {
    result.gps_heading = null;
    result.velocity_x = null;
    result.velocity_y = null;
  }
  result.gateways = Array.isArray(row.gateways) ? row.gateways.map((gateway, index) => {
    const position = publicPosition(gateway.lat, gateway.lon);
    return { gateway_id: position.location_approximate ? `sf-receiver-${index + 1}` : gateway.gateway_id,
      rssi: gateway.rssi, snr: gateway.snr, alt: position.location_approximate ? null : gateway.alt, ...position };
  }) : null;
  return result;
}
export function sanitizeDevice(row) {
  const position = publicPosition(row.launch_lat, row.launch_lon);
  return { ...row, launch_lat: position.lat, launch_lon: position.lon, location_approximate: position.location_approximate ?? false };
}
function sanitizeGeometry(value) {
  if (Array.isArray(value)) {
    if (value.length === 2 && value.every(Number.isFinite)) {
      const [lon, lat] = value;
      return isPrivateLocation(lat, lon) ? [SAN_FRANCISCO.lon, SAN_FRANCISCO.lat] : value;
    }
    return value.map(sanitizeGeometry);
  }
  if (!value || typeof value !== 'object') return value;
  const result = Object.fromEntries(Object.entries(value).map(([key, child]) => [key, sanitizeGeometry(child)]));
  if ('lat' in result && 'lon' in result) Object.assign(result, publicPosition(result.lat, result.lon));
  return result;
}
export function sanitizeForecast(raw, view = 'full') {
  if (view === 'path') return sanitizeGeometry({ generated_at: raw.generated_at, nominal_path: raw.nominal_path ?? [] });
  // History only: the reconstructed track through past GPS gaps, for balloons that are no longer flying.
  if (view === 'history') {
    return sanitizeGeometry({ generated_at: raw.generated_at,
      observed: { reconstructed_path: raw.observed?.reconstructed_path ?? [], reconstructed_track: raw.observed?.reconstructed_track ?? [] } });
  }
  // Only return fields consumed by the dashboard, never source metadata/launch notes.
  return sanitizeGeometry({
    generated_at: raw.generated_at, forecast_horizon_h: raw.forecast_horizon_h,
    forecast_origin: { time_utc: raw.forecast_origin?.time_utc },
    stale_gps: raw.stale_gps ? { coverage_limited: Boolean(raw.stale_gps.coverage_limited) } : null,
    nominal_path: raw.nominal_path ?? [], ensemble: raw.ensemble ?? [], ellipses: raw.ellipses ?? [],
    predicted_hindcast: { path: raw.predicted_hindcast?.path ?? [] }, divergence: raw.divergence ?? null,
    observed: { reconstructed_path: raw.observed?.reconstructed_path ?? [], reconstructed_track: raw.observed?.reconstructed_track ?? [] },
  });
}
