BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
CREATE SCHEMA IF NOT EXISTS community_private;
REVOKE ALL ON SCHEMA community_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA community_private TO service_role;

ALTER TABLE public.devices
 ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES auth.users(id) ON DELETE RESTRICT,
 ADD COLUMN IF NOT EXISTS owner_github text,
 ADD COLUMN IF NOT EXISTS display_name text,
 ADD COLUMN IF NOT EXISTS official boolean NOT NULL DEFAULT false,
 ADD COLUMN IF NOT EXISTS connection_status text NOT NULL DEFAULT 'pending';
UPDATE public.devices SET display_name = coalesce(display_name, device_id), connection_status = 'connected', official = true
 WHERE device_id IN ('stratolink-2','stratolink-3') AND owner_id IS NULL;
ALTER TABLE public.devices DROP CONSTRAINT IF EXISTS devices_status_check;
ALTER TABLE public.devices ADD CONSTRAINT devices_status_check CHECK (status IN ('storage','planned','flying','landed','missing','retired'));
UPDATE public.devices SET status='missing' WHERE device_id='stratolink-2' AND owner_id IS NULL;
ALTER TABLE public.devices ADD CONSTRAINT devices_connection_status_check CHECK (connection_status IN ('pending','connected'));
ALTER TABLE public.devices ADD CONSTRAINT devices_display_name_check CHECK (display_name IS NULL OR display_name ~ '^[A-Za-z0-9][A-Za-z0-9 ._-]{1,39}$');
CREATE INDEX IF NOT EXISTS devices_owner_id_idx ON public.devices(owner_id) WHERE owner_id IS NOT NULL;

CREATE TABLE community_private.balloon_registration (
 device_id text PRIMARY KEY REFERENCES public.devices(device_id) ON DELETE CASCADE,
 dev_eui text NOT NULL CHECK (dev_eui ~ '^[0-9A-F]{16}$')
);
CREATE TABLE community_private.webhook_integrations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 owner_id uuid REFERENCES auth.users(id) ON DELETE RESTRICT,
 provider text NOT NULL DEFAULT 'ttn' CHECK (provider = 'ttn'),
 tenant text NOT NULL DEFAULT 'ttn' CHECK (tenant = 'ttn'),
 cluster text NOT NULL CHECK (cluster IN ('nam1','eu1','au1')),
 application_id text NOT NULL CHECK (application_id ~ '^[a-z0-9](?:[a-z0-9-]{0,34}[a-z0-9])?$'),
 token_hash text NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 revoked_at timestamptz,
 UNIQUE (id,cluster,application_id),
 UNIQUE (token_hash,application_id)
);
CREATE TABLE community_private.radio_identities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 integration_id uuid NOT NULL REFERENCES community_private.webhook_integrations(id) ON DELETE RESTRICT,
 device_id text NOT NULL REFERENCES public.devices(device_id) ON DELETE RESTRICT,
 cluster text NOT NULL CHECK (cluster IN ('nam1','eu1','au1')),
 application_id text NOT NULL,
 ttn_device_id text NOT NULL CHECK (ttn_device_id ~ '^[a-z0-9](?:[a-z0-9-]{0,34}[a-z0-9])?$'),
 dev_eui text NOT NULL CHECK (dev_eui ~ '^[0-9A-F]{16}$'),
 region text NOT NULL,
 verified_at timestamptz NOT NULL DEFAULT now(),
 last_received_at timestamptz,
 UNIQUE (cluster, application_id, ttn_device_id),
 UNIQUE (cluster, application_id, dev_eui),
 FOREIGN KEY (integration_id,cluster,application_id) REFERENCES community_private.webhook_integrations(id,cluster,application_id)
);
CREATE INDEX radio_identities_device_idx ON community_private.radio_identities(device_id);
CREATE INDEX radio_identities_integration_idx ON community_private.radio_identities(integration_id);
CREATE TABLE community_private.rate_limits (
 owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 action text NOT NULL,
 window_start timestamptz NOT NULL,
 count integer NOT NULL CHECK (count > 0),
 PRIMARY KEY(owner_id, action)
);
ALTER TABLE community_private.balloon_registration ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_private.webhook_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_private.radio_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_private.rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA community_private FROM PUBLIC, anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA community_private TO service_role;

