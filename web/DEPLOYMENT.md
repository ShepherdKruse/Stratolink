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

The new website is deployed as a preview in the existing Vercel project. The production website remains unchanged. The original dashboard still needs direct telemetry reads, so the final raw-data permission change is staged separately.

## Verified on October 7, 2026

- GitHub authentication is enabled in the shared Supabase project. The approved app returned to the local dashboard through PKCE, preserved the selected Stratolink 3 view, and displayed the verified GitHub account. Sign-out and repeat sign-in passed.
- `20261007201932_payload_claim_compatibility.sql` is applied. Its filename matches the shared migration history. All 1,515 telemetry records and both device records matched their pre-migration fingerprints; the five regional identities and three webhook integrations remained in place.
- The private claim table has RLS enabled and no client grants. All five new RPCs use invoker privileges, deny anonymous and authenticated execution, and permit the server role.
- With registration enabled only in the loopback review process, the UI registered a temporary payload, saved its status, and reserved a callsign through `/claim`. The resulting records belonged to the verified GitHub account and were excluded from the public fleet. Both temporary records were removed and the local registration switch was returned to its disabled default after verification. No real TTN identity or webhook was changed.
- The full local verification suite passed on Node 25.9.0, including 101 unit/API tests, decoder and migration contracts, forecast tests, staff CLI tests, type checks and the production build. All 16 isolated PostgreSQL integration groups passed, including competing claims, token expiry/reuse, ownership and data preservation. These fixture tests are separate from a deployed QR claim test. GitHub CI independently passed on the deployment's Node 22 version.

The live website has not been promoted. Vercel runtime review, a dedicated end-to-end TTN connection/QR claim check, production ingress verification, and the raw-data permission cutover remain pending. Existing PostGIS platform-owner advisories and the email-provider leaked-password warning remain; the new application functions add no privileged client RPCs.

Supabase's remediation references cover [public tables without RLS](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public), [extensions in the public schema](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public), [anonymous privileged function access](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable), [authenticated privileged function access](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable), and [leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection). Follow the platform-owner process below for the PostGIS objects.

## Preview review

