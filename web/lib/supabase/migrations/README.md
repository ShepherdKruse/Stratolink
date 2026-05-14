# Supabase Migrations

## Running Migrations

1. Open Supabase Dashboard → SQL Editor
2. Copy and paste the SQL from each migration file
3. Run the SQL in order: **001** → **003** → **004** / **005** (telemetry columns) → **006** (launch QR tokens)

## Migration Files

### 006_launch_token.sql
Adds `launch_token_hash` and `launch_token_expires_at` on `devices` for QR launch links (`?k=` on `/activate/[deviceId]`).

**Run after** `devices` exists. Required for seamless launch QR flow.

### 001_launchpad_devices.sql
Creates the `devices` table and adds launchpad functionality columns.

**Run this first** to set up the device activation system.

### 003_fix_devices_rls.sql
Fixes Row Level Security (RLS) policies for the devices table.

**Run this after 001** to enable device activation.

This migration ensures that the anon key can insert and update devices, which is required for the auto-creation feature in development mode.

## Development Mode

In development mode (`NODE_ENV=development`), the activation system will:
- Auto-create devices if they don't exist
- Use the PIN you provide as the claim code
- Allow re-activation of devices already in flight

This allows you to test the activation flow without pre-creating devices in the database.

## Production Security

**Important:** Auto-creation is disabled in production for security. In production:
- Devices must be pre-registered in the database before activation
- Users must use the correct PIN that matches the device's `claim_code`
- This prevents unauthorized device creation

To manually create devices in production, use the Supabase dashboard, **`/admin/register-payload`** (TTN + DB + launch link), or `createDeviceAdmin` with `ADMIN_ACTIVATION_KEY`.

**Activation** (`/activate/...`) uses the **service role** on the server: set `SUPABASE_SERVICE_ROLE_KEY` in production or activation will fail.

## Test Data

For test devices and development data, see the `.internal` folder (not included in public repository).
