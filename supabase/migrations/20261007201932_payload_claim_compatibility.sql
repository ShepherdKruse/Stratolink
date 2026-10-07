BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- A callsign can be reserved before staff verifies its physical radio.
ALTER TABLE community_private.balloon_registration ALTER COLUMN dev_eui DROP NOT NULL;

-- Legacy PINs and launch-token hashes were client-writable. They are retained
-- as historical fields, but never accepted as account ownership evidence.
CREATE TABLE community_private.payload_claims (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 device_id text NOT NULL REFERENCES public.devices(device_id) ON DELETE RESTRICT,
 dev_eui text NOT NULL CHECK (dev_eui ~ '^[0-9A-F]{16}$' AND dev_eui <> '0000000000000000'),
 token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
 issued_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
 issued_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now() + interval '7 days',
 revoked_at timestamptz,
 consumed_at timestamptz,
 consumed_by uuid REFERENCES auth.users(id) ON DELETE RESTRICT,
 CHECK (expires_at > issued_at AND expires_at <= issued_at + interval '7 days'),
 CHECK ((consumed_at IS NULL) = (consumed_by IS NULL))
);
CREATE UNIQUE INDEX payload_claims_one_pending_per_device ON community_private.payload_claims(device_id)
 WHERE revoked_at IS NULL AND consumed_at IS NULL;
CREATE INDEX payload_claims_issuer_idx ON community_private.payload_claims(issued_by);
CREATE INDEX payload_claims_consumer_idx ON community_private.payload_claims(consumed_by) WHERE consumed_by IS NOT NULL;
ALTER TABLE community_private.payload_claims ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON community_private.payload_claims FROM PUBLIC, anon, authenticated;
GRANT ALL ON community_private.payload_claims TO service_role;

