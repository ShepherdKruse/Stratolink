# Stratolink Analysis Research

Research reports from sub-agent investigations into atmospheric science and link-layer analytics that can be derived from balloon telemetry. Each report is a self-contained implementation plan with math, library recommendations, validation strategy, and pitfalls.

## Reports

| File | Topic | Status |
|---|---|---|
| [ozone.md](ozone.md) | UV → vertical ozone profile via Beer-Lambert + OMI/TROPOMI anchoring | Headline science output, building first |
| [inversion.md](inversion.md) | Deep-dive: joint multi-altitude OEM, ratio retrieval, quant-aware S_ε. Pushes ozone accuracy to ±5-7% column | Adopt |
| [code_survey.md](code_survey.md) | Deep-dive: open-source libraries (libRadtran, pyOptimalEstimation, HARP, ussa1976, woudc-extcsv) | Integration list for analysis/ozone/ |
| [atmosphere.md](atmosphere.md) | Tropopause detection, wind profile, gravity wave decomposition | Queued after ozone |
| [satellite.md](satellite.md) | OMI/TROPOMI/ERA5/MERRA-2/IGRA collocation pipeline | Built alongside ozone (needed for anchor) |
| [lora.md](lora.md) | Link-budget modeling, coverage geometry, PacketBroker un-collapse | Queued |
| [trajectory.md](trajectory.md) | RK4 advection on GFS/GEFS, -30° crossing ETA | Queued |

## Build order

1. **Ozone** + **Satellite** together (satellite provides OMI anchor for ozone calibration). Validate locally on flight #1 data before anything else.
2. **Atmosphere** (tropopause, wind, gravity waves) — pure derivation from existing telemetry + ERA5 validation.
3. **LoRa** — independent of atmospheric data; runs on Supabase telemetry directly.
4. **Trajectory** — operational forecasting; needs GFS data pipeline (overlaps with satellite work).

## Conventions for `analysis/`

- Each domain gets its own subpackage: `analysis/ozone/`, `analysis/atmosphere/`, `analysis/external/`, `analysis/lora/`, `analysis/trajectory/`.
- Pure functions with typed signatures. `xarray.Dataset` for gridded data, `pandas.DataFrame` for per-row telemetry, plain dicts/JSON for API responses.
- Each subpackage has `tests/` with at least one regression-locked synthetic test (e.g. known SZA at known time, FSPL at known distance).
- Plotting functions return matplotlib/Plotly `Figure` objects, never call `.show()` or `.savefig()` directly — caller decides.
- All slow data fetches go through `cache.py` (on-disk Parquet/NetCDF) so re-runs are fast.

## Deployment

Local validation first. Once a retrieval is robust enough to promote, options are:

- **Pre-computed JSON artifacts** uploaded to Supabase Storage / Vercel Blob, served by a Next.js API route. Zero compute on request path.
- **Cron worker** on Fly.io/Railway runs the Python pipeline daily, refreshes artifacts.
- Heavy science compute (HYSPLIT, large NetCDF) never runs inline on Vercel.
