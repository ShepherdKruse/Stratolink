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

1. Create a Supabase project at https://supabase.com
2. Copy `web/.env.local.example` to `web/.env.local`
3. Fill in your Supabase credentials:
   - `NEXT_PUBLIC_SUPABASE_URL`: Found in Project Settings > API
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Found in Project Settings > API

## Step 3: Install Web Dependencies

Dependencies have been installed. If you need to reinstall:

```bash
cd web
npm install
```

## Step 4: Create Supabase Database Schema

1. Open your Supabase project dashboard
2. Navigate to SQL Editor
3. Copy and paste the contents of `web/supabase_schema.sql`
4. Execute the SQL to create the telemetry table and indexes

## Additional Configuration

### TTN Webhook Setup

1. In The Things Network console, navigate to your application
2. Go to Integrations > Webhooks
3. Add a new webhook with:
   - Webhook ID: `stratolink-webhook`
   - Webhook URL: `https://your-vercel-domain.com/api/ttn-webhook`
   - Format: JSON

### Running the Development Server

```bash
cd web
npm run dev
```

The dashboard will be available at http://localhost:3000

### Building Firmware

```bash
cd firmware
pio run
```

To upload to device:
```bash
pio run --target upload
```
