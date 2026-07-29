# Stratolink Trajectory Prediction — Implementation Plan

> Research output from sub-agent investigation. Predict balloon forward trajectory, overlay against actual telemetry, compute ETA for region-switch geofence crossings.

## 1. HYSPLIT overview and access

HYSPLIT (NOAA ARL) is a Lagrangian particle dispersion / trajectory model. For Stratolink we want **trajectory mode**: a single particle released at a starting lat/lon/altitude (or pressure level), advected forward through gridded meteorology (GFS or GDAS). The model interpolates winds in space and time and integrates particle position with an iterative scheme.

**Access tiers, ranked by friction:**
- **READY web interface** (https://www.ready.noaa.gov) — browser-only, fine for a sanity check but unscriptable. Skip for production.
- **HYSPLIT executable** — free pre-compiled binaries for macOS (Sequoia/Ventura tested), Linux, Windows from NOAA ARL. Registration required for the full version; trial works for development. Tcl/Tk needed for the GUI but not for CLI runs. **No official Docker image** (NOAA forbids public-registry hosting), but a homebrew Dockerfile is straightforward.
- **Python wrappers:**
  - **PySPLIT** (mscross/pysplit) — most-cited (Warner 2018, IEEE CiSE). Wraps the HYSPLIT executable, generates trajectories, parses output `tdump` files into pandas. Last meaningful release ~2020; *unmaintained but functional*. The hysplitpy and monet-arl alternatives are thinner and less used; **PySPLIT is the only one worth adopting** if you go the HYSPLIT route.

HYSPLIT requires **ARL-format meteorology files** (proprietary packed binary). GFS-ARL files are ~400 MB per 6-hour cycle for global coverage; you'd typically pull just a regional subset. Output is the `tdump` text file: header lines plus tab-separated rows of `time, lat, lon, height, pressure, theta, …`.

## 2. Alternative: pure-Python RK4 advection on GFS winds (recommended)

For a pico-balloon at a known float pressure, you do **not need HYSPLIT's machinery**. Dispersion, mixed-layer turbulence, deposition — none of it matters for a sealed envelope at 12-20 km. The balloon is effectively a Lagrangian tracer of the wind.

**Math:** RK4 on `d(lat,lon)/dt = (v/R, u/(R·cos(lat)))` where `u, v` come from interpolating the GFS wind field at the balloon's pressure level. Standard, well-validated, identical to what Tawhiri/CUSF does for HAB prediction. Tawhiri itself uses Forward Euler with GFS winds, written in Python+Cython (https://github.com/cuspaceflight/tawhiri). RK4 is strictly better than their Euler integrator at trivial extra cost.

**Verdict for Stratolink:** simpler approach is adequate and dramatically more deployable. Use HYSPLIT only as a cross-check during validation, not in the production path.

## 3. Meteorology data sources

| Product | Resolution | Horizon | Source | Use |
|---|---|---|---|---|
| **GFS 0.25°** | 0.25° / 3h steps to 240h | 16 days | `s3://noaa-gfs-bdp-pds` (no egress), NOMADS, NODD | Primary forecast |
| **GEFS** | 0.5° / 31 members | 16 days | AWS via Herbie `model="gefs"` | Ensemble / uncertainty |
| **HRRR** | 3 km / 48h | 48h | AWS `noaa-hrrr-bdp-pds` | Not useful — CONUS-only, balloon leaves quickly |
| **ERA5** | 0.25° reanalysis | Past only | Copernicus CDS / AWS | Hindcast/backtest |

**Library: Herbie (`herbie-data`)** — actively maintained (release 2026.3.x), purpose-built for this, handles AWS/GCS/NOMADS fallback, returns xarray Datasets via cfgrib. https://herbie.readthedocs.io. Strongly preferred over rolling your own NOMADS scraper.

For runtime: pull only the `UGRD`/`VGRD` variables on the pressure levels bracketing your float altitude (e.g., 150-250 hPa for a 12 km balloon). A single forecast cycle for that subset is tens of MB, not GB.

## 4. Float altitude handling

Pico balloons (zero-pressure latex that tops out, or sealed mylar) at float behave as **isopycnic** tracers — drifting along a constant-density surface, which closely tracks a constant pressure level. **Use the pressure-level trajectory**, not fixed altitude. The balloon's reported `pressure` telemetry is the ground truth for which GFS pressure surface to interpolate winds on. Standard atmosphere conversion (`altitude_m` → pressure) is fine as a fallback when pressure telemetry is missing.

Diurnal altitude variation for *true* superpressure is ~1%; for the more common pico-mylar it's 5-10%. Telemetry-driven pressure-level selection (recompute the level each forecast cycle from the latest reported `pressure`) handles this transparently without modeling balloon thermodynamics.

## 5. Ensemble / uncertainty

Two options, complementary:
- **GEFS ensemble** (31 members): run the same RK4 advection on each member, get a true probabilistic cone. Best practice for any forecast horizon > 24h.
- **Perturbed-IC Monte Carlo**: jitter the starting position by GPS error (~10 m, negligible) and the pressure level by ±10 hPa (meaningful for diurnal uncertainty). Combine with GEFS for total uncertainty.

Output as a **probability density of position at each forecast hour**, plotted as cone of uncertainty (hurricane-style) — 50%, 75%, 95% contours.

## 6. Backtest validation

You have ~134 telemetry rows. Methodology:
1. Pick a starting telemetry point at hour T.
2. Pull the GFS forecast cycle that was operational at T (NOMADS keeps ~10 days; AWS has full history).
3. Run forecast forward for h ∈ {12, 24, 48, 72} hours.
4. Compute great-circle distance between predicted and actual position at T+h.
5. Repeat across all viable starting points.

**Expected skill** (from Podglajen et al. 2016, ConcordIASI campaign, https://journals.ametsoc.org/view/journals/atot/33/8/jtech-d-15-0110_1.xml; Boullot et al. 2019 https://www.mdpi.com/2073-4433/10/2/102): **median 24-hour position error ~250 km without wind-data assimilation, ~60 km with assimilation.** Loon's RL paper (https://www.nature.com/articles/s41586-020-2939-8) confirms similar magnitudes at 18-20 km. Expect *worse* skill at 12 km because troposphere-stratosphere transition winds are more variable and jet-stream-coupled.

## 7. Long-range / circumnavigation skill

Skill collapses past **~5 days** for jet-stream trajectories — that's the predictability horizon for synoptic flow. By day 7, ensemble spread typically exceeds a quarter of Earth's circumference at mid-latitudes. By day 14 the position prediction is uninformative; only zonal-mean drift rate is meaningful. Communicate this honestly on the dashboard — show the cone, not a line, past 72 hours.

**For the -30° crossing specifically**: at typical 30-50 kt zonal jet speeds from California, that's ~5-7 days. Skill there is marginal. Report ETA as a window (e.g., "Day 5-8, 60% probability") with the ensemble spread.

## 8. Code architecture (`analysis/trajectory/`)

```
analysis/trajectory/
  met_data.py        # Herbie wrappers: fetch_gfs(cycle, levels), fetch_gefs(...)
                     # Returns xarray Dataset (time, level, lat, lon) for U, V
  advection.py       # rk4_step(pos, t, dt, wind_interp) and advect(pos0, t0, horizon)
                     # wind_interp: trilinear in (lat, lon, time) on the chosen level
  hysplit_runner.py  # Optional: writes CONTROL file, invokes hysplit binary,
                     # parses tdump. Use only for cross-validation.
  ensemble.py        # Drives advection over GEFS members + IC perturbations,
                     # returns (member, time, lat, lon) DataArray
  backtest.py        # Hindcast harness: for each telemetry row, fetch
                     # contemporaneous GFS, advect forward, compute great-circle
                     # error vs actual at +12/24/48/72h. Outputs RMSE table.
  geofence.py        # Crossing detection: when does the ensemble cross lon=-30?
                     # Returns ETA distribution.
  plot.py            # Cartopy maps: actual track + forecast cone + ensemble
                     # members; ETA histogram for -30 crossing.
```

Keep `met_data.py` cache-aware — Herbie writes GRIBs to local disk by default; reuse them.

## 9. Backend deployment

**Vercel Next.js cannot run HYSPLIT or hold GB of GRIB.** Architecture:

- **Cron worker** (GitHub Actions, Fly.io, Railway, or a small AWS Lambda with Container image) runs every 6h on GFS cycle release (00/06/12/18 UTC + ~4h latency). It:
  1. Pulls latest telemetry from your Supabase / Postgres.
  2. Runs `met_data` + `ensemble.advect_all_members()`.
  3. Writes a JSON forecast artifact (ensemble tracks + cone polygons + -30 ETA distribution) to S3 / Supabase Storage / Vercel Blob.
- **Next.js API route** on stratolink.org serves the cached JSON. No compute on the request path. Sub-100ms responses.
- **Failure mode**: if the cron fails, the dashboard shows stale-but-labeled forecast rather than a 500.

This separation is also what Tawhiri does (separate OCaml downloader + Python predictor + Flask API).

## 10. Pitfalls

- **Jet-stream meander**: a single Rossby-wave amplification event can deflect the balloon 1000+ km off the deterministic forecast. Only ensembles capture this.
- **Tropopause crossing**: 12 km in May at California's latitude is near the tropopause. Wind regimes flip across it. If altitude drifts you may cross the boundary mid-flight — pressure-level interpolation handles this gracefully, fixed-altitude does not.
- **Diurnal altitude oscillation** on pico-mylar: 5-10% altitude swing → meaningful change in wind direction. The pressure-driven approach naturally tracks this, but only if you re-anchor to live telemetry between cron cycles.
- **Polar vortex**: not relevant at California latitudes in May, becomes relevant if the balloon migrates poleward in winter.
- **You are not modeling balloon vertical dynamics.** For 14-day mission planning that's fine; just note it explicitly in the dashboard methodology page.
- **GFS-ARL vs GFS-GRIB2**: HYSPLIT needs ARL format, Herbie produces GRIB2. If you do want HYSPLIT cross-checks, NOAA hosts pre-converted ARL files at https://www.ready.noaa.gov/archives.php.

## 11. Open questions to flag back

- **Higher temporal cadence of GFS** isn't really available — 0.25° / 3h is the operational frontier. ECMWF IFS Open Data (0.25°/3h, also via Herbie) would give a second-opinion model; cheap to add.
- **Balloon altitude prediction model**: only worth building if backtest shows altitude-driven error dominates. Probably not for v1 — pressure telemetry is the input.
- **Wind shear awareness**: useful as a *diagnostic* (flag low-skill windows) rather than predictor. Compute `|∂V/∂z|` at the float level; high shear → wider uncertainty cone.
- **Data assimilation of Stratolink's own observations**: Boullot 2019 showed assimilating balloon-observed winds cuts 24h error from 250 km to 60 km. With a single balloon this isn't transformative, but it'd be a publishable result. Out of scope for v1.

**Recommended v1 scope:** pure-Python RK4 + Herbie/GFS + GEFS ensemble + Vercel-friendly cron architecture. Defer HYSPLIT to a "cross-validation" tab on the dashboard.

## Sources

- [Herbie documentation](https://herbie.readthedocs.io/en/stable/)
- [Herbie GitHub (blaylockbk)](https://github.com/blaylockbk/Herbie)
- [Herbie GEFS guide](https://herbie.readthedocs.io/en/latest/gallery/noaa_models/gefs.html)
- [NOAA GFS on AWS Open Data](https://registry.opendata.aws/noaa-gfs-bdp-pds/)
- [NOAA ARL — HYSPLIT downloads](https://www.arl.noaa.gov/hysplit/getrun-hysplit/)
- [HYSPLIT macOS install](https://ready.arl.noaa.gov/documents/Tutorial/html/install_mac.html)
- [PySPLIT on GitHub](https://github.com/mscross/pysplit)
- [Warner 2018 — PySPLIT in IEEE CiSE](https://ieeexplore.ieee.org/document/8452052/)
- [Tawhiri (CUSF predictor)](https://github.com/cuspaceflight/tawhiri)
- [SondeHub predictor](https://predict.sondehub.org/)
- [Podglajen et al. 2016 — Stratospheric balloon trajectory prediction](https://journals.ametsoc.org/view/journals/atot/33/8/jtech-d-15-0110_1.xml)
- [Boullot et al. 2019 — Accuracy of balloon trajectory forecasts](https://www.mdpi.com/2073-4433/10/2/102)
- [Bellemare et al. 2020 — Loon RL navigation (Nature)](https://www.nature.com/articles/s41586-020-2939-8)
- [Superpressure balloon — Wikipedia](https://en.wikipedia.org/wiki/Superpressure_balloon)
