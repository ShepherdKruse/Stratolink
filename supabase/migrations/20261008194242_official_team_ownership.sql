BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- GitHub numeric IDs are stable across username changes. Only the authenticated
-- server may associate one with a Supabase user after auth.getUser succeeds.
CREATE TABLE community_private.official_team_members (
 github_id text PRIMARY KEY CHECK (github_id ~ '^[0-9]{1,20}$'),
 github_login text NOT NULL UNIQUE,
 user_id uuid UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL
);
CREATE TABLE community_private.team_balloons (
 device_id text PRIMARY KEY REFERENCES public.devices(device_id) ON DELETE CASCADE
);
ALTER TABLE community_private.official_team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_private.team_balloons ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON community_private.official_team_members, community_private.team_balloons FROM PUBLIC,anon,authenticated;
GRANT ALL ON community_private.official_team_members, community_private.team_balloons TO service_role;
INSERT INTO community_private.official_team_members(github_id,github_login) VALUES
 ('48384497','Twarner491'),('13071901','clkruse'),('22897970','ShepherdKruse');
-- Seed accounts that have already signed in without hardcoding auth UUIDs.
UPDATE community_private.official_team_members m SET user_id=i.user_id
 FROM auth.identities i WHERE i.provider='github' AND i.provider_id=m.github_id;
INSERT INTO community_private.team_balloons(device_id)
 SELECT device_id FROM public.devices WHERE device_id IN ('stratolink-2','stratolink-3')
 OR owner_id IN (SELECT user_id FROM community_private.official_team_members);
UPDATE public.devices SET official=true WHERE NOT official AND device_id IN (SELECT device_id FROM community_private.team_balloons);

CREATE FUNCTION community_private.is_team_member(p_user_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM community_private.official_team_members WHERE user_id=p_user_id);
$$;
CREATE FUNCTION community_private.can_manage_balloon(p_user_id uuid,p_device_id text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.devices d WHERE d.device_id=p_device_id AND
   (d.owner_id=p_user_id OR (community_private.is_team_member(p_user_id) AND
     EXISTS(SELECT 1 FROM community_private.team_balloons t WHERE t.device_id=d.device_id))));
$$;

