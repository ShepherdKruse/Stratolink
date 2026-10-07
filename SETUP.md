# Stratolink Setup Instructions

## Step 1: Configure Firmware Secrets

Edit `firmware/include/secrets.h` and replace the placeholder values:

```cpp
#define LORAWAN_DEV_EUI "your_actual_dev_eui"
#define LORAWAN_APP_EUI "your_actual_app_eui"
#define LORAWAN_APP_KEY "your_actual_app_key"
```

These values are obtained from The Things Network (TTN) console when you register your device.

## Step 2: Configure Supabase Environment Variables

1. Use the intended Supabase project and copy `web/.env.example` to `web/.env.local`.
2. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` for browser authentication.
3. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for server database access. Never prefix the service role key with `VITE_` or `NEXT_PUBLIC_`.
4. Set `NEXT_PUBLIC_MAPBOX_TOKEN`, the exact deployed `SITE_URL`, and `BLOB_READ_WRITE_TOKEN` for stored forecasts. Add explicit local or preview origins through `AUTH_ALLOWED_ORIGINS` when needed.

See [web/README.md](web/README.md#deployment) for the full environment contract. The dashboard reads telemetry through the website API; the publishable key is used only for authentication.

## Step 3: Install Web Dependencies

Use Node.js 22 and install the locked dependencies:

```bash
cd web
ONNXRUNTIME_NODE_INSTALL=skip npm ci
```

## Step 4: Prepare the Database and Authentication

1. Review the existing database and migration history before applying `supabase/migrations/`. The shared project already has all four application migrations, including the raw-data privacy cutover. Do not run the historical `web/lib/supabase/` chain as an automatically inferred migration history; it contains duplicate version names.
2. Configure a GitHub OAuth application with the callback URL supplied by Supabase, then add its credentials to the project's GitHub auth provider.
3. Add the exact site callback URL, `https://your-domain/dashboard`, to Supabase's redirect allowlist. Add each local callback explicitly, using the local server's actual origin and `/dashboard` path.
4. Run `npm run verify` in `web`. Run `npm run test:backend` with Docker to check the schema and API against a disposable local database.
5. `supabase/migrations/20261007225324_private_raw_data_cutover.sql` records the completed production privacy cutover. On a new installation with the required legacy baseline, apply the current migration sequence before serving the new site. When upgrading an installation still using the old browser client, defer this final migration until the replacement server APIs are live and verified. Its original comments describe that staged upgrade; the SQL is retained unchanged to match the applied migration.

The full deployment sequence is in [web/README.md](web/README.md#deployment). Running the old schema file alone is not sufficient to configure this backend.

## Additional Configuration

### TTN Webhook Setup

1. Sign in with GitHub on the dashboard and register the balloon.
2. In **Your balloons > Connect TTN**, enter the TTN cluster, application ID and that regional device's DevEUI. Supply an application API key with permission to read end devices. It is used for verification, then discarded.
3. In TTN, open **Integrations > Webhooks** and add a custom JSON webhook. Copy the URL and `Authorization` header returned by the dashboard, and enable uplink messages.
4. Send a packet and confirm a received timestamp. Add each additional regional identity to the same balloon.

The webhook secret is shown once. Reconnecting replaces that network connection's secret, so update its TTN webhook before expecting new packets.

### Running the Development Server

```bash
cd web
npm run dev
```

Open the local URL printed by Vite, then `/dashboard`. The default development URL is `http://127.0.0.1:5173/dashboard`. Add that exact origin to `AUTH_ALLOWED_ORIGINS` and its `/dashboard` callback to Supabase if testing sign-in there.

### Deploying the Website

Use Vercel Root Directory `web`, the Vite preset and output directory `dist`. Run `npm run verify` before deploying. Configure the server environment and complete the database cutover described in [web/README.md](web/README.md#deployment).

The scheduled forecast worker remains in `.github/workflows/gfs-ingest.yml`. Confirm a successful worker run and a readable stored forecast before retiring any old scheduler.

### Building Firmware

```bash
cd firmware
pio run
```

To upload to device:
```bash
pio run --target upload
```
