# Balloon wind-forecast architecture

How Stratolink predicts where a balloon will drift, and reconstructs where it has
been, entirely from **self-ingested NOAA wind data** (GFS, GEFS, AIGEFS). There is
**no live weather API** anywhere in the pipeline, and nothing computes on Vercel.

> Authoritative overview as of 2026-10 (runner-only compute). Restored from the
> pre-migration `web/docs/` tree and rewritten to match the current code. The
> older `wind-forecast-vercel.md` and `cron-job-org-setup.md` in this folder
> describe the retired Vercel-compute / external-cron design and are kept as
> history only.

---

## 1. The big picture

```
  GitHub Actions  .github/workflows/gfs-ingest.yml  (cron 05/11/17/23 UTC + manual dispatch)
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ 1. scripts/gfs_ingest.py      flying devices + full-mission fixes (Supabase)  │
  │                               byte-range U/V GRIB from NOAA NODD S3           │
  │                               → .windcube/cubes/{device}.slwc  (reconstruction)│
  │                               → .windcube/cubes/{device}-fc.slwc (forecast)    │
  │ 2. scripts/gefs_ingest.py     31 GEFS member tubes  {device}-mNN.slwc          │
  │    └ aigefs_ingest.py         31 AIGEFS member tubes {device}-aNN.slwc (best-effort)
  │ 3. scripts/compute_forecasts.ts   (tsx, WIND_CUBE_DIR=.windcube/cubes)         │
  │       buildForecastInputForDevice → computeMonteCarloForecast → storeForecast  │
  │                               → Vercel Blob  forecasts/{device}.json           │
  └──────────────────────────────────────────────────────────────────────────────┘
                                          │  (cubes never leave the runner)
                                          ▼
  Browser  GET /api/forecast?device=…[&view=path]
           web/api/forecast.js → web/server/forecastApi.js
             • device must be `connection_status = connected` (Supabase)
             • reads forecasts/{device}.json from the private Blob store
             • sanitizeForecast (web/server/locationPrivacy.js) strips private fields
             • CDN-cached: public, s-maxage=300, stale-while-revalidate=3600 + ETag/304
```

Two tiers, both cheap and rate-limit-free:

| Tier | Where | Cadence | Cost |
|---|---|---|---|
| **Ingest + compute** (NOAA → cubes → forecast JSON) | GitHub Actions runner | 4×/day | free (public repo), wall-clock only |
| **Read** (forecast JSON → UI) | Vercel function `/api/forecast` | per cache miss | one Blob read + one Supabase lookup per 5 min per device/view (CDN) |

**Why self-ingest?** Open-Meteo's free tier meters by grid point, which made
fleet-wide, fine-grid forecasts impossible, and it must never be on the production
path (hard constraint: no API key, can't pay; see the agent memory note
`open-meteo-free-tier`). NOAA's NODD S3 buckets are free and unthrottled, and
**we own the download**, so cube resolution is decoupled from fetch cost. The
Open-Meteo code paths (live fallback in `fetchWindCube`, the per-point hourly
integrators, the call budget) were deleted in Oct 2026; a device with no cube now
fails its compute with a clear error instead of fetching anything.

---

## 2. The wind cube

The core data structure (`web/lib/wind/windCube.ts`). A `WindCube` is a stack of
hourly-or-3-hourly wind grids over one bounding box at one pressure level (the
grids are vertically interpolated to the balloon's float pressure at ingest, see
§3 step 2, so the level can be a non-standard value like 280 hPa):

```ts
type WindCube = {
  t0Ms, stepMs;        // grids[h] is valid at t0Ms + h*stepMs
  grids: GfsGrid[];    // each: lat0/dLat/nLat, lon0/dLon/nLon, U[], V[] (Float32)
  bounds, gridStep, levelHpa;
  source, generatedAt; // 'gfs' | 'gefs' | ... + ingest run time
  isTube?, centers?, track?;   // v2 tube metadata (below)
};
```

`sampleWind(cube, lat, lon, whenMs)` is bilinear in space and linear in time
between the two bracketing grids. **Every** trajectory (dead-reckon, forecast,
each ensemble member, every reconstruction gap bridge) samples one cube, so they
share one continuous, evolving wind field with no seams.

