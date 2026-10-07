-- Run explicitly after the new website's server APIs are live and verified.
-- This is deliberately outside migrations: old clients read Supabase directly.
-- Raw telemetry, receiver metadata and account records remain available only
-- to the server. The public dashboard API supplies the redacted read model.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
BEGIN
 IF to_regclass('public.community_telemetry') IS NULL
   OR to_regclass('community_private.radio_identities') IS NULL THEN
   RAISE EXCEPTION 'Apply and verify the community backend migrations first';
 END IF;
END;
$$;

-- Only application-owned objects are changed. Supabase-owned PostGIS objects
-- have a separate hardening script and cannot block this privacy cutover.
REVOKE ALL ON public.devices,public.telemetry,public.uplink_events,
 public.latest_telemetry,public.community_telemetry,
 public.wildlife_detections,public.b2b_packets FROM PUBLIC,anon,authenticated;
REVOKE ALL ON public.devices_id_seq FROM PUBLIC,anon,authenticated;

-- Table-level revocation does not revoke separately granted column access.
DO $$
DECLARE relation record; columns text;
BEGIN
 FOR relation IN
   SELECT c.oid,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f')
     AND c.relname IN ('devices','telemetry','uplink_events','latest_telemetry','community_telemetry','wildlife_detections','b2b_packets')
 LOOP
   SELECT string_agg(quote_ident(a.attname),',') INTO columns
   FROM pg_attribute a WHERE a.attrelid=relation.oid AND a.attnum>0 AND NOT a.attisdropped;
   IF columns IS NOT NULL THEN
     EXECUTE format('REVOKE ALL (%s) ON TABLE public.%I FROM PUBLIC,anon,authenticated',columns,relation.relname);
   END IF;
 END LOOP;
END;
$$;

DROP POLICY IF EXISTS "Allow public read access" ON public.devices;
DROP POLICY IF EXISTS "Allow public read" ON public.devices;
DROP POLICY IF EXISTS "Read connected devices" ON public.devices;
DROP POLICY IF EXISTS "Allow public read access" ON public.telemetry;
DROP POLICY IF EXISTS "Allow public read access" ON public.uplink_events;

-- Close the application RPC that previously returned raw coordinates.
REVOKE EXECUTE ON FUNCTION public.get_active_balloons(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_active_balloons(integer) TO service_role;

-- Confirm the privacy boundary instead of accepting warning-only revocations.
DO $$
DECLARE client text; relation text;
BEGIN
 FOREACH client IN ARRAY ARRAY['anon','authenticated'] LOOP
   FOREACH relation IN ARRAY ARRAY['devices','telemetry','uplink_events','latest_telemetry','community_telemetry','wildlife_detections','b2b_packets'] LOOP
     IF has_table_privilege(client,'public.'||relation,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
       OR has_any_column_privilege(client,'public.'||relation,'SELECT,INSERT,UPDATE,REFERENCES') THEN
       RAISE EXCEPTION 'Client access remains on application relation %',relation;
     END IF;
   END LOOP;
   IF has_function_privilege(client,'public.get_active_balloons(integer)','EXECUTE') THEN
     RAISE EXCEPTION 'Client access remains on the legacy coordinate RPC';
   END IF;
 END LOOP;
END;
$$;

NOTIFY pgrst, 'reload schema';
COMMIT;
