# Forecast-replay backtest harness

Verifies the balloon wind-forecast by **replaying it from a known past fix**: feed a
start position into the same ensemble technique using the forecast cycle that *would
have been available then*, integrate every member forward to a later (known) fix, and
score the predicted cloud against where the balloon actually went.

Reuses the production ingest helpers (`gfs_ingest`, `gefs_ingest`, `aigefs_ingest`,
`ecmwf_ingest`) for the wind fetch + level interpolation. Run from the `web/`
directory; outputs (pickles + PNGs) go to `$BACKTEST_OUT` (default `/tmp`).

## Scripts

| script | what it does |
|---|---|
| `backtest_multi.py` | 3-panel GEFS/AIGEFS/ECMWF replay for one test leg; per-member trajectories, 50/90% ellipses, miss + containment. `<test> [--plot-only]` |
| `backtest_levels.py` | Sweep a pressure-level **bracket** (e.g. 250–300 or 300–400) — all levels are blends of the two fetched fields, so no extra download — **plus a diurnal-cycle sweep** (pressure oscillating with local solar time). 3×N grid + diurnal-vs-constant table. `<test> [--plot-only]` |
| `combine_levels.py` | Merge two bracket sweeps into one map per source: each level's mean trajectory + 50% spread, colored by pressure. Pure plotting from cache. |
| `rerun_ecmwf.py` | Re-run a single source after a transient fetch failure and merge into the cached pickle (no full re-run). |

## Key idea

Pressure level is an *upstream* choice; the two bracket levels are fetched once, then
any in-between level (and the diurnal trajectory) is a free re-integration. Trajectories
are cached per run (`bt_*.pkl`), so re-plots/re-styles cost nothing.

## Findings so far (stratolink-3, May 2026)

- **Short leg (CA→Mexico, 36 h):** all sources fit best at ~290–300 hPa (near nominal
  float); AIGEFS@290 within 130 km.
- **Long leg (ABQ→Spain, 10 d, 8,657 km):** effective level is much deeper (~350–400 hPa);
  forecasts at the nominal float over-predict the eastward distance by thousands of km
  because the fast upper-level jet carries an idealized parcel far past where the
  (lower/slower, likely descending) balloon actually went. The deeper the assumed level,
  the smaller the overshoot. Diurnal oscillation gives only a marginal extra improvement
  (one source), so the dominant signal is a net descent, not the day/night wiggle.
