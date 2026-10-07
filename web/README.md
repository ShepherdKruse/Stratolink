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

Server configuration:

- `SITE_URL`: the exact website origin used for authenticated requests.
- `AUTH_ALLOWED_ORIGINS`: optional comma-separated origins for local or preview authentication. Keep this explicit; do not allow every preview domain.
- `COMMUNITY_REGISTRATION_ENABLED`: defaults to disabled and requires exactly `true` to enable new registrations and TTN connections. Keep production disabled until strict ingress and the raw-data permission cutover are verified. Account reads and owned status changes remain available. See `DEPLOYMENT.md` for controlled preview testing.
- `SUPABASE_URL`: the database project's HTTPS URL.
- `SUPABASE_SERVICE_ROLE_KEY`: a server-only database key. `SUPABASE_SERVER_KEY` is accepted as an alternative name.
- `BLOB_READ_WRITE_TOKEN`: the existing private forecast store token.
- `TTN_WEBHOOK_SECRET`: optional rollout input for seeding an existing fleet integration. The new ingress handler authenticates scoped database credentials, not a global environment fallback.

Use the scoped community connection credentials for new TTN integrations. Never put server credentials in a `VITE_` or `NEXT_PUBLIC_` variable. The server also accepts `NEXT_PUBLIC_SUPABASE_URL` for existing forecast worker configuration; that value is a URL, not a key.

Apply the reviewed additive migrations before enabling the new APIs. Historical migration files remain under `lib/supabase/migrations`; new migrations live at the repository's `supabase/migrations`. The old chain has two files named with version `005` and must not be pushed as an automatically inferred migration history.

Keep `supabase/cutover/private_raw_data.sql` out of the initial migration run. Apply it only after the new deployed telemetry, account and ingestion endpoints pass their checks. This explicit cutover closes anonymous raw-table reads and the old sensitive RPCs; running it before replacing the old site would interrupt that site. The disposable database suite verifies this sequence.

Legacy activation, claim and admin pages currently redirect to the dashboard. This is not sufficient for existing printed QR labels: preserve their entry URLs and device context in a GitHub-owned claim flow before deployment. Claim the existing device rather than creating a duplicate or re-provisioning its TTN credentials. The compatibility review and remaining requirements are in `DEPLOYMENT.md`.

## Forecast worker

`.github/workflows/gfs-ingest.yml` retains the four daily NOAA ingestion runs. It builds GFS cubes, attempts the optional GEFS ensemble, computes forecasts and writes private Vercel Blob objects. The website reads those stored objects after checking that the balloon has a connected registry entry. It never proxies its own domain or runs an expensive forecast in response to a public request.

The workflow needs `SUPABASE_URL` (or the existing `NEXT_PUBLIC_SUPABASE_URL` secret), `SUPABASE_SERVICE_ROLE_KEY`, and `BLOB_READ_WRITE_TOKEN`. `HEALTHCHECK_URL` is optional. The worker uses its own TypeScript configuration, `tsconfig.worker.json`.

```sh
npm run forecast:compute -- stratolink-3 --dry
```

This requires that device's ingested cube in `WIND_CUBE_DIR` and server database credentials. A failed ingest or incomplete compute fails the job. A fleet with no active devices exits without downloading weather.

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

The additive migrations preserve the existing 1,513 telemetry rows. Live permission checks confirm that anonymous and signed-in clients cannot write flight records, read owner UUIDs or claim codes, access the private registry, or execute account and ingestion RPCs. The old dashboard's six-column device read remains available until cutover. Raw legacy telemetry reads remain available until the separate cutover script runs.

The disposable PostgreSQL suite verifies ownership isolation, concurrent registration limits, exact TTN application/device/EUI matching, token rotation, independent delivery deduplication and the full cutover. Application webhooks acknowledge unrelated devices without writing data. A partially matching registered identity is rejected. Server reads expose only connected devices and redact protected launch coordinates before returning selected fields.

Supabase owns the PostGIS reference table and three `st_estimatedextent` functions. Their existing client grants require extension-owner authority to remove. The fail-closed script in [`supabase/platform-hardening`](../supabase/platform-hardening/README.md) is outside automatic migrations. No application table currently has geometry or geography columns. This residual platform issue does not block the application data cutover or justify bypassing the reserved role.

Before production activation, verify GitHub sign-in and redirects, seed the official verified TTN bindings, test a real scoped webhook delivery, and verify the forecast worker against the deployed private store. Local and synthetic checks do not establish those external integrations.
