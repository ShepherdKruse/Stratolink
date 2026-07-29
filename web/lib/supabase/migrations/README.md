# Supabase Migrations

## Running Migrations

Use the Supabase CLI migration workflow for new changes. Existing installations
must apply the files in lexical/order dependency order:

**001** → **003** → **004** → **005_acoustic_event** →
**005_add_uv_lux_acoustic** → **006** → **007** → **008** → **009** →
**010** → **20260725090324** → **20260725184000** → **20260725222000**

Expanded exact order (both historical `005` files are required):

`001_launchpad_devices.sql` → `003_fix_devices_rls.sql` →
`004_add_telemetry_fields.sql` → `005_acoustic_event.sql` →
`005_add_uv_lux_acoustic.sql` → `006_launch_token.sql` →
`007_allow_nogps_telemetry.sql` → `008_telemetry_system_state.sql` →
`009_wildlife_detections.sql` → `010_b2b_packets.sql` →
`20260725090324_ttn_ingest_integrity.sql` →
`20260725184000_ctt_detection_age.sql` →
`20260725222000_telemetry_observability_v2.sql`.

The duplicate `005` prefix predates adoption of timestamped Supabase migration
versions. Do not rename already-applied history or ask the CLI to infer an order
from those two version labels; apply both legacy files in the explicit order
above when bootstrapping an existing/manual installation. Create every new
migration with a unique timestamped version.

Do not deploy only the webhook code: the authenticated route requires the
auxiliary tables and the TTN session/counter columns from the final migration.

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
Apply this before flashing telemetry v2; historical 35-byte rows remain valid.

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
