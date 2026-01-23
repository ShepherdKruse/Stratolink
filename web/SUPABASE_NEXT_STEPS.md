# Supabase Setup - Next Steps

## ✅ Completed

1. ✓ Supabase credentials added to `.env.local`
2. ✓ Database schema created (telemetry table, indexes, functions)
3. ✓ PostGIS extension enabled
4. ✓ Webhook route updated to match schema

## 🧪 Test the Connection

1. **Open your dashboard:** http://localhost:3000
2. **Check the browser console** (F12 → Console)
   - Should see no Supabase errors
   - Fleet status should show "Active: 0" and "Landed: 0" (no data yet)

## 📊 Add Test Data (Optional)

To verify everything works, you can add test data directly in Supabase:

1. Go to Supabase → **Table Editor** → `telemetry` table
2. Click **Insert row**
3. Add a test entry:
   - `device_id`: `test-balloon-1`
   - `time`: (current timestamp)
   - `lat`: `40.7128` (New York)
   - `lon`: `-74.0060`
   - `altitude_m`: `15000`
4. Click **Save**

The dashboard should now show "Active: 1" if the data is recent (within last hour).

## 🔗 Connect TTN Webhook

When ready to receive real telemetry:

1. In The Things Network console, go to your application
2. Navigate to **Integrations** → **Webhooks**
3. Add webhook:
   - **Webhook ID:** `stratolink-webhook`
   - **Webhook URL:** `https://your-vercel-domain.com/api/ttn-webhook`
   - **Format:** JSON
4. Save

## 📝 Payload Parsing

The webhook route currently has TODO comments for parsing the telemetry payload. You'll need to:

1. Define your payload format (how GPS, altitude, etc. are encoded)
2. Update `web/app/api/ttn-webhook/route.ts` to parse the decoded payload
3. Map the parsed values to the database columns

## 🎯 Current Status

- Database: ✓ Ready
- Connection: ✓ Configured
- Webhook endpoint: ✓ Ready (needs payload parsing)
- Dashboard: ✓ Connected and displaying data
