-- PostGIS objects may be owned by Supabase's reserved supabase_admin role.
-- Run with extension-owner authority. Postconditions deliberately reject a
-- nominally successful REVOKE that did not remove another owner's grants.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

REVOKE ALL ON public.spatial_ref_sys FROM PUBLIC,anon,authenticated;
DO $$
DECLARE columns text; routine record;
BEGIN
 SELECT string_agg(quote_ident(attname),',') INTO columns
 FROM pg_attribute WHERE attrelid='public.spatial_ref_sys'::regclass AND attnum>0 AND NOT attisdropped;
 EXECUTE format('REVOKE ALL (%s) ON public.spatial_ref_sys FROM PUBLIC,anon,authenticated',columns);
 FOR routine IN
   SELECT p.oid::regprocedure AS signature
   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='public' AND p.proname='st_estimatedextent' AND p.prosecdef
 LOOP
   EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC,anon,authenticated',routine.signature);
   EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',routine.signature);
 END LOOP;
END;
$$;

DO $$
DECLARE client text; routine record;
BEGIN
 FOREACH client IN ARRAY ARRAY['anon','authenticated'] LOOP
   IF has_table_privilege(client,'public.spatial_ref_sys','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
     OR has_any_column_privilege(client,'public.spatial_ref_sys','SELECT,INSERT,UPDATE,REFERENCES') THEN
     RAISE EXCEPTION 'PostGIS grant revocation requires extension-owner privileges';
   END IF;
   FOR routine IN
     SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname='public' AND p.proname='st_estimatedextent' AND p.prosecdef
   LOOP
     IF has_function_privilege(client,routine.oid,'EXECUTE') THEN
       RAISE EXCEPTION 'PostGIS function revocation requires extension-owner privileges';
     END IF;
     IF NOT has_function_privilege('service_role',routine.oid,'EXECUTE') THEN
       RAISE EXCEPTION 'PostGIS service function grant was not preserved';
     END IF;
   END LOOP;
 END LOOP;
END;
$$;

NOTIFY pgrst, 'reload schema';
COMMIT;
