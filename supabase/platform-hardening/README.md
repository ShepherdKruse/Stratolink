# PostGIS grants

`20261007003602_restrict_postgis_client_access.sql` requires authority over the PostGIS extension objects. On the hosted project those objects are owned by Supabase's reserved `supabase_admin` role. The normal `postgres` role has neither ownership nor grant options. A plain `REVOKE` can warn without changing the existing grants, so this script checks the resulting privileges and rolls back if they remain.

Request an owner-authorized change through Supabase. Do not change object ownership, relocate or reinstall the extension to bypass this restriction. This script is kept outside automatic migrations until that access is available.

The remaining public surface consists of `spatial_ref_sys` and the three `st_estimatedextent` overloads. No application table currently has geometry or geography columns. These extension permissions do not expose the telemetry's numeric latitude and longitude columns, but remain a platform hardening issue, including unnecessary client write grants on the reference table.

The applied `../migrations/20261007225324_private_raw_data_cutover.sql` closes application-owned raw telemetry, receiver data, device records and the legacy coordinate RPC. It does not depend on this PostGIS change.
