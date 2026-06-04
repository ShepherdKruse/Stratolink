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
hourly-or-3-hourly GFS wind grids over one bounding box at one pressure level
(the grids are vertically interpolated to the balloon's float pressure at ingest
— see §3 step 2 — so the level can be a non-standard value like 280 hPa):

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

**On-disk format (`.slwc`, packed binary).** Cubes are stored as
`[uint32 LE headerLen][header JSON, 4-byte aligned][per grid: int16 U then V]`,
gzipped to `.slwc.gz` for Blob. Geometry (constant across a cube's grids) lives in
the header once; values are `int16 = round(value×10)` — lossless vs the old 0.1 m/s
JSON, ~3× smaller raw, and decoded to `Float32Array` via a typed-array view
(`cubeFromBinary`) with ~zero parse cost instead of `JSON.parse`-ing millions of
numbers. This is what keeps a GEFS 31-member ensemble tractable. Readers try
`.slwc` before legacy `.json` (migration fallback).

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
2. **Level** — winds are **vertically interpolated to the device's actual float
   pressure** (`float_pressure()` = the robust median of recent float-band
   telemetry, ~280 hPa for stratolink-3). GFS only publishes standard isobars
   (250, 300, … — no 280), so `fetch_uv_p()` fetches the two bracketing levels and
   blends them linearly in pressure (`bracket_levels()`): for 280 hPa,
   `0.6·U₃₀₀ + 0.4·U₂₅₀`. The cube stays single-level — `levelHpa` just records the
   interpolated target (e.g. `280.0`) — so nothing downstream changes.
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
   message's `.idx` offsets, for UGRD+VGRD only. **Persistently cached** by
   `(cycle, fhr, level)` under `.windcube/fetchcache/` (`fetch_uv`): each raw GRIB
   field is immutable — a past analysis or a published forecast hour never changes
   — so a cache hit is always valid, no invalidation. This makes the historical
   recon **incremental**: each 6-hourly run re-downloads only the new ~6h tail and
   the new forward forecast, not the whole mission (a 90-day recon drops from
   hundreds of fetches to ~4 at steady state). `prune_fetch_cache()` drops cycles
   older than `HISTORY_DAYS`. On Actions the dir is restored/saved via
   `actions/cache`; locally it just lives under `.windcube/`. `http_get` retries
   with backoff; `TIMEOUT=30s` (the two-cube ingest makes ~2–3× more requests, so
   a hung socket must fail fast, not stall 90s).
5. **Box** — `bounds_for_forecast`: `bbox(fixes) ± 4°` plus a downwind pad sized
   from the most-recent **non-frozen, short-dt** fix pair's velocity × horizon,
   capped. (Non-frozen because this fleet's GPS re-sends identical fixes; the last
   pair is often zero-displacement → a collapsed pad — see `stratolink-frozen-gps`.)
6. **Resolution** — `choose_grid_step` picks the finest step keeping ≤ `MAX_GRID_PTS`
   (8000) points. Small box ⇒ 0.25–0.5°; continent-wide ⇒ ~1°.
7. **Write** both cubes as **packed binary** (`.slwc` — see §2); `upload_cubes.mjs`
   gzips each to `cubes/{device}.slwc.gz` and `cubes/{device}-fc.slwc.gz`.

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

## 6b. Worker-side compute (GEFS-ready)

The default path computes in a **Vercel serverless function** reading the cube
from Blob. That's fine for one GFS run, but it doesn't scale to a **GEFS
ensemble**: the bottleneck is *not* the raw data transfer (1–1.5 GB is cheap and
one-time from free NOAA), it's that a serverless function would have to pull the
cube from Blob and `JSON.parse` it into memory **every cron tick** — hitting the
function's RAM (~1–3 GB; JSON parse balloons 2–5×) and `maxDuration`, and
re-incurring **Vercel Blob** read bandwidth every ~30 min (this is Blob, not
Supabase — unrelated stores).

The fix is to **compute on the GitHub Actions runner**, where the cubes are
already local and there's no memory/time cap, and upload only the small forecast
JSON:

- `scripts/compute_forecasts.ts` (run via `tsx`) — for each device with a cube,
  `buildForecastInputForDevice` → `computeMonteCarloForecast` → `storeForecast`.
- `fetchWindCube` reads cubes from local disk when **`WIND_CUBE_DIR`** is set
  (per-device, same filenames as Blob) — no Blob round-trip.
- The workflow (`gfs-ingest.yml`) now: ingest cubes → **compute + store forecasts
  on the runner** → (optional, transitional) upload cubes to Blob for the
  serverless cold-miss fallback.

End state: drop the cube upload and disable the external cron → `/api/compute-forecast`,
so cubes never leave the runner and Blob holds only forecast JSON.

### GEFS ensemble (`scripts/gefs_ingest.py`)

The runner is also where the **GEFS ensemble** runs. `gefs_ingest.py` builds one
binary cube per member (`{device}-mNN.slwc`, 0.5°, 250↔300 interp to float
pressure, time-correct gap sourcing, concurrent prefetch), reusing the gfs_ingest
helpers + `.slwc` packer. In the compute, `computeMonteCarloForecast` detects
member cubes (`listMemberCubes`) and builds the ensemble as **one real trajectory
per member** — each integrated in its *own* cube (the member field is the
perturbation; neutral bias, zero synthetic jitter), **streamed one member at a
time** so peak memory stays flat. Nominal = control (`m00`); falls back to the
parametric GFS+jitter ensemble when no member cubes exist. This gives
flow-dependent spread: for a 123 h-stale balloon the dead-reckoned "now" is a
~3,500 km *cloud*, not the deceptively crisp point a single GFS track implies.

**Multi-model: AIGEFS (`scripts/aigefs_ingest.py`).** GEFS members all share the
physics model (FV3), so they under-represent *model* error (a biased jet position
advects a balloon consistently wrong). `aigefs_ingest.py` adds members from NOAA's
**GraphCast AI ensemble** (`noaa-nws-graphcastgfs-pds`, 0.25°, 31 members
`mem000–030`, 6-hourly) as `{device}-aNN.slwc`, and `listMemberCubes` pools both
`-mNN` (physics) + `-aNN` (AI) into one ensemble — a poor-man's multi-model
ensemble that hedges structural model error. It's invoked from `gefs_ingest.py` in
a try/except (best-effort: a failure never touches the GFS/GEFS pipeline), and
remaps each step to the nearest *available* cycle (AIGEFS occasionally skips one).

Cost lives entirely on the free runner: ~1–1.5 GB ingest per stale device per
source (each byte-range GET pulls a whole-globe field — GRIB2 messages aren't
spatially subsettable). Member cubes (`-mNN`/`-aNN`) are **not** uploaded to Blob
(`upload_cubes.mjs`) — they're runner-only — so the serverless cold-miss path
can't pull dozens into a 60 s function. Remaining optimizations: bbox subsetting
(NOMADS `g2subset`) or fetch-once-resample-many across the fleet; and box-sizing
for the very wide stale clouds (currently a generous capped pad).

## 7. Deferred / known follow-ups

- ~~**Incremental history cube** for very long flights~~ — **done** (§3 step 4):
  rather than appending cube steps, the fetch layer persistently caches the
  immutable raw `(cycle, fhr, level)` GRIB fields, so each run re-downloads only
  the new tail. Decoupled from box/grid changes (those just re-sample the cached
  fields). Remaining: extend the cache to the GEFS/AIGEFS/ECMWF member ingests
  (lower value — they're forward-forecast and re-anchor each cycle).
- **Multi-level / altitude-aware sampling** — the cube is interpolated to one
  representative float pressure at ingest (single level per cube). Tracking
  diurnal altitude swings within a run would need a multi-level cube + vertical
  interpolation at sample time (touches the cube schema, `sampleWind`, and every
  caller). Deferred.
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
