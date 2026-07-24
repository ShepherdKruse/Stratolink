"""Stratolink-3 transatlantic flight, robust ensemble reconstruction.

Methodology:
  1. Fetch real GFS winds at multiple pressure levels (250/300/400/500 hPa)
     across the Atlantic-crossing gap period.
  2. Run an ensemble of trajectories from the last known US fix, perturbing
     starting position, time, and altitude-schedule (representing diurnal
     day-up/night-down helium thermal cycling on a superpressure balloon).
  3. Score each ensemble member by great-circle distance to the actual first
     EU fix. Weight by exp(-d^2/2 sigma^2).
  4. Plot the weighted mean path, the 25/75 percentile envelope, and the
     faint cloud of all members. Overlay wind speed backdrop and actual
     telemetry fixes.

The reconstruction is honest about uncertainty: shows the cloud, not just a
single line.
"""
from __future__ import annotations

import os, sys, math, time, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.interpolate import griddata

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# Wire up Shepherd's NOAA predictor module - gives us anonymous-S3 access to
# multi-cycle GFS pressure-level winds with no rate limits. The clients live
# in simulation/predictor/weather/ on origin/main; we expose them by adding
# simulation/ to the import path.
_SIM_DIR = Path(__file__).resolve().parents[2] / "simulation"
if _SIM_DIR.is_dir() and str(_SIM_DIR) not in sys.path:
    sys.path.insert(0, str(_SIM_DIR))
try:
    import xarray as xr
    from predictor.weather import gfs_client
    from predictor.weather.wind_field import RegularGridWindField
    from predictor.weather.wind_factory import _gfs_levels_for_altitude
    _PREDICTOR_AVAILABLE = True
except Exception as _pred_err:
    _PREDICTOR_AVAILABLE = False
    _PREDICTOR_ERR = _pred_err

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
OUT_PNG = Path(__file__).parent / "transatlantic_path.png"

# Map extent
LON_MIN, LON_MAX = -135.0, 10.0
LAT_MIN, LAT_MAX = 22.0, 60.0

# Wind backdrop
GRID_STEP_BACKDROP = 3.0
BACKDROP_PRESSURE = "300hPa"
SAMPLE_TIME_UTC = "2026-05-24T12:00"

# Drift winds: multiple pressure levels for ensemble advection
PRESSURE_LEVELS = [250, 300, 400, 500]
DRIFT_GRID_STEP = 5.0
DRIFT_SAMPLE_HOURS = 6        # wind samples every 6h

# Ensemble parameters
N_ENSEMBLE = 2000
START_POS_SIGMA_KM = 75.0       # starting position uncertainty
START_TIME_SIGMA_HR = 4.0       # starting time uncertainty
ENDPOINT_SCALE_KM = 600.0       # weighting scale: members within ~600km get high weight
WIND_NOISE_STD = 5.0            # per-member wind-field perturbation (m/s, applied to each component)

# Reproducibility
RNG_SEED = 20260529

CACHE_DIR = Path.home() / ".cache" / "stratolink"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---- data fetch ----