CREATE OR REPLACE FUNCTION community_private.balloon_json(p_device_id text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT jsonb_build_object('id',d.device_id,'callsign',coalesce(d.display_name,d.device_id),
   'status',CASE WHEN d.status='storage' THEN 'planned' ELSE d.status END,
   'devEui',r.dev_eui,'ownerId',d.owner_id,'ownerGithub',d.owner_github,
   'registeredAt',d.created_at,'launchedAt',CASE WHEN d.launched_at IS NULL THEN NULL ELSE extract(epoch FROM d.launched_at)*1000 END,
   'connectionStatus',d.connection_status,'connections',coalesce((
     SELECT jsonb_agg(jsonb_build_object('id',i.id,'cluster',i.cluster,'applicationId',i.application_id,
       'devEui',i.dev_eui,'region',i.region,'connectedAt',i.verified_at,'lastReceivedAt',i.last_received_at,
       'managedBy',CASE WHEN w.owner_id=d.owner_id AND
         (SELECT count(*) FROM community_private.radio_identities shared WHERE shared.integration_id=w.id)=1
         THEN 'owner' ELSE 'stratolink' END) ORDER BY i.verified_at)
     FROM community_private.radio_identities i JOIN community_private.webhook_integrations w ON w.id=i.integration_id
     WHERE i.device_id=d.device_id AND w.revoked_at IS NULL
   ),'[]'::jsonb))
 FROM public.devices d LEFT JOIN community_private.balloon_registration r ON r.device_id=d.device_id WHERE d.device_id=p_device_id;
$$;

CREATE OR REPLACE FUNCTION public.community_rate_limit(p_owner_id uuid,p_action text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE c integer;
BEGIN
 INSERT INTO community_private.rate_limits(owner_id,action,window_start,count) VALUES(p_owner_id,p_action,now(),1)
 ON CONFLICT(owner_id,action) DO UPDATE SET
 count=CASE WHEN community_private.rate_limits.window_start < now()-interval '1 minute' THEN 1 ELSE community_private.rate_limits.count+1 END,
 window_start=CASE WHEN community_private.rate_limits.window_start < now()-interval '1 minute' THEN now() ELSE community_private.rate_limits.window_start END
 RETURNING count INTO c;
 RETURN c <= CASE WHEN p_action IN ('connect','register','claim','reserve','issue') THEN 5 ELSE 30 END;
END;
$$;

CREATE FUNCTION public.reserve_community_payload(p_owner_id uuid,p_github_login text,p_callsign text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
 IF p_owner_id IS NULL OR p_github_login IS NULL OR p_github_login !~* '^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$'
   OR p_callsign IS NULL OR length(p_callsign) NOT BETWEEN 3 AND 36 OR p_callsign !~ '^[a-z0-9](?:-?[a-z0-9]){2,35}$'
 THEN RAISE EXCEPTION 'Invalid reservation' USING ERRCODE='22023'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_owner_id::text,0));
 IF (SELECT count(*) FROM public.devices WHERE owner_id=p_owner_id)>=50 THEN RAISE EXCEPTION 'Registration limit reached' USING ERRCODE='P0001'; END IF;
 INSERT INTO public.devices(device_id,owner_id,owner_github,display_name,status,official,connection_status)
 VALUES(p_callsign,p_owner_id,p_github_login,p_callsign,'storage',false,'pending');
 INSERT INTO community_private.balloon_registration(device_id,dev_eui) VALUES(p_callsign,NULL);
 RETURN community_private.balloon_json(p_callsign);
END;
$$;

-- Only the server's independently authorized staff endpoint may call this.
-- The EUI must already be attested by a private registration or verified radio.
CREATE FUNCTION public.issue_payload_claim(p_issuer_id uuid,p_device_id text,p_dev_eui text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE expires timestamptz;
BEGIN
 IF p_issuer_id IS NULL OR p_dev_eui IS NULL OR p_dev_eui !~ '^[0-9A-F]{16}$' OR p_dev_eui='0000000000000000'
   OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'Invalid claim proof' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND owner_id IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF NOT EXISTS(SELECT 1 FROM community_private.balloon_registration WHERE device_id=p_device_id AND dev_eui=p_dev_eui)
   AND NOT EXISTS(SELECT 1 FROM community_private.radio_identities r JOIN community_private.webhook_integrations w ON w.id=r.integration_id
     WHERE r.device_id=p_device_id AND r.dev_eui=p_dev_eui AND r.verified_at IS NOT NULL AND w.revoked_at IS NULL)
 THEN RAISE EXCEPTION 'Radio identity has not been verified' USING ERRCODE='55000'; END IF;
 UPDATE community_private.payload_claims SET revoked_at=now()
 WHERE device_id=p_device_id AND revoked_at IS NULL AND consumed_at IS NULL;
 INSERT INTO community_private.payload_claims(device_id,dev_eui,token_hash,issued_by)
 VALUES(p_device_id,p_dev_eui,p_token_hash,p_issuer_id) RETURNING expires_at INTO expires;
 RETURN jsonb_build_object('deviceId',p_device_id,'expiresAt',expires);
END;
$$;

CREATE FUNCTION public.claim_existing_payload(p_owner_id uuid,p_github_login text,p_device_id text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE proof community_private.payload_claims%ROWTYPE;
BEGIN
 IF p_owner_id IS NULL OR p_github_login IS NULL OR p_github_login !~* '^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$'
   OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_owner_id::text,0));
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND owner_id IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO proof FROM community_private.payload_claims
 WHERE device_id=p_device_id AND token_hash=p_token_hash AND revoked_at IS NULL AND consumed_at IS NULL AND expires_at>clock_timestamp() FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF (SELECT count(*) FROM public.devices WHERE owner_id=p_owner_id)>=50 THEN RAISE EXCEPTION 'Registration limit reached' USING ERRCODE='P0001'; END IF;
 -- Preserve a primary registration when the claim used another verified region.
 INSERT INTO community_private.balloon_registration(device_id,dev_eui) VALUES(p_device_id,proof.dev_eui)
 ON CONFLICT(device_id) DO UPDATE SET dev_eui=coalesce(community_private.balloon_registration.dev_eui,EXCLUDED.dev_eui);
 UPDATE public.devices SET owner_id=p_owner_id,owner_github=p_github_login WHERE device_id=p_device_id;
 UPDATE community_private.payload_claims SET consumed_at=now(),consumed_by=p_owner_id WHERE id=proof.id;
 RETURN community_private.balloon_json(p_device_id);
END;
$$;

CREATE FUNCTION public.staff_payload_inventory() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT jsonb_build_object('payloads',coalesce((
   SELECT jsonb_agg(jsonb_build_object('deviceId',d.device_id,'callsign',coalesce(d.display_name,d.device_id),
     'launcherName',d.launcher_name,'status',d.status,'owned',d.owner_id IS NOT NULL,
     'devEui',r.dev_eui,'connectionStatus',d.connection_status,'connections',coalesce((
       SELECT jsonb_agg(jsonb_build_object('id',i.id,'integrationId',i.integration_id,'cluster',i.cluster,
         'applicationId',i.application_id,'deviceId',i.ttn_device_id,'devEui',i.dev_eui,'region',i.region) ORDER BY i.verified_at)
       FROM community_private.radio_identities i JOIN community_private.webhook_integrations w ON w.id=i.integration_id
       WHERE i.device_id=d.device_id AND w.revoked_at IS NULL
     ),'[]'::jsonb)) ORDER BY d.created_at,d.device_id)
   FROM public.devices d LEFT JOIN community_private.balloon_registration r ON r.device_id=d.device_id
 ),'[]'::jsonb),'integrations',coalesce((
   SELECT jsonb_agg(jsonb_build_object('id',w.id,'cluster',w.cluster,'applicationId',w.application_id) ORDER BY w.cluster,w.application_id)
   FROM community_private.webhook_integrations w WHERE w.owner_id IS NULL AND w.revoked_at IS NULL
 ),'[]'::jsonb));
$$;

-- The API has already read this exact identity from TTN. Bind it to an existing
-- staff integration without rotating its token or touching another payload.
CREATE FUNCTION public.bind_staff_payload_radio(p_device_id text,p_integration_id uuid,p_cluster text,p_application_id text,p_ttn_device_id text,p_dev_eui text,p_region text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
 IF p_dev_eui IS NULL OR p_dev_eui !~ '^[0-9A-F]{16}$' OR p_dev_eui='0000000000000000'
   OR p_region IS NULL OR p_region !~ '^[A-Z0-9_-]{1,80}$'
 THEN RAISE EXCEPTION 'Invalid radio identity' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM 1 FROM community_private.webhook_integrations
 WHERE id=p_integration_id AND cluster=p_cluster AND application_id=p_application_id AND owner_id IS NULL AND revoked_at IS NULL FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Shared integration unavailable' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM community_private.radio_identities
 WHERE cluster=p_cluster AND application_id=p_application_id AND (ttn_device_id=p_ttn_device_id OR dev_eui=p_dev_eui) FOR UPDATE;
 IF EXISTS(SELECT 1 FROM community_private.radio_identities WHERE cluster=p_cluster AND application_id=p_application_id
   AND (ttn_device_id=p_ttn_device_id OR dev_eui=p_dev_eui)
   AND (device_id<>p_device_id OR integration_id<>p_integration_id OR ttn_device_id<>p_ttn_device_id OR dev_eui<>p_dev_eui))
 THEN RAISE EXCEPTION 'Radio identity already bound' USING ERRCODE='23505'; END IF;
 IF NOT EXISTS(SELECT 1 FROM community_private.radio_identities WHERE cluster=p_cluster AND application_id=p_application_id AND ttn_device_id=p_ttn_device_id) THEN
   IF (SELECT count(*) FROM community_private.radio_identities WHERE device_id=p_device_id)>=8 THEN RAISE EXCEPTION 'Regional connection limit reached' USING ERRCODE='P0001'; END IF;
   INSERT INTO community_private.radio_identities(integration_id,device_id,cluster,application_id,ttn_device_id,dev_eui,region)
   VALUES(p_integration_id,p_device_id,p_cluster,p_application_id,p_ttn_device_id,p_dev_eui,p_region);
 END IF;
 INSERT INTO community_private.balloon_registration(device_id,dev_eui) VALUES(p_device_id,p_dev_eui)
 ON CONFLICT(device_id) DO UPDATE SET dev_eui=coalesce(community_private.balloon_registration.dev_eui,EXCLUDED.dev_eui);
 RETURN community_private.balloon_json(p_device_id);
END;
$$;

-- An owner may rotate their own dedicated connection, never an integration
-- shared with another payload or maintained by staff.
CREATE OR REPLACE FUNCTION public.connect_community_radio(p_owner_id uuid,p_device_id text,p_cluster text,p_application_id text,p_ttn_device_id text,p_dev_eui text,p_region text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE new_integration uuid; old_identity community_private.radio_identities%ROWTYPE; old_integration community_private.webhook_integrations%ROWTYPE;
BEGIN
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND owner_id=p_owner_id FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF (SELECT count(*) FROM community_private.radio_identities WHERE device_id=p_device_id)>=8
   AND NOT EXISTS(SELECT 1 FROM community_private.radio_identities WHERE device_id=p_device_id AND cluster=p_cluster AND application_id=p_application_id AND ttn_device_id=p_ttn_device_id)
 THEN RAISE EXCEPTION 'Regional connection limit reached' USING ERRCODE='P0001'; END IF;
 SELECT * INTO old_identity FROM community_private.radio_identities
 WHERE cluster=p_cluster AND application_id=p_application_id AND (ttn_device_id=p_ttn_device_id OR dev_eui=p_dev_eui) FOR UPDATE;
 IF FOUND AND old_identity.device_id<>p_device_id THEN RAISE EXCEPTION 'Device already connected' USING ERRCODE='23505'; END IF;
 IF old_identity.id IS NOT NULL THEN
   SELECT * INTO old_integration FROM community_private.webhook_integrations WHERE id=old_identity.integration_id FOR UPDATE;
   IF old_integration.owner_id IS DISTINCT FROM p_owner_id
     OR (SELECT count(*) FROM community_private.radio_identities WHERE integration_id=old_identity.integration_id)>1
   THEN RAISE EXCEPTION 'This connection is managed by Stratolink' USING ERRCODE='55000'; END IF;
 END IF;
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
 INSERT INTO community_private.balloon_registration(device_id,dev_eui) VALUES(p_device_id,p_dev_eui)
 ON CONFLICT(device_id) DO UPDATE SET dev_eui=coalesce(community_private.balloon_registration.dev_eui,EXCLUDED.dev_eui);
 RETURN community_private.balloon_json(p_device_id);
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_community_payload(uuid,text,text),public.issue_payload_claim(uuid,text,text,text),
 public.claim_existing_payload(uuid,text,text,text),public.staff_payload_inventory(),public.bind_staff_payload_radio(text,uuid,text,text,text,text,text)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_community_payload(uuid,text,text),public.issue_payload_claim(uuid,text,text,text),
 public.claim_existing_payload(uuid,text,text,text),public.staff_payload_inventory(),public.bind_staff_payload_radio(text,uuid,text,text,text,text,text)
 TO service_role;
COMMIT;
