# Balloon wind-forecast architecture

How Stratolink predicts where a balloon will drift, and reconstructs where it has
been — entirely from **self-ingested NOAA GFS** wind data, with **no live weather
API** in the hot path.

> This is the authoritative overview as of 2026-06 (the GFS self-ingest era).
> The older `wind-forecast-vercel.md` describes the original Open-Meteo
> live-compute design and is superseded; only its Vercel env-var / setup reference
> is still current.

---

## 1. The big picture

```
                 GitHub Actions (6-hourly: 05/11/17/23 UTC) — free, repo is public
                 ┌──────────────────────────────────────────────────────────┐
                 │ scripts/gfs_ingest.py                                      │
                 │   • find flying devices + their full-mission GPS fixes      │
                 │     (Supabase)                                             │
                 │   • byte-range GETs of GFS U/V GRIB from NOAA NODD S3       │
                 │   • build TWO cubes per device (forecast + reconstruction)  │
                 │ scripts/upload_cubes.mjs → gzip → Vercel Blob               │
                 └──────────────────────────────────────────────────────────┘
                                          │  cubes/{device}.json.gz
                                          │  cubes/{device}-fc.json.gz
                                          ▼
   cron-job.org (~25–30 min)   ┌───────────────────────────────────────────┐
   GET /api/compute-forecast → │ computeMonteCarloForecast (Vercel function) │
   (Bearer CRON_SECRET)        │   • read both cubes from Blob               │
                               │   • bias-fit, AR(1) ensemble, dead-reckon   │
                               │   • reconstruct historical track            │
                               │ → Blob forecasts/{device}.json              │
                               └───────────────────────────────────────────┘
                                          │
   Browser (dashboard)  GET /api/forecast?device=…  (CDN max-age=300)
                                          ▼
                              the stored forecast JSON
```

Three independent tiers, each cheap and rate-limit-free:

| Tier | Where | Cadence | Cost |
|---|---|---|---|
| **Ingest** (wind data → cubes) | GitHub Actions | 6-hourly | free (public repo) |
| **Compute** (cubes → forecast) | Vercel fn via cron-job.org | ~25–30 min | Vercel fn time |
| **Read** (forecast → UI) | Vercel `/api/forecast` | per page load | CDN-cached |

