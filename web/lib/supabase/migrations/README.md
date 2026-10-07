# Supabase Migrations

## Running Migrations

Use the Supabase CLI migration workflow for new changes. This historical
directory is not itself a directly pushable Supabase CLI project: it is outside
`supabase/migrations`, and the two legacy `005` files intentionally share one
version. Do not point `supabase db push` at production and expect it to infer
this chain.

For the existing StratoLink installation, first bind a database-admin channel
to the verified StratoLink project, inventory its live columns, constraints,
grants, and `supabase_migrations.schema_migrations` history, and preserve a
telemetry export. Then execute only the missing reviewed files, one at a time,
in the dependency order below. Record the target project reference, file
SHA-256, start/end time, and result for each file without recording credentials.
The database channel may be a correctly scoped Supabase SQL/MCP connection or
the SQL editor opened on that exact project. On October 5, direct access to
StratoLink project `iazmnyyfsobucndqncgw` was verified despite its omission from
project listing; an unrelated listed project must never be used instead.

Existing installations must apply the files in this dependency order:

**001** → **003** → **004** → **005_acoustic_event** →
**005_add_uv_lux_acoustic** → **006** → **007** → **008** → **009** →
**010** → **20260725090324** → **20260725184000** → **20260725222000** →
**20260831043000** → **20261005194611**

Expanded exact order (both historical `005` files are required):

`001_launchpad_devices.sql` → `003_fix_devices_rls.sql` →
`004_add_telemetry_fields.sql` → `005_acoustic_event.sql` →
`005_add_uv_lux_acoustic.sql` → `006_launch_token.sql` →
`007_allow_nogps_telemetry.sql` → `008_telemetry_system_state.sql` →
`009_wildlife_detections.sql` → `010_b2b_packets.sql` →
`20260725090324_ttn_ingest_integrity.sql` →
`20260725184000_ctt_detection_age.sql` →
`20260725222000_telemetry_observability_v2.sql` →
`20260831043000_telemetry_server_liveness_v3.sql` →
`20261005194611_telemetry_raw_evidence.sql`.

The duplicate `005` prefix predates adoption of timestamped Supabase migration
versions. Do not rename already-applied history or ask the CLI to infer an order
from those two version labels; apply both legacy files in the explicit order
above when bootstrapping an existing/manual installation. Create every new
migration with a unique timestamped version.

Do not deploy only the webhook code: the authenticated route requires the
auxiliary tables, TTN delivery-identity columns, and telemetry-v3 columns from
the complete chain through the final migration.

### Live transition invariant

Migrations `20260725222000` and `20260831043000` deliberately install their
telemetry checks `NOT VALID`. PostgreSQL therefore avoids scanning and rejecting
historical drift while still checking each later insert/update. During the
schema-first cutover, the old unauthenticated route continues writing rows with
`ttn_device_id IS NULL`; both GPS and observability checks contain an explicit
identity-null transition branch for those rows. The hardened route requires and
writes a non-null TTN device ID, so its rows immediately receive the strict
v1/v2/v3 checks. Do not remove that branch before the old deployment has been
retired and its rollback window has closed.

The live order is: stage the complete schema, verify the public schema contract,
configure the same independent webhook secret in the production web environment
and every regional TTN webhook, deploy the hardened web build, then prove a new
identity-bearing v3 row. Historical identity-null rows must not be assigned
guessed TTN identity. Audit them before optionally validating constraints.

## Migration Files

### 006_launch_token.sql
Adds `launch_token_hash` and `launch_token_expires_at` on `devices` for QR launch links (`?k=` on `/activate/[deviceId]`).

**Run after** `devices` exists. Required for seamless launch QR flow.

### 001_launchpad_devices.sql
Creates the `devices` table and adds launchpad functionality columns.

**Run this first** to set up the device activation system.

### 003_fix_devices_rls.sql
Historical development policy for the devices table.

**Run this after 001** to enable device activation.

### 005_acoustic_event.sql and 005_add_uv_lux_acoustic.sql

Historical two-step sensor schema transition. Apply both in the exact order
shown above. The second file adds UV/lux, removes nonexistent gyro channels,
and replaces the intermediate `latest_telemetry` view; only the resulting
post-second-file schema is current.

