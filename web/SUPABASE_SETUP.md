# Supabase Setup Guide for Stratolink

## Step 1: Create Supabase Project

1. Go to https://supabase.com
2. Sign in or create an account
3. Click "New Project"
4. Fill in:
   - **Name:** Stratolink (or your preferred name)
   - **Database Password:** Create a strong password (save this - you'll need it)
   - **Region:** Choose closest to your deployment (for Vercel, US East is good)
5. Click "Create new project"
6. Wait 2-3 minutes for the project to be created

## Step 2: Get Your Supabase Credentials

1. Once your project is ready, go to **Settings** (gear icon in left sidebar)
2. Click **API** in the settings menu
3. You'll see two important values:
   - **Project URL** - Looks like: `https://xxxxx.supabase.co`
   - **anon public** key - A long JWT token starting with `eyJ...`

## Step 3: Update .env.local

Open `web/.env.local` and replace the placeholder values:

```
NEXT_PUBLIC_SUPABASE_URL=https://your-actual-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-actual-anon-key-here
```

## Step 4: Run the Database Schema

1. In Supabase dashboard, click **SQL Editor** in the left sidebar
2. Click **New query**
3. Open the file `web/lib/supabase/schema.sql` in your editor
4. Copy ALL the SQL code from that file
5. Paste it into the Supabase SQL Editor
6. Click **Run** (or press Cmd/Ctrl + Enter)
7. You should see "Success. No rows returned" - this is correct!

This creates:
- `telemetry` table for balloon tracking data
- Indexes for performance
- Security policies
- Helper functions and views

## Step 5: Verify Setup

1. In Supabase, go to **Table Editor** in the left sidebar
2. You should see a `telemetry` table listed
3. Click on it to see the table structure

## Step 6: Test the Connection

Restart your dev server and check the dashboard - it should now connect to Supabase without errors.