**Why GFS self-ingest?** Open-Meteo's free tier meters by grid point, which made
fleet-wide, fine-grid forecasts impossible (see `open-meteo-free-tier` in agent
memory — a hard constraint: no API key, can't pay). NOAA's GFS on NODD S3 is free
and unthrottled, and **we own the download**, so cube resolution is decoupled from
fetch cost: a finer grid just resamples more points locally.

---

## 2. The wind cube

The core data structure (`lib/wind/windCube.ts`). A `WindCube` is a stack of
hourly-or-3-hourly GFS wind grids over one bounding box at one pressure level:

```ts
type WindCube = {
  t0Ms, stepMs;        // grids[h] is valid at t0Ms + h*stepMs
  grids: GfsGrid[];    // each: lat0/dLat/nLat, lon0/dLon/nLon, U[], V[] (Float32)
  bounds, gridStep, levelHpa;
  source, generatedAt; // 'gfs' + ingest run time
};
```

`sampleWind(cube, lat, lon, whenMs)` — bilinear in space, linear in time between
the two bracketing grids. **Every** trajectory (dead-reckon, forecast, each
ensemble member, every reconstruction gap bridge) samples one cube, so they share
one continuous, evolving wind field with no seams.

### Two cubes per device (decoupled)

| | **forecast** `{device}-fc` | **reconstruction** `{device}` |
|---|---|---|
| Drives | forward forecast, ensemble, bias, origin | historical track only |
| Box | recent track + dead-reckon + cone (small) | full mission (launch → now), continent-wide |
| Grid | finest under the ~8000-pt cap (≈0.75° for stratolink-3; finer regional) | `choose_grid_step` (≈1° for stratolink-3) |
| Time step | **hourly** | **3-hourly** |
| Forward pad | large (`PAD_CAP_DEG=32`) to contain the dead-reckon | small (`pad_cap=8`); its forward leg is unused |

They were split so the small forecast box can be fine without the continent-wide
reconstruction box dragging the grid coarse. `fetchWindCube({kind})` reads the
right one; the `forecast` read falls back to the full cube if no `-fc` exists yet.

---

## 3. Ingest — `scripts/gfs_ingest.py`

Runs in `.github/workflows/gfs-ingest.yml` (micromamba + pygrib/eccodes; the
GRIB2 complex packing needs eccodes from conda-forge). Per run:

1. **Devices + fixes** — `active_devices()` reads flying devices from Supabase;
   `mission_fixes()` pulls the full mission since launch (capped `HISTORY_DAYS=90`).
   Corrupt coordinates are dropped (a stray `lat -222` once blew up a box).
2. **Level** — nearest GFS pressure level to the device's latest reported pressure.
3. **Source selection** — `pick_source(t, latest)` returns the GFS **forecast
   hour** giving the wind *valid at* `t`:
   - future (`t > latest`): `(latest_cycle, fhr = hours_ahead)` — so the forward
     forecast **evolves** instead of freezing at the analysis;
   - past (`t ≤ latest`): `(containing 6h cycle, fhr = 0..5)` — real winds per step,
     not a 6-hourly analysis repeated.
   > This was a real bug fix: previously `pick_source` always returned `fhr=0`, so
   > the entire forward forecast used the single latest analysis (verified: 0.000
   > m/s change between future grids). For a long dead-reckon the evolving-vs-static
   > difference is thousands of km.
4. **Fetch** — byte-range GETs from `noaa-gfs-bdp-pds` (`pgrb2.0p25`) using each
   message's `.idx` offsets, for UGRD+VGRD only. Cached by `(cycle, fhr, level)`.
   `http_get` retries with backoff; `TIMEOUT=30s` (the two-cube ingest makes
   ~2–3× more requests, so a hung socket must fail fast, not stall 90s).
5. **Box** — `bounds_for_forecast`: `bbox(fixes) ± 4°` plus a downwind pad sized
   from the most-recent **non-frozen, short-dt** fix pair's velocity × horizon,
   capped. (Non-frozen because this fleet's GPS re-sends identical fixes; the last
   pair is often zero-displacement → a collapsed pad — see `stratolink-frozen-gps`.)
6. **Resolution** — `choose_grid_step` picks the finest step keeping ≤ `MAX_GRID_PTS`
   (8000) points. Small box ⇒ 0.25–0.5°; continent-wide ⇒ ~1°.
7. **Write** both cubes; `upload_cubes.mjs` gzips each (~4× smaller) to
   `cubes/{device}.json.gz` and `cubes/{device}-fc.json.gz`.

Timestamps from Supabase can have odd fractional seconds / trailing `Z`;
`tparse()` normalizes them (`datetime.fromisoformat` is picky pre-3.11).

**Runtime:** ~10–15 min/device now (hourly forecast cube + real 3-hourly recon =
many byte-range GETs). NODD is free, so the only cost is wall-clock.

---

## 4. Compute — `lib/wind/monteCarloForecast.ts`

`computeMonteCarloForecast(input)`:

1. **Cubes** — fetch `fcCube` (forecast) and `reconCube` (reconstruction) from Blob.
2. **Bias** — `computeBiasFromCube` compares recent observed displacements to the
   cube wind at that time/place (skipping frozen pairs), yielding a speed
   multiplier, direction offset, and **data-driven** speed/dir sigmas. Capped
   (`SPEED_CAP`, `DIR_CAP_DEG`) and gated by `MIN_SIGMA_SAMPLES=12` (below that,
   fixed default sigmas — the frozen-GPS thin-sample stopgap).
3. **Ensemble** (`N_ENSEMBLE=200`) — each member is **one** continuous integration
   from the last fix → now → horizon through `fcCube`, with a persistent AR(1)
   (Ornstein-Uhlenbeck) perturbation correlated over `PERTURB_TAU_H=18h`. The cone
   grows continuously from ~0 at the fix.
4. **Dead-reckon** — if GPS is stale (gap ≥ 1h), integration starts at the last fix
   and the `fix→now` portion of the nominal path is the `predicted_hindcast`; the
   forecast leg continues seamlessly.
5. **Reconstruction** — `resolveReconstruction` → `computePathReconstruction`
   bridges every historical GPS gap by sampling `reconCube` (short gaps = line,
   medium = shooting/particle smoother, long = corridor smoother). **Zero** live
   API calls. Per-gap + whole-mission caches live in Blob (`hindcasts/{device}*`),
   keyed by the fixes — so unchanged fixes reuse the cached track.
6. **Output** — `nominal_path` (forecast leg only), `ensemble`, a single horizon
   uncertainty `ellipse`, `endpoint` + wind, `bias_correction`, `observed`
   (reconstructed track + gaps), and `metadata` (`grid_step_deg` = fc, plus
   `recon_grid_step_deg`, `wind_source`, `wind_cube_generated_at`, timings).

---

## 5. Deployment & APIs

- **`/api/compute-forecast`** — protected by `Bearer CRON_SECRET`. Hit by
  cron-job.org (~25–30 min; Vercel Hobby cron is only 1/day, too coarse). A
  `MIN_RECOMPUTE_MS = 25min` freshness gate caps per-device recompute rate;
  `?force=1` bypasses it; `?device=X` does one device. Writes
  `forecasts/{device}.json` to Blob.
- **`/api/forecast?device=…`** — the browser read. Served with `max-age=300`, so
  the CDN/browser may hold a forecast up to 5 min (hard-refresh to bust).
- **Secrets** (Vercel env + GitHub repo secrets; never committed):
  `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `BLOB_READ_WRITE_TOKEN`,
  `CRON_SECRET`. See `wind-forecast-vercel.md` for the Vercel setup steps.

---

## 6. Operational gotchas

- **Uploading cubes does NOT refresh the forecast.** The compute reads cubes but
  the stored forecast + reconstruction caches are separate. To force the live
  forecast onto new cubes:
  ```bash
  # 1. clear the reconstruction caches (Blob) for the device
  node -e 'const{list,del}=require("@vercel/blob");(async()=>{const{blobs}=await list({prefix:"hindcasts/stratolink-3"});if(blobs.length)await del(blobs.map(b=>b.url))})()'
  # 2. force a recompute
  curl -H "authorization: Bearer $CRON_SECRET" "https://stratolink.org/api/compute-forecast?device=stratolink-3&force=1"
  ```
  The reconstruction cache is keyed by GPS fixes only, **not** the cube/code
  version — so after a reconstruction-code change, clear it or it self-migrates
  only as new fixes arrive (old immutable gaps keep their old geometry).
- **Local dev reads forecasts from Blob too** (`.env.local` has the Blob token), so
  `localhost:3000` and prod show the *same stored forecast*. Local dev is not
  computing unless you point `WIND_CUBE_FILE` / `WIND_CUBE_FC_FILE` at local cubes.
- **CDN cache**: a "stale" forecast on prod after a recompute is usually the 5-min
  `max-age` — hard refresh.
- **Frozen GPS** (`stratolink-3`): the device re-sends identical fixes. Bias fitting
  and box-pad velocity both skip zero-displacement pairs; even so, a balloon that's
  been GPS-dark for many hours produces a thin, cap-pinned bias — treat its forecast
  cautiously until GPS recovers.
- **Long stale-gap edge-clip**: a >~72h gap makes the forecast a ~96h
  dead-reckon+forecast cone whose leading edge can exit the forecast box (logged as
  "ensemble endpoints near grid edge"). Clears when GPS recovers.

### Local testing knobs
- `WIND_CUBE_FILE` / `WIND_CUBE_FC_FILE` — point `fetchWindCube` at local cube
  files (skips Blob), e.g. to test a freshly-built `.windcube/cubes/*.json`.
- `python3 -u scripts/gfs_ingest.py [device]` — build cubes locally (needs Supabase
  + NOAA access; `-u` for live progress).

---

## 7. Deferred / known follow-ups

- **Incremental history cube** for very long flights (append new 3-hourly steps
  instead of re-downloading the whole mission each run).
- **Mixed-level handling** (single pressure level per cube today).
- **Forecast-uncertainty improvements** (`forecast-uncertainty-followups` in
  memory): coarse-grid sigma inflation, frozen→real transition-pair skew, and the
  mean-bias thin-sample problem — the `MIN_SIGMA_SAMPLES` gate is a stopgap.
- **Read-only Supabase key** for the ingest secret (currently service-role).

---

## Key files

| File | Role |
|---|---|
| `scripts/gfs_ingest.py` | build the two cubes from NOAA GFS |
| `scripts/upload_cubes.mjs` | gzip + upload cubes to Blob |
| `.github/workflows/gfs-ingest.yml` | 6-hourly ingest job |
| `lib/wind/windCube.ts` | `WindCube`, `sampleWind`, `fetchWindCube` |
| `lib/wind/monteCarloForecast.ts` | the forecast pipeline |
| `lib/wind/pathReconstruction*.ts` | historical-track reconstruction |
| `lib/wind/hindcastStorage.ts` | reconstruction Blob caches |
| `app/api/compute-forecast/route.ts` | cron compute endpoint |
| `app/api/forecast/route.ts` | browser read endpoint |
