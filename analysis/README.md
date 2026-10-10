# Analysis scripts

Research code for acoustic sampling, antennas, radio networks, power budgets,
telemetry plots, and altitude sensitivity. The original studies are by Teddy
Warner. The altitude analysis reuses the existing website float calculator and
Caleb's ISA implementation in `simulation/predictor`; neither is copied or changed.

From the repository root, install Python 3.11 or 3.12 dependencies with
`uv sync --project analysis --locked`. Node is required by the altitude analysis.
Parquet pipelines additionally require `pyarrow`. Antenna field solves require
PyNEC 1.7.3.4, SWIG, and a C++ compiler. SDR capture tools require `pyrtlsdr` and
the system `librtlsdr` library. These optional native dependencies are not in
the base lockfile.

Offline examples:

```sh
analysis/.venv/bin/python -m unittest discover -s analysis/altitude_encounters -p 'test_*.py' -v
analysis/.venv/bin/python -m unittest discover -s analysis/visualization -p 'test_*.py' -v
node --test web/src/float-model.test.mjs
analysis/.venv/bin/python analysis/altitude_encounters/analyze.py
analysis/.venv/bin/python analysis/network/40_ocean_relay_physics.py
analysis/.venv/bin/python analysis/power/relay_power_budget.py
analysis/.venv/bin/python analysis/acoustic/pdm.py
```

`altitude_encounters` writes three plots and `results.json`, including calculator
inputs and source hash. It models density equilibrium, hypothetical encounter
exposure, and ideal sphere flow. It uses no measured aircraft traffic or balloon
contact dynamics. The tests compare the live calculator with an independent ISA
mass balance, so no saved results fixture is required.

The May 2026 antenna and network pipelines retain their study dates, flight IDs,
and assumptions. They need the operator's own telemetry, not included here:

- `antenna/10_fetch.py` reads `SUPABASE_URL` and `SBKEY` or
  `SUPABASE_SERVICE_ROLE_KEY`; it writes `antenna/data/telemetry_raw.*`.
  Run `20_receptions.py`, `40_geometry.py`, and `50_attitude.py` to prepare the
  reception geometry and attitude inputs for the antenna models.
- `network/10_gateway_census.py` fetches the same telemetry. Located-gateway
  plots also require `~/.cache/stratolink/ttn_gateways.csv`, containing gateway
  identifiers and coordinates, and the resulting `gateway_census_located.csv`.
- `acoustic/01_flight_audit.py` expects that telemetry CSV and
  `acoustic/data/bench_stratolink2.csv`. `06_precise_audio.py` expects captured
  `acoustic/data/frame_*.npz`; `mic_bench.py --help` describes capture formats.
- `power/relay_availability.py` expects `power/flight_power.csv` with `time`,
  `lon`, `battery_voltage`, `solar_voltage`, `ambient_lux`, and `uv_index` columns.

The three `visualization` scripts accept `TELEMETRY_CSV` with ISO-8601 `time`,
`lat`, `lon`, and `altitude_m`. The signal plots also require `gateways`, a
CSV-quoted JSON array of objects containing `lat`, `lon`, and optional `snr` and
`rssi`. The heatmap accepts `GATEWAYS_CSV` with `lat`, `lon`, and optional `id`
to bypass public gateway fetching. Without CSV inputs, set the Supabase variables
above. Original flight filters and map extents remain in place; Cartopy maps
also need cached Natural Earth data for offline rendering.

Radio timing diagrams and power constants describe their historical study
configuration, not the current flight firmware. Network fetchers, microphone
capture, and `network/bench/tools/sdr_*` need explicit operator invocation;
they are not part of the offline test commands. Generated plots, raw inputs,
captures, and local caches are excluded from version control.
