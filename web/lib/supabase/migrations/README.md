# Supabase Migrations

## Running Migrations

1. Open Supabase Dashboard → SQL Editor
2. Copy and paste the SQL from each migration file
3. Run the SQL in order (001, then 002, etc.)

## Migration Files

### 001_launchpad_devices.sql
Creates the `devices` table and adds launchpad functionality columns.

**Run this first** to set up the device activation system.

### 002_test_devices.sql
Creates test devices for development and testing.

**Run this after 001** to populate test data.

### 003_fix_devices_rls.sql
Fixes Row Level Security (RLS) policies for the devices table.

**Run this if you're getting "device not found" errors when trying to activate devices.**

This migration ensures that the anon key can insert and update devices, which is required for the auto-creation feature in development mode.

## Test Devices

After running `002_test_devices.sql`, you can use these devices for testing:

- **balloon-001** - PIN: `123456`
- **balloon-002** - PIN: `234567`
- **balloon-003** - PIN: `345678`
- **balloon-042** - PIN: `042042`
- **balloon-test** - PIN: `000000`

## Development Mode

In development mode (`NODE_ENV=development`), the activation system will:
- Auto-create devices if they don't exist
- Generate a random 6-digit PIN
- Display the PIN in the error message if activation fails

This allows you to test the activation flow without pre-creating devices in the database.