**On-disk format (`.slwc`, packed binary).** Cubes are stored as
`[uint32 LE headerLen][header JSON, 4-byte aligned][per grid: int16 U then V]`.
Geometry (constant across a cube's grids) lives in the header once; values are
`int16 = round(value×10)`, lossless vs the old 0.1 m/s JSON, ~3× smaller raw,
and decoded to `Float32Array` via a typed-array view (`cubeFromBinary`) with
~zero parse cost. This is what keeps a 31-member ensemble tractable. Readers
try `.slwc(.gz)` before legacy `.json(.gz)`.

**Two header versions.** `v1` (static box) stores one geometry in the header,
shared by every grid. `v2` (**trajectory "tube"**) keeps the cell size + dims
shared but gives each time-slice its own origin in `origins[[lat0,lon0],…]`, so
the box can follow the balloon across time. Optional `centers` (true per-slice
trajectory centers, unsnapped) and `track` (the hourly pre-integrated walk) let
the compute read a member's exact path instead of re-integrating it. The int16
payload layout is identical; `cubeFromBinary` reads both.

### Trajectory-following "tube" cubes (forecast + members)

A static box big enough to contain a multi-day dead-reckon forces a coarse grid
**and** still degrades once the drift leaves it: the sampler clamps to the edge
and a long drift was advected by a frozen edge wind for most of its length (it
"wrapped the globe" to a fictitious spot). Two fixes, layered:

- **Honesty.** `windAt`/`sampleWind` **wrap longitude** into the grid range
  (dateline-safe), and `integrateBalloonPathT` **stops** when a step leaves the
  cube's space/time coverage instead of extrapolating on clamped winds. The
  compute reports `stale_gps.coverage_limited` + `modeled_hours` when the
  dead-reckon runs out of coverage before "now" (the origin is then the last
  modeled point, surfaced in the UI as "position uncertain since {date}").

- **The tube.** The forecast cube and **every GEFS/AIGEFS member cube** are
  built as a stack of moderate boxes laid **along a pre-integrated nominal path**,
  each slice centered on where the balloon is then (a member tube integrates that
  member's *own* flow). Consecutive boxes overlap (half-width ≫ one step's drift)
  so `sampleWind`'s time-interpolation always has both brackets. Shared helpers
  live in `gfs_ingest.py` (`bilin_uv`, `cut_box`, `integrate_nominal_centers`,
  `build_tube_grids`); `FC_TUBE` / `GEFS_TUBE` / `AIGEFS_TUBE` = `0` revert to
  the static box. The dead-reckon is capped at `FC_DEAD_RECKON_CAP_H` (14 d);
  beyond that even a perfect tube is a globe-sized cloud.

  *Why the member tube needs no cloud-sizing:* the compute reads member *i*'s
  path straight from member *i*'s tube (`memberPathFromTube`: the stored hourly
  `track`, else the slice `centers`), so a member can't hit its own tube wall.
  (GRIB messages are whole-globe regardless, so the tube's win is coverage
  correctness + resolution, not bandwidth.)

### Two cubes per device (decoupled)

| | **forecast** `{device}-fc` | **reconstruction** `{device}` |
|---|---|---|
| Drives | forward forecast, parametric ensemble fallback, origin | historical track only |
| Box | tube along the nominal path (recent track + dead-reckon + horizon) | full mission (launch → now), continent-wide static box |
| Grid | 0.25° GFS native inside the tube | `choose_grid_step` under `MAX_GRID_PTS=8000` (≈1° for a long mission) |
| Time step | **hourly** | **3-hourly** |

`fetchWindCube({ deviceId, kind })` reads the right one; the `forecast` read falls
back to the full cube if no `-fc` cube exists. Member cubes are read by
`listMemberCubes` / `fetchMemberCube` (`-mNN` physics + `-aNN` AI, pooled).

---

## 3. Ingest: `scripts/gfs_ingest.py` (+ `gefs_ingest.py`, `aigefs_ingest.py`)

Runs in `.github/workflows/gfs-ingest.yml` (micromamba + pygrib/eccodes; the
GRIB2 complex packing needs eccodes from conda-forge). Per run:

1. **Devices + fixes**: `active_devices()` reads devices with
   `connection_status = connected` **and** `status = flying` from Supabase (the
   manual `flying` flag gates the whole pipeline); `mission_fixes()` pulls the
   full mission since launch (capped `HISTORY_DAYS=90`). Corrupt coordinates are
   dropped. `workflow_dispatch` with a `device` input restricts the run to one id.
2. **Level**: winds are **vertically interpolated to the device's float
   pressure** (`float_pressure()` = robust median of recent float-band
   telemetry). NOAA only publishes standard isobars, so `fetch_uv_p()` fetches the
   two bracketing levels and blends them linearly in pressure
   (`bracket_levels()`). The cube stays single-level; `levelHpa` records the
   target.
