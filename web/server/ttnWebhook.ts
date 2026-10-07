import { createHash } from 'node:crypto';
import { parseB2BEventPayload, parseCTTEventPayload, parseTTNPayload, type TTNWebhookPayload } from '../lib/ttn/payload-parser.ts';
import { isExpectedTTNDeliveryDuplicate, parseTTNUplinkIdentity, readRequestBodyWithinLimit } from '../lib/ttn/webhook-auth.ts';
import { createServerSupabase } from './supabaseServer.js';

const MAX_BODY_BYTES = 256 * 1024;
const ID = /^[a-z0-9](?:[a-z0-9-]{0,34}[a-z0-9])?$/;
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
const duplicateIndexes = {
  telemetry: 'telemetry_ttn_scoped_delivery',
  wildlife_detections: 'wildlife_ttn_scoped_delivery',
  b2b_packets: 'b2b_ttn_scoped_delivery',
};
type Table = keyof typeof duplicateIndexes;
type Binding = {
  canonical_device_id: string | null;
  integration_id: string;
  radio_identity_id: string | null;
  identity_mismatch: boolean;
};
type Lookup = { p_token_hash: string; p_application_id: string; p_ttn_device_id: string; p_dev_eui: string };
type Dependencies = {
  resolveIdentity: (lookup: Lookup) => Promise<Binding | null>;
  insert: (table: Table, row: Record<string, unknown>) => Promise<{ error: unknown }>;
  markReceived: (identityId: string, receivedAt: string) => Promise<{ error: unknown }>;
};

const defaults: Dependencies = {
  async resolveIdentity(lookup) {
    const { data, error } = await createServerSupabase().rpc('resolve_ttn_ingress', lookup);
    if (error) throw new Error('Identity registry unavailable');
    if (!Array.isArray(data) || data.length !== 1) return null;
    return data[0];
  },
  async insert(table, row) { return await createServerSupabase().from(table).insert(row); },
  async markReceived(identityId, receivedAt) {
    return await createServerSupabase().rpc('mark_radio_received', { p_radio_identity_id: identityId, p_received_at: receivedAt });
  },
};

function response(status: number, errorOrData: string | Record<string, unknown>) {
  return Response.json(typeof errorOrData === 'string' ? { error: errorOrData } : errorOrData, {
    status,
    headers: {
      'Cache-Control': 'no-store',
      ...(status === 401 ? { 'WWW-Authenticate': 'Bearer' } : {}),
      ...(status === 405 ? { Allow: 'POST' } : {}),
    },
  });
}

function record(value: unknown): value is Record<string, any> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Keep complete rx_metadata privately; normalize only the dashboard receiver fields. */
export function extractGateways(metadata: unknown) {
  if (!Array.isArray(metadata)) return [];
  const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null;
  return metadata.flatMap(reception => {
    if (!record(reception)) return [];
    const id = reception.gateway_ids?.gateway_id ?? reception.gateway_ids?.eui;
    if (typeof id !== 'string' || id.length < 1 || id.length > 128) return [];
    const latitude = number(reception.location?.latitude);
    const longitude = number(reception.location?.longitude);
    const valid = latitude !== null && longitude !== null && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
    return [{
      gateway_id: id,
      rssi: number(reception.rssi) ?? number(reception.channel_rssi),
      snr: number(reception.snr),
      lat: valid ? latitude : null,
      lon: valid ? longitude : null,
      alt: valid ? number(reception.location?.altitude) : null,
    }];
  }).sort((a, b) => (b.rssi ?? -Infinity) - (a.rssi ?? -Infinity));
}