CREATE FUNCTION community_private.balloon_json(p_device_id text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT jsonb_build_object('id',d.device_id,'callsign',d.display_name,
   'status',CASE WHEN d.status='storage' THEN 'planned' ELSE d.status END,
   'devEui',r.dev_eui,'ownerId',d.owner_id,'ownerGithub',d.owner_github,
   'registeredAt',d.created_at,'launchedAt',CASE WHEN d.launched_at IS NULL THEN NULL ELSE extract(epoch FROM d.launched_at)*1000 END,
   'connectionStatus',d.connection_status,'connections',coalesce((
     SELECT jsonb_agg(jsonb_build_object('id',i.id,'cluster',i.cluster,'applicationId',i.application_id,
       'devEui',i.dev_eui,'region',i.region,'connectedAt',i.verified_at,'lastReceivedAt',i.last_received_at) ORDER BY i.verified_at)
     FROM community_private.radio_identities i JOIN community_private.webhook_integrations w ON w.id=i.integration_id
     WHERE i.device_id=d.device_id AND w.revoked_at IS NULL
   ),'[]'::jsonb))
 FROM public.devices d JOIN community_private.balloon_registration r ON r.device_id=d.device_id WHERE d.device_id=p_device_id;
$$;
CREATE FUNCTION public.community_account(p_owner_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT coalesce(jsonb_agg(community_private.balloon_json(d.device_id) ORDER BY d.created_at DESC),'[]'::jsonb)
 FROM public.devices d WHERE d.owner_id=p_owner_id;
$$;
CREATE FUNCTION public.community_rate_limit(p_owner_id uuid,p_action text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE c integer;
BEGIN
 INSERT INTO community_private.rate_limits(owner_id,action,window_start,count) VALUES(p_owner_id,p_action,now(),1)
 ON CONFLICT(owner_id,action) DO UPDATE SET
 count=CASE WHEN community_private.rate_limits.window_start < now()-interval '1 minute' THEN 1 ELSE community_private.rate_limits.count+1 END,
 window_start=CASE WHEN community_private.rate_limits.window_start < now()-interval '1 minute' THEN now() ELSE community_private.rate_limits.window_start END
 RETURNING count INTO c;
 RETURN c <= CASE WHEN p_action='connect' THEN 5 WHEN p_action='register' THEN 5 ELSE 30 END;
END;
$$;
CREATE FUNCTION public.register_community_balloon(p_owner_id uuid,p_github_login text,p_callsign text,p_dev_eui text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE new_id text;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_owner_id::text,0));
 IF (SELECT count(*) FROM public.devices WHERE owner_id=p_owner_id)>=50 THEN RAISE EXCEPTION 'Registration limit reached' USING ERRCODE='P0001'; END IF;
 IF EXISTS(SELECT 1 FROM public.devices d JOIN community_private.balloon_registration r USING(device_id) WHERE d.owner_id=p_owner_id AND r.dev_eui=p_dev_eui) THEN
   RAISE EXCEPTION 'Device already registered' USING ERRCODE='23505';
 END IF;
 new_id := 'balloon-' || gen_random_uuid()::text;
 INSERT INTO public.devices(device_id,owner_id,owner_github,display_name,status,official,connection_status)
 VALUES(new_id,p_owner_id,p_github_login,p_callsign,'planned',false,'pending');
 INSERT INTO community_private.balloon_registration(device_id,dev_eui) VALUES(new_id,p_dev_eui);
 RETURN community_private.balloon_json(new_id);
END;
$$;
CREATE FUNCTION public.update_community_balloon(p_owner_id uuid,p_device_id text,p_status text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
 IF p_status NOT IN ('planned','flying','landed','missing','retired') THEN RAISE EXCEPTION 'Invalid status' USING ERRCODE='22023'; END IF;
 UPDATE public.devices SET status=p_status,
   launched_at=CASE WHEN p_status='flying' AND launched_at IS NULL THEN now() ELSE launched_at END
 WHERE device_id=p_device_id AND owner_id=p_owner_id;
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN community_private.balloon_json(p_device_id);
END;
$$;
CREATE FUNCTION public.connect_community_radio(p_owner_id uuid,p_device_id text,p_cluster text,p_application_id text,p_ttn_device_id text,p_dev_eui text,p_region text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE new_integration uuid; old_identity community_private.radio_identities%ROWTYPE;
BEGIN
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND owner_id=p_owner_id FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF (SELECT count(*) FROM community_private.radio_identities WHERE device_id=p_device_id)>=8
   AND NOT EXISTS(SELECT 1 FROM community_private.radio_identities WHERE device_id=p_device_id AND cluster=p_cluster AND application_id=p_application_id AND ttn_device_id=p_ttn_device_id)
 THEN RAISE EXCEPTION 'Regional connection limit reached' USING ERRCODE='P0001'; END IF;
 SELECT * INTO old_identity FROM community_private.radio_identities
 WHERE cluster=p_cluster AND application_id=p_application_id AND (ttn_device_id=p_ttn_device_id OR dev_eui=p_dev_eui) FOR UPDATE;
 IF FOUND AND old_identity.device_id<>p_device_id THEN RAISE EXCEPTION 'Device already connected' USING ERRCODE='23505'; END IF;
 INSERT INTO community_private.webhook_integrations(owner_id,cluster,application_id,token_hash)
 VALUES(p_owner_id,p_cluster,p_application_id,p_token_hash) RETURNING id INTO new_integration;
 IF old_identity.id IS NOT NULL THEN
   UPDATE community_private.webhook_integrations SET revoked_at=now() WHERE id=old_identity.integration_id;
   UPDATE community_private.radio_identities SET integration_id=new_integration,ttn_device_id=p_ttn_device_id,dev_eui=p_dev_eui,region=p_region,verified_at=now(),last_received_at=NULL
    WHERE id=old_identity.id;
 ELSE
   INSERT INTO community_private.radio_identities(integration_id,device_id,cluster,application_id,ttn_device_id,dev_eui,region)
    VALUES(new_integration,p_device_id,p_cluster,p_application_id,p_ttn_device_id,p_dev_eui,p_region);
 END IF;
 RETURN community_private.balloon_json(p_device_id);
END;
$$;
CREATE FUNCTION public.resolve_ttn_ingress(p_token_hash text,p_application_id text,p_ttn_device_id text,p_dev_eui text)
RETURNS TABLE(canonical_device_id text,integration_id uuid,radio_identity_id uuid,owner_id uuid,identity_mismatch boolean)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT CASE WHEN r.ttn_device_id=p_ttn_device_id AND r.dev_eui=upper(p_dev_eui) AND r.verified_at IS NOT NULL THEN r.device_id END,
   w.id,
   CASE WHEN r.ttn_device_id=p_ttn_device_id AND r.dev_eui=upper(p_dev_eui) AND r.verified_at IS NOT NULL THEN r.id END,
   w.owner_id,
   r.id IS NOT NULL AND NOT (r.ttn_device_id=p_ttn_device_id AND r.dev_eui=upper(p_dev_eui) AND r.verified_at IS NOT NULL)
 FROM community_private.webhook_integrations w
 LEFT JOIN community_private.radio_identities r ON r.integration_id=w.id AND r.application_id=w.application_id AND r.cluster=w.cluster
   AND (r.ttn_device_id=p_ttn_device_id OR r.dev_eui=upper(p_dev_eui))
 WHERE w.token_hash=p_token_hash AND w.revoked_at IS NULL AND w.application_id=p_application_id;
$$;
CREATE FUNCTION public.mark_radio_received(p_radio_identity_id uuid,p_received_at timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE canonical_id text;
BEGIN
 UPDATE community_private.radio_identities r SET last_received_at=greatest(r.last_received_at,p_received_at)
 FROM community_private.webhook_integrations w WHERE r.id=p_radio_identity_id AND w.id=r.integration_id AND w.revoked_at IS NULL
 RETURNING r.device_id INTO canonical_id;
 IF canonical_id IS NULL THEN RAISE EXCEPTION 'Connection unavailable' USING ERRCODE='P0001'; END IF;
 UPDATE public.devices SET connection_status='connected' WHERE device_id=canonical_id;
END;
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA community_private FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA community_private TO service_role;
REVOKE ALL ON FUNCTION public.community_account(uuid),public.community_rate_limit(uuid,text),public.register_community_balloon(uuid,text,text,text),public.update_community_balloon(uuid,text,text),public.connect_community_radio(uuid,text,text,text,text,text,text,text),public.resolve_ttn_ingress(text,text,text,text),public.mark_radio_received(uuid,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.community_account(uuid),public.community_rate_limit(uuid,text),public.register_community_balloon(uuid,text,text,text),public.update_community_balloon(uuid,text,text),public.connect_community_radio(uuid,text,text,text,text,text,text,text),public.resolve_ttn_ingress(text,text,text,text),public.mark_radio_received(uuid,timestamptz) TO service_role;

-- Keep the deployed dashboard's six-column device query working at cutover.
-- Owner UUIDs and pending registrations never enter the anonymous read surface.
REVOKE SELECT ON public.devices FROM PUBLIC,anon,authenticated;
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='devices' LOOP
   EXECUTE format('REVOKE SELECT (%I) ON public.devices FROM PUBLIC,anon,authenticated',c.column_name);
 END LOOP;
END $$;
GRANT SELECT(device_id,launcher_name,status,launch_lat,launch_lon,launched_at) ON public.devices TO anon,authenticated;
DROP POLICY IF EXISTS "Allow public read access" ON public.devices;
DROP POLICY IF EXISTS "Allow public read" ON public.devices;
CREATE POLICY "Read connected devices" ON public.devices FOR SELECT TO anon,authenticated USING(connection_status='connected');
-- Keep telemetry reads working until the new public API is deployed.
-- No browser client is allowed to write flight records directly.
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.devices,public.telemetry,public.uplink_events FROM PUBLIC,anon,authenticated;
DROP POLICY IF EXISTS "Allow insert for activation" ON public.devices;
DROP POLICY IF EXISTS "Allow update for activation" ON public.devices;
DROP POLICY IF EXISTS "Allow insert from service role" ON public.telemetry;
ALTER VIEW public.latest_telemetry SET (security_invoker=true);
ALTER FUNCTION public.update_devices_updated_at() SET search_path = public,pg_temp;
ALTER FUNCTION public.get_active_balloons(integer) SET search_path = public,pg_temp;
COMMIT;
