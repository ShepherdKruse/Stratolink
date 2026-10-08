# Existing-project rollout

Use `ShepherdKruse/Stratolink`, Supabase project `iazmnyyfsobucndqncgw`, and Vercel project `shepherdkruses-projects/v0-strato-link-marketing-site`. Do not create replacement projects.

## Official team ownership - October 8, 2026

The additive `20261008194242_official_team_ownership.sql` migration is applied to the existing shared project. Stratolink 2 and 3 are managed jointly by the verified GitHub accounts Twarner491, clkruse, and ShepherdKruse. New registrations, reservations and valid payload claims from those accounts become official and shared automatically. GitHub numeric provider IDs establish membership; usernames and client-supplied fields do not. Shepherd's membership activates on his first site sign-in. This does not grant organizer inventory privileges or replace `PAYLOAD_STAFF_USER_IDS`.

Existing payload rows, all 1,517 telemetry records, all five radio mappings and all three webhook integrations retained identical before/after fingerprints. The new private tables have RLS and no browser grants. The existing service-only account endpoints enforce team access. Dedicated member-owned connections can be managed by co-owners; shared organizer integrations remain protected from token replacement. Historical team balloons cannot be reassigned through QR claims.

The complete local verification suite and disposable PostgreSQL integration checks passed, including all three members, outsiders, copied usernames, direct RPC denial, current-account filters, future official registration, shared-token protection and historical preservation. Production still returned `503 Registration unavailable` on October 8 while awaiting Shepherd's environment update and redeploy. That gate must be verified separately from the ownership migration; do not announce end-to-end registration, QR claims or new TTN delivery based only on these local checks.

## Current production status - October 7, 2026