[Draft PR #77](https://github.com/ShepherdKruse/Stratolink/pull/77) passed GitHub CI on Node 22 at commit `c2498473cdc594d7f000801d6c04f4943e99eab5`. Its Vercel preview build succeeded at the same commit:

https://v0-strato-link-marketing-sit-git-ccbef2-shepherdkruses-projects.vercel.app

Runtime and UI review are blocked by Vercel deployment protection. The signed-in `twarner491` account sees “You Need Access.” A member of `shepherdkruses-projects` must grant access before review can continue. Build success does not verify API runtime configuration or sign-in.

Check these settings in the existing project's Preview environment before rebuilding:

- Browser authentication needs `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`. The old `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` names do not configure the Vite auth client.
- `SITE_URL` controls both allowed authenticated requests and generated webhook URLs. The old `NEXT_PUBLIC_APP_URL` is not read. Production uses `https://stratolink.org`. For restricted preview UI/account review, keep that production value and add only the exact preview origin to `AUTH_ALLOWED_ORIGINS`. The local review configuration similarly permits explicit localhost origins while retaining the production webhook URL.
- The exact preview `/dashboard` callback is already in Supabase's redirect allowlist. Add another origin to `AUTH_ALLOWED_ORIGINS` only if that additional preview hostname is intentionally being tested.
- Leave `COMMUNITY_REGISTRATION_ENABLED` unset or `false` initially. GitHub sign-in is configured; set the switch to `true` only in the protected Preview environment and redeploy for owner registration tests. The switch controls new registrations and TTN connection changes. Account reads and owner status changes do not require it.

The existing Mapbox, server Supabase and Blob variable names remain compatible; confirm their Preview scopes. Changes to public build variables require a new deployment.

Keep preview protection in place and grant access only to the reviewers who need it. A protected preview cannot receive ordinary TTN webhook requests. Preview UI/account checks are separate from live packet delivery: do not redirect real production hooks to a preview, reconnect official devices for testing, or overwrite their mappings. With the production `SITE_URL`, any generated webhook points to production, where the old handler remains active until cutover. Full live TTN delivery through the new handler has not been tested.

Testing a separate preview webhook would require its own approved access arrangement and test identity, with `SITE_URL` set to that preview's exact HTTPS origin. It is not required for the current owner review. Keep the Production registration switch unset or `false` until strict production ingress and the raw-data permission cutover are both verified. A successful preview test is not permission to enable the Production switch.

## Existing QR registration

QR compatibility is required before production promotion. The compatibility implementation retains `/activate`, `/activate/{deviceId}` and `/claim`, preserving device context through GitHub sign-in. The legacy database IDs, claim fields, launch-token fields, TTN mappings and telemetry remain present. The claim migration is applied; the external owner flow still needs the deployment checks below. Local tests are not a production verification.

Shepherd's existing [provisioner](https://github.com/ShepherdKruse/Stratolink/blob/b95c4f4/web/lib/ttn/register-payload.ts) creates TTN credentials and firmware configuration. The [launch kit](https://github.com/ShepherdKruse/Stratolink/blob/b95c4f4/web/lib/actions/launch-kit.ts) generates `/activate/{deviceId}?k={token}` labels with a seven-day token and a PIN fallback. `/claim` separately reserves a callsign before provisioning. These workflows must be accounted for in the migration.

Fresh ownership labels use `/activate/{deviceId}#k={token}`. The fragment is handled by the page and is not sent in the initial HTTP request. The page still recognizes old query-style links to preserve their device context, but old credentials do not grant ownership. The staff CLI rejects query credentials or ambiguous fragments in newly issued labels.

- The additive `20261007201932_payload_claim_compatibility.sql` migration is applied with existing records preserved. Fresh ownership proof lives in the private registry and is consumed transactionally. Legacy PINs and token records are retained but never authorize account ownership.
- Set `PAYLOAD_STAFF_USER_IDS` to the exact Supabase UUIDs of approved GitHub-authenticated organizers. The old shared `ADMIN_ACTIVATION_KEY` does not grant staff access. Reviewers still need Vercel project access. Supabase OAuth is configured.
- Set an independent `PAYLOAD_CLAIM_COOKIE_SECRET` in each server environment, using 32 random bytes encoded as base64url. This signs a 30-minute HttpOnly claim context, bound to the initiating origin. The credential never enters the GitHub callback or browser storage.
- Use [organizer onboarding](ONBOARDING.md) to inspect reservations, verify manually provisioned TTN records, and issue a fresh seven-day claim label. The CLI requires an organizer session in a private file, defaults to read-only and writes the URL and printable SVG only to a new private directory outside the repository. It does not change TTN devices or rotate shared webhook credentials.
- Confirm the relevant shared integration already exists before binding a radio. Existing integration IDs come from staff inventory. A new application or cluster requires separate administrator setup and webhook verification; the staff binding command cannot create that integration or guess its credential.
- Verify that a valid claim assigns the existing device without changing its canonical ID, official flag, launch state, location, time, TTN bindings or telemetry. Check expiry, replacement, second-use and competing claims, plus device-only links and return through GitHub sign-in.
- Verify a signed-in callsign reservation can receive its manually provisioned radio without a second ownership claim. The old reservation name remains organizer context, not identity proof.

The local KiCad V1 files contain the globe and open-hardware artwork, but no QR. The old web code confirms generated labels; PCB integration was planned. Use a permanent device-only address on a future board and provide its temporary ownership credential separately. If any existing manufactured board has a QR, confirm its hostname and path before rollout, keeping the credential private.

## Authentication

The GitHub provider is enabled in the existing Supabase project using that app's client ID and secret. Keep the secret in the provider configuration, never in this repository or browser build.

Site URL is `https://stratolink.org`. The configured exact callback destinations are:

- `https://stratolink.org/dashboard`
- `http://127.0.0.1:4173/dashboard`
- `http://localhost:4173/dashboard`
- `https://v0-strato-link-marketing-sit-git-ccbef2-shepherdkruses-projects.vercel.app/dashboard`

Add a specific preview callback only when testing that deployment. Do not add wildcard preview domains. The signed-in account now has access to edit these settings.

Local sign-in, sign-out, selected-balloon return, registration, reservation and status updates passed. Repeat the owner flow in Vercel and verify a dedicated regional connection and QR claim before promoting the site.

## Deployment and cutover

1. Obtain access to the existing Vercel project and protected preview. The current GitHub-linked account can access only its personal Vercel team.
2. Keep Root Directory `web`. Use the build configuration in `vercel.json`, Node 22, and the public/server variables documented in `README.md`. Retain the shared private forecast Blob token.
3. Review the existing preview, redeploying after any environment changes. Confirm static pages, native API functions, semantic search, privacy filtering, stored forecasts, and the QR/reservation checks above in Vercel's runtime. Use dedicated review payloads, not the two official historical balloons.
4. Confirm all TTN headers and scoped identity lookups still match before replacing ingress. Do not replay old packets into the live archive just to test the new handler; dry-run its insert and receipt adapters instead.
5. Confirm `COMMUNITY_REGISTRATION_ENABLED` is unset or `false` in Production. Deploy the verified site with strict ingress when its content is ready, then apply `../supabase/cutover/private_raw_data.sql`. Verify direct raw reads are denied, public API reads still work, and scoped ingress accepts the intended identities. Registration and TTN connection changes remain disabled during this sequence.
6. Verify the existing forecast Actions secrets and scheduled worker. Disable any external caller of the retired compute endpoint.
7. After those checks pass, set `COMMUNITY_REGISTRATION_ENABLED=true` in Production and redeploy. Verify the owner flow before announcing public registration. Keep preview-only origins out of Production unless they are still explicitly required.

The private database backup and TTN header rollback records are retained locally outside the repository. Coordinate header restoration with a compatible ingress version; the new handler rejects missing or revoked tokens.

PostGIS ACL hardening is a separate platform-owner task documented in `../supabase/platform-hardening/README.md`. It does not block revoking access to application telemetry. Do not claim the reserved-role extension permissions were changed by the application migration.
