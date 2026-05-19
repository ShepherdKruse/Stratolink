# Wind forecast on Vercel

Monte Carlo drift forecasts run on Stratolink via **live compute** and optional **Vercel Blob cache** refreshed by cron.

## Architecture

```
Vercel Cron (every 30 min, Pro plan)
  → GET /api/compute-forecast
  → Supabase telemetry + computeMonteCarloForecast
  → Vercel Blob  forecasts/{deviceId}.json

Browser (Wind Outlook)
  → GET /api/forecast?device=…     (fast, cached blob)
  → else POST /api/wind-forecast   (live compute fallback)
```

## One-time Vercel setup

### 1. Project root directory

In **Vercel → Project → Settings → General → Root Directory**, set:

```
web
```

The repo’s root `vercel.json` cron path assumes the Next.js app lives in `web/`.

### 2. Environment variables

Add these in **Vercel → Settings → Environment Variables** (Production + Preview):

| Variable | Required | Notes |
|----------|----------|--------|
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Yes | Map |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Telemetry |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Client telemetry |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Cron + server forecast input |
| `CRON_SECRET` | Recommended | Random string; secures `/api/compute-forecast` |
| `BLOB_READ_WRITE_TOKEN` | For cron cache | Auto-created when you connect Blob storage |

### 3. Vercel Blob storage

1. **Vercel Dashboard → Storage → Create → Blob**
2. Connect the store to your Stratolink project
3. Redeploy — `BLOB_READ_WRITE_TOKEN` is injected automatically

Without Blob, the site still works: Wind Outlook uses **POST `/api/wind-forecast`** on each refresh.

### 4. Cron (30-minute refresh)

`vercel.json` registers:

```json
{ "path": "/api/compute-forecast", "schedule": "*/30 * * * *" }
```

**Requires Vercel Pro** for sub-hourly cron. On Hobby, trigger manually:

```bash
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  "https://YOUR_DOMAIN.vercel.app/api/compute-forecast"
```

Or use [cron-job.org](https://cron-job.org) to hit that URL every 30 minutes.

### 5. Deploy

Push to GitHub (or `vercel deploy`). After deploy:

1. Open `https://YOUR_DOMAIN/dashboard-v2/wind?device=YOUR_DEVICE_ID`
2. First visit may take **10–20s** (live Monte Carlo + Open-Meteo)
3. After cron runs, reload should be **&lt;1s** (blob cache)

## Manual operations

**Warm cache for one device:**

```bash
curl -H "Authorization: Bearer $CRON_SECRET" \
  "https://YOUR_DOMAIN.vercel.app/api/compute-forecast?device=stratolink-3"
```

**Read cached forecast:**

```bash
curl "https://YOUR_DOMAIN.vercel.app/api/forecast?device=stratolink-3"
```

**Force live compute (no cache):**

Use **Refresh** on the map after clearing blob, or POST to `/api/wind-forecast` from the browser network tab.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Map empty / “Forecast failed” | Check Vercel function logs for `/api/wind-forecast`; confirm device has GPS rows in Supabase |
| Cron 503 `BLOB_READ_WRITE_TOKEN` | Connect Blob store and redeploy |
| Cron 401 | Set `CRON_SECRET` in Vercel; Vercel Cron sends `Authorization: Bearer …` automatically when the secret is configured |
| Slow every load | Cron not running or Blob missing — run manual `compute-forecast` once |
| Function timeout | Reduce active devices or upgrade function `maxDuration` (currently 60s) |

## Local development

`.env.local` needs the same Supabase + Mapbox vars. Blob is optional locally; without it you always use live POST.

To test cron locally:

```bash
curl -H "Authorization: Bearer dev-secret" \
  "http://localhost:3000/api/compute-forecast?device=YOUR_DEVICE_ID"
```

Set `CRON_SECRET=dev-secret` in `.env.local`.