def fetch_track() -> pd.DataFrame:
    r = requests.get(
        f"{SBURL}/rest/v1/telemetry",
        params={
            "device_id": "in.(stratolink-3,stratolink-3-eu)",
            "select": "time,device_id,lat,lon,altitude_m,pressure",
            "order": "time.asc",
            "limit": "5000",
        },
        headers={"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    df = df[df["lat"].notna() & df["lon"].notna() & (df["altitude_m"] > 1000)]
    df = df.sort_values("time").reset_index(drop=True)
    # filter stale repeats
    keep = []
    last = None
    for _, row in df.iterrows():
        cur = (round(row["lat"], 6), round(row["lon"], 6), int(row["altitude_m"]))
        if last is None or cur != last:
            keep.append(True); last = cur
        else:
            keep.append(False)
    return df[keep].reset_index(drop=True)


def _open_meteo(times: list[str], lats: np.ndarray, lons: np.ndarray,
                 vars_to_get: list[str], chunk: int = 12,
                 between_chunk_pause_s: float = 12.0,
                 max_attempts: int = 4) -> dict:
    """Multi-point, multi-time, multi-var fetch from Open-Meteo forecast endpoint.

    Retries on 429 / 5xx with exponential backoff. Uses small location chunks
    by default since multi-pressure-level requests are heavy. Caller can tune
    chunk size / pause to trade speed for politeness.
    """
    n_lats = len(lats)
    out = {v: np.full((len(times), n_lats), np.nan) for v in vars_to_get}
    n_chunks = (n_lats + chunk - 1) // chunk
    print(f"      _open_meteo: {n_lats} pts / {chunk} per chunk = {n_chunks} chunks, "
          f"{len(vars_to_get)} vars × {len(times)} times", flush=True)
    for c_idx, start in enumerate(range(0, n_lats, chunk)):
        end = min(start + chunk, n_lats)
        params = {
            "latitude": ",".join(f"{x:.3f}" for x in lats[start:end]),
            "longitude": ",".join(f"{x:.3f}" for x in lons[start:end]),
            "hourly": ",".join(vars_to_get),
            "wind_speed_unit": "ms",
            "timezone": "UTC",
            "past_days": 14,
            "forecast_days": 1,
        }
        data = None
        backoff = 30.0
        for attempt in range(max_attempts):
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast",
                                 params=params, timeout=90)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                print(f"      [chunk {c_idx+1}/{n_chunks}] network err attempt "
                      f"{attempt+1}/{max_attempts}: {e}", flush=True)
                time.sleep(backoff); backoff *= 2; continue
            if r.status_code == 429:
                print(f"      [chunk {c_idx+1}/{n_chunks}] 429 rate-limited, "
                      f"attempt {attempt+1}/{max_attempts}, sleeping {backoff:.0f}s", flush=True)
                time.sleep(backoff); backoff *= 2; continue
            if r.status_code >= 500:
                print(f"      [chunk {c_idx+1}/{n_chunks}] server error {r.status_code}, "
                      f"attempt {attempt+1}/{max_attempts}, sleeping {backoff:.0f}s", flush=True)
                time.sleep(backoff); backoff *= 2; continue
            if r.status_code >= 400:
                # 4xx other than 429: usually a query problem (too many points,
                # bad var name) - body explains what.
                print(f"      [chunk {c_idx+1}/{n_chunks}] client error {r.status_code}: "
                      f"{r.text[:300]}", flush=True)
                raise RuntimeError(f"Open-Meteo client error {r.status_code}: {r.text[:200]}")
            data = r.json()
            break
        if data is None:
            raise RuntimeError(f"Open-Meteo exhausted {max_attempts} attempts on chunk "
                               f"{c_idx+1}/{n_chunks}")
        if isinstance(data, dict): data = [data]
        for k, item in enumerate(data):
            hourly = item.get("hourly", {})
            t_list = hourly.get("time", [])
            for var in vars_to_get:
                v_list = hourly.get(var, [])
                for ti, target in enumerate(times):
                    if target in t_list:
                        idx = t_list.index(target)
                        if idx < len(v_list) and v_list[idx] is not None:
                            out[var][ti, start + k] = v_list[idx]
        print(f"      [chunk {c_idx+1}/{n_chunks}] ok ({end}/{n_lats} pts)", flush=True)
        if c_idx < n_chunks - 1:  # no need to sleep after the last chunk
            time.sleep(between_chunk_pause_s)
    return out


def fetch_single_level_wind(pressure: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Fetch wind on the backdrop grid at a single pressure level / single time.
    Returns (lons, lats, U, V, S) or None if rate-limited."""
    cache = CACHE_DIR / f"backdrop_{pressure}_{SAMPLE_TIME_UTC.replace(':','-')}_{GRID_STEP_BACKDROP}deg.npz"
    if cache.exists():
        print(f"  loading cached {pressure} wind: {cache.name}")
        d = np.load(cache)
        return d["lons"], d["lats"], d["U"], d["V"], d["S"]
    lats = np.arange(LAT_MIN, LAT_MAX + GRID_STEP_BACKDROP, GRID_STEP_BACKDROP)
    lons = np.arange(LON_MIN, LON_MAX + GRID_STEP_BACKDROP, GRID_STEP_BACKDROP)
    LON, LAT = np.meshgrid(lons, lats)
    print(f"  fetching {pressure} wind at {LON.size} points")
    try:
        out = _open_meteo([SAMPLE_TIME_UTC], LAT.flatten(), LON.flatten(),
                          [f"wind_speed_{pressure}", f"wind_direction_{pressure}"])
    except RuntimeError as e:
        print(f"  {pressure} fetch failed: {e}")
        return None
    sp = out[f"wind_speed_{pressure}"][0]
    di = out[f"wind_direction_{pressure}"][0]
    di_rad = np.radians(di)
    U = -sp * np.sin(di_rad)
    V = -sp * np.cos(di_rad)
    S = sp
    U = U.reshape(LAT.shape); V = V.reshape(LAT.shape); S = S.reshape(LAT.shape)
    np.savez(cache, lons=lons, lats=lats, U=U, V=V, S=S)
    return lons, lats, U, V, S


def fetch_backdrop_wind() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The main backdrop wind for visualization (300 hPa)."""
    return fetch_single_level_wind(BACKDROP_PRESSURE)


def fetch_drift_winds_multilevel(gap_start: datetime, gap_end: datetime,
                                   backdrop=None) -> dict:
    """Try to fetch multi-level drift winds. If Open-Meteo is rate-limiting,
    fall back to using the (single-pressure, single-time) backdrop wind as a
    frozen field. Honest about its limitations."""
    cache = CACHE_DIR / f"drift_multilevel_{DRIFT_GRID_STEP}deg.npz"
    if cache.exists():
        print(f"  loading cached drift winds: {cache.name}")
        d = np.load(cache, allow_pickle=True)
        return {
            "lats": d["lats"], "lons": d["lons"],
            "times": list(d["times"]),
            "U": {int(p): d[f"U_{p}"] for p in PRESSURE_LEVELS},
            "V": {int(p): d[f"V_{p}"] for p in PRESSURE_LEVELS},
            "mode": "multi-level",
        }

    dr_lats = np.arange(20, 61, DRIFT_GRID_STEP)
    dr_lons = np.arange(-135, 11, DRIFT_GRID_STEP)
    DR_LON, DR_LAT = np.meshgrid(dr_lons, dr_lats)
    flat_la = DR_LAT.flatten(); flat_lo = DR_LON.flatten()

    # Cover the WHOLE flight period, not just the Atlantic gap. US-side hops
    # need pre-gap wind, EU-side hops need post-gap wind. 3 days back gives
    # margin for the launch + CONUS phase; 2 days forward covers EU-side fixes
    # up to and past Málaga.
    times = []
    t = (gap_start - timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
    t_end_window = gap_end + timedelta(days=2)
    while t <= t_end_window:
        times.append(t.strftime("%Y-%m-%dT%H:00"))
        t += timedelta(hours=DRIFT_SAMPLE_HOURS)

    try:
        print(f"  fetching drift winds: {len(flat_la)} pts x {len(times)} times x "
              f"{len(PRESSURE_LEVELS)} levels")
        vars_to_get = []
        for p in PRESSURE_LEVELS:
            vars_to_get.extend([f"wind_speed_{p}hPa", f"wind_direction_{p}hPa"])
        # Smaller chunk than the historical default - multi-level + multi-time
        # responses are heavy, and Open-Meteo will 429 hard on bursts above ~20.
        out = _open_meteo(times, flat_la, flat_lo, vars_to_get,
                          chunk=15, between_chunk_pause_s=15.0, max_attempts=4)
        U_by = {}; V_by = {}
        for p in PRESSURE_LEVELS:
            sp = out[f"wind_speed_{p}hPa"]
            di = out[f"wind_direction_{p}hPa"]
            di_rad = np.radians(di)
            U = (-sp * np.sin(di_rad)).reshape((len(times),) + DR_LAT.shape)
            V = (-sp * np.cos(di_rad)).reshape((len(times),) + DR_LAT.shape)
            U_by[p] = U
            V_by[p] = V
        save_dict = {"lats": dr_lats, "lons": dr_lons, "times": np.array(times)}
        for p in PRESSURE_LEVELS:
            save_dict[f"U_{p}"] = U_by[p]
            save_dict[f"V_{p}"] = V_by[p]
        np.savez(cache, **save_dict)
        print(f"  cached → {cache.name}")
        return {"lats": dr_lats, "lons": dr_lons, "times": times,
                "U": U_by, "V": V_by, "mode": "multi-level"}
    except Exception as e:
        if backdrop is None:
            raise
        print(f"  multi-level fetch failed ({e}); falling back to frozen wind")
        # NOTE: Skip the secondary 500 hPa single-time fetch - when the
        # multi-level fetch fails it's almost always because Open-Meteo is
        # rate-limiting us, and the 500 hPa attempt will hit the same wall.
        # Just use the cached 300 hPa backdrop with synthetic level scaling.
        b_lons, b_lats, b_U, b_V, b_S = backdrop
        real_500 = None
        levels_real = {300: (b_U, b_V)}
        print(f"  using cached 300 hPa only with synthetic pressure scaling")

        U_by = {}; V_by = {}
        for p in PRESSURE_LEVELS:
            if p in levels_real:
                Up, Vp = levels_real[p]
            else:
                # Interpolate / extrapolate from real levels
                p_real = sorted(levels_real.keys())
                if p < p_real[0]:
                    # Above shallowest, slightly amplify (higher altitude → faster jet usually)
                    Up = levels_real[p_real[0]][0] * 1.05
                    Vp = levels_real[p_real[0]][1] * 1.05
                elif p > p_real[-1]:
                    # Below deepest, attenuate
                    Up = levels_real[p_real[-1]][0] * 0.8
                    Vp = levels_real[p_real[-1]][1] * 0.8
                else:
                    # Between two real levels - linear blend
                    for j in range(len(p_real) - 1):
                        if p_real[j] <= p <= p_real[j+1]:
                            w = (p - p_real[j]) / (p_real[j+1] - p_real[j])
                            Up = (1-w)*levels_real[p_real[j]][0] + w*levels_real[p_real[j+1]][0]
                            Vp = (1-w)*levels_real[p_real[j]][1] + w*levels_real[p_real[j+1]][1]
                            break
            U_by[p] = Up[np.newaxis, :, :].repeat(len(times), axis=0)
            V_by[p] = Vp[np.newaxis, :, :].repeat(len(times), axis=0)
        mode = "multi-level-frozen" if real_500 is not None else "single-level-frozen"
        return {"lats": b_lats, "lons": b_lons, "times": times,
                "U": U_by, "V": V_by, "mode": mode}


# ---- ensemble advection ----

def make_interpolators(drift):
    """Legacy adapter for the Open-Meteo dict-based wind field.

    Returns the dict unchanged plus a `_legacy=True` flag so wind_at knows
    to use the in-script bilinear sampler. Kept for the fallback path when
    the NOAA GFS fetch is unavailable.
    """
    lats = drift["lats"]; lons = drift["lons"]
    times_dt = np.array([
        datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        for t in drift["times"]
    ])
    return {"lats": lats, "lons": lons, "times_dt": times_dt,
            "U": drift["U"], "V": drift["V"], "_legacy": True}


def wind_at(wf, t: datetime, lat: float, lon: float,
            pressure_hpa: float, noise_u: float = 0.0, noise_v: float = 0.0) -> tuple[float, float]:
    """Sample (u, v) wind in m/s, with optional additive perturbation.

    Two backends:
      • Shepherd's :class:`RegularGridWindField` (real GFS data) - dispatches
        via :meth:`get_wind`.
      • Legacy dict-of-arrays from Open-Meteo, used when GFS is unavailable.
    """
    if hasattr(wf, "get_wind"):
        t_aware = t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)
        try:
            u, v = wf.get_wind(lat=float(lat), lon=float(lon),
                                pressure_pa=float(pressure_hpa) * 100.0,
                                time=t_aware)
        except Exception:
            return float(noise_u), float(noise_v)
        if not (np.isfinite(u) and np.isfinite(v)):
            return float(noise_u), float(noise_v)
        return float(u) + float(noise_u), float(v) + float(noise_v)

    # ---- Legacy fallback (Open-Meteo dict format) ----
    interp = wf
    times_dt = interp["times_dt"]
    deltas = np.abs((times_dt - np.array(t)).astype("timedelta64[s]").astype(float))
    ti = int(np.argmin(deltas))

    p_levels = sorted(interp["U"].keys())
    if pressure_hpa <= p_levels[0]:
        levels_use = [p_levels[0]]; weights = [1.0]
    elif pressure_hpa >= p_levels[-1]:
        levels_use = [p_levels[-1]]; weights = [1.0]
    else:
        for j in range(len(p_levels) - 1):
            if p_levels[j] <= pressure_hpa <= p_levels[j+1]:
                p_lo, p_hi = p_levels[j], p_levels[j+1]
                w_hi = (pressure_hpa - p_lo) / (p_hi - p_lo)
                w_lo = 1 - w_hi
                levels_use = [p_lo, p_hi]; weights = [w_lo, w_hi]
                break

    lats_g = interp["lats"]; lons_g = interp["lons"]
    i_lat = np.searchsorted(lats_g, lat) - 1
    i_lon = np.searchsorted(lons_g, lon) - 1
    i_lat = max(0, min(i_lat, len(lats_g) - 2))
    i_lon = max(0, min(i_lon, len(lons_g) - 2))
    flat = (lat - lats_g[i_lat]) / (lats_g[i_lat+1] - lats_g[i_lat])
    flon = (lon - lons_g[i_lon]) / (lons_g[i_lon+1] - lons_g[i_lon])
    flat = max(0.0, min(1.0, flat))
    flon = max(0.0, min(1.0, flon))

    u_total = 0.0; v_total = 0.0
    for p, w in zip(levels_use, weights):
        U = interp["U"][p][ti]; V = interp["V"][p][ti]
        u00 = U[i_lat, i_lon]; u01 = U[i_lat, i_lon+1]
        u10 = U[i_lat+1, i_lon]; u11 = U[i_lat+1, i_lon+1]
        v00 = V[i_lat, i_lon]; v01 = V[i_lat, i_lon+1]
        v10 = V[i_lat+1, i_lon]; v11 = V[i_lat+1, i_lon+1]
        u_b = (u00*(1-flat)*(1-flon) + u01*(1-flat)*flon
               + u10*flat*(1-flon) + u11*flat*flon)
        v_b = (v00*(1-flat)*(1-flon) + v01*(1-flat)*flon
               + v10*flat*(1-flon) + v11*flat*flon)
        if np.isfinite(u_b) and np.isfinite(v_b):
            u_total += w * u_b
            v_total += w * v_b
    return float(u_total + noise_u), float(v_total + noise_v)


def fetch_gfs_wind_field(
    start_time: datetime,
    end_time: datetime,
    altitude_m: float,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    cache_dir: Path,
    fxx_stride: int = 3,
    levels_hpa: tuple = (250, 300, 350),
    now_utc: datetime | None = None,
):
    """Build a time-resolved multi-cycle GFS WindField covering [start, end].

    Uses Shepherd's predictor module to:
      • Pick GFS cycles via :func:`gfs_client.latest_cycle_before`
      • Partial-fetch only the UGRD/VGRD pressure-level records via
        byte-range GETs against ``s3://noaa-gfs-bdp-pds`` (no rate limit)
      • Stitch multiple cycles into a single :class:`RegularGridWindField`
        with hourly time resolution

    Spatial subset: lat ∈ [lat_min, lat_max], lon ∈ [lon_min, lon_max] in
    the −180..+180 convention. GFS stores 0..360, so this routine wraps
    the western half (e.g. -135° → 225°) and concatenates.

    Anonymous S3 GETs - no API keys, no rate limits.
    """
    if not _PREDICTOR_AVAILABLE:
        raise RuntimeError(f"predictor module not importable: {_PREDICTOR_ERR}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    # 3 levels tight around the 300 hPa flight altitude is enough for our
    # advection - wider stacks blow up cache size for negligible accuracy.
    levels = tuple(levels_hpa)
    print(f"  GFS levels: {levels} hPa, fxx stride: {fxx_stride}h "
          f"(time res = {fxx_stride}h)", flush=True)

    # Convert our [-180, 180] domain to one or two [0, 360] slices.
    def _to_360(lon):
        return lon if lon >= 0 else lon + 360.0
    if lon_min < 0 and lon_max >= 0:
        slices_360 = [(_to_360(lon_min), 360.0 - 0.001), (0.0, lon_max)]
    elif lon_min < 0 and lon_max < 0:
        slices_360 = [(_to_360(lon_min), _to_360(lon_max))]
    else:
        slices_360 = [(lon_min, lon_max)]

    def _load_fxx(cycle, fxx):
        p = gfs_client.download_uv_pressure_levels(
            cycle, fxx, cache_dir=cache_dir, levels_mb=list(levels)
        )
        ds = gfs_client.open_pressure_levels(p)
        ds = ds.sel(isobaricInhPa=list(levels))
        # Lat: GFS coord is descending (90 → -90); sel with slice(high, low)
        ds = ds.sel(latitude=slice(lat_max, lat_min))
        # Lon: handle the meridian wrap
        if len(slices_360) > 1:
            parts = [ds.sel(longitude=slice(lo, hi)) for lo, hi in slices_360]
            ds = xr.concat(parts, dim="longitude")
        else:
            lo, hi = slices_360[0]
            ds = ds.sel(longitude=slice(lo, hi))
        # Drop the per-file scalar coords that vary by fxx and would break concat
        for c in ("time", "step", "valid_time"):
            if c in ds.coords:
                ds = ds.drop_vars(c)
        vt = (cycle.cycle_dt + timedelta(hours=int(fxx))).replace(tzinfo=None)
        ds = ds.expand_dims(time=[np.datetime64(vt, "ns")])
        return ds

    # Walk through the requested window, fetching ~30 hours from each cycle
    # then jumping forward.
    all_snapshots = []
    seen_times: set = set()
    cur = start_time
    n_failed_cycles = 0
    while cur < end_time + timedelta(hours=6):
        # Pick the FRESHEST cycle for `cur`: must have cycle_dt ≤ cur AND
        # cycle is published (cycle_dt + 4h ≤ now_utc). For forecasts whose
        # window starts in the past relative to now, this picks much fresher
        # cycles than the bare `latest_cycle_before(cur, 4)` would.
        if now_utc is not None:
            upper = min(cur, now_utc - timedelta(hours=4))
            h = (upper.hour // 6) * 6
            cycle_dt_pick = upper.replace(hour=h, minute=0, second=0, microsecond=0)
            cycle = gfs_client.GFSCycle(cycle_dt=cycle_dt_pick)
        else:
            cycle = gfs_client.latest_cycle_before(cur, latency_padding_h=4.0)
        if cycle.cycle_dt > cur:
            cycle = gfs_client.latest_cycle_before(cur - timedelta(hours=6))
        elapsed_h = (cur - cycle.cycle_dt).total_seconds() / 3600.0
        fxx_start = max(0, int(math.floor(elapsed_h)))
        fxx_end = min(fxx_start + 30, 120)
        # Align fxx_start to the nearest stride so consecutive cycles share
        # the same time grid (avoids weird half-hour offsets in the stitched
        # WindField).
        if fxx_stride > 1:
            fxx_start = ((fxx_start + fxx_stride - 1) // fxx_stride) * fxx_stride
        print(f"  GFS cycle {cycle.cycle_dt.isoformat()} fxx {fxx_start}..{fxx_end} "
              f"stride {fxx_stride}", flush=True)
        # Concurrent partial-fetch - byte-range GETs against S3 are IO-bound,
        # so 8 workers gives ~6× speedup over sequential fetching.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        fxx_todo = []
        for fxx in range(fxx_start, fxx_end + 1, fxx_stride):
            vt = (cycle.cycle_dt + timedelta(hours=int(fxx))).replace(tzinfo=None)
            t_key = np.datetime64(vt, "ns")
            if t_key in seen_times:
                continue
            fxx_todo.append((fxx, t_key))
        n_loaded_this_cycle = 0
        bail_after = None
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_load_fxx, cycle, fxx): (fxx, t_key)
                        for fxx, t_key in fxx_todo}
            for fut in as_completed(futures):
                fxx, t_key = futures[fut]
                try:
                    ds = fut.result()
                except FileNotFoundError as e:
                    # Forecast hour not yet uploaded - record where we stop
                    if bail_after is None or fxx < bail_after:
                        bail_after = fxx
                    continue
                except Exception as e:
                    print(f"    fxx {fxx} load failed ({e})", flush=True)
                    continue
                all_snapshots.append(ds)
                seen_times.add(t_key)
                n_loaded_this_cycle += 1
        if bail_after is not None:
            print(f"    cycle truncated at fxx {bail_after} (not yet uploaded)", flush=True)
        if n_loaded_this_cycle == 0:
            n_failed_cycles += 1
            if n_failed_cycles >= 2:
                raise RuntimeError("two consecutive GFS cycles produced no data; aborting")
        else:
            n_failed_cycles = 0
        cur = cycle.cycle_dt + timedelta(hours=fxx_end + 1)

    if not all_snapshots:
        raise RuntimeError("no GFS data could be fetched")

    print(f"  stitching {len(all_snapshots)} GFS snapshots into a single WindField", flush=True)
    combined = xr.concat(all_snapshots, dim="time", coords="minimal")
    # Concurrent fxx fetches finish in arbitrary order; sort the time axis to
    # ascending. RegularGridWindField uses np.searchsorted on this axis and
    # would silently return wrong wind values if it were unsorted.
    combined = combined.sortby("time")
    combined = combined.assign_coords(valid_time=("time", combined["time"].values))
    return RegularGridWindField(combined, time_dim="time")


def advect_single(interp, start_pos, start_time, end_time,
                   pressure_schedule, dt_minutes=30,
                   noise_u: float = 0.0, noise_v: float = 0.0) -> list[tuple]:
    """RK4 forward advection with time-varying pressure schedule and an
    optional constant additive wind-field perturbation (noise_u, noise_v)."""
    R = 6371000.0
    path = [(start_time, start_pos[0], start_pos[1])]
    t = start_time
    lat, lon = start_pos
    dt_s = dt_minutes * 60
    while t < end_time:
        p_cur = pressure_schedule(t)
        u1, v1 = wind_at(interp, t, lat, lon, p_cur, noise_u, noise_v)
        k1_lat = (v1 / R) * (180 / math.pi)
        k1_lon = (u1 / (R * math.cos(math.radians(lat)))) * (180 / math.pi)

        t_half = t + timedelta(seconds=dt_s / 2)
        p_half = pressure_schedule(t_half)
        u2, v2 = wind_at(interp, t_half,
                         lat + k1_lat*dt_s/2, lon + k1_lon*dt_s/2, p_half, noise_u, noise_v)
        k2_lat = (v2 / R) * (180 / math.pi)
        k2_lon = (u2 / (R * math.cos(math.radians(lat + k1_lat*dt_s/2)))) * (180 / math.pi)

        u3, v3 = wind_at(interp, t_half,
                         lat + k2_lat*dt_s/2, lon + k2_lon*dt_s/2, p_half, noise_u, noise_v)
        k3_lat = (v3 / R) * (180 / math.pi)
        k3_lon = (u3 / (R * math.cos(math.radians(lat + k2_lat*dt_s/2)))) * (180 / math.pi)

        t_full = t + timedelta(seconds=dt_s)
        p_full = pressure_schedule(t_full)
        u4, v4 = wind_at(interp, t_full,
                         lat + k3_lat*dt_s, lon + k3_lon*dt_s, p_full, noise_u, noise_v)
        k4_lat = (v4 / R) * (180 / math.pi)
        k4_lon = (u4 / (R * math.cos(math.radians(lat + k3_lat*dt_s)))) * (180 / math.pi)

        lat += dt_s/6 * (k1_lat + 2*k2_lat + 2*k3_lat + k4_lat)
        lon += dt_s/6 * (k1_lon + 2*k2_lon + 2*k3_lon + k4_lon)
        t = t_full
        path.append((t, lat, lon))
    return path


def make_pressure_schedule(p_day: float, p_night: float,
                            lat: float) -> callable:
    """Return a callable that gives pressure as a function of time, based on
    a simple diurnal model (day = lower pressure / higher alt, night = higher
    pressure / lower alt)."""
    def schedule(t: datetime) -> float:
        # Approximate local solar time at the rough mid-Atlantic longitude
        local_hour = (t.hour + t.minute / 60.0) - 2.0  # mid-Atlantic UTC shift ~ -2h
        local_hour = local_hour % 24
        # smooth day/night blend centered on noon
        x = math.cos(2 * math.pi * (local_hour - 12) / 24)
        # x = 1 at noon (day), -1 at midnight (night)
        # Day -> p_day, Night -> p_night
        w_day = (x + 1) / 2
        return w_day * p_day + (1 - w_day) * p_night
    return schedule


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((lat2-lat1)*p)/2
         + math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def advect_backward(interp, end_pos, start_time, end_time,
                     pressure_schedule, dt_minutes=30,
                     noise_u: float = 0.0, noise_v: float = 0.0) -> list[tuple]:
    """Backward integration with optional wind perturbation."""
    R = 6371000.0
    rev_path = [(end_time, end_pos[0], end_pos[1])]
    t = end_time
    lat, lon = end_pos
    dt_s = dt_minutes * 60
    while t > start_time:
        p_cur = pressure_schedule(t)
        u1, v1 = wind_at(interp, t, lat, lon, p_cur, noise_u, noise_v)
        u1, v1 = -u1, -v1
        k1_lat = (v1 / R) * (180 / math.pi)
        k1_lon = (u1 / (R * math.cos(math.radians(lat)))) * (180 / math.pi)

        t_half = t - timedelta(seconds=dt_s / 2)
        p_half = pressure_schedule(t_half)
        u2, v2 = wind_at(interp, t_half,
                         lat + k1_lat*dt_s/2, lon + k1_lon*dt_s/2, p_half, noise_u, noise_v)
        u2, v2 = -u2, -v2
        k2_lat = (v2 / R) * (180 / math.pi)
        k2_lon = (u2 / (R * math.cos(math.radians(lat + k1_lat*dt_s/2)))) * (180 / math.pi)

        u3, v3 = wind_at(interp, t_half,
                         lat + k2_lat*dt_s/2, lon + k2_lon*dt_s/2, p_half, noise_u, noise_v)
        u3, v3 = -u3, -v3
        k3_lat = (v3 / R) * (180 / math.pi)
        k3_lon = (u3 / (R * math.cos(math.radians(lat + k2_lat*dt_s/2)))) * (180 / math.pi)

        t_full = t - timedelta(seconds=dt_s)
        p_full = pressure_schedule(t_full)
        u4, v4 = wind_at(interp, t_full,
                         lat + k3_lat*dt_s, lon + k3_lon*dt_s, p_full, noise_u, noise_v)
        u4, v4 = -u4, -v4
        k4_lat = (v4 / R) * (180 / math.pi)
        k4_lon = (u4 / (R * math.cos(math.radians(lat + k3_lat*dt_s)))) * (180 / math.pi)

        lat += dt_s/6 * (k1_lat + 2*k2_lat + 2*k3_lat + k4_lat)
        lon += dt_s/6 * (k1_lon + 2*k2_lon + 2*k3_lon + k4_lon)
        t = t_full
        rev_path.append((t, lat, lon))
    return list(reversed(rev_path))


def advect_segment_anchored(interp, pos_a, t_a, pos_b, t_b,
                              pressure: float = 300.0, dt_minutes: int = 30) -> list[tuple]:
    """Wind-driven path from pos_a@t_a to pos_b@t_b that lands EXACTLY at pos_b.

    Forward-integrate at the given pressure, then linearly blend a correction
    along the path so the endpoint matches. Used to draw a curved-by-wind
    segment between two known GPS fixes (rather than a straight chord) while
    still passing through both fixes precisely.
    """
    if not isinstance(t_a, datetime):
        t_a = pd.to_datetime(t_a).to_pydatetime()
        if t_a.tzinfo is None: t_a = t_a.replace(tzinfo=timezone.utc)
    if not isinstance(t_b, datetime):
        t_b = pd.to_datetime(t_b).to_pydatetime()
        if t_b.tzinfo is None: t_b = t_b.replace(tzinfo=timezone.utc)
    if t_b <= t_a:
        return [(t_a, pos_a[0], pos_a[1]), (t_b, pos_b[0], pos_b[1])]
    schedule = lambda _t, _p=pressure: _p
    path = advect_single(interp, pos_a, t_a, t_b, schedule, dt_minutes=dt_minutes)
    if len(path) < 2:
        return [(t_a, pos_a[0], pos_a[1]), (t_b, pos_b[0], pos_b[1])]
    end_lat, end_lon = path[-1][1], path[-1][2]
    d_lat = pos_b[0] - end_lat
    d_lon = pos_b[1] - end_lon
    n = len(path)
    out = []
    for i, (t, la, lo) in enumerate(path):
        a = i / (n - 1)
        out.append((t, la + a * d_lat, lo + a * d_lon))
    # Force endpoints exact (numerical paranoia)
    out[0] = (out[0][0], pos_a[0], pos_a[1])
    out[-1] = (out[-1][0], pos_b[0], pos_b[1])
    return out


def run_ensemble_bidirectional(interp, start_pos, start_time, end_pos, end_time,
                                  n=N_ENSEMBLE, seed=RNG_SEED):
    """Bidirectional shooting-method ensemble. Each member runs:
      forward from start_pos → some midpoint, AND
      backward from end_pos → some other midpoint.
    Score = great-circle distance between the two midpoints. Members whose
    forward and backward halves agree at the middle are best - those are the
    members that actually fit both endpoints simultaneously."""
    rng = np.random.default_rng(seed)
    members = []
    lat0_jit = START_POS_SIGMA_KM / 111.0
    lon0_jit_s = START_POS_SIGMA_KM / (111.0 * math.cos(math.radians(start_pos[0])))
    lat1_jit = START_POS_SIGMA_KM / 111.0
    lon1_jit_e = START_POS_SIGMA_KM / (111.0 * math.cos(math.radians(end_pos[0])))

    # Define midpoint time
    mid_time = start_time + (end_time - start_time) / 2

    print(f"  running {n} bidirectional ensemble members...")
    for k in range(n):
        dlat_s = rng.normal(0, lat0_jit)
        dlon_s = rng.normal(0, lon0_jit_s)
        dlat_e = rng.normal(0, lat1_jit)
        dlon_e = rng.normal(0, lon1_jit_e)
        dt_s_hrs = rng.normal(0, START_TIME_SIGMA_HR)
        dt_e_hrs = rng.normal(0, START_TIME_SIGMA_HR)
        p_day = float(rng.uniform(260, 340))
        p_night = float(rng.uniform(p_day + 30, 480))
        # Per-member additive wind perturbation (m/s) - represents wind-data
        # uncertainty since we only have one frozen time snapshot.
        noise_u = float(rng.normal(0, WIND_NOISE_STD))
        noise_v = float(rng.normal(0, WIND_NOISE_STD))

        s_pos = (start_pos[0] + dlat_s, start_pos[1] + dlon_s)
        e_pos = (end_pos[0] + dlat_e, end_pos[1] + dlon_e)
        s_t = start_time + timedelta(hours=dt_s_hrs)
        e_t = end_time + timedelta(hours=dt_e_hrs)
        schedule = make_pressure_schedule(p_day, p_night, (s_pos[0] + e_pos[0]) / 2)

        try:
            fwd = advect_single(interp, s_pos, s_t, mid_time, schedule, dt_minutes=30,
                                noise_u=noise_u, noise_v=noise_v)
            bwd = advect_backward(interp, e_pos, mid_time, e_t, schedule, dt_minutes=30,
                                   noise_u=noise_u, noise_v=noise_v)
        except Exception:
            continue

        # Midpoint = where forward ended (fwd[-1]) and where backward started (bwd[0])
        fwd_mid_lat, fwd_mid_lon = fwd[-1][1], fwd[-1][2]
        bwd_mid_lat, bwd_mid_lon = bwd[0][1], bwd[0][2]
        mid_err_km = haversine_km(fwd_mid_lat, fwd_mid_lon,
                                   bwd_mid_lat, bwd_mid_lon)

        # Stitched path: forward half + backward half, with smooth blend over
        # a window around the midpoint
        full_path = list(fwd) + list(bwd[1:])
        members.append({"fwd": fwd, "bwd": bwd, "path": full_path,
                        "err_km": mid_err_km,
                        "p_day": p_day, "p_night": p_night})
        if (k + 1) % 100 == 0:
            print(f"    {k+1}/{n} done", flush=True)
    print(f"  ensemble complete: {len(members)} members", flush=True)
    return members


def run_ensemble(interp, start_pos, start_time, end_time,
                  target_pos, n=N_ENSEMBLE, seed=RNG_SEED):
    """Backward-compat alias to the bidirectional version."""
    return run_ensemble_bidirectional(interp, start_pos, start_time,
                                        target_pos, end_time, n, seed)


def summarise_ensemble(members, n_time_points=80, target_pos=None, start_pos_known=None, **kwargs):
    """Resample all paths to a common time grid then compute weighted mean
    and percentiles. If target_pos is given, apply linear endpoint anchoring
    to the mean path so it lands at the known endpoint while preserving the
    wind-driven middle shape."""
    if not members: return None
    # Build a common time grid from the first member's path
    paths = [m["path"] for m in members]
    t0 = paths[0][0][0]; tN = paths[0][-1][0]
    common_t = [t0 + i * (tN - t0) / (n_time_points - 1) for i in range(n_time_points)]

    # Resample each path to common grid by linear interpolation in time
    resampled_lat = np.full((len(paths), n_time_points), np.nan)
    resampled_lon = np.full((len(paths), n_time_points), np.nan)
    for mi, p in enumerate(paths):
        p_times = [pp[0] for pp in p]
        p_lats = np.array([pp[1] for pp in p])
        p_lons = np.array([pp[2] for pp in p])
        # convert to seconds since t0 for interpolation
        p_secs = np.array([(t - p_times[0]).total_seconds() for t in p_times])
        c_secs = np.array([(t - p_times[0]).total_seconds() for t in common_t])
        resampled_lat[mi] = np.interp(c_secs, p_secs, p_lats)
        resampled_lon[mi] = np.interp(c_secs, p_secs, p_lons)

    # Drop members whose resampled paths contain NaN/inf (e.g. wind-interpolation
    # blow-ups when a perturbed member walks far off the wind grid).
    good = (np.isfinite(resampled_lat).all(axis=1)
            & np.isfinite(resampled_lon).all(axis=1)
            & np.isfinite(np.array([m["err_km"] for m in members])))
    n_bad = int((~good).sum())
    if n_bad:
        print(f"  dropping {n_bad}/{len(members)} ensemble members with NaN/inf paths")
    resampled_lat = resampled_lat[good]
    resampled_lon = resampled_lon[good]
    members = [m for m, g in zip(members, good) if g]
    if not members:
        return None

    # Weights from endpoint error (gaussian)
    errs = np.array([m["err_km"] for m in members])
    weights = np.exp(-(errs**2) / (2 * ENDPOINT_SCALE_KM**2))
    weights /= weights.sum()

    # Weighted mean
    mean_lat = (resampled_lat * weights[:, None]).sum(axis=0)
    mean_lon = (resampled_lon * weights[:, None]).sum(axis=0)

    # Weighted percentiles approximated via weighted distribution
    # Sort along each time column by lat, accumulate weights, find p25/p75
    def weighted_percentile(values, weights, q):
        order = np.argsort(values)
        v_sorted = values[order]
        w_sorted = weights[order]
        cum = np.cumsum(w_sorted)
        cum /= cum[-1]
        idx = np.searchsorted(cum, q)
        idx = min(idx, len(v_sorted) - 1)
        return v_sorted[idx]

    p25_lat = np.array([weighted_percentile(resampled_lat[:, j], weights, 0.25)
                         for j in range(n_time_points)])
    p75_lat = np.array([weighted_percentile(resampled_lat[:, j], weights, 0.75)
                         for j in range(n_time_points)])
    p25_lon = np.array([weighted_percentile(resampled_lon[:, j], weights, 0.25)
                         for j in range(n_time_points)])
    p75_lon = np.array([weighted_percentile(resampled_lon[:, j], weights, 0.75)
                         for j in range(n_time_points)])

    # Smooth the percentile bands with a Savitzky-Golay filter so the envelope
    # flows smoothly rather than wiggling member-by-member.
    try:
        from scipy.signal import savgol_filter
        win = max(7, min(31, n_time_points // 6) | 1)   # odd window, ~1/6 of length
        p25_lat = savgol_filter(p25_lat, win, 3)
        p75_lat = savgol_filter(p75_lat, win, 3)
        p25_lon = savgol_filter(p25_lon, win, 3)
        p75_lon = savgol_filter(p75_lon, win, 3)
        mean_lat = savgol_filter(mean_lat, win, 3)
        mean_lon = savgol_filter(mean_lon, win, 3)
    except ImportError:
        pass

    # Top-N best matches
    best_idx = np.argsort(errs)[:max(5, len(errs) // 20)]

    # Dual-endpoint anchoring: the mean path starts exactly at start_pos and
    # ends exactly at end_pos. Linear blend between the start-side correction
    # and the end-side correction interpolates through the middle.
    if target_pos is not None and start_pos_known is not None:
        s_lat_actual, s_lon_actual = start_pos_known
        e_lat_actual, e_lon_actual = target_pos
        s_lat_off = s_lat_actual - mean_lat[0]
        s_lon_off = s_lon_actual - mean_lon[0]
        e_lat_off = e_lat_actual - mean_lat[-1]
        e_lon_off = e_lon_actual - mean_lon[-1]
        alpha = np.linspace(0.0, 1.0, len(mean_lat))
        # Blend: alpha=0 → full start correction, alpha=1 → full end correction
        d_lat = (1 - alpha) * s_lat_off + alpha * e_lat_off
        d_lon = (1 - alpha) * s_lon_off + alpha * e_lon_off
        mean_lat = mean_lat + d_lat
        mean_lon = mean_lon + d_lon
        p25_lat = p25_lat + d_lat; p75_lat = p75_lat + d_lat
        p25_lon = p25_lon + d_lon; p75_lon = p75_lon + d_lon
    elif target_pos is not None:
        # Fallback: single-endpoint anchoring
        d_lat = target_pos[0] - mean_lat[-1]
        d_lon = target_pos[1] - mean_lon[-1]
        alpha = np.linspace(0.0, 1.0, len(mean_lat))
        mean_lat = mean_lat + alpha * d_lat
        mean_lon = mean_lon + alpha * d_lon
        p25_lat = p25_lat + alpha * d_lat; p75_lat = p75_lat + alpha * d_lat
        p25_lon = p25_lon + alpha * d_lon; p75_lon = p75_lon + alpha * d_lon

    return {
        "common_t": common_t,
        "mean_lat": mean_lat, "mean_lon": mean_lon,
        "p25_lat": p25_lat, "p75_lat": p75_lat,
        "p25_lon": p25_lon, "p75_lon": p75_lon,
        "best_idx": best_idx, "all_lat": resampled_lat, "all_lon": resampled_lon,
        "errs": errs, "weights": weights, "members": members,
    }


# ---- plotting ----

def plot(track, lons, lats, U, V, S, ens_summary, last_us_pos, first_eu_pos, interp=None):
    # Sized so the map (with its natural ~145°W / 38°N projected aspect)
    # essentially fills the axes vertically - no centered-blank-space artifact.
    fig = plt.figure(figsize=(22, 7.8), facecolor="#0a0a14")
    proj = ccrs.PlateCarree(central_longitude=-60)
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())
    ax.set_anchor("N")   # if any vertical slack remains, push the map to top
    ax.set_facecolor("#0a0a14")

    # Wind palette
    wind_colors = [
        (0.04, 0.08, 0.18), (0.07, 0.18, 0.40), (0.08, 0.40, 0.55),
        (0.18, 0.65, 0.50), (0.42, 0.82, 0.38), (0.86, 0.88, 0.20),
        (0.98, 0.60, 0.10), (0.95, 0.25, 0.18), (0.85, 0.20, 0.55),
        (0.75, 0.40, 0.85),
    ]
    wind_cmap = mcolors.LinearSegmentedColormap.from_list("wind", wind_colors, N=512)

    LON_grid, LAT_grid = np.meshgrid(lons, lats)
    S_filled = np.where(np.isfinite(S), S, 0)
    pcm = ax.pcolormesh(
        LON_grid, LAT_grid, S_filled,
        cmap=wind_cmap, vmin=0, vmax=60,
        shading="gouraud", transform=ccrs.PlateCarree(),
        zorder=1, alpha=0.55,
    )

    # Streamlines
    lon_fine = np.linspace(LON_MIN, LON_MAX, 280)
    lat_fine = np.linspace(LAT_MIN, LAT_MAX, 120)
    LON_fine, LAT_fine = np.meshgrid(lon_fine, lat_fine)
    valid = np.isfinite(S)
    pts = np.column_stack([LON_grid[valid], LAT_grid[valid]])
    U_fine = griddata(pts, U[valid], (LON_fine, LAT_fine), method="cubic")
    V_fine = griddata(pts, V[valid], (LON_fine, LAT_fine), method="cubic")
    ax.streamplot(
        LON_fine, LAT_fine, U_fine, V_fine,
        density=4.5, linewidth=0.4,
        color=(1, 1, 1, 0.5), arrowsize=0,
        transform=ccrs.PlateCarree(), zorder=2,
    )

    # Coastlines, borders
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"),
                   linewidth=0.85, edgecolor=(0.92, 0.94, 0.99, 0.85), zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"),
                   linewidth=0.55, edgecolor=(0.86, 0.90, 0.96, 0.65), zorder=3)
    ax.add_feature(cfeature.LAKES.with_scale("50m"),
                   facecolor=(0.04, 0.06, 0.10, 0.55),
                   edgecolor=(0.50, 0.55, 0.65, 0.45), linewidth=0.35, zorder=3)

    # Use raw GPS fixes as waypoints (no cluster averaging). Averaging fixes
    # into centroids loses two things we need: (a) the exact (lat, lon) of
    # every reported position, and (b) the exact time of the LAST fix before
    # a long gap - which is what should anchor the start of a reconstruction
    # segment. Reconstructing from a centroid time/position creates the spin
    # visible near Spain.
    #
    # We do one piece of filtering: drop fixes whose implied speed from the
    # previous good fix exceeds an absolute physical ceiling. 80 m/s caps at
    # the strongest jet-stream wind ever observed (Concorde-era N. Atlantic
    # peak ~ 145 m/s in *headwind*, balloon ground-speed never reaches that).
    # Anything above that is a packet-decoding glitch or GPS error, not motion.
    raw_lats = track["lat"].values
    raw_lons = track["lon"].values
    raw_times = pd.to_datetime(track["time"].values)

    def _hav_km(la1, lo1, la2, lo2):
        p = math.pi / 180.0
        a = (0.5 - math.cos((la2-la1)*p)/2
             + math.cos(la1*p)*math.cos(la2*p)*(1-math.cos((lo2-lo1)*p))/2)
        return 2 * 6371 * math.asin(math.sqrt(a))

    SPEED_CAP_MPS = 80.0
    keep_mask = [True]
    for i in range(1, len(raw_lats)):
        # Walk back to the last fix we accepted.
        j = i - 1
        while j >= 0 and not keep_mask[j]:
            j -= 1
        if j < 0:
            keep_mask.append(True); continue
        dt_s = (raw_times[i] - raw_times[j]).total_seconds()
        if dt_s <= 0:
            keep_mask.append(False); continue
        dd_m = _hav_km(raw_lats[i], raw_lons[i], raw_lats[j], raw_lons[j]) * 1000.0
        v_mps = dd_m / dt_s
        keep_mask.append(v_mps <= SPEED_CAP_MPS)
    keep_arr = np.array(keep_mask)
    n_dropped = int((~keep_arr).sum())

    way_lats = raw_lats[keep_arr]
    way_lons = raw_lons[keep_arr]
    way_times = raw_times[keep_arr]
    print(f"  raw fixes: {len(raw_lats)} | dropped {n_dropped} as physically impossible "
          f"(>{SPEED_CAP_MPS:.0f} m/s) | path waypoints: {len(way_lats)}")

    # Split at the largest time gap = Atlantic crossing
    gaps_h = np.diff(way_times) / np.timedelta64(1, "h")
    big_idx = int(np.argmax(gaps_h))

    gps_lats = way_lats
    gps_lons = way_lons
    gps_times = way_times
    run_us = (way_lats[:big_idx + 1], way_lons[:big_idx + 1])
    run_eu = (way_lats[big_idx + 1:], way_lons[big_idx + 1:])

    # 25-75 percentile envelope only across the reconstructed gap.
    # IMPORTANT: sort the polygon by longitude so the envelope renders as a
    # single ribbon, not a self-intersecting bowtie (which would create the
    # 'curl/spin' visual where the path momentarily backtracks).
    if ens_summary:
        order = np.argsort(ens_summary["mean_lon"])
        sorted_lon = np.array(ens_summary["mean_lon"])[order]
        sorted_p25_lat = np.array(ens_summary["p25_lat"])[order]
        sorted_p75_lat = np.array(ens_summary["p75_lat"])[order]
        poly_lon = np.concatenate([sorted_lon, sorted_lon[::-1]])
        poly_lat = np.concatenate([sorted_p25_lat, sorted_p75_lat[::-1]])
        ax.fill(poly_lon, poly_lat,
                color=(1.00, 0.85, 0.55, 0.18),
                edgecolor="none",
                transform=ccrs.PlateCarree(), zorder=7)

    line_color = (1.00, 0.97, 0.90, 1.00)        # bright cream stroke

    # ---- Path construction: segment-by-segment between every raw waypoint.
    # Three policies:
    #   1. Atlantic crossing (i == big_idx) → use the 2000-member ensemble mean
    #      we already computed (endpoint-pinned to the actual waypoints).
    #   2. Long non-Atlantic gap (> LONG_GAP_HRS) → straight chord. We don't
    #      have time-matched wind data for these gaps (our wind snapshot is
    #      May 24); integrating frozen wind for 24h can trace eddies that
    #      don't reflect the actual conditions. A chord is the honest answer.
    #   3. Short hop (≤ LONG_GAP_HRS) → wind-advect with endpoint anchoring.
    #      Wind effect is small over short times but adds visible character.
    LONG_GAP_HRS = 8.0
    n_chord = 0
    n_wind = 0
    segments_lon, segments_lat = [], []
    if interp is not None:
        for i in range(len(way_lats) - 1):
            pa = (float(way_lats[i]),     float(way_lons[i]))
            pb = (float(way_lats[i + 1]), float(way_lons[i + 1]))
            ta = pd.to_datetime(way_times[i]).to_pydatetime()
            tb = pd.to_datetime(way_times[i + 1]).to_pydatetime()
            if ta.tzinfo is None: ta = ta.replace(tzinfo=timezone.utc)
            if tb.tzinfo is None: tb = tb.replace(tzinfo=timezone.utc)
            gap_hr = (tb - ta).total_seconds() / 3600.0
            if i == big_idx and ens_summary is not None:
                rec_lon = np.array(ens_summary["mean_lon"], dtype=float)
                rec_lat = np.array(ens_summary["mean_lat"], dtype=float)
                rec_lon[0]  = pa[1]; rec_lat[0]  = pa[0]
                rec_lon[-1] = pb[1]; rec_lat[-1] = pb[0]
                seg_lo = rec_lon.tolist(); seg_la = rec_lat.tolist()
            elif gap_hr > LONG_GAP_HRS:
                seg_lo = [pa[1], pb[1]]
                seg_la = [pa[0], pb[0]]
                n_chord += 1
            else:
                gap_min = gap_hr * 60.0
                # Aim for ~10 wind-advected sample points per segment;
                # never finer than 1 min, never coarser than 30 min.
                dt_min = max(1.0, min(30.0, gap_min / 10.0))
                seg = advect_segment_anchored(interp, pa, ta, pb, tb,
                                                pressure=300.0, dt_minutes=dt_min)
                seg_lo = [s[2] for s in seg]
                seg_la = [s[1] for s in seg]
                n_wind += 1
            segments_lon.append(seg_lo)
            segments_lat.append(seg_la)
        print(f"  segments: ensemble=1, wind-advected={n_wind}, chord={n_chord}")
    else:
        # Fallback: straight chords if we somehow lost the interpolator
        for i in range(len(way_lats) - 1):
            segments_lon.append([float(way_lons[i]), float(way_lons[i + 1])])
            segments_lat.append([float(way_lats[i]), float(way_lats[i + 1])])

    # Concatenate segments, dropping each successor's duplicated start point
    full_lon = list(segments_lon[0])
    full_lat = list(segments_lat[0])
    for slo, sla in zip(segments_lon[1:], segments_lat[1:]):
        full_lon.extend(slo[1:])
        full_lat.extend(sla[1:])

    arr_lon = np.array(full_lon); arr_lat = np.array(full_lat)
    print(f"  path: {len(arr_lon)} pts across {len(segments_lon)} wind-advected segments, "
          f"lon [{arr_lon.min():.2f}, {arr_lon.max():.2f}], "
          f"lat [{arr_lat.min():.2f}, {arr_lat.max():.2f}], "
          f"NaN: lon={int(np.isnan(arr_lon).sum())} lat={int(np.isnan(arr_lat).sum())}")

    # Persist the reconstructed polyline so sister scripts (e.g. the gateway
    # overlay) can reuse it bit-exactly without re-running the ensemble.
    try:
        _path_cache = CACHE_DIR / "reconstructed_path.npz"
        np.savez(_path_cache,
                  full_lon=arr_lon, full_lat=arr_lat,
                  way_lons=np.asarray(way_lons), way_lats=np.asarray(way_lats))
        print(f"  cached reconstructed path → {_path_cache.name}")
    except Exception as _e:
        print(f"  could not cache path: {_e}")

    # Single clean cream stroke - no dark outer border. The brightness against
    # the dark base + the slight halo from anti-aliasing carries readability
    # everywhere on the map.
    ax.plot(full_lon, full_lat,
            color=line_color, linewidth=2.4,
            solid_capstyle="round", solid_joinstyle="round",
            transform=ccrs.PlateCarree(), zorder=10)

    # Subtle dots at every recorded GPS fix - visual proof the line is
    # anchored to actual telemetry, not interpolation.
    ax.scatter(gps_lons, gps_lats,
               s=9, c=[(1.00, 0.95, 0.78, 0.75)],
               edgecolors=(0.10, 0.10, 0.14, 0.7), linewidths=0.4,
               transform=ccrs.PlateCarree(), zorder=11)

    # Launch and current markers - both small + white
    ax.scatter(gps_lons[0], gps_lats[0],
               s=130, c="white", marker="o",
               edgecolors=(0.10, 0.10, 0.14, 0.9), linewidths=1.2,
               transform=ccrs.PlateCarree(), zorder=13)
    ax.scatter(gps_lons[-1], gps_lats[-1],
               s=150, c="white", marker="o",
               edgecolors=(0.10, 0.10, 0.14, 0.9), linewidths=1.2,
               transform=ccrs.PlateCarree(), zorder=13)

    # Colorbar
    cbar = fig.colorbar(pcm, ax=ax, orientation="horizontal",
                        pad=0.04, shrink=0.32, aspect=30)
    cbar.set_label("wind speed at 300 hPa  •  m/s",
                   color="#e6e6f0", fontsize=10)
    cbar.ax.xaxis.set_tick_params(color="#a8a8b8", labelcolor="#cccce0", labelsize=9)
    cbar.outline.set_edgecolor("#444450")

    # Stats for caption
    if ens_summary:
        best_err = ens_summary["errs"].min()
        n_kept = (ens_summary["errs"] < 2 * ENDPOINT_SCALE_KM).sum()
    else:
        best_err = float("nan")
        n_kept = 0

    # Title (no em-dash)
    fig.text(0.5, 0.945,
             "Stratolink-3 Transatlantic Flight",
             color="#f0f0fa", fontsize=28, fontweight="light",
             ha="center", va="center")
    # Subtitle: single wider line
    fig.text(0.5, 0.882,
             "Launched 2026-05-17 from SF.  Now over Spain, 2026-05-29.  "
             "~9,400 km of drift across 12 days of flight.",
             color="#c8ccd6", fontsize=13, ha="center", va="center")
    # Description: two slightly wider lines
    fig.text(0.5, 0.825,
             f"Reconstruction: {len(ens_summary['members'])}-member bidirectional ensemble - "
             f"perturbed start + diurnal altitude schedule, weighted by midpoint convergence.\n"
             f"Line passes through every clustered GPS waypoint; reconstruction fills the Atlantic gap.  "
             f"Shaded band = 25-75% confidence envelope.",
             color="#9aa0b0", fontsize=10.5, ha="center", va="center",
             linespacing=1.5)

    ax.text(0.99, 0.012,
            "data: stratolink.org + GFS wind via open-meteo",
            transform=ax.transAxes, color="#888898", fontsize=9,
            va="bottom", ha="right")

    # A touch tighter than 0.73 - small reduction in the desc-to-map gap.
    plt.subplots_adjust(top=0.755, bottom=0.10, left=0.02, right=0.98)

    plt.savefig(OUT_PNG, dpi=240, bbox_inches="tight", pad_inches=0.08,
                facecolor=fig.get_facecolor())
    print(f"  wrote {OUT_PNG}")


def main():
    if not SBKEY: sys.exit("Set SBKEY")
    print("[1/5] Fetching track...")
    track = fetch_track()
    print(f"  {len(track)} fresh GPS fixes")
    gaps = track["time"].diff().dt.total_seconds() / 3600
    biggest = gaps.idxmax()
    gap_start = track["time"].iloc[biggest - 1].to_pydatetime()
    gap_end = track["time"].iloc[biggest].to_pydatetime()
    last_us_pos = (track["lat"].iloc[biggest - 1], track["lon"].iloc[biggest - 1])
    first_eu_pos = (track["lat"].iloc[biggest], track["lon"].iloc[biggest])
    print(f"  GAP: {gap_start.isoformat()[:19]} → {gap_end.isoformat()[:19]} "
          f"({gaps.iloc[biggest]:.1f} h)")
    print(f"  from {last_us_pos[0]:.2f}, {last_us_pos[1]:.2f} "
          f"to {first_eu_pos[0]:.2f}, {first_eu_pos[1]:.2f}")

    print("[2/5] Fetching backdrop wind...")
    lons, lats, U, V, S = fetch_backdrop_wind()

    print("[3/5] Fetching time-resolved GFS winds (NOAA AWS S3, no rate limits)...")
    flight_start = track["time"].iloc[0].to_pydatetime()
    flight_end = track["time"].iloc[-1].to_pydatetime()
    if flight_start.tzinfo is None: flight_start = flight_start.replace(tzinfo=timezone.utc)
    if flight_end.tzinfo is None: flight_end = flight_end.replace(tzinfo=timezone.utc)
    interp = None
    if _PREDICTOR_AVAILABLE:
        try:
            interp = fetch_gfs_wind_field(
                start_time=flight_start - timedelta(hours=6),
                end_time=flight_end + timedelta(hours=12),
                altitude_m=10000.0,                 # float altitude ≈ 10 km
                lat_min=LAT_MIN, lat_max=LAT_MAX,
                lon_min=LON_MIN, lon_max=LON_MAX,
                cache_dir=Path.home() / ".cache" / "stratolink" / "predictor",
            )
            print("  drift winds mode: gfs-multicycle")
        except Exception as e:
            print(f"  GFS fetch failed ({e}); falling back to Open-Meteo frozen wind")
            interp = None
    else:
        print(f"  predictor module unavailable ({_PREDICTOR_ERR}); using Open-Meteo")
    if interp is None:
        drift = fetch_drift_winds_multilevel(gap_start, gap_end,
                                              backdrop=(lons, lats, U, V, S))
        print(f"  drift winds mode: {drift.get('mode')}")
        interp = make_interpolators(drift)

    print(f"[4/5] Running ensemble ({N_ENSEMBLE} members)...")
    members = run_ensemble(interp, last_us_pos, gap_start, gap_end,
                            first_eu_pos, n=N_ENSEMBLE)
    summary = summarise_ensemble(members, target_pos=first_eu_pos,
                                   start_pos_known=last_us_pos)
    if summary:
        print(f"  best endpoint error: {summary['errs'].min():.0f} km")
        print(f"  median endpoint error: {np.median(summary['errs']):.0f} km")
        print(f"  members < 500 km: {(summary['errs'] < 500).sum()}/{len(members)}")

    print("[5/5] Rendering...")
    plot(track, lons, lats, U, V, S, summary, last_us_pos, first_eu_pos, interp=interp)


if __name__ == "__main__":
    main()
