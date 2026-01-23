# Mission Control Dashboard - Setup Guide

## Step 1: Configure Mapbox Access Token

1. **In the Mapbox page you have open:**
   - Token name is already set to "Stratolink" ✓
   - **Token Scopes:** Keep the public scopes checked (STYLES:TILES, STYLES:READ, FONTS:READ, DATASETS:READ, VISION:READ)
   - **Token Restrictions (URLs):** Add these URLs:
     - `http://localhost:3000` (for local development)
     - `https://your-vercel-app.vercel.app` (add this after you deploy to Vercel)
   - Click "Add URL" after entering each one
   - Click "Create token" or "Save" button

2. **Copy the token** - It will look like `pk.eyJ1Ijoi...` (starts with `pk.`)

3. **Save the token:**
   - Create a file called `.env.local` in the `web/` directory
   - Add your token:
     ```
     NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_actual_token_here
     ```

## Step 2: Configure Supabase Environment Variables

1. **Get your Supabase credentials:**
   - Go to https://supabase.com and open your project
   - Navigate to Settings → API
   - Copy your "Project URL" and "anon public" key

2. **Add to `.env.local`:**
   ```
   NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_mapbox_token
   NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here
   ```

## Step 3: Set Up Database Schema

1. **Open Supabase SQL Editor:**
   - Go to your Supabase project dashboard
   - Click "SQL Editor" in the left sidebar

2. **Run the schema:**
   - Open the file `web/lib/supabase/schema.sql`
   - Copy all the SQL code
   - Paste it into the Supabase SQL Editor
   - Click "Run" to execute

   This creates:
   - `telemetry` table for balloon tracking data
   - Indexes for performance
   - Security policies
   - Helper functions

## Step 4: Install Dependencies (if not already done)

```bash
cd web
npm install
```

## Step 5: Start Development Server

```bash
npm run dev
```

The dashboard will be available at: **http://localhost:3000**

## Step 6: Test the Dashboard

1. Open http://localhost:3000 in your browser
2. You should see:
   - Full-screen 3D globe map (dark theme)
   - Glassmorphism sidebar on the left
   - Fleet status showing "Active: 0" and "Landed: 0"
   - Toggle button to switch between 3D Globe and 2D Mercator

## Step 7: Deploy to Vercel (When Ready)

1. **Push your code to GitHub** (already done ✓)

2. **Connect to Vercel:**
   - Go to https://vercel.com
   - Import your GitHub repository
   - Add environment variables in Vercel dashboard:
     - `NEXT_PUBLIC_MAPBOX_TOKEN`
     - `NEXT_PUBLIC_SUPABASE_URL`
     - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

3. **Update Mapbox token restrictions:**
   - Add your Vercel deployment URL to the Mapbox token restrictions
   - Format: `https://your-app-name.vercel.app`

## Troubleshooting

**Map not showing?**
- Check that `NEXT_PUBLIC_MAPBOX_TOKEN` is set correctly in `.env.local`
- Restart the dev server after adding environment variables
- Check browser console for errors

**Database errors?**
- Verify Supabase credentials are correct
- Ensure the schema SQL was run successfully
- Check Supabase dashboard for table creation

**Build errors?**
- Run `npm install` to ensure all dependencies are installed
- Check that Node.js version is 18+
