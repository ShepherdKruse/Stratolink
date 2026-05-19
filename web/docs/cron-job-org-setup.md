# Free cron with cron-job.org (Vercel Hobby)

Use [cron-job.org](https://cron-job.org) to refresh wind forecasts every 30 minutes without Vercel Pro.

## Before you start (on Vercel)

1. App is deployed and working at `https://YOUR-DOMAIN.vercel.app`
2. **Environment variables** are set (Production):
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `CRON_SECRET` — long random string (save it; you’ll paste it into cron-job.org)
   - `BLOB_READ_WRITE_TOKEN` — from connected **private** Blob store
3. Redeploy after adding env vars

Generate a secret locally:

```bash
openssl rand -hex 32
```

## Step 1 — Create a cron-job.org account

1. Go to [https://cron-job.org](https://cron-job.org)
2. Sign up (free tier is enough)
3. Confirm your email if prompted

## Step 2 — Create the cron job

1. Click **Cronjobs** → **Create cronjob**
2. **Title:** `Stratolink wind forecast`

### URL & schedule

| Field | Value |
|--------|--------|
| **Address (URL)** | `https://YOUR-DOMAIN.vercel.app/api/compute-forecast` |
| **Schedule** | Every **30** minutes (or use custom: `*/30 * * * *`) |
| **Request method** | `GET` |

Replace `YOUR-DOMAIN` with your real Vercel hostname (e.g. `stratolink.vercel.app`).

### Authentication (important)

Open **Advanced** (or **Headers** / **Request settings**):

| Header name | Header value |
|-------------|----------------|
| `Authorization` | `Bearer YOUR_CRON_SECRET` |

Paste the **exact** same `CRON_SECRET` value from Vercel. Include the word `Bearer` and a space before the secret.

### Timeouts

- Set **timeout** to **60 seconds** if the UI allows it (Monte Carlo + Open-Meteo can take 15–45s).

### Optional: single device only

If you only fly one balloon and want faster runs:

```
https://YOUR-DOMAIN.vercel.app/api/compute-forecast?device=stratolink-3
```

Use your real `device_id` from Supabase.

3. **Save** the cronjob
4. Enable notifications only if you want email on failure

## Step 3 — Test once manually

On cron-job.org, use **Run now** / **Execute now** on the job.

Expected result: HTTP **200** and JSON like:

```json
{
  "ok": true,
  "devices": 1,
  "succeeded": 1,
  "elapsed_ms": 12000,
  "results": [{ "deviceId": "stratolink-3", "ok": true, ... }]
}
```

Or test from your terminal:

```bash
curl -i -H "Authorization: Bearer YOUR_CRON_SECRET" \
  "https://YOUR-DOMAIN.vercel.app/api/compute-forecast"
```

### Common errors

| HTTP | Meaning |
|------|---------|
| **401** | Wrong `Authorization` header or `CRON_SECRET` mismatch |
| **503** + `CRON_SECRET not configured` | Add `CRON_SECRET` in Vercel and redeploy |
| **503** + `BLOB_READ_WRITE_TOKEN` | Connect Vercel Blob to the project and redeploy |
| **504 / timeout** | Too many devices at once — use `?device=one-id` or upgrade timeout |

## Step 4 — Confirm the website uses the cache

1. Wait for a successful cron run
2. Open: `https://YOUR-DOMAIN.vercel.app/dashboard-v2/wind?device=YOUR_DEVICE_ID`
3. Map should load in a few seconds (not 15–20s live compute)

Check cache:

```bash
curl "https://YOUR-DOMAIN.vercel.app/api/forecast?device=YOUR_DEVICE_ID"
```

Should return **200** with forecast JSON.

## Schedule tips

| Interval | cron-job.org | Notes |
|----------|----------------|-------|
| Every 30 min | `*/30 * * * *` | Good default |
| Every 15 min | `*/15 * * * *` | Fresher; more Open-Meteo load |
| Hourly | `0 * * * *` | Fine for slow missions |

Free tier limits vary; 30-minute jobs are usually allowed.

## Security notes

- Never put `CRON_SECRET` in the URL query string (logs get leaked)
- Always use the `Authorization: Bearer …` header
- Private Blob keeps forecast files off public URLs; the map still works via your API

## Alternatives to cron-job.org

- **[cron-job.org](https://cron-job.org)** — recommended, simple UI
- **GitHub Actions** — free for repos; schedule workflow calling your URL (see user `forecast.yml` in Downloads module)
- **Uptime Robot** — can hit a URL on interval (monitoring-focused)
