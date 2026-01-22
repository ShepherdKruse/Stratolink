# Stratolink

Global pico-balloon telemetry system using RAK3172 LoRaWAN module with Next.js ground station.

## Architecture

1. Flight Hardware: RAK3172 (STM32WLE5) microcontroller running Arduino Framework
2. Telemetry Transport: The Things Network (TTN) LoRaWAN
3. Ground Station: Next.js App Router hosted on Vercel
4. Database: Supabase PostgreSQL
5. Data Flow: TTN HTTP Webhook -> Next.js API Route -> Supabase

## Repository Structure

```
/stratolink-monorepo
├── /firmware                  # PlatformIO Project (C++)
│   ├── /src
│   │   ├── main.cpp
│   │   ├── region_manager.cpp
│   │   └── power_manager.cpp
│   ├── /include
│   │   ├── config.h           # Template for User Keys
│   │   └── secrets.h          # GITIGNORED
│   ├── platformio.ini
│   └── flash_firmware.bat
├── /web                       # Next.js Project (Ground Station)
│   ├── /app
│   │   ├── /api/ttn-webhook   # API Route
│   │   └── /dashboard         # Frontend map
│   ├── /lib
│   │   └── supabase.ts
│   └── package.json
├── .gitignore
└── setup_repo.sh
```

## Prerequisites

1. PlatformIO CLI or PlatformIO IDE
2. Node.js 18 or higher
3. Supabase account
4. The Things Network account
5. RAK3172 development board

## Quick Start

### Firmware Setup

1. Navigate to firmware directory: `cd firmware`
2. Copy `include/config.h` values to `include/secrets.h`
3. Edit `include/secrets.h` with your TTN credentials:
   - DEV_EUI
   - APP_EUI
   - APP_KEY
4. Build firmware: `pio run`
5. Upload to device: `pio run --target upload`

### Web Application Setup

1. Navigate to web directory: `cd web`
2. Install dependencies: `npm install`
3. Copy `.env.local.example` to `.env.local`
4. Configure Supabase credentials in `.env.local`:
   - NEXT_PUBLIC_SUPABASE_URL
   - NEXT_PUBLIC_SUPABASE_ANON_KEY
5. Run database schema: Execute `supabase_schema.sql` in Supabase SQL Editor
6. Start development server: `npm run dev`

### TTN Webhook Configuration

1. Log into The Things Network console
2. Navigate to Applications > Your Application > Integrations > Webhooks
3. Add webhook with format: JSON
4. Set webhook URL: `https://your-vercel-domain.com/api/ttn-webhook`
5. Save webhook configuration

## Configuration Files

### firmware/include/config.h

Template configuration file with placeholder values. Contains:
- LoRaWAN region settings
- GNSS configuration
- Power management settings
- Debug options

### firmware/include/secrets.h

Sensitive credentials file. This file is gitignored. Contains:
- LoRaWAN DEV_EUI
- LoRaWAN APP_EUI
- LoRaWAN APP_KEY

### web/.env.local

Environment variables for Next.js application. This file is gitignored. Contains:
- Supabase project URL
- Supabase anonymous key
- Optional service role key

## Development

### Building Firmware

```bash
cd firmware
pio run
```

### Flashing Firmware

```bash
cd firmware
pio run --target upload
```

Or use the provided script:
```bash
./flash_firmware.bat
```

### Running Web Application

Development mode:
```bash
cd web
npm run dev
```

Production build:
```bash
cd web
npm run build
npm start
```

## Database Schema

The telemetry table stores:
- Device identification
- Timestamp of reception
- GPS coordinates (latitude, longitude, altitude)
- Battery voltage
- Environmental data (temperature, pressure)
- Raw payload data

See `web/supabase_schema.sql` for complete schema definition.

## Security Notes

1. Never commit `firmware/include/secrets.h` to version control
2. Never commit `web/.env.local` to version control
3. Use Supabase Row Level Security policies for data access control
4. Validate and sanitize all webhook inputs
5. Use HTTPS for all production endpoints

## License

[Specify your license here]

## Contributing

[Specify contribution guidelines here]
