# Stratolink External Data Pipeline — Implementation Plan

> Research output from sub-agent investigation. Pulls OMI/TROPOMI ozone, ERA5/MERRA-2 reanalysis, IGRA radiosondes, AIRS for collocation along the flight track. Supports ozone absolute calibration AND atmospheric retrieval validation.

## 1. OMI (Aura) Total Column Ozone

- **Products**: `OMTO3` (L2 swath, OMI-TOMS retrieval), `OMTO3d` (L3 daily 0.25° gridded — recommended for collocation), `OMTO3G` (L3 daily gridded swath data, harder to use)
- **Access**: NASA GES DISC via `earthaccess` (preferred — handles auth + S3/HTTPS fallover). Direct OPeNDAP at `https://acdisc.gesdisc.eosdis.nasa.gov/opendap/HDF-EOS5/Aura_OMI_Level3/OMTO3d.003/`
- **Latency**: 1-2 days behind for OFFL; OMTO3 NRT available with ~3 hr lag from `acdisc.gesdisc.eosdis.nasa.gov`. Watch for the OMI row-anomaly mask (`QualityFlags_TOMS` field) — skip flagged rows
- **Library**: `earthaccess>=0.10`, `xarray`, `h5py`/`netCDF4`. The HDF-EOS5 files open cleanly with `xr.open_dataset(..., group="HDFEOS/GRIDS/OMI Column Amount O3/Data Fields")`
- **Auth**: `earthaccess.login(strategy="netrc")` — needs `~/.netrc` with `urs.earthdata.nasa.gov` entry

## 2. TROPOMI (Sentinel-5P) Total Column Ozone

