-- Synthetic baseline with the columns observed before this migration.
-- No real telemetry, account information or credentials are included.
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE TABLE auth.identities (user_id uuid REFERENCES auth.users(id), provider text NOT NULL, provider_id text NOT NULL, UNIQUE(provider,provider_id));
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

CREATE TABLE public.devices (
    "id" bigserial PRIMARY KEY,
    "device_id" text NOT NULL UNIQUE,
    "created_at" timestamptz DEFAULT now(),
    "updated_at" timestamptz DEFAULT now(),
    "claim_code" text,
    "status" text DEFAULT 'storage'::text,
    "launcher_name" text,
    "launch_lat" float8,
    "launch_lon" float8,
    "launched_at" timestamptz,
    "launch_token_hash" text,
    "launch_token_expires_at" timestamptz
);

ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE public.devices TO anon, authenticated, service_role;
CREATE POLICY "Allow public read access" ON public.devices FOR SELECT USING (true);

CREATE TABLE public.telemetry (
    "id" uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    "device_id" text NOT NULL,
    "time" timestamptz NOT NULL DEFAULT now(),
    "lat" float8,
    "lon" float8,
    "altitude_m" float8,
    "velocity_x" float8,
    "velocity_y" float8,
    "created_at" timestamptz DEFAULT now(),
    "uv_index" int4,
    "ambient_lux" float8,
    "acoustic_event" int2,
    "temperature" float8,
    "pressure" float8,
    "solar_voltage" float8,
    "battery_voltage" float8,
    "rssi" float8,
    "snr" float8,
    "gps_speed" float8,
    "gps_heading" float8,
    "gps_satellites" int4,
    "mems_accel_x" float8,
    "mems_accel_y" float8,
    "mems_accel_z" float8,
    "firmware_version" text,
    "uptime_s" int4,
    "tx_count" int4,
    "hdop" float4,
    "power_mode" text,
    "sleep_ms" int4,
    "lora_sf" int4,
    "lora_bw" int4,
    "frequency_hz" int8,
    "gateways" jsonb,
    "f_port" int2,
    "frm_payload" text,
    "telemetry_version" int2,
    "status_byte" int2,
    "boot_count" int2,
    "power_tier" int2,
    "reset_cause" int2,
    "gps_fix_age_min" int4,
    "command_ack_seq" int4,
    "relay_enabled" bool,
    "relay_fwd_delta" int2,
    "ctt_tags_delta" int2
);

ALTER TABLE public.telemetry ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE public.telemetry TO anon, authenticated, service_role;
CREATE POLICY "Allow public read access" ON public.telemetry FOR SELECT USING (true);

CREATE TABLE public.uplink_events (
    "id" uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    "device_id" text NOT NULL,
    "time" timestamptz NOT NULL,
    "f_port" int2 NOT NULL,
    "frm_payload" text,
    "rssi" float8,
    "snr" float8,
    "gateways" jsonb,
    "created_at" timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.uplink_events ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE public.uplink_events TO anon, authenticated, service_role;
CREATE POLICY "Allow public read access" ON public.uplink_events FOR SELECT USING (true);

GRANT ALL ON SEQUENCE public.devices_id_seq TO anon,authenticated,service_role;
CREATE POLICY "Allow insert from service role" ON public.telemetry FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert for activation" ON public.devices FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow update for activation" ON public.devices FOR UPDATE USING (true) WITH CHECK (true);
CREATE FUNCTION public.update_devices_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN NEW.updated_at=now(); RETURN NEW; END$$;
CREATE TRIGGER devices_updated_at_trigger BEFORE UPDATE ON public.devices FOR EACH ROW EXECUTE FUNCTION public.update_devices_updated_at();
CREATE VIEW public.latest_telemetry AS SELECT DISTINCT ON(device_id) id,device_id,time,lat,lon,altitude_m,velocity_x,velocity_y,created_at FROM public.telemetry ORDER BY device_id,time DESC;
GRANT ALL ON public.latest_telemetry TO anon,authenticated,service_role;
CREATE FUNCTION public.get_active_balloons(hours_ago integer DEFAULT 1)
RETURNS TABLE(device_id text,lat float8,lon float8,altitude_m float8,last_seen timestamptz)
LANGUAGE sql AS $$ SELECT t.device_id,t.lat,t.lon,t.altitude_m,t.time FROM public.telemetry t WHERE t.time>now()-hours_ago*interval '1 hour' $$;
-- Synthetic stand-ins exercise cutover grants without requiring PostGIS.
CREATE TABLE public.spatial_ref_sys(srid integer);
GRANT ALL ON public.spatial_ref_sys TO anon,authenticated,service_role;
CREATE FUNCTION public.st_estimatedextent(text,text) RETURNS text LANGUAGE sql SECURITY DEFINER AS $$SELECT 'test'::text$$;
INSERT INTO public.devices(device_id,status) VALUES ('stratolink-2','flying'),('stratolink-3','flying');
INSERT INTO public.telemetry(id,device_id,time,lat,lon,altitude_m,telemetry_version)
SELECT md5(g::text)::uuid,CASE WHEN g%2=0 THEN 'stratolink-2' ELSE 'stratolink-3' END,
'2026-05-17 12:00:00Z'::timestamptz+g*interval '1 minute',10,20,1000,2 FROM generate_series(1,1513) g;
CREATE SCHEMA test_audit;
CREATE TABLE test_audit.original_telemetry AS SELECT id,to_jsonb(t) AS row FROM public.telemetry t;
