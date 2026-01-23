# Mission Control Dashboard - Installation

## Required npm Packages

Run the following command to install all required dependencies:

```bash
npm install react-map-gl mapbox-gl tailwindcss@3.4.1 postcss autoprefixer @types/mapbox-gl
```

## Environment Variables

Copy `.env.local.example` to `.env.local` and fill in:

- `NEXT_PUBLIC_MAPBOX_TOKEN` - Your Mapbox access token (get from https://account.mapbox.com/)
- `NEXT_PUBLIC_SUPABASE_URL` - Your Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` - Your Supabase anonymous key

## Database Setup

Run the SQL script in `lib/supabase/schema.sql` in your Supabase SQL Editor to create the telemetry table.

## Development

```bash
npm run dev
```

The Mission Control dashboard will be available at http://localhost:3000
