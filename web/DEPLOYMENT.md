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

The new website is deployed as a preview in the existing Vercel project. Production remains unchanged. The original dashboard still needs direct telemetry reads, so the final raw-data permission change is staged separately.

## Preview review

[Draft PR #77](https://github.com/ShepherdKruse/Stratolink/pull/77) passed GitHub CI at commit `40b6bd514fa7d320b3c853b1ec673905780fe457`. Its Vercel preview build succeeded:

https://v0-strato-link-marketing-sit-git-ccbef2-shepherdkruses-projects.vercel.app

Runtime and UI review are blocked by Vercel deployment protection. The signed-in `twarner491` account sees “You Need Access.” A member of `shepherdkruses-projects` must grant access before review can continue. Build success does not verify API runtime configuration or sign-in.

Check these settings in the existing project's Preview environment before rebuilding:

- Browser authentication needs `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`. The old `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` names do not configure the Vite auth client.
- `SITE_URL` controls both allowed authenticated requests and generated webhook URLs. The old `NEXT_PUBLIC_APP_URL` is not read. Production uses `https://stratolink.org`. For restricted preview UI/account review, keep that production value and add only the exact preview origin to `AUTH_ALLOWED_ORIGINS`. The local review configuration similarly permits explicit localhost origins while retaining the production webhook URL.
- Add the exact preview `/dashboard` callback to Supabase's redirect allowlist. Add another origin to `AUTH_ALLOWED_ORIGINS` only if that additional preview hostname is intentionally being tested.
- Leave `COMMUNITY_REGISTRATION_ENABLED` unset or `false` initially. After GitHub sign-in is configured, set it to `true` only in the protected Preview environment and redeploy for owner registration tests. The switch controls new registrations and TTN connection changes. Account reads and owner status changes do not require it.

The existing Mapbox, server Supabase and Blob variable names remain compatible; confirm their Preview scopes. Changes to public build variables require a new deployment.

Keep preview protection in place and grant access only to the reviewers who need it. A protected preview cannot receive ordinary TTN webhook requests. Preview UI/account checks are separate from live packet delivery: do not redirect real production hooks to a preview, reconnect official devices for testing, or overwrite their mappings. With the production `SITE_URL`, any generated webhook points to production, where the old handler remains active until cutover. Full live TTN delivery through the new handler has not been tested.

Testing a separate preview webhook would require its own approved access arrangement and test identity, with `SITE_URL` set to that preview's exact HTTPS origin. It is not required for the current owner review. Keep the Production registration switch unset or `false` until strict production ingress and the raw-data permission cutover are both verified. A successful preview test is not permission to enable the Production switch.

## Existing QR registration

QR compatibility is required before production promotion. The current redirects drop the device path, and the owner API only accepts new `balloon-UUID` identifiers. The legacy database IDs, claim fields, launch-token fields, TTN mappings and telemetry remain present.

Shepherd's existing [provisioner](https://github.com/ShepherdKruse/Stratolink/blob/b95c4f4/web/lib/ttn/register-payload.ts) creates TTN credentials and firmware configuration. The [launch kit](https://github.com/ShepherdKruse/Stratolink/blob/b95c4f4/web/lib/actions/launch-kit.ts) generates `/activate/{deviceId}?k={token}` labels with a seven-day token and a PIN fallback. `/claim` separately reserves a callsign before provisioning. These workflows must be accounted for in the migration.

- Preserve `/activate` and `/activate/{deviceId}` entry points, including device context through GitHub sign-in. Expired and device-only links should retain that context without granting ownership.
- Claim the existing device transactionally. Retain its canonical ID, TTN identities, telemetry, official flag and launch history. Populate the private registration metadata from trusted provisioning or verified TTN identity data; setting `owner_id` alone does not make a legacy row usable in the current account API.
- Require fresh trusted ownership proof and consume it atomically. Legacy claim codes were covered by public read policies; old public update policies also allowed credential-field changes. Do not assume an old PIN or token record proves permanent ownership. A public board identifier alone is not a credential.
- Keep claiming separate from launching. Scanning or assigning an owner must not mark a payload flying or reset its launch time/location.
- Adapt the organizer provisioning workflow behind verified staff access. Check existing inventory before TTN writes, preserve existing registrations on failure, and verify the regional registries. The old provisioner writes TTN before checking the database status and attempts deletion as rollback, so it must not be restored unchanged.

The physical PCB QR destination still needs confirmation. The local KiCad V1 files contain the globe and open-hardware artwork, but no QR. The web code confirms generated labels, not what was printed on manufactured boards. Confirm only the hostname and path, keeping any credential private. Future assembled-payload onboarding should preserve this distinction between a permanent board identifier and a one-time ownership credential.

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

1. Obtain access to the existing Vercel project and protected preview. The current GitHub-linked account can access only its personal Vercel team.
2. Keep Root Directory `web`. Use the build configuration in `vercel.json`, Node 22, and the public/server variables documented in `README.md`. Retain the shared private forecast Blob token.
3. Review the existing preview, redeploying after any environment changes. Confirm static pages, native API functions, semantic search, privacy filtering, and stored forecasts in Vercel's runtime.
4. Confirm all TTN headers and scoped identity lookups still match before replacing ingress. Do not replay old packets into the live archive just to test the new handler; dry-run its insert and receipt adapters instead.
5. Confirm `COMMUNITY_REGISTRATION_ENABLED` is unset or `false` in Production. Deploy the verified site with strict ingress when its content is ready, then apply `../supabase/cutover/private_raw_data.sql`. Verify direct raw reads are denied, public API reads still work, and scoped ingress accepts the intended identities. Registration and TTN connection changes remain disabled during this sequence.
6. Verify the existing forecast Actions secrets and scheduled worker. Disable any external caller of the retired compute endpoint.
7. After those checks pass, set `COMMUNITY_REGISTRATION_ENABLED=true` in Production and redeploy. Verify the owner flow before announcing public registration. Keep preview-only origins out of Production unless they are still explicitly required.

The private database backup and TTN header rollback records are retained locally outside the repository. Coordinate header restoration with a compatible ingress version; the new handler rejects missing or revoked tokens.

PostGIS ACL hardening is a separate platform-owner task documented in `../supabase/platform-hardening/README.md`. It does not block revoking access to application telemetry. Do not claim the reserved-role extension permissions were changed by the application migration.
