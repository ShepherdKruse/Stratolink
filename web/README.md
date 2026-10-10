# Stratolink website

The public site, documentation and dashboard live in this directory. Vite builds static pages; Vercel Node functions handle authentication, registration, telemetry, forecasts and documentation search.

## Local development

Use Node 22. Copy `.env.example` to `.env.local` and set the required values.

```sh
ONNXRUNTIME_NODE_INSTALL=skip npm ci
npm run dev
```

`npm run build` builds the site. `npm run preview -- --port 4173` serves that build with the same local API handlers. The search index downloads a pinned model with verified checksums during the first build.

## Verification

```sh
npm run verify
```

This runs the dashboard and API tests, firmware decoder contracts, migration contracts, forecast worker checks, type checking and the production build. Tests use local fixtures and mocked services. They do not write to Supabase or TTN.

`npm run test:backend` runs the SQL and API integration checks against a disposable local PostgreSQL container. It requires Docker. CI runs both commands.

## Deployment

Configure the Vercel project with Root Directory `web`, the Vite preset and output directory `dist`. `web/vercel.json` contains the routes, headers and function settings. The root Next.js configuration and old frontend have been removed.

Public build configuration:

- `NEXT_PUBLIC_MAPBOX_TOKEN`: a Mapbox public token restricted to the deployed domains.
- `VITE_SUPABASE_URL`: the project's HTTPS URL.
- `VITE_SUPABASE_PUBLISHABLE_KEY`: its publishable key, used only for authentication.