/** TTN owns the network identity; a user-entered callsign never routes an uplink. */
export function createTTNWebhook(dependencies: Dependencies = defaults) {
  return async function ttnWebhook(request: Request): Promise<Response> {
    if (request.method !== 'POST') return response(405, 'Method not allowed');
    const bearer = request.headers.get('authorization')?.match(/^Bearer ([A-Za-z0-9._~+\/-]{32,512})$/i)?.[1];
    if (!bearer) return response(401, 'Unauthorized');
    if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type') ?? '')) {
      return response(415, 'Expected application/json');
    }
    const declaredLength = request.headers.get('content-length');
    if (declaredLength && /^\d+$/.test(declaredLength) && Number(declaredLength) > MAX_BODY_BYTES) {
      return response(413, 'Webhook payload too large');
    }

    let payload: TTNWebhookPayload;
    let applicationId: string;
    let devEui: string;
    try {
      const body = await readRequestBodyWithinLimit(request, MAX_BODY_BYTES);
      if (body === null) return response(413, 'Webhook payload too large');
      const parsed: unknown = JSON.parse(body);
      if (!record(parsed) || !record(parsed.end_device_ids) || !record(parsed.uplink_message)) {
        return response(400, 'Invalid uplink');
      }
      const ids = parsed.end_device_ids;
      applicationId = ids.application_ids?.application_id;
      devEui = ids.dev_eui;
      if (typeof applicationId !== 'string' || !ID.test(applicationId) ||
          typeof ids.device_id !== 'string' || !ID.test(ids.device_id) ||
          typeof devEui !== 'string' || !/^[a-fA-F0-9]{16}$/.test(devEui)) {
        return response(400, 'Missing network identity');
      }
      const uplink = parsed.uplink_message;
      if (uplink.rx_metadata !== undefined && (!Array.isArray(uplink.rx_metadata) || uplink.rx_metadata.some((item: unknown) => !record(item)))) {
        return response(400, 'Invalid receiver metadata');
      }
      // Buffer.from(base64) otherwise accepts truncated/non-base64 strings.
      if (uplink.frm_payload !== undefined &&
          (typeof uplink.frm_payload !== 'string' || uplink.frm_payload.length === 0 ||
           uplink.frm_payload.length > 512 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(uplink.frm_payload))) {
        return response(400, 'Invalid frame bytes');
      }
      if (uplink.decoded_payload !== undefined && !record(uplink.decoded_payload)) return response(400, 'Invalid decoded payload');
      payload = parsed;
    } catch { return response(400, 'Invalid JSON payload'); }

    const identity = parseTTNUplinkIdentity(payload);
    if (!identity) return response(400, 'Invalid uplink identity');
    try {
      const binding = await dependencies.resolveIdentity({
        p_token_hash: createHash('sha256').update(bearer).digest('hex'),
        p_application_id: applicationId,
        p_ttn_device_id: identity.rawDeviceId,
        p_dev_eui: devEui.toUpperCase(),
      });
      if (!binding) return response(401, 'Unauthorized');
      if (!UUID.test(binding.integration_id)) throw new Error('Invalid registry response');
      if (binding.identity_mismatch) return response(401, 'Unauthorized');
      // TTN webhooks cover an application, which can contain unrelated devices.
      // Acknowledge only an explicitly authenticated, unbound identity.
      if (binding.canonical_device_id === null && binding.radio_identity_id === null && binding.identity_mismatch === false) {
        return response(202, { ignored: true });
      }
      if (typeof binding.canonical_device_id !== 'string' || binding.canonical_device_id.length > 80 ||
          typeof binding.radio_identity_id !== 'string' || !UUID.test(binding.radio_identity_id)) {
        throw new Error('Invalid registry response');
      }
      const port = payload.uplink_message!.f_port;
      if (port !== 1 && port !== 11 && port !== 12) return response(400, 'Unsupported uplink port');
      const provenance = {
        integration_id: binding.integration_id,
        radio_identity_id: binding.radio_identity_id,
        ttn_device_id: identity.rawDeviceId,
        dev_addr: identity.devAddr,
        session_key_id: identity.sessionKeyId,
        ttn_received_at: identity.receivedAt,
        f_cnt: identity.frameCounter,
      };
      let table: Table;
      let row: Record<string, unknown>;
      if (port === 11) {
        const event = parseCTTEventPayload(payload);
        if (!event) return response(400, 'Invalid wildlife event');
        table = 'wildlife_detections';
        row = { ...event, ...provenance, device_id: binding.canonical_device_id };
      } else if (port === 12) {
        const event = parseB2BEventPayload(payload);
        if (!event) return response(400, 'Invalid relay event');
        const { device_id: _rawDeviceId, ...values } = event;
        table = 'b2b_packets';
        row = { ...values, ...provenance, gateway_balloon_id: binding.canonical_device_id };
      } else {
        const telemetry = parseTTNPayload(payload);
        if (!telemetry) return response(400, 'Invalid telemetry');
        table = 'telemetry';
        row = {
          ...telemetry, ...provenance, device_id: binding.canonical_device_id,
          frm_payload: payload.uplink_message!.frm_payload ?? null,
          f_port: port,
          gateways: extractGateways(payload.uplink_message!.rx_metadata),
          rx_metadata: payload.uplink_message!.rx_metadata ?? null,
        };
      }
      const { error } = await dependencies.insert(table, row);
      let duplicate = false;
      if (error) {
        if (!isExpectedTTNDeliveryDuplicate(error, duplicateIndexes[table])) return response(503, 'Ingestion unavailable');
        duplicate = true;
      }
      const marked = await dependencies.markReceived(binding.radio_identity_id, identity.receivedAt);
      if (marked.error) return response(503, 'Ingestion unavailable');
      return response(200, { success: true, device_id: binding.canonical_device_id, ...(duplicate ? { duplicate: true } : {}) });
    } catch { return response(503, 'Ingestion unavailable'); }
  };
}

export const ttnWebhook = createTTNWebhook();
