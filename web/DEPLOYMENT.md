# Existing-project rollout

Use `ShepherdKruse/Stratolink`, Supabase project `iazmnyyfsobucndqncgw`, and Vercel project `shepherdkruses-projects/v0-strato-link-marketing-site`. Do not create replacement projects.

## Applied on October 6, 2026

- `20261007003455_community_backend.sql` and `20261007003501_telemetry_ingest_contract.sql` are applied to the shared database. Their filenames match its migration history.
- A private backup and field-by-field comparison confirmed all 1,513 original telemetry records remain unchanged.
- Anonymous and authenticated clients cannot write flight records, read owner UUIDs or pending registrations, or call the account and ingestion RPCs.
- Stratolink 2 is marked missing. Stratolink 3 remains landed.
- Three existing TTN webhooks have independent Authorization tokens. Five verified regional identities resolve to the two official balloons. Their destinations and other settings are unchanged. The current deployed handler ignores Authorization, so these headers remain compatible before cutover.
- Stratolink 3's AS identity needs confirmation before adding that physical-device mapping.
- The Stratolink GitHub OAuth app exists at `https://github.com/settings/applications/3910509`, with only the shared Supabase callback registered.

The new website is not deployed. The original dashboard still needs direct telemetry reads, so the final raw-data permission change is staged separately.

## Authentication

Enable the GitHub provider in the existing Supabase project using that app's client ID and secret. Keep the secret in the provider configuration, never in this repository or browser build.

Set Site URL to `https://stratolink.org`. Allow only the required exact callback destinations:

- `https://stratolink.org/dashboard`
- `http://127.0.0.1:4173/dashboard`
- `http://localhost:4173/dashboard`
- `http://127.0.0.1:4174/dashboard` while that review server is in use
- `http://localhost:4174/dashboard` while that review server is in use

Add a specific preview callback only when testing that deployment. Do not add wildcard preview domains. The signed-in account currently sees read-only URL configuration controls; a project administrator must update them.

Verify GitHub sign-in, sign-out, selected-balloon return, registration, regional connection, and owner-only status changes before promoting the site.

## Deployment and cutover

1. Obtain access to the existing Vercel project. The current GitHub-linked account can access only its personal Vercel team.
2. Keep Root Directory `web`. Use the build configuration in `vercel.json`, Node 22, and the public/server variables documented in `README.md`. Retain the shared private forecast Blob token.
3. Deploy this branch as a preview. Confirm static pages, native API functions, semantic search, privacy filtering, and stored forecasts in Vercel's runtime.
4. Confirm all TTN headers and scoped identity lookups still match before replacing ingress. Do not replay old packets into the live archive just to test the new handler; dry-run its insert and receipt adapters instead.
5. Promote the verified site when its content is ready, then apply `../supabase/cutover/private_raw_data.sql`. Verify direct raw reads are denied and public API reads still work. Run this before opening community registration publicly.
6. Verify the existing forecast Actions secrets and scheduled worker. Disable any external caller of the retired compute endpoint.

The private database backup and TTN header rollback records are retained locally outside the repository. Coordinate header restoration with a compatible ingress version; the new handler rejects missing or revoked tokens.

PostGIS ACL hardening is a separate platform-owner task documented in `../supabase/platform-hardening/README.md`. It does not block revoking access to application telemetry. Do not claim the reserved-role extension permissions were changed by the application migration.