Existing deployments can keep `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. They are fallbacks for the corresponding `VITE_` settings. The build exposes only these validated public settings and the public Mapbox token. Private Supabase keys are rejected. Vercel Production builds fail if any of these three settings is missing.

Server configuration:

- `SITE_URL`: the exact website origin used for authenticated requests. The existing `NEXT_PUBLIC_APP_URL` is accepted when `SITE_URL` is unset; request headers and preview hostnames never supply this value.
- `AUTH_ALLOWED_ORIGINS`: optional comma-separated origins for local or preview authentication. Keep this explicit; do not allow every preview domain.
- `COMMUNITY_REGISTRATION_ENABLED`: defaults to disabled and requires exactly `true` to enable new registrations and TTN connections. Keep production disabled until strict ingress and the raw-data permission cutover are verified. Account reads and owned status changes remain available. See `DEPLOYMENT.md` for controlled preview testing.
- `PAYLOAD_STAFF_USER_IDS`: comma-separated Supabase user UUIDs allowed to inspect organizer inventory, bind verified radios to reservations, and issue one-time payload claims. Leave unset to disable staff access.
- `PAYLOAD_CLAIM_COOKIE_SECRET`: independent random 32-byte base64url server secret for short-lived claim cookies. Keep it out of browser variables and source control. Rotation clears pending browser claim sessions; fresh printed claim links remain valid.
- `SUPABASE_URL`: the database project's HTTPS URL.
- `SUPABASE_SERVICE_ROLE_KEY`: a server-only database key. `SUPABASE_SERVER_KEY` is accepted as an alternative name.
- `BLOB_READ_WRITE_TOKEN`: the existing private forecast store token.
- `TTN_WEBHOOK_SECRET`: optional rollout input for seeding an existing fleet integration. The new ingress handler authenticates scoped database credentials, not a global environment fallback.

Use the scoped community connection credentials for new TTN integrations. Never put server credentials in a `VITE_` or `NEXT_PUBLIC_` variable. The server also accepts `NEXT_PUBLIC_SUPABASE_URL` for existing forecast worker configuration; that value is a URL, not a key.

Historical migration files remain under `lib/supabase/migrations`; the current application history lives at the repository's `supabase/migrations`. The shared project has all four application migrations applied. The old chain has two files named with version `005` and must not be pushed as an automatically inferred migration history.

`supabase/migrations/20261007225324_private_raw_data_cutover.sql` records the completed production cutover, closing client access to raw tables, views and the legacy coordinate RPC. Its SQL is unchanged from the separately staged cutover script, including comments describing the original deployment order. For a new installation with the required legacy baseline, apply all current migrations before serving the new site. For an upgrade that still serves the old browser client, defer this final migration until the replacement server APIs are live and verified. The disposable database suite retains that staged sequence to verify compatibility and the final privacy boundary.

Activation URLs preserve their device context through GitHub sign-in. Ownership requires a fresh one-time claim issued through the staff API; a public device ID or old PIN is not proof. Callsign reservations and existing TTN identities retain their canonical device IDs. Follow [organizer onboarding](ONBOARDING.md) to verify manually provisioned radios and print fresh QR labels using `npm run onboarding:staff`. The tool uses the organizer's session, defaults to a read-only dry run and does not modify TTN devices or webhooks.

## Forecast worker

`.github/workflows/gfs-ingest.yml` retains the four daily NOAA ingestion runs. It builds GFS cubes, attempts the optional GEFS ensemble, computes forecasts and writes private Vercel Blob objects. The website reads those stored objects after checking that the balloon has a connected registry entry. It never proxies its own domain or runs an expensive forecast in response to a public request.

The workflow needs `SUPABASE_URL` (or the existing `NEXT_PUBLIC_SUPABASE_URL` secret), `SUPABASE_SERVICE_ROLE_KEY`, and `BLOB_READ_WRITE_TOKEN`. `HEALTHCHECK_URL` is optional. The worker uses its own TypeScript configuration, `tsconfig.worker.json`.

```sh
npm run forecast:compute -- stratolink-3 --dry
```

This requires that device's ingested cube in `WIND_CUBE_DIR` and server database credentials. A failed ingest or incomplete compute fails the job. A fleet with no active devices exits without downloading weather.

Engineering notes for the whole pipeline (cubes, tube ingest, compute, read path, data volumes and timing) live in [`docs/forecast/forecast-architecture.md`](../docs/forecast/forecast-architecture.md). Local iteration tools: `python3 scripts/_run_with_env.py scripts/gfs_ingest.py <device>` builds cubes with `.env.local` loaded, `npm run forecast:local -- <device> [--offline]` runs the compute on local cubes with Blob disabled, `npx tsx scripts/inspect_cube.ts <cube.slwc>` decodes a cube, and `node --env-file=.env.local scripts/blob_cleanup.mjs [--apply]` lists (or, with `--apply`, deletes) stale `cubes/*` and `forecasts/*.lock.json` Blob objects.

Before cutover, disable any external scheduler calling the retired `/api/compute-forecast` endpoint. The GitHub worker is the sole forecast writer. Confirm a successful scheduled run and a readable stored forecast in the deployed environment.

## Content

- `content/`: documentation and blog articles.
- `scripts/`: static page generation and search indexing.
- `src/`: page styling and interaction.
- `src/dashboard/`: the React dashboard.
- `server/` and `api/`: server handlers and Vercel entry points.
- `lib/ttn/`: firmware packet decoder and ingress contracts.
- `lib/wind/`: the existing forecast model and private worker storage.

Private research archives and original media are not copied into this repository. Public images, licensed favicon source data and the search model's license remain available with the site.

## Backend verification

Production cutover checks preserved the 1,517 telemetry rows in the pre-cutover snapshot, both devices, five radio identities and three integrations. Both anonymous and authenticated roles now lack table and column privileges on all seven application tables/views and execution privilege on the legacy coordinate RPC. Anonymous REST reads returned permission-denied errors while the public website APIs remained available. The private registry and account/ingestion RPCs remain inaccessible to browser roles. See [DEPLOYMENT.md](DEPLOYMENT.md) for the verification record and remaining registration checks.

The disposable PostgreSQL suite verifies ownership isolation, concurrent registration limits, exact TTN application/device/EUI matching, token rotation, independent delivery deduplication and the full cutover. Application webhooks acknowledge unrelated devices without writing data. A partially matching registered identity is rejected. Server reads expose only connected devices and redact protected launch coordinates before returning selected fields.

Supabase owns the PostGIS reference table and three `st_estimatedextent` functions. Their existing client grants require extension-owner authority to remove. The fail-closed script in [`supabase/platform-hardening`](../supabase/platform-hardening/README.md) is outside automatic migrations. No application table currently has geometry or geography columns. This residual platform issue does not block the application data cutover or justify bypassing the reserved role.

Production GitHub sign-in and stored forecast reads passed. The official verified TTN bindings remain intact. Production registration is still disabled pending Shepherd's environment change and redeploy; dedicated deployed TTN connection and QR claim checks remain before announcing registration. Verify the scheduled forecast worker separately from its readable stored output. Local and synthetic checks do not establish those external integrations.