-- This service-only RPC accepts the provider ID read from the verified GitHub
-- identity, never a request body, user_metadata, a display name, or an email.
CREATE FUNCTION public.sync_official_team_member(p_user_id uuid,p_github_id text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_user_id IS NULL OR p_github_id IS NULL OR p_github_id !~ '^[0-9]{1,20}$'
 THEN RAISE EXCEPTION 'Invalid GitHub identity' USING ERRCODE='22023'; END IF;
 UPDATE community_private.official_team_members SET user_id=NULL
 WHERE user_id=p_user_id AND github_id<>p_github_id;
 UPDATE community_private.official_team_members SET user_id=p_user_id
 WHERE github_id=p_github_id AND user_id IS DISTINCT FROM p_user_id;
 RETURN community_private.is_team_member(p_user_id);
END;
$$;

CREATE FUNCTION community_private.share_official_balloon() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF community_private.is_team_member(NEW.owner_id) THEN
   INSERT INTO community_private.team_balloons(device_id) VALUES(NEW.device_id) ON CONFLICT DO NOTHING;
   UPDATE public.devices SET official=true WHERE device_id=NEW.device_id AND NOT official;
 END IF;
 RETURN NULL;
END;
$$;
CREATE TRIGGER share_official_balloon AFTER INSERT OR UPDATE OF owner_id ON public.devices
 FOR EACH ROW EXECUTE FUNCTION community_private.share_official_balloon();

CREATE OR REPLACE FUNCTION community_private.balloon_json(p_device_id text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT jsonb_build_object('id',d.device_id,'callsign',coalesce(d.display_name,d.device_id),
   'status',CASE WHEN d.status='storage' THEN 'planned' ELSE d.status END,
   'devEui',r.dev_eui,'ownerId',d.owner_id,'ownerGithub',d.owner_github,
   'official',d.official,'sharedWith',CASE WHEN EXISTS(SELECT 1 FROM community_private.team_balloons t WHERE t.device_id=d.device_id)
     THEN (SELECT jsonb_agg(m.github_login ORDER BY m.github_login) FROM community_private.official_team_members m) ELSE '[]'::jsonb END,
   'registeredAt',d.created_at,'launchedAt',CASE WHEN d.launched_at IS NULL THEN NULL ELSE extract(epoch FROM d.launched_at)*1000 END,
   'connectionStatus',d.connection_status,'connections',coalesce((
     SELECT jsonb_agg(jsonb_build_object('id',i.id,'cluster',i.cluster,'applicationId',i.application_id,
       'devEui',i.dev_eui,'region',i.region,'connectedAt',i.verified_at,'lastReceivedAt',i.last_received_at,
       'managedBy',CASE WHEN (w.owner_id=d.owner_id OR (community_private.is_team_member(w.owner_id) AND
         EXISTS(SELECT 1 FROM community_private.team_balloons t WHERE t.device_id=d.device_id))) AND
         (SELECT count(*) FROM community_private.radio_identities shared WHERE shared.integration_id=w.id)=1
         THEN 'owner' ELSE 'stratolink' END) ORDER BY i.verified_at)
     FROM community_private.radio_identities i JOIN community_private.webhook_integrations w ON w.id=i.integration_id
     WHERE i.device_id=d.device_id AND w.revoked_at IS NULL
   ),'[]'::jsonb))
 FROM public.devices d LEFT JOIN community_private.balloon_registration r ON r.device_id=d.device_id WHERE d.device_id=p_device_id;
$$;

CREATE OR REPLACE FUNCTION public.community_account(p_owner_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT coalesce(jsonb_agg(community_private.balloon_json(d.device_id) ORDER BY d.created_at DESC),'[]'::jsonb)
 FROM public.devices d WHERE community_private.can_manage_balloon(p_owner_id,d.device_id);
$$;

CREATE OR REPLACE FUNCTION public.update_community_balloon(p_owner_id uuid,p_device_id text,p_status text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
 IF p_status NOT IN ('planned','flying','landed','missing','retired') THEN RAISE EXCEPTION 'Invalid status' USING ERRCODE='22023'; END IF;
 UPDATE public.devices SET status=p_status,
   launched_at=CASE WHEN p_status='flying' AND launched_at IS NULL THEN now() ELSE launched_at END
 WHERE device_id=p_device_id AND community_private.can_manage_balloon(p_owner_id,p_device_id);
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN community_private.balloon_json(p_device_id);
END;
$$;

CREATE OR REPLACE FUNCTION public.connect_community_radio(p_owner_id uuid,p_device_id text,p_cluster text,p_application_id text,p_ttn_device_id text,p_dev_eui text,p_region text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE new_integration uuid; old_identity community_private.radio_identities%ROWTYPE; old_integration community_private.webhook_integrations%ROWTYPE;
BEGIN
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND community_private.can_manage_balloon(p_owner_id,p_device_id) FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF (SELECT count(*) FROM community_private.radio_identities WHERE device_id=p_device_id)>=8
   AND NOT EXISTS(SELECT 1 FROM community_private.radio_identities WHERE device_id=p_device_id AND cluster=p_cluster AND application_id=p_application_id AND ttn_device_id=p_ttn_device_id)
 THEN RAISE EXCEPTION 'Regional connection limit reached' USING ERRCODE='P0001'; END IF;
 SELECT * INTO old_identity FROM community_private.radio_identities
 WHERE cluster=p_cluster AND application_id=p_application_id AND (ttn_device_id=p_ttn_device_id OR dev_eui=p_dev_eui) FOR UPDATE;
 IF FOUND AND old_identity.device_id<>p_device_id THEN RAISE EXCEPTION 'Device already connected' USING ERRCODE='23505'; END IF;
 IF old_identity.id IS NOT NULL THEN
   SELECT * INTO old_integration FROM community_private.webhook_integrations WHERE id=old_identity.integration_id FOR UPDATE;
   IF (old_integration.owner_id IS DISTINCT FROM p_owner_id AND NOT
       (community_private.is_team_member(old_integration.owner_id) AND community_private.is_team_member(p_owner_id)
         AND EXISTS(SELECT 1 FROM community_private.team_balloons WHERE device_id=p_device_id)))
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

CREATE OR REPLACE FUNCTION public.issue_payload_claim(p_issuer_id uuid,p_device_id text,p_dev_eui text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE expires timestamptz;
BEGIN
 IF p_issuer_id IS NULL OR p_dev_eui IS NULL OR p_dev_eui !~ '^[0-9A-F]{16}$' OR p_dev_eui='0000000000000000'
   OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'Invalid claim proof' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND owner_id IS NULL
   AND NOT EXISTS(SELECT 1 FROM community_private.team_balloons t WHERE t.device_id=p_device_id) FOR UPDATE;
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

CREATE OR REPLACE FUNCTION public.claim_existing_payload(p_owner_id uuid,p_github_login text,p_device_id text,p_token_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE proof community_private.payload_claims%ROWTYPE;
BEGIN
 IF p_owner_id IS NULL OR p_github_login IS NULL OR p_github_login !~* '^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$'
   OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_owner_id::text,0));
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id AND owner_id IS NULL
   AND NOT EXISTS(SELECT 1 FROM community_private.team_balloons t WHERE t.device_id=p_device_id) FOR UPDATE;
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

CREATE OR REPLACE FUNCTION public.staff_payload_inventory() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT jsonb_build_object('payloads',coalesce((
   SELECT jsonb_agg(jsonb_build_object('deviceId',d.device_id,'callsign',coalesce(d.display_name,d.device_id),
     'launcherName',d.launcher_name,'status',d.status,'owned',d.owner_id IS NOT NULL OR EXISTS(SELECT 1 FROM community_private.team_balloons t WHERE t.device_id=d.device_id),
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

CREATE OR REPLACE FUNCTION public.register_community_balloon(p_owner_id uuid,p_github_login text,p_callsign text,p_dev_eui text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE new_id text;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_owner_id::text,0));
 IF (SELECT count(*) FROM public.devices WHERE owner_id=p_owner_id)>=50 THEN RAISE EXCEPTION 'Registration limit reached' USING ERRCODE='P0001'; END IF;
 IF EXISTS(SELECT 1 FROM public.devices d JOIN community_private.balloon_registration r USING(device_id) WHERE community_private.can_manage_balloon(p_owner_id,d.device_id) AND r.dev_eui=p_dev_eui) THEN
   RAISE EXCEPTION 'Device already registered' USING ERRCODE='23505';
 END IF;
 new_id := 'balloon-' || gen_random_uuid()::text;
 INSERT INTO public.devices(device_id,owner_id,owner_github,display_name,status,official,connection_status)
 VALUES(new_id,p_owner_id,p_github_login,p_callsign,'planned',false,'pending');
 INSERT INTO community_private.balloon_registration(device_id,dev_eui) VALUES(new_id,p_dev_eui);
 RETURN community_private.balloon_json(new_id);
END;
$$;

REVOKE ALL ON FUNCTION community_private.is_team_member(uuid),community_private.can_manage_balloon(uuid,text),community_private.share_official_balloon(),public.sync_official_team_member(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION community_private.is_team_member(uuid),community_private.can_manage_balloon(uuid,text),community_private.share_official_balloon(),public.sync_official_team_member(uuid,text) TO service_role;
COMMIT;