3. **Cycle + source selection**: `latest_cycle()` walks back from the current
   6-hourly cycle until a cycle's `f000` index exists on S3. `pick_source(t,
   latest)` returns the forecast hour giving the wind *valid at* `t`: future
   instants come from the latest cycle's forecast hours (so the forward forecast
   **evolves**), past instants from the 6-hourly cycle containing `t` with
   `fhr = 0..5`. Later forecast hours of the chosen cycle must already be
   published, or the byte-range GET fails after retries.
4. **Fetch**: byte-range GETs from `noaa-gfs-bdp-pds` (`pgrb2.0p25`) using each
   message's `.idx` offsets, UGRD+VGRD only, cached by `(cycle, fhr, level)`.
   `http_get` retries with backoff; `TIMEOUT=30s`.
5. **Box / tube**: the reconstruction cube uses `bounds_for_forecast` (bbox of
   the fixes ± pad, capped `PAD_CAP_DEG`); the forecast cube is a tube laid along a
   pre-integrated nominal path (§2). Pad velocity comes from the most recent
   **non-frozen, short-dt** fix pair (this fleet's GPS re-sends identical fixes,
   see the `stratolink-frozen-gps` memory note).
6. **Write** both cubes as packed binary `.slwc` into `.windcube/cubes/`
   (gitignored). Nothing is uploaded; the compute step reads them from disk.

`gefs_ingest.py` then builds one tube cube per GEFS member (`gec00` + `gep01..30`,
0.5° `pgrb2ap5`, 3-hourly, same level blending), and calls `aigefs_ingest.run()`
in a try/except for the 31 GraphCast members (`noaa-nws-graphcastgfs-pds`,
0.25° native, 6-hourly, written at 0.5°). AIGEFS occasionally skips a cycle;
`ideal_cycle`/`cycle_exists` remap each step to the nearest available one.

### Data volume and timing (Oct 2026 review)

Each byte-range GET pulls a **whole-globe** field (GRIB2 messages are not
spatially subsettable), so download volume scales with the number of
(cycle, fhr, level) pairs, not the box size. Per stale device per run:

| Source | Download | Members | Runtime |
|---|---|---|---|
| GFS (two cubes) | ~2.2 GB | 1 | ~10–15 min |
| GEFS | ~2.5 GB | 31 | ≈14.5 min for 31 members |
| AIGEFS | ~10 GB | 31 | pushes the GEFS step past its timeout |

NOAA publication lag after a cycle (measured): **GFS f120 +4:05**, **GEFS f240
+5:13**, **AIGEFS f000 +6:42**. The workflow's cron (`0 5,11,17,23 * * *`) starts
5 h after each cycle, so GFS is complete, GEFS's long-range hours land 13 min
after the run starts, and the newest AIGEFS cycle is not out yet (its
`latest_cycle()` probe then settles on the previous cycle). The workflow's
"Ingest GEFS member cubes" step runs both ensemble ingests under
`timeout-minutes: 28` with `continue-on-error: true`: GEFS alone fits, but with
AIGEFS the step is routinely killed at 28 min and the kill is masked, leaving a
partial AI member set. Moving the cron later and/or splitting AIGEFS into its own
step are the open fixes.

---

## 4. Compute: `scripts/compute_forecasts.ts` → `lib/wind/monteCarloForecast.ts`

`compute_forecasts.ts` (run as `npm run forecast:compute -- [device] [--dry]`,
`tsx` with `tsconfig.worker.json`) lists devices from the reconstruction cubes
in `WIND_CUBE_DIR`, and for each one runs
`buildForecastInputForDevice` (Supabase telemetry, service role) →
`computeMonteCarloForecast` → `storeForecast` (Blob `forecasts/{device}.json`,
or `.forecast-cache/` locally when no Blob token is set). A device with no cube,
or any failed compute, fails the job.

`computeMonteCarloForecast(input)`:

1. **Cubes**: `fetchWindCube` for `fcCube` (forecast) and `reconCube`
   (reconstruction). Precedence: `WIND_CUBE_DIR` on disk, then the Blob
   `cubes/` prefix (legacy; nothing writes there any more). No cube ⇒ throws.
2. **Bias**: intentionally **neutral** (`neutralBias`: speedMult 1, dirOffset 0,
   fixed `SPEED_SIGMA`/`DIR_SIGMA_DEG`); the chord-derived fit was unreliable on
   frozen-GPS fixes. Clean fix pairs are only counted for `n_samples`.
3. **Ensemble**: with ≥2 member cubes, one real trajectory per member read from
   its tube (`memberPathFromTube`), streamed one member at a time; nominal =
   component-wise **median** path. Otherwise the parametric fallback: `N_ENSEMBLE=200`
   AR(1)-perturbed integrations through `fcCube` (`PERTURB_TAU_H=18h`).
4. **Predictability horizon**: the forecast is cut at the first hour the robust
   ensemble spread (75th-percentile distance from the median) exceeds
   `DIVERGENCE_CAP_KM=2000`; `divergence` records where.
5. **Dead-reckon**: if GPS is stale (gap ≥ 1 h), integration starts at the last fix
   and the fix→now portion of the nominal path is the `predicted_hindcast`; the
   forecast leg continues seamlessly. `coverage_limited` when the cubes run out
   before "now".
6. **Reconstruction**: `resolveReconstruction` → `computePathReconstruction`
   bridges every historical GPS gap by sampling `reconCube` (short gaps = line,
   medium = shooting/particle smoother, long = corridor smoother). Per-gap and
   whole-mission caches live in Blob (`hindcasts/{device}*`), keyed by the fixes
   and `ALGO_VERSION` (see §6).
7. **Output**: `nominal_path` (forecast leg only), `ensemble`, one horizon
   `ellipse` (50/90 %, fitted to the inner 75 % of members), `endpoint` + wind,
   `bias_correction`, `observed` (reconstructed track, gap bridges, per-gap scalar
   metadata), and `metadata` (`grid_step_deg`, `recon_grid_step_deg`,
   `wind_source`, `wind_cube_generated_at`, timings). The `wind_field` grid
   snapshot and the per-gap occupancy/ellipse geometry are **not** stored: nothing
   read them, and `sanitizeForecast` never forwarded them.

---

## 5. Read path and deployment

- **`GET /api/forecast?device=ID[&view=path]`** (`web/api/forecast.js` →
  `web/server/forecastApi.js`). 400 on a malformed id/view, 404 unless the device
  is a connected registry entry, 202 `{status:'pending'}` when no stored forecast
  exists, 503 when the Blob read fails. 200 responses are the sanitized forecast
  (`view=path` = `generated_at` + `nominal_path` only, for the fleet map) with
  `Cache-Control: public, s-maxage=300, stale-while-revalidate=3600` and an
  `ETag` derived from `generated_at`; `If-None-Match` yields 304. 202/404/503 stay
  `no-store`. `web/server/forecastStorage.js` bounds the stored object at 8 MB.
- **Dashboard**: `useForecastPath` polls every 5 min per selected device;
  `FleetProjections` watches `view=path` per fleet device. Both skip devices whose
  registry status is landed / recovered / retired / lost / missing (their stored
  forecast is a months-old dead-reckon); the reconstructed path is still drawn
  for the selected device because it is history.
- **Secrets**: GitHub repo secrets `SUPABASE_URL` (or `NEXT_PUBLIC_SUPABASE_URL`),
  `SUPABASE_SERVICE_ROLE_KEY`, `BLOB_READ_WRITE_TOKEN`, optional `HEALTHCHECK_URL`;
  Vercel needs `BLOB_READ_WRITE_TOKEN` and the server Supabase key for the read
  path. There is no `CRON_SECRET` and no compute endpoint any more.

---

## 6. Operational gotchas

- **Forcing a recompute** = re-running the workflow:
  ```bash
  gh workflow run gfs-ingest.yml -f device=stratolink-3
  ```
  (blank `device` = every flying device). There is no on-demand compute.
- **Reconstruction caches are keyed by fixes + `ALGO_VERSION`, not by cube.** After
  a reconstruction-code change bump `ALGO_VERSION` in `lib/wind/hindcastStorage.ts`
  (and `GAP_ALGO_VERSION` in `pathReconstruction.ts` for per-gap bridges), or the
  whole-mission cache short-circuits `computePathReconstruction` and old gaps keep
  their old geometry. To clear by hand:
  ```bash
  node -e 'const{list,del}=require("@vercel/blob");(async()=>{const{blobs}=await list({prefix:"hindcasts/stratolink-3"});if(blobs.length)await del(blobs.map(b=>b.url))})()'
  ```
- **CDN cache**: `/api/forecast` is cached for 5 min (`s-maxage=300`) and may be
  served stale for up to an hour while revalidating; the dashboard also caches
  200s for 5 min client-side. A "stale" forecast right after a run is usually
  that; cache-bust the URL when verifying.
- **Local dev reads forecasts from Blob too** (`.env.local` has the Blob token), so
  `localhost` and prod show the *same stored forecast*. Local dev never computes
  unless you run the worker or `forecast_local.ts` against local cubes.
- **Frozen GPS** (`stratolink-3`): the device re-sends identical fixes. The
  clean-pair count and box-pad velocity both skip zero-displacement pairs.
- **Stale Blob objects**: `cubes/*` (from the retired upload step) and
  `forecasts/*.lock.json` (from the retired on-demand compute) are dead weight;
  `node --env-file=.env.local scripts/blob_cleanup.mjs` lists them and
  `--apply` deletes them.
- **`stratolink-2` never flew** (bench unit); its stored forecast is a
  dead-reckon fiction and the pipeline only recomputes devices flagged `flying`.

### Local testing knobs
- `WIND_CUBE_DIR`: directory of cubes read by `fetchWindCube` and the member
  loaders (`{device}-fc.slwc`, `{device}.slwc`, `{device}-mNN.slwc`,
  `{device}-aNN.slwc`). `compute_forecasts.ts` defaults it to `.windcube/cubes`.
- `python3 scripts/_run_with_env.py scripts/gfs_ingest.py [device]`: build cubes
  locally (loads `.env.local`; needs Supabase + NOAA access). The full pipeline
  (pygrib decode included) runs locally.
- `npm run forecast:local -- <device> [--offline]`: run the compute on the local
  cubes with Blob disabled (caches go to `.forecast-cache/`), writing
  `$FORECAST_LOCAL_DIR/forecast_local.json` (default `/tmp`); `--offline` reuses
  the cached Supabase input.
- `npx tsx scripts/inspect_cube.ts <path.slwc[.gz]>`: decode a cube and, for a v2
  tube, trace how its per-slice box centers walk along the path.
- Ingest dev flags: `SKIP_RECON=1` (skip the slow full-mission recon),
  `FC_DEAD_RECKON_CAP_H=48` (short cap for fast fetches), `FC_TUBE_HALF_DEG`,
  `FC_TUBE=0` / `GEFS_TUBE=0` / `AIGEFS_TUBE=0` (legacy static box),
  `GEFS_N_MEMBERS` / `AIGEFS_N_MEMBERS` (fewer members).

---

## 7. Deferred / known follow-ups

- **Workflow timing** (§3): move the cron past the GEFS/AIGEFS publication lag
  and give AIGEFS its own step so a timeout is visible instead of masked.
- **Incremental history cube** for very long flights (append new 3-hourly steps
  instead of re-downloading the whole mission each run).
- **Multi-level / altitude-aware sampling**: the cube is interpolated to one
  float pressure at ingest. The backtest found the *effective* float level
  deepens with lead (~290 → 350–400 hPa); tracking that needs a multi-level cube
  + vertical interpolation at sample time (cube schema, `sampleWind`, every
  caller). See `long-drift-forecast-plan.md` P3.
- **Forecast-uncertainty improvements** (`forecast-uncertainty-followups` memory
  note): coarse-grid sigma inflation, frozen→real transition-pair skew, and the
  mean-bias thin-sample problem.
- **Read-only Supabase key** for the ingest secret (currently service-role).

---

## Key files

| File | Role |
|---|---|
| `.github/workflows/gfs-ingest.yml` | 4×/day ingest + compute job (the only forecast writer) |
| `web/scripts/gfs_ingest.py` | build the two GFS cubes from NOAA NODD |
| `web/scripts/gefs_ingest.py`, `aigefs_ingest.py` | per-member GEFS / AIGEFS tube cubes |
| `web/scripts/compute_forecasts.ts` | runner-side compute + store |
| `web/lib/wind/windCube.ts` | `WindCube`, `.slwc` decoding, `sampleWind`, `fetchWindCube`, member loaders |
| `web/lib/wind/balloonIntegrate.ts` | `integrateBalloonPathT` (coverage-aware AR(1) integrator) |
| `web/lib/wind/monteCarloForecast.ts` | the forecast pipeline |
| `web/lib/wind/pathReconstruction*.ts` | historical-track reconstruction |
| `web/lib/wind/hindcastStorage.ts` | reconstruction Blob caches (`ALGO_VERSION`) |
| `web/lib/wind/forecastStorage.ts` | worker-side `storeForecast` (Blob or local cache) |
| `web/lib/wind/buildForecastInput.ts` | Supabase telemetry → compute input |
| `web/server/forecastApi.js`, `web/api/forecast.js` | browser read endpoint (gating, caching) |
| `web/server/forecastStorage.js`, `locationPrivacy.js` | bounded private Blob read, `sanitizeForecast` |
| `web/scripts/blob_cleanup.mjs` | list/delete stale `cubes/*` and lock objects |
| `web/scripts/forecast_local.ts`, `inspect_cube.ts`, `_run_with_env.py` | local iteration tools |
