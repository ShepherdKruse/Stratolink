# Stratolink Predictor

Short-range trajectory and float-altitude prediction for a single in-flight
pico-balloon. Built to the precision targets in `predictor-spec.md`:

| Horizon | CEP target |
| ------- | ---------- |
| 3 h     | < 5 km     |
| 6 h     | < 15 km    |
| 10 h    | < 40 km    |

## Why this is separate from `balloon_sim`

`balloon_sim` is a **fleet-coverage** simulator: many balloons, long horizons,
coarse hourly NCEP Reanalysis 2 winds, answers "how many balloons do we need."

`predictor` is a **single-balloon operational** tool: one balloon, 0–10 h
horizon, HRRR/GFS forecast winds, ensemble uncertainty, answers "where will
*this* balloon be in 6 hours, and how confident are we." The two share no
runtime state and no Python imports cross between them.

## Module layout (target)

```
predictor/
  atmosphere/
    isa.py              # U.S. Standard Atmosphere 1976 (0–32 km)
  buoyancy/
    float_solver.py     # ρ_air(h)·V = m_total root find (H2 / He)
    ascent_model.py     # vertical RK4 with buoyancy − drag
  weather/
    hrrr_client.py      # noaa-hrrr-bdp-pds S3 → xarray
    gfs_client.py       # noaa-gfs-bdp-pds S3 → xarray
    wind_field.py       # 4D (lat, lon, level, time) wind interpolation
  trajectory/
    integrator.py       # solve_ivp RK45, altitude-as-function-of-time
    ensemble.py         # 50-member perturbed ensemble + uncertainty cones
  api/
    predict.py          # FastAPI POST /predict
```

Tests live under `simulation/tests/predictor/` so the repo-level
`testpaths = ["tests"]` continues to discover them.

## Install

The predictor pulls in GRIB readers, AWS clients, and a web server — none of
which `balloon_sim` users need — so it lives in its own optional extra:

```bash
pip install -e ".[predictor]"
```

Add `dev` for tests: `pip install -e ".[predictor,dev]"`.

## Conventions

- **SI units internally** (m, m/s, Pa, kg, K). Convert only at API boundaries.
- **Docstrings declare units** on every public function parameter and return.
- **No module-level globals.** Clients and configuration are passed explicitly
  so every component is testable in isolation.
- **Field naming** matches the Supabase `telemetry` schema (`lat`, `lon`,
  `altitude_m`, `time`, `device_id`) so API payloads round-trip cleanly with
  the rest of the stack.

## Balloon physical parameters

Envelope volume, system mass, lift gas, and gas mass live on the `devices`
table (added in a migration introduced with Phase 5). When a row is `NULL`
the predictor falls back to: 0.5 m³ envelope, 12 g system mass, H2,
2 g gas mass. `POST /predict` accepts inline overrides in the request body
for A/B fills without a DB write — the DB is source of truth, the request
body is an override.
