# Stratolink antenna analysis

Substantiating the v2 antenna decision on real flight-3 data + electromagnetic
modeling. Companion to `ROADMAP.md` and `firmware/STRATOLINK_3_FLIGHT_NOTES.md`.

## Pipeline / file map
- `_common.py`   — Supabase creds + spherical geometry (haversine, slant, elevation, depression).
- `_gps.py`      — GPS fresh/stale classifier (the integrity gate; mirrors `diagnostics/gps_stale_audit.py`). **Geometry uses FRESH fixes only.**
- `_style.py`    — matplotlib dark theme matching the dashboard-v2 palette.
- `00_recon.py` / `10_fetch.py` / `20_receptions.py` / `30_characterize.py` — data foundation (telemetry → per-reception table).
- `40_geometry.py` — **Part A**: reception geometry (where, angularly, were we heard). Figs `A1..A4`.
- `50_attitude.py` — **Part B-0**: payload attitude from the accelerometer (stable hang vs tumble). Fig `B0`.
- `60_patterns.py` — **Part B**: PyNEC antenna pattern modeling (in progress).

Reports: `01_signal_characterization.md`, `02_geometry_partA.md`. Data cache: `data/`. Figures: `figs/`.

## Running
```sh
set -a; source ~/.config/stratolink/env; set +a     # only for (re)fetch; cached parquet otherwise
analysis/.venv/bin/python analysis/antenna/40_geometry.py
analysis/.venv/bin/python analysis/antenna/50_attitude.py
```

## PyNEC install (NEC2 method-of-moments) — read this, PyPI PyNEC is a minefield
The current PyPI release **1.7.3.6 is broken** (uv_build backend ships a wheel with no
`PyInit`, and its sdist is missing the C++ sources). **Use 1.7.3.4**, which has the full
SWIG wrapper + 17 necpp sources. Requires `swig` (`brew install swig`) and a C++ compiler.

```sh
brew install swig
cd /tmp && python - <<'PY'
import urllib.request,json,io,tarfile
d=json.load(urllib.request.urlopen("https://pypi.org/pypi/PyNEC/json"))
url=[f["url"] for f in d["releases"]["1.7.3.4"] if f["filename"].endswith(".tar.gz")][0]
tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(url).read())).extractall(".")
PY
cd PyNEC-1.7.3.4 && /path/to/analysis/.venv/bin/python -m pip install .
```
Validation (must pass before trusting any model): a thin half-wave dipole at 900 MHz gives
**~2.15 dBi peak** and input Z **≈ 73+j42 Ω** (we measure 2.18 dBi, 86.7+j48.9 Ω — correct for
1 mm wire). See `60_patterns.py` self-test.

## Key findings so far
- **Link is orientation/pattern-limited, not range-limited** (Part A; n=0.44 path-loss slope).
- **GPS stale-fix bug contaminated 86% of post-launch uplinks** → geometry on 39 fresh fixes / 50
  geolocated receptions only. True max fresh range 252 km.
- **At float, gateways sit a median ~8° below horizon (long-range links near 0°); nadir never used.**
- **Payload hangs STABLY (body-axis tilt σ ≈ 1–3°) and spins about vertical — it does NOT tumble.**
  So antenna elevation pointing is controllable by mounting (Part D is a real lever), and azimuthal
  omni is required (the spin sweeps all bearings).
- Firmware requests 14 dBm in all regions. The US/EU RSSI gap may reflect gateway
  density or band/antenna effects; requested power does not prove conducted EU868
  output from the exact fitted `RAK3172-9-SM-NI`.
