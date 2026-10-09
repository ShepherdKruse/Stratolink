BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.devices ADD COLUMN planned_launch_date date
 CHECK (planned_launch_date BETWEEN DATE '2020-01-01' AND DATE '2100-12-31');

-- Registration records describe intended radios. Only verified radio_identities
-- may route telemetry; entering a DevEUI never proves control of a TTN device.
CREATE FUNCTION community_private.valid_regional_euis(value jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT CASE WHEN jsonb_typeof(value)='object' THEN NOT EXISTS (
   SELECT 1 FROM jsonb_each(value) AS e(region,eui)
   WHERE region NOT IN ('northAmerica','europe','asia','australia')
     OR jsonb_typeof(eui)<>'string' OR (eui #>> '{}') !~ '^[0-9A-F]{16}$'
     OR (eui #>> '{}')='0000000000000000'
 ) ELSE false END;
$$;
ALTER TABLE community_private.balloon_registration
 ADD COLUMN regional_euis jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (community_private.valid_regional_euis(regional_euis)),
 ADD COLUMN share_research_data boolean NOT NULL DEFAULT false,
 ADD COLUMN research_choice_at timestamptz;

CREATE OR REPLACE FUNCTION community_private.balloon_json(p_device_id text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT jsonb_build_object('id',d.device_id,'callsign',coalesce(d.display_name,d.device_id),
   'status',CASE WHEN d.status='storage' THEN 'planned' ELSE d.status END,
   'devEui',r.dev_eui,'regionalEuis',coalesce(r.regional_euis,'{}'::jsonb),
   'plannedLaunchDate',d.planned_launch_date,'shareResearchData',coalesce(r.share_research_data,false),'ownerId',d.owner_id,'ownerGithub',d.owner_github,
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


CREATE FUNCTION public.update_balloon_settings(p_owner_id uuid,p_device_id text,p_callsign text,p_planned_launch_date date,p_regional_euis jsonb,p_share_research_data boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_callsign IS NULL OR p_callsign !~ '^[A-Za-z0-9][A-Za-z0-9 ._-]{1,39}$'
   OR NOT community_private.valid_regional_euis(p_regional_euis) OR p_regional_euis IS NULL
   OR p_share_research_data IS NULL
 THEN RAISE EXCEPTION 'Invalid balloon settings' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.devices WHERE device_id=p_device_id
   AND community_private.can_manage_balloon(p_owner_id,p_device_id) FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE public.devices SET display_name=p_callsign,planned_launch_date=p_planned_launch_date WHERE device_id=p_device_id;
 INSERT INTO community_private.balloon_registration(device_id,dev_eui,regional_euis,share_research_data,research_choice_at)
 VALUES(p_device_id,(SELECT value FROM jsonb_each_text(p_regional_euis) ORDER BY key LIMIT 1),p_regional_euis,p_share_research_data,now())
 ON CONFLICT(device_id) DO UPDATE SET
   regional_euis=EXCLUDED.regional_euis,share_research_data=EXCLUDED.share_research_data,
   research_choice_at=CASE WHEN community_private.balloon_registration.share_research_data IS DISTINCT FROM EXCLUDED.share_research_data
     OR community_private.balloon_registration.research_choice_at IS NULL THEN now()
     ELSE community_private.balloon_registration.research_choice_at END;
 RETURN community_private.balloon_json(p_device_id);
END;
$$;

CREATE FUNCTION public.register_planned_balloon(p_owner_id uuid,p_github_login text,p_callsign text,p_planned_launch_date date,p_regional_euis jsonb,p_share_research_data boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE registered jsonb; primary_eui text;
BEGIN
 IF p_regional_euis IS NULL OR NOT community_private.valid_regional_euis(p_regional_euis) OR p_regional_euis='{}'::jsonb
 THEN RAISE EXCEPTION 'Add at least one regional DevEUI' USING ERRCODE='22023'; END IF;
 SELECT value INTO primary_eui FROM jsonb_each_text(p_regional_euis) ORDER BY key LIMIT 1;
 registered := public.register_community_balloon(p_owner_id,p_github_login,p_callsign,primary_eui);
 RETURN public.update_balloon_settings(p_owner_id,registered->>'id',p_callsign,p_planned_launch_date,p_regional_euis,p_share_research_data);
END;
$$;

REVOKE ALL ON FUNCTION community_private.valid_regional_euis(jsonb),
 public.update_balloon_settings(uuid,text,text,date,jsonb,boolean),
 public.register_planned_balloon(uuid,text,text,date,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION community_private.valid_regional_euis(jsonb),
 public.update_balloon_settings(uuid,text,text,date,jsonb,boolean),
 public.register_planned_balloon(uuid,text,text,date,jsonb,boolean) TO service_role;
COMMIT;