- [PR #77](https://github.com/ShepherdKruse/Stratolink/pull/77) is merged into `main` at `2e9c001d5632b577bb579e25ea756341d22a75b5`. The new site is live at [stratolink.org](https://stratolink.org), and production GitHub OAuth succeeds.
- Production telemetry, fleet, stored forecast and semantic search endpoints returned `200`. The webhook returns `405` for GET and `401` for an unsigned POST; an unauthenticated account request returns `401`. Registration remains disabled and returns `503`.
- `20261007225324_private_raw_data_cutover.sql` is applied and matches the shared migration history. Both `anon` and `authenticated` lack table and column privileges on all seven application tables/views and execution privilege on `get_active_balloons`. Anonymous REST reads of all seven relations returned `42501`; the public website APIs remained available.
- The 1,517 telemetry rows in the pre-cutover snapshot, both device records, five radio identities and three integrations matched their pre-cutover fingerprints. The cutover changed permissions, not flight data or TTN configuration.
- The final release verification passed 110 unit/API tests, the remaining contract and worker checks, type checks and the production build. The isolated PostgreSQL suite passed all 16 integration groups. Public page review covered 60 page/viewport combinations at widths 320, 390, 768, 1440 and 1920 pixels, plus interactive controls.

Shepherd still needs to enable `COMMUNITY_REGISTRATION_ENABLED=true` in Production and redeploy. Dedicated deployed TTN connection and QR claim checks remain before announcing registration; unsigned-request rejection does not establish successful live TTN delivery. Existing PostGIS reserved-role advisories and the email-provider leaked-password warning remain. Their remediation is separate from the completed application privacy cutover.

## Historical schema staging - October 6, 2026

- `20261007003455_community_backend.sql` and `20261007003501_telemetry_ingest_contract.sql` are applied to the shared database. Their filenames match its migration history.
- A private backup and field-by-field comparison confirmed all 1,513 original telemetry records remain unchanged.
- Anonymous and authenticated clients cannot write flight records, read owner UUIDs or pending registrations, or call the account and ingestion RPCs.
- Stratolink 2 is marked missing. Stratolink 3 remains landed.
- Three existing TTN webhooks received independent Authorization tokens. Five verified regional identities resolve to the two official balloons. Their destinations and other settings stayed unchanged. The old handler ignored Authorization, allowing those headers to be staged before the strict handler was deployed.
- Stratolink 3's AS identity needs confirmation before adding that physical-device mapping.
- The Stratolink GitHub OAuth app exists at `https://github.com/settings/applications/3910509`, with only the shared Supabase callback registered.

At this stage the new website was a preview and the original dashboard still required direct telemetry reads. The raw-data permission change was therefore staged separately, then applied after the new production APIs were verified on October 7.

## Earlier local and schema verification - October 7, 2026

- GitHub authentication is enabled in the shared Supabase project. The approved app returned to the local dashboard through PKCE, preserved the selected Stratolink 3 view, and displayed the verified GitHub account. Sign-out and repeat sign-in passed.
- `20261007201932_payload_claim_compatibility.sql` is applied. Its filename matches the shared migration history. All 1,515 telemetry records and both device records matched their pre-migration fingerprints; the five regional identities and three webhook integrations remained in place.
- The private claim table has RLS enabled and no client grants. All five new RPCs use invoker privileges, deny anonymous and authenticated execution, and permit the server role.
- With registration enabled only in the loopback review process, the UI registered a temporary payload, saved its status, and reserved a callsign through `/claim`. The resulting records belonged to the verified GitHub account and were excluded from the public fleet. Both temporary records were removed and the local registration switch was returned to its disabled default after verification. No real TTN identity or webhook was changed.
- The full local verification suite passed on Node 25.9.0, including 101 unit/API tests, decoder and migration contracts, forecast tests, staff CLI tests, type checks and the production build. All 16 isolated PostgreSQL integration groups passed, including competing claims, token expiry/reuse, ownership and data preservation. These fixture tests are separate from a deployed QR claim test. GitHub CI independently passed on the deployment's Node 22 version.

Supabase's remediation references cover [public tables without RLS](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public), [extensions in the public schema](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public), [anonymous privileged function access](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable), [authenticated privileged function access](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable), and [leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection). Follow the platform-owner process below for the PostGIS objects.

## Preview review

Before the production release, [PR #77](https://github.com/ShepherdKruse/Stratolink/pull/77) passed GitHub CI on Node 22 at commit `c2498473cdc594d7f000801d6c04f4943e99eab5`. Its Vercel preview build succeeded at the same commit:

https://v0-strato-link-marketing-sit-git-ccbef2-shepherdkruses-projects.vercel.app

The branch preview requires Vercel access; during review the signed-in `twarner491` account saw “You Need Access.” A member of `shepherdkruses-projects` can provide a Share link or Viewer access; a paid administrator seat is not required. Production runtime checks have since passed as recorded above. Shepherd can apply the remaining server settings using [VERCEL-SETUP.md](VERCEL-SETUP.md).

Check these settings in the existing project's Preview environment before rebuilding:

- Browser authentication uses `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`, with explicit compatibility for the existing `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` names. The public build configuration rejects server credentials.
- `SITE_URL` controls both allowed authenticated requests and generated webhook URLs, with `NEXT_PUBLIC_APP_URL` as the existing-name fallback. Production uses `https://stratolink.org`. For restricted preview UI/account review, keep that production value and add only the exact preview origin to `AUTH_ALLOWED_ORIGINS`. The local review configuration similarly permits explicit localhost origins while retaining the production webhook URL.
- The exact preview `/dashboard` callback is already in Supabase's redirect allowlist. Add another origin to `AUTH_ALLOWED_ORIGINS` only if that additional preview hostname is intentionally being tested.
- Leave `COMMUNITY_REGISTRATION_ENABLED` unset or `false` initially. GitHub sign-in is configured; set the switch to `true` only in the protected Preview environment and redeploy for owner registration tests. The switch controls new registrations and TTN connection changes. Account reads and owner status changes do not require it.

The existing Mapbox, server Supabase and Blob variable names remain compatible; confirm their Preview scopes. Changes to public build variables require a new deployment.

Keep preview protection in place and grant access only to the reviewers who need it. A protected preview cannot receive ordinary TTN webhook requests. Preview UI/account checks are separate from live packet delivery: do not redirect real production hooks to a preview, reconnect official devices for testing, or overwrite their mappings. With the production `SITE_URL`, any generated webhook points to production, where the strict handler is now live. Full live TTN delivery through that handler has not been tested.

Testing a separate preview webhook would require its own approved access arrangement and test identity, with `SITE_URL` set to that preview's exact HTTPS origin. It is not required for the current owner review. Keep the Production registration switch unset or `false` until strict production ingress and the raw-data permission cutover are both verified. A successful preview test is not permission to enable the Production switch.

## Existing QR registration

The deployed implementation retains `/activate`, `/activate/{deviceId}` and `/claim`, preserving device context through GitHub sign-in. The legacy database IDs, claim fields, launch-token fields, TTN mappings and telemetry remain present. The claim migration is applied; the external owner flow still needs the checks below before announcing registration. Local tests are not a production verification.

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

Local sign-in, sign-out, selected-balloon return, registration, reservation and status updates passed. Production GitHub sign-in also passed. After the Production registration switch is enabled and the site redeployed, verify the deployed owner flow, a dedicated regional connection and a QR claim before announcing registration.

## Remaining registration and operations checks

1. Shepherd should confirm the Production staff UUIDs, independent claim-cookie secret and trusted site origin using [VERCEL-SETUP.md](VERCEL-SETUP.md), enable `COMMUNITY_REGISTRATION_ENABLED=true`, and redeploy. Keep preview-only origins out of Production unless explicitly required.
2. Verify deployed registration, reservation, owner status changes, a dedicated regional TTN connection and the QR checks above before announcing registration. Use dedicated review payloads, not the two official historical balloons. Do not replay old packets into the live archive or replace existing TTN mappings for testing.
3. Verify the existing forecast Actions secrets and scheduled worker independently of the successful stored-forecast read. Disable any external caller of the retired compute endpoint.
4. Recheck protection of old deployment URLs and aliases. Keep Root Directory `web`, Node 22, the repository's build settings and the existing private forecast Blob token for future deployments.

## Recorded database cutover

The applied migration is [`20261007225324_private_raw_data_cutover.sql`](../supabase/migrations/20261007225324_private_raw_data_cutover.sql). It was executed only after the new server APIs were live, with registration disabled. Its contents are preserved byte-for-byte from the original separate script so the repository matches the remote migration history; the opening comments describe that historical sequence.

For a new installation with the required legacy baseline, apply the full current migration sequence before serving the new site. An upgrade still serving the old browser client must defer this final migration until the replacement server APIs are ready. Do not replay the already-applied migration against the shared project as a new version. The integration harness applies it after the compatibility checks to preserve coverage of both rollout phases.

The previous production deployment's immutable URL redirected to Vercel authentication during the release review. Check it again after promotion, along with any old aliases. Old server functions retain their deployment-time service credentials: the old unauthenticated webhook and unmasked forecast must not remain publicly reachable. Retire or protect any such deployment through Vercel. After the raw-data cutover, use a corrected version of the new server-backed site for rollback; restoring the old browser client would require reopening raw reads.

The private database backup and TTN header rollback records are retained locally outside the repository. Coordinate header restoration with a compatible ingress version; the new handler rejects missing or revoked tokens.

PostGIS ACL hardening is a separate platform-owner task documented in `../supabase/platform-hardening/README.md`. It does not block revoking access to application telemetry. Do not claim the reserved-role extension permissions were changed by the application migration.