- **Products**: `S5P_L2__O3_____` (offline OFFL, ~5-day latency) and `S5P_L2__O3__NRT` (near-real-time, ~3 hr). Variable of interest: `/PRODUCT/ozone_total_vertical_column` with `qa_value > 0.5` filter
- **Access**: Copernicus Data Space Ecosystem (CDSE) replaced the old Open Access Hub in late 2023. Use the STAC catalog at `https://catalogue.dataspace.copernicus.eu/stac` plus S3-compatible object storage at `eodata.dataspace.copernicus.eu`
- **Library**: `sentinelhub-py` for query, `harp` (ESA's atmospheric toolkit) for L2 ingestion and regridding to lat/lon. `harpy` ingestions handle the destriping and qa_value masking. `tropomi_tools` and `s5p-tools` are useful but harp is the canonical path
- **Auth**: CDSE OAuth client (client_id + client_secret from your CDSE account)

## 3. ERA5 Reanalysis

- **Variables**: `u_component_of_wind`, `v_component_of_wind`, `temperature` on pressure levels [1000, 850, 700, 500, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10] hPa (request all — bytes are cheap, lets us extend later)
- **Dataset names**: `reanalysis-era5-pressure-levels` (hourly, 0.25°) for nominal validation; `reanalysis-era5-complete` (MARS, model levels) only if you need above 1 hPa
- **Access**: Copernicus Climate Data Store via `cdsapi>=0.7`. Output GRIB or NetCDF — prefer NetCDF for xarray simplicity (skip cfgrib's eccodes dependency)
- **Latency**: ERA5T preliminary ~5 days behind; final ERA5 ~2-3 months. For a live mission, expect ERA5T quality
- **Auth**: `~/.cdsapirc` with URL `https://cds.climate.copernicus.eu/api` and personal access token (CDS migrated from API key to PAT in 2024 — old `uid:key` format no longer works)

## 4. MERRA-2

- **Collections**: `M2I3NPASM` (3-hourly instantaneous, pressure levels — 0.625°×0.5°), `M2I1NXASM` (single-level hourly). Better for cross-validation; ERA5 is preferred for primary.
- **Access**: GES DISC OPeNDAP via `earthaccess` (same auth as OMI). Path pattern: `https://goldsmr5.gesdisc.eosdis.nasa.gov/opendap/MERRA2/M2I3NPASM.5.12.4/YYYY/MM/`
- **Latency**: 2-3 weeks behind real-time — use for post-mission analysis only

## 5. IGRA Radiosonde

- **Source**: NOAA NCEI IGRA v2 at `https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/`. Subdaily data under `access/data-y2d/` (year-to-date, updated daily). Station list: `igra2-station-list.txt`
- **Library**: `igra` (pip package, A. Buchholz) for parsing the fixed-width format; or `siphon.simplewebservice.igra2.IGRAUpperAir` for cleaner pandas output. `metpy.calc.tropopause_definition` (or its WMO replacement) for tropopause height comparison
- **Method**: Pre-load station list, build a KD-tree on (lat, lon), query nearest ~5 stations to each track point, pull subdaily files for any station within ~500 km, match by `|t_balloon − t_sonde| ≤ 6 h`
- **Note**: California has limited high-altitude sondes — VBG (Vandenberg), OAK (Oakland 72493), REV (Reno). Once we drift east of the Sierras, NKX (Miramar) and DRA (Desert Rock) become primary

## 6. AIRS Temperature

- **Product**: `AIRS3STD` (L3 daily standard, 1°) for trends; `AIRS2RET` (L2 retrieved profiles) for sharper collocation. Aqua AIRS has been the gold standard since 2002 but is aging — also fetch SNPP `NUCAPS` retrievals as backup
- **Access**: GES DISC, same earthaccess auth as OMI/MERRA-2

## 7. Collocation Methodology

- **Spatial match**: nearest-neighbor for L2 swath (use the satellite footprint center; ≤25 km from balloon); bilinear for gridded L3 reanalysis using `xarray.interp(method="linear")`
- **Temporal match**: nearest-overpass time for satellites (record `dt_seconds` per match), linear-in-time interp for hourly reanalysis (`xr.Dataset.interp(time=balloon_time)`)
- **Match criterion (start strict)**: satellite footprint center within 0.25° of balloon track, same UTC day, `qa_value ≥ 0.5` (TROPOMI) / quality flag clean (OMI). Loosen progressively if matches are sparse
- **Quality flags**: TROPOMI `qa_value`, OMI `QualityFlags_TOMS` and `XTrackQualityFlags` (row-anomaly), AIRS `RetQAFlag`. Always carry through to the output Parquet so we can filter downstream
- **Deliverable**: a Parquet "collocation table" with one row per balloon telemetry point: `t, lat, lon, alt, p_balloon, o3_omi, o3_tropomi, u_era5_250, v_era5_250, T_era5_250, ..., trop_height_igra, station_id_igra, dt_match`

## 8. Sample Queries (2026-05-17, 37.7°N -122.5°E)

- **OMI O3**: `earthaccess.search_data(short_name="OMTO3d", temporal=("2026-05-17","2026-05-17"))` → open with xarray → `ds["ColumnAmountO3"].sel(lat=37.7, lon=-122.5, method="nearest")`. Expected ~280-320 DU
- **ERA5 250 hPa wind**: cdsapi request `{"variable":["u_component_of_wind","v_component_of_wind"], "pressure_level":["250"], "time":["14:00"], "year":"2026","month":"05","day":"17", "area":[38,-123,37,-122]}` → xarray `.sel(latitude=37.7, longitude=-122.5, method="nearest")`
- **IGRA nearest**: query station list → Oakland 72493 (37.75°N, -122.21°W) is closest → fetch `USM00072493-data-beg2026.txt.zip` → parse → filter to `2026-05-17 12Z`

## 9. Code Architecture

Place under `analysis/external/` as a sibling package to `simulation/balloon_sim` (follow existing package conventions in `simulation/pyproject.toml`):

- `analysis/external/__init__.py`
- `analysis/external/omi.py` — `fetch_omto3d(date) -> xr.Dataset`, `column_at(ds, lat, lon) -> float`
- `analysis/external/tropomi.py` — `search_tropomi(date, bbox) -> list[granule]`, `extract_o3(granule, lat, lon) -> dict`
- `analysis/external/era5.py` — `fetch_era5_levels(date_range, bbox, levels, variables) -> xr.Dataset`, `interp_to_track(ds, track_df) -> pd.DataFrame`
- `analysis/external/merra2.py` — `fetch_merra2(date, bbox) -> xr.Dataset` (mirror of era5)
- `analysis/external/igra.py` — `nearest_stations(lat, lon, n=5) -> pd.DataFrame`, `fetch_sounding(station, date) -> pd.DataFrame`, `tropopause_height(sounding) -> float`
- `analysis/external/airs.py` — `fetch_airs_profile(date, lat, lon) -> xr.Dataset`
- `analysis/external/collocate.py` — `collocate_track(track_df, sources=[...]) -> pd.DataFrame` (the orchestrator)
- `analysis/external/cache.py` — local Parquet/NetCDF cache keyed by `(source, date, bbox_hash)`, default at `~/.cache/stratolink/external/`
- `analysis/external/auth.py` — credential loaders (netrc check, cdsapirc check, CDSE OAuth refresh)

A separate `pyproject.toml` for `analysis/` keeps satellite deps (`earthaccess`, `cdsapi`, `harp`, `siphon`, `pyarrow`) out of the lightweight simulation package.

## 10. Auth Checklist

- **NASA Earthdata Login** at `urs.earthdata.nasa.gov` → `.netrc` entry. Covers OMI, MERRA-2, AIRS, GES DISC
- **Copernicus CDS PAT** at `cds.climate.copernicus.eu/profile` → `~/.cdsapirc`. Accept ERA5 license once interactively
- **Copernicus Data Space (CDSE)** OAuth client at `dataspace.copernicus.eu` → `client_id`/`client_secret` env vars. Required for TROPOMI
- **NOAA IGRA** — no auth, public HTTPS
- **Optional ESA S5P-PAL** at `s5p-pal.com` — only if you need the reprocessed PAL stream; CDSE covers the operational product

## 11. Backend Deployment

Don't run NASA fetches inline from Next.js — granules are 100s of MB and earthaccess needs a long-lived netrc. Recommended:

- **Worker**: Python pipeline runs daily on Fly.io / Railway / a cheap EC2, on cron (`0 6 * * *` UTC — after ERA5T daily release at ~05:00 UTC and OMI/TROPOMI offline products). Pulls all sources for the previous UTC day's track segment
- **Cache**: write collocation Parquet + raw NetCDF subsets to Supabase Storage or S3. Cloudflare R2 if you want zero egress
- **API surface**: Next.js `/api/atmosphere/[date]` reads the pre-built Parquet from object storage and returns JSON. Vercel KV / Supabase Postgres can hold a small lookup table (`flight_id, date → parquet_url`) for sub-100ms responses
- **Live mode**: if you need NRT during the flight, run a second cron every 3 hr that hits OMI NRT + TROPOMI NRTI only — skip ERA5 (too laggy) and IGRA (12-hourly anyway). Render as "preliminary" in the UI

## 12. Open Questions / Flags

- **ERA5T vs ERA5 final**: during the 14-day mission, you'll only get ERA5T. Quality is "good enough" for validation but document the disclaimer
- **OMI row-anomaly coverage gaps**: roughly half of OMI swaths over CA are now masked. TROPOMI is the primary; OMI is the longer-baseline cross-check
- **TROPOMI O3 absolute calibration**: TROPOMI total ozone has a known ~2-4 DU low bias vs ground Brewer/Dobson. If your goal is absolute calibration of the balloon retrieval, anchor to the **Brewer/Dobson network** (WOUDC) directly, not TROPOMI — and use TROPOMI/OMI only for spatial context. This is the biggest methodological note
- **IGRA timing**: 00Z/12Z launches mean a worst-case 6-hour offset to balloon position. For a drifting balloon this can mean 200+ km mismatch — flag in the collocation table
- **License**: Copernicus products are free and open under their license; NASA data is public domain. No commercial restrictions, but cite per each provider's policy
- **Coverage**: confirm whether the 14-day window crosses into the OMI Aura mission decommissioning timeline — Aura was planned for retirement in 2026; check current status before committing OMI as a primary source
- **Data volumes**: a 14-day window of TROPOMI L2 (~6 swaths/day over CONUS, ~500 MB each) is ~40 GB. ERA5 subsetted to the track bbox is ~2 GB. Plan worker disk accordingly

## Relevant existing paths in the repo

- `/Users/twarn/Repositories/Stratolink/simulation/balloon_sim/wind.py` — already implements NCEP Reanalysis 2 download via xarray; can serve as the template for `era5.py` and `merra2.py` (same fetch-cache-interp pattern)
- `/Users/twarn/Repositories/Stratolink/simulation/pyproject.toml` — sibling pyproject layout to follow for `analysis/`
- `/Users/twarn/Repositories/Stratolink/web/app/api/` — where the Next.js read endpoints would live