This file allowed anonymous inserts/updates for the original browser-side
development flow. The later integrity migration revokes those privileges; all
current mutations use server-side service-role actions.

### 009_wildlife_detections.sql

Creates the typed fPort-11 CTT/Motus event table with public read-only access.

### 010_b2b_packets.sql

Creates the typed fPort-12 authenticated wire-v3 balloon-to-balloon tunnel
table with service-role-only access.

### 20260725090324_ttn_ingest_integrity.sql

Adds raw TTN device/session/FCntUp identity and unique indexes for idempotent
webhook delivery. Revokes anonymous table writes, removes public access to
claim codes/token hashes, and makes `latest_telemetry` security-invoker.

### 20260725184000_ctt_detection_age.sql

Adds fPort-11 wire-version, queue-age, and derived detection-time fields so a
delayed auxiliary uplink does not relabel an earlier wildlife detection with
its TTN receipt time. Legacy wire-v1 rows retain their listen-window value.

### 20260725222000_telemetry_observability_v2.sql

Adds nullable, range-constrained columns for the exact 40-byte primary
telemetry-v2 health fields: power tier, reset cause, boot count, fresh-fix age,
command acknowledgement, retained relay state, and relay/CTT activity deltas.
The version-coherence constraint preserves historical NULL-version rows,
requires v1 rows to omit every v2-only field, and requires each v2 status field
that is always present on wire; fresh-fix age and command ACK may remain NULL to
represent their explicit wire sentinels.
Every check is installed `NOT VALID` and the two row-coherence checks exempt
only identity-null writes from the legacy production route. Identity-bearing
rows are strict immediately, including during the rollback window.
Apply this before flashing telemetry v2; historical 35-byte rows remain valid.

### 20260831043000_telemetry_server_liveness_v3.sql

Adds the three telemetry-v3 server-liveness fields packed into bytes 36-37:
authenticated proof count modulo 8, qualified-miss streak, and session-recovery
parity. Version coherence keeps 35-byte v1 and 40-byte v2 rows unchanged while
requiring every v3 liveness value and its bounded 0..510-minute fix age. Apply
this migration before deploying the v3 webhook and before accepting v3 packets
as production soak or flight evidence.
All new checks are installed `NOT VALID`: PostgreSQL still enforces them for
every new or updated row without scanning historical data during deployment.
The version-coherence check's identity-null transition branch preserves live
writes from the old formatter, including rows it labels v2 without populating
all v2 status columns. Validate constraints only after historical rows are
explicitly audited; do not invent identity or sensor values merely to make a
validation pass.

### 20261005194611_telemetry_raw_evidence.sql

Preserves primary on-air bytes in `frm_payload`, their `f_port`, and the
existing normalized `gateways` shape. These three columns already exist in
production; the additive migration makes new installations match and adds
`rx_metadata` for the complete, unmodified TTN gateway metadata array.
All columns remain nullable and no historical rows are rewritten. Apply before
deploying the raw-preserving webhook. `gateways` remains strongest-first with
the established `gateway_id`, `rssi`, `snr`, `lat`, `lon`, and `alt` fields, so
existing dashboard consumers and rollback deployments retain their contract.

## Development Mode

Only on the actual local development server (`NODE_ENV=development`), the
activation system will:
- Auto-create devices if they don't exist
- Use the PIN you provide as the claim code
- Allow re-activation of devices already in flight

This allows you to test the activation flow without pre-creating devices in the
database. Auto-creation still occurs through a server-side service-role client;
the anonymous Data API remains read-only. Browser-visible flags, Vercel preview
environments, and device-ID contents cannot enable this path.

## Production Security

**Important:** Auto-creation is disabled in production for security. In production:
- Devices must be pre-registered in the database before activation
- The TTN webhook rejects uplinks from unregistered devices
- Users must use the correct PIN that matches the device's `claim_code`
- This prevents unauthorized device creation

To manually create devices in production, use the Supabase dashboard, **`/admin/register-payload`** (TTN + DB + launch link), or `createDeviceAdmin` with `ADMIN_ACTIVATION_KEY`.

**Activation** (`/activate/...`) uses the **service role** on the server: set `SUPABASE_SERVICE_ROLE_KEY` in production or activation will fail.

## Test Data

For test devices and development data, see the `.internal` folder (not included in public repository).
