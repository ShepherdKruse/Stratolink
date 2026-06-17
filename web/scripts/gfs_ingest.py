#!/usr/bin/env python3
"""
GFS -> WindCube ingest (production). For each active balloon it derives the
forecast region / pressure level / time window from Supabase telemetry (mirroring
the app's boundsForForecast + chooseGridStep + snapPressure so the cube matches
what computeMonteCarloForecast asks for), then builds a multi-cycle cube from
NOAA's free NODD S3 (byte-range U/V via the .idx: past 3-hourly *analyses* +
forward *forecast* from the latest cycle) and writes it to .windcube/cubes/.

A separate Node step (scripts/upload_cubes.mjs) uploads those to Vercel Blob.

Env: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
Run: python3 scripts/gfs_ingest.py            (all active devices)
     python3 scripts/gfs_ingest.py stratolink-3   (one device)
"""
import io
import json
import os
import re
import struct
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pygrib


def tparse(s):
    """Parse a Supabase ISO timestamp to a UTC datetime. datetime.fromisoformat
    (pre-3.11) rejects fractional seconds that aren't 3 or 6 digits (Supabase
    emits e.g. '.58768') and a trailing 'Z' — normalize both first."""
    s = s.replace("Z", "+00:00")
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)
    return datetime.fromisoformat(s).astimezone(timezone.utc)

# ── Config (mirror the app) ──────────────────────────────────────────────────
HORIZON_H = 24
MAX_GAP_H = 72
# Two cubes per device (decoupled so the small forecast box can be fine without
# the continent-wide reconstruction box dragging it coarse):
#   - forecast cube ({device}-fc): recent track + dead-reckon + forward cone,
#     HOURLY, finest grid that fits the point cap. Drives the forward forecast.
#   - reconstruction cube ({device}): full mission, 3-HOURLY, coarser grid. Drives
#     the historical track only.
FC_STEP_H = 1                    # forecast cube time step (hourly forecast hours)
RECON_STEP_H = 3                 # reconstruction cube time step
# Hours of recent track to include in the forecast box on top of the live GPS gap
# (covers the bias-fit fixes); keeps the FC box small => finer grid.
FC_BIAS_H = 36
HOURLY_FHR_MAX = 120             # GFS publishes hourly forecast hours through f120
# Cube resolution is now bounded by SIZE, not API calls (we own the GFS download).
# A higher point budget => a much finer grid than Open-Meteo's 120-pt cap allowed.
MAX_GRID_PTS = 8000
HISTORY_DAYS = 90                # cap full-mission lookback (matches app MAX_HISTORY)
PAD_CAP_DEG = 32                 # cap the downwind forecast pad so the box can't run away
                                 # (large enough to contain a multi-day dead-reckon)
# ── Trajectory-following "tube" forecast cube (P1) ───────────────────────────
# Instead of one static box big enough to contain a multi-day dead-reckon (which
# forces a coarse grid AND still clamps once the drift leaves it), lay a stack of
# moderate boxes ALONG a pre-integrated nominal path — each time-slice centered on
# where the balloon is then. Consecutive boxes overlap (half-width >> one step's
# drift) so sampleWind's time-interpolation always has both brackets. Per-slice
# geometry rides in the v2 .slwc header (origins[]). The win is *coverage
# correctness + fine resolution along the path*, not bandwidth (GFS messages are
# whole-globe regardless).
FC_TUBE = os.environ.get("FC_TUBE", "1") != "0"     # set FC_TUBE=0 for the legacy static box
TUBE_HALF_DEG = float(os.environ.get("FC_TUBE_HALF_DEG", "9"))   # box half-width around nominal
# Cap the dead-reckon the tube covers. Beyond ~a week even a perfect tube is a
# globe-sized cloud (predictability is gone), so don't fetch/integrate past it;
# the compute then truncates honestly (coverage_limited). Small value for fast
# local iteration: FC_DEAD_RECKON_CAP_H=48.
DEAD_RECKON_CAP_H = int(os.environ.get("FC_DEAD_RECKON_CAP_H", str(7 * 24)))
TUBE_SUBSTEP_H = 1.0 / 6.0       # nominal integration sub-step (matches BALLOON_STEP_HOURS)
GFS_LEVELS = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30]
BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
OUTDIR = os.path.join(os.path.dirname(__file__), "..", ".windcube", "cubes")
TIMEOUT = 30  # per-request; a hung S3 socket should fail fast and retry, not stall

SUPA_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
SUPA_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


# ── HTTP ─────────────────────────────────────────────────────────────────────
def http_get(u, rng=None, headers=None, retries=4):
    """GET (optionally a byte range) with retry + backoff. The two-cube ingest
    makes 2-3x more byte-range requests to NOAA S3, so transient resets/timeouts
    are likely over a full run — retry them rather than fail the whole device."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(u, headers=headers or {})
            if rng:
                req.add_header("Range", f"bytes={rng}")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — transient network: reset, timeout, 5xx
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last


def supa(path, params):
    if not SUPA_URL or not SUPA_KEY:
        raise SystemExit("NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    q = urllib.parse.urlencode(params, safe=",")  # keep commas (select/order); encode +,: in timestamps
    u = f"{SUPA_URL}/rest/v1/{path}?{q}"
    body = http_get(u, headers={"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"})
    return json.loads(body)


# ── Supabase: fleet + recent track + level ───────────────────────────────────
def active_devices():
    rows = supa("devices", {"select": "device_id,status,launched_at"})
    return [(r["device_id"], r.get("launched_at")) for r in rows if r.get("status") == "flying"]


def mission_since(launched_at):
    """Earliest time to fetch fixes from: launch, but never older than HISTORY_DAYS."""
    floor = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
    if launched_at:
        lt = tparse(launched_at)
        if lt > floor:
            floor = lt
    return floor.strftime("%Y-%m-%dT%H:%M:%SZ")


def mission_fixes(device, since_iso):
    """All GPS fixes since launch (full mission) — for the cube's bounds + span."""
    rows = supa("telemetry", {
        "device_id": f"eq.{device}",
        "time": f"gte.{since_iso}",
        "lat": "not.is.null", "lon": "not.is.null",
        "select": "time,lat,lon,altitude_m", "order": "time.asc", "limit": "50000",
    })
    # Drop corrupt coordinates (the telemetry has occasional garbage fixes, e.g.
    # lat -222) — a single outlier blows up the bounding box and coarsens the grid.
    return [{"lat": r["lat"], "lon": r["lon"], "t": r["time"], "alt": r.get("altitude_m")}
            for r in rows if -90 <= r["lat"] <= 90 and -180 <= r["lon"] <= 180]


def float_pressure(device):
    """Robust estimate of the balloon's float pressure (hPa): the median of the
    last ~200 non-null readings, restricted to the float band (80–400 hPa) so a
    single noisy packet — or ground/ascent/garbage rows — can't shift it. The
    cube is then interpolated to this pressure rather than snapped to the nearest
    standard GFS level (so ~280 hPa is sampled as 280, not 300). Fallback 285."""
    rows = supa("telemetry", {
        "device_id": f"eq.{device}", "pressure": "not.is.null",
        "select": "pressure", "order": "time.desc", "limit": "200",
    })
    ps = sorted(r["pressure"] for r in rows
                if isinstance(r["pressure"], (int, float)) and 80 <= r["pressure"] <= 400)
    return ps[len(ps) // 2] if ps else 285.0


# ── Region / grid step (faithful ports of the app) ───────────────────────────
def bounds_for_forecast(fixes, forecast_hours, pad_cap=PAD_CAP_DEG):
    lats = [f["lat"] for f in fixes]; lons = [f["lon"] for f in fixes]
    base = dict(latMin=min(lats) - 4, latMax=max(lats) + 4, lonMin=min(lons) - 4, lonMax=max(lons) + 4)
    # Rate for the downwind pad. Use the most recent NON-FROZEN, SHORT-dt pair:
    # this balloon re-sends identical fixes (frozen GPS), so the last pair is often
    # zero-displacement (=> ~0 rate => too-small pad) or a frozen→real transition
    # with a stretched dt (=> a bogus direction that blew the lat pad to 67°N).
    # Scan back for a real recent step instead.  (See [[stratolink-frozen-gps]].)
    dLatPerH, dLonPerH = 0.35, 0.45
    for i in range(len(fixes) - 1, 0, -1):
        a, b = fixes[i - 1], fixes[i]
        if a["lat"] == b["lat"] and a["lon"] == b["lon"]:
            continue
        dtH = (tparse(b["t"]).timestamp() - tparse(a["t"]).timestamp()) / 3600
        if 0.15 < dtH < 6:
            dLatPerH = (b["lat"] - a["lat"]) / dtH
            dLonPerH = (b["lon"] - a["lon"]) / dtH
            break
    padH = forecast_hours * 1.35
    padLat = min(pad_cap, abs(dLatPerH * padH)) + 6
    padLon = min(pad_cap, abs(dLonPerH * padH)) + 6
    up = padLat if dLatPerH >= 0 else 6
    down = padLat if dLatPerH <= 0 else 6
    east = padLon if dLonPerH >= 0 else 6
    west = padLon if dLonPerH <= 0 else 6
    return dict(latMin=base["latMin"] - down, latMax=base["latMax"] + up,
                lonMin=base["lonMin"] - west, lonMax=base["lonMax"] + east)


def choose_grid_step(b, max_pts=MAX_GRID_PTS):
    spanLat, spanLon = b["latMax"] - b["latMin"], b["lonMax"] - b["lonMin"]
    for step in [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]:
        n = (round(spanLat / step) + 1) * (round(spanLon / step) + 1)
        if n <= max_pts:
            return step
    return 3.0


# ── GFS fetch (multi-cycle: past analyses + forward forecast) ────────────────
def gfs_url(cyc, fhr):
    return f"{BUCKET}/gfs.{cyc:%Y%m%d}/{cyc:%H}/atmos/gfs.t{cyc:%H}z.pgrb2.0p25.f{fhr:03d}"


def exists(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


def latest_cycle():
    c = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    c = c.replace(hour=(c.hour // 6) * 6)
    for _ in range(8):
        if exists(gfs_url(c, 0) + ".idx"):
            return c
        c -= timedelta(hours=6)
    raise SystemExit("no published GFS cycle")


def pick_source(t, latest):
    """Cycle + forecast hour giving the wind VALID AT t.
      - Future (t > latest): the latest cycle's forecast hour fhr = hours ahead —
        so the forward forecast actually EVOLVES (not a frozen analysis).
      - Past/now (t <= latest): the 6-hourly cycle containing t, with the short-range
        forecast hour fhr = 0..5 into that cycle — so hourly/3-hourly steps get real
        winds at t (not the same analysis repeated across the cycle)."""
    if t > latest:
        fhr = round((t - latest).total_seconds() / 3600)
        return latest, max(0, min(fhr, HOURLY_FHR_MAX))
    cyc = t.replace(minute=0, second=0, microsecond=0)
    cyc = cyc.replace(hour=(cyc.hour // 6) * 6)
    fhr = round((t - cyc).total_seconds() / 3600)
    return cyc, max(0, min(fhr, 5))


_uv_cache = {}


def fetch_uv(cyc, fhr, level):
    key = (cyc, fhr, level)
    if key in _uv_cache:
        return _uv_cache[key]
    lines = http_get(gfs_url(cyc, fhr) + ".idx").decode().splitlines()
    rows = [ln.split(":") for ln in lines if ln]
    starts = [int(r[1]) for r in rows]
    want = {}
    for i, r in enumerate(rows):
        if r[3] in ("UGRD", "VGRD") and r[4] == f"{level} mb":
            end = starts[i + 1] - 1 if i + 1 < len(starts) else ""
            want[r[3]] = f"{starts[i]}-{end}"
    if "UGRD" not in want or "VGRD" not in want:
        raise SystemExit(f"{cyc} f{fhr}: UGRD/VGRD@{level}mb missing")
    buf = io.BytesIO()
    for v in ("UGRD", "VGRD"):
        buf.write(http_get(gfs_url(cyc, fhr), want[v]))
    tmp = os.path.join(OUTDIR, f".{cyc:%Y%m%d%H}f{fhr}_{level}.grib2")
    os.makedirs(OUTDIR, exist_ok=True)
    open(tmp, "wb").write(buf.getvalue())
    out = {}
    g = pygrib.open(tmp)
    for grb in g:
        if grb.typeOfLevel == "isobaricInhPa" and int(grb.level) == level and grb.shortName in ("u", "v"):
            out[grb.shortName] = np.asarray(grb.values, dtype=float)
    g.close()
    os.remove(tmp)
    _uv_cache[key] = out
    return out


def bracket_levels(p):
    """The two GFS levels bracketing pressure `p`, and the blend weight toward the
    lower-pressure (higher-altitude) bound. `hi` = nearest level at >= p (e.g. 300),
    `lo` = nearest at <= p (e.g. 250). Linear in pressure: U(p) = U_hi*(1-w) + U_lo*w
    with w = (hi - p)/(hi - lo). p outside the level range clamps to one level (w=0)."""
    hi = min((lv for lv in GFS_LEVELS if lv >= p), default=max(GFS_LEVELS))
    lo = max((lv for lv in GFS_LEVELS if lv <= p), default=min(GFS_LEVELS))
    w = 0.0 if hi == lo else (hi - p) / (hi - lo)
    return lo, hi, w


_uv_p_cache = {}


def fetch_uv_p(cyc, fhr, p):
    """U/V interpolated to pressure `p` between the two bracketing GFS levels."""
    lo, hi, w = bracket_levels(p)
    if lo == hi:
        return fetch_uv(cyc, fhr, lo)
    key = (cyc, fhr, round(p, 1))
    if key in _uv_p_cache:
        return _uv_p_cache[key]
    a = fetch_uv(cyc, fhr, hi)   # higher-pressure bound
    b = fetch_uv(cyc, fhr, lo)   # lower-pressure bound
    out = {"u": a["u"] * (1 - w) + b["u"] * w, "v": a["v"] * (1 - w) + b["v"] * w}
    _uv_p_cache[key] = out
    return out


def floor_step(t, step_h):
    t = t.replace(minute=0, second=0, microsecond=0)
    return t.replace(hour=(t.hour // step_h) * step_h)


def sample_grids(bounds, step, start, end, step_h, target_p, latest, now, tag=""):
    """Sample the GFS field over `bounds` at `step`° resolution, every `step_h`
    hours from `start` to `end`, interpolated vertically to pressure `target_p`.
    Returns the cube dict (no file write)."""
    lats = np.arange(bounds["latMin"], bounds["latMax"] + 1e-6, step)
    lons = np.arange(bounds["lonMin"], bounds["lonMax"] + 1e-6, step)
    rows_idx = np.round((90.0 - lats) / 0.25).astype(int).clip(0, 720)
    cols_idx = (np.round((lons % 360.0) / 0.25).astype(int)) % 1440

    n_steps = int((end - start).total_seconds() // (step_h * 3600)) + 1
    times, grids = [], []
    t = start
    i = 0
    while t <= end:
        cyc, fhr = pick_source(t, latest)
        uv = fetch_uv_p(cyc, fhr, target_p)
        i += 1
        if i % 10 == 0 or i == n_steps:
            print(f"      {tag}: {i}/{n_steps} grids", flush=True)
        U = uv["u"][np.ix_(rows_idx, cols_idx)]
        V = uv["v"][np.ix_(rows_idx, cols_idx)]
        times.append(int(t.timestamp() * 1000))
        # Keep raw numpy arrays; pack_cube() int16-quantizes them at write time
        # (no giant Python list of rounded floats — faster + less memory).
        grids.append({
            "lat0": float(lats[0]), "dLat": step, "nLat": len(lats),
            "lon0": float(lons[0]), "dLon": step, "nLon": len(lons),
            "U": U.ravel(), "V": V.ravel(),
        })
        t += timedelta(hours=step_h)

    return {
        "source": "gfs", "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "levelHpa": round(target_p, 1), "gridStep": step,
        "t0Ms": times[0], "stepMs": step_h * 3600 * 1000,
        "bounds": {"latMin": float(lats[0]), "latMax": float(lats[-1]),
                   "lonMin": float(lons[0]), "lonMax": float(lons[-1])},
        "grids": grids,
    }, len(lats), len(lons)


# ── Trajectory-following tube (shared by gfs_ingest + gefs_ingest) ────────────
def bilin_uv(u, v, lat, lon):
    """Bilinear U/V at one point from a whole-globe field, resolution INFERRED
    from the array shape (721×1440 = 0.25° GFS, 361×720 = 0.5° GEFS; row 0 = 90°N,
    col 0 = 0°E). Wraps longitude and clamps latitude at the poles."""
    nlat, nlon = u.shape
    dlat = 180.0 / (nlat - 1); dlon = 360.0 / nlon
    r = min(max((90.0 - lat) / dlat, 0.0), float(nlat - 1))
    c = (lon % 360.0) / dlon
    r0 = min(int(np.floor(r)), nlat - 2); fr = r - r0
    c0 = int(np.floor(c)) % nlon; c1 = (c0 + 1) % nlon; fc = c - np.floor(c)
    def bl(a):
        return (a[r0, c0] * (1 - fr) * (1 - fc) + a[r0 + 1, c0] * fr * (1 - fc)
                + a[r0, c1] * (1 - fr) * fc + a[r0 + 1, c1] * fr * fc)
    return bl(u), bl(v)


def cut_box(u, v, clat, clon, half_deg, step, n):
    """Sub-sample an `n`×`n`, `step`° box centered on (clat, clon) out of a
    whole-globe field (resolution inferred from shape). The origin is snapped to
    the source grid so sampling is exact. Returns (lat0, lon0, U_flat, V_flat).
    Longitude is kept UNWRAPPED on the cube axis (so origins/bounds stay
    continuous across ±180) but wrapped when indexing the source."""
    nlat, nlon = u.shape
    dlat = 180.0 / (nlat - 1); dlon = 360.0 / nlon
    lat0 = round(clat / dlat) * dlat - half_deg
    lon0 = round(clon / dlon) * dlon - half_deg
    lats = lat0 + np.arange(n) * step
    lons = lon0 + np.arange(n) * step
    rows = np.round((90.0 - lats) / dlat).astype(int).clip(0, nlat - 1)
    cols = (np.round((lons % 360.0) / dlon).astype(int)) % nlon
    return float(lats[0]), float(lons[0]), u[np.ix_(rows, cols)].ravel(), v[np.ix_(rows, cols)].ravel()


def integrate_nominal_centers(slice_ms, start_ms, start_lat, start_lon, wind_fn):
    """Pre-integrate ONE nominal trajectory (neutral bias, no perturbation) forward
    from (start_lat, start_lon) at `start_ms`, snapshotting its position at each
    slice time ≥ start_ms. `wind_fn(lat, lon, t_ms) -> (u, v)` supplies the field
    (GFS or a GEFS member). Longitude is left UNWRAPPED so the tube's per-slice
    origins + union bounds form a continuous range the integrator agrees with.
    Slices before start_ms stay None for the caller to fill. Cheap: the global
    fields are fetched/cached once and reused to cut the boxes."""
    centers = [None] * len(slice_ms)
    lat, lon = start_lat, start_lon
    k = 0
    while k < len(slice_ms) and slice_ms[k] < start_ms:
        k += 1
    first_fwd = k
    while k < len(slice_ms) and slice_ms[k] <= start_ms:      # slice exactly at start
        centers[k] = (lat, lon); k += 1
    dt_s = TUBE_SUBSTEP_H * 3600
    t_ms = start_ms
    end_ms = slice_ms[-1]
    while t_ms < end_ms and k < len(slice_ms):
        u, v = wind_fn(lat, lon, t_ms)
        coslat = max(np.cos(np.radians(lat)), 0.05)
        lat += v * dt_s / 111_320
        lon += u * dt_s / (111_320 * coslat)
        t_ms += TUBE_SUBSTEP_H * 3600 * 1000
        while k < len(slice_ms) and slice_ms[k] <= t_ms + 1:
            centers[k] = (lat, lon); k += 1
    for j in range(first_fwd, len(slice_ms)):                 # trailing (shouldn't happen)
        if centers[j] is None:
            centers[j] = (lat, lon)
    return centers


def sample_global(uv, lat, lon):
    """Bilinear U/V from a {"u","v"} dict field (back-compat thin wrapper)."""
    return bilin_uv(uv["u"], uv["v"], lat, lon)


def prefetch_fields(slice_ms, target_p, latest):
    """Warm `fetch_uv_p`'s cache for every (cycle, fhr) the tube needs, IN PARALLEL.
    The needed source field depends only on a slice's TIME (not the balloon's
    position), so we fetch them all up front with threads — turning the GFS tube's
    otherwise-serial hundreds of byte-range fetches (the long-gap bottleneck) into
    a concurrent batch. The nominal walk + box cuts then read from the warm cache.
    Sub-step times between hourly slices map to the same (cyc, fhr) the hourly
    slices already cover, so this is complete."""
    want = sorted({pick_source(datetime.fromtimestamp(ms / 1000, timezone.utc), latest)
                   for ms in slice_ms})
    n = len(want)
    print(f"      prefetch: {n} GFS fields (parallel)…", flush=True)
    done = [0]
    def fetch(cf):
        fetch_uv_p(cf[0], cf[1], target_p)
        done[0] += 1
        if done[0] % 50 == 0 or done[0] == n:
            print(f"      prefetch: {done[0]}/{n}", flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(fetch, want))


def nominal_centers(slice_ms, last_fix_ms, last_lat, last_lon, target_p, latest):
    """GFS nominal centers: integrate through the GFS field interpolated to
    `target_p`, snapshotting per slice ≥ last fix (slices before are the caller's
    track interp)."""
    def wind_fn(lat, lon, t_ms):
        cyc, fhr = pick_source(datetime.fromtimestamp(t_ms / 1000, timezone.utc), latest)
        return sample_global(fetch_uv_p(cyc, fhr, target_p), lat, lon)
    return integrate_nominal_centers(slice_ms, last_fix_ms, last_lat, last_lon, wind_fn)


def build_tube_grids(centers, half_deg, step, slice_ms, field_at, source, levelHpa, latest, now, tag=""):
    """Assemble a tube cube from pre-computed `centers`: one `step`° box per slice,
    cut from the whole-globe field returned by `field_at(k) -> (u, v)`. All slices
    share dims (so v2 needs only per-slice origins). Returns (cube_dict, n, n)."""
    n = int(round(2 * half_deg / step)) + 1
    grids = []
    uminLat = uminLon = float("inf"); umaxLat = umaxLon = float("-inf")
    for k, (clat, clon) in enumerate(centers):
        u, v = field_at(k)
        lat0, lon0, U, V = cut_box(u, v, clat, clon, half_deg, step, n)
        grids.append({"lat0": lat0, "dLat": step, "nLat": n,
                      "lon0": lon0, "dLon": step, "nLon": n, "U": U, "V": V})
        uminLat = min(uminLat, lat0); umaxLat = max(umaxLat, lat0 + (n - 1) * step)
        uminLon = min(uminLon, lon0); umaxLon = max(umaxLon, lon0 + (n - 1) * step)
        if tag and ((k + 1) % 24 == 0 or k + 1 == len(centers)):
            print(f"      {tag}: {k + 1}/{len(centers)} slices", flush=True)
    return {
        "source": source, "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "levelHpa": round(levelHpa, 1), "gridStep": step,
        "t0Ms": slice_ms[0], "stepMs": int(slice_ms[1] - slice_ms[0]) if len(slice_ms) > 1 else FC_STEP_H * 3600 * 1000,
        "bounds": {"latMin": uminLat, "latMax": umaxLat, "lonMin": uminLon, "lonMax": umaxLon},
        "grids": grids,
    }, n, n


def interp_track(fixes_ms, t_ms):
    """Linear-interpolate the observed track at instant t_ms (clamped to the ends).
    `fixes_ms` = sorted [(t_ms, lat, lon)]; used to center tube slices that fall on
    the known recent track (before the last fix), where we don't dead-reckon."""
    if t_ms <= fixes_ms[0][0]:
        return fixes_ms[0][1], fixes_ms[0][2]
    if t_ms >= fixes_ms[-1][0]:
        return fixes_ms[-1][1], fixes_ms[-1][2]
    lo, hi = 0, len(fixes_ms) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fixes_ms[mid][0] <= t_ms:
            lo = mid
        else:
            hi = mid
    (ta, la, loa), (tb, lb, lob) = fixes_ms[lo], fixes_ms[hi]
    f = 0.0 if tb == ta else (t_ms - ta) / (tb - ta)
    return la + (lb - la) * f, loa + (lob - loa) * f


def sample_tube(centers, half_deg, step, slice_ms, target_p, latest, now, tag=""):
    """GFS tube: cut a box per slice from the GFS field (interpolated to target_p)."""
    def field_at(k):
        cyc, fhr = pick_source(datetime.fromtimestamp(slice_ms[k] / 1000, timezone.utc), latest)
        uv = fetch_uv_p(cyc, fhr, target_p)
        return uv["u"], uv["v"]
    return build_tube_grids(centers, half_deg, step, slice_ms, field_at,
                            "gfs", target_p, latest, now, tag)


SCALE = 10  # store winds as int16 = round(value*SCALE); lossless vs the old 0.1 rounding


def pack_cube(cube):
    """Pack a cube dict into the .slwc binary form (see windCube.ts cubeFromBinary):
      [uint32 LE headerLen][header JSON utf-8, padded to a 4-byte boundary]
      [ per grid: int16 U[nLat*nLon] then int16 V[nLat*nLon], little-endian ].
    Geometry is constant across grids, so it lives in the header once."""
    grids = cube["grids"]
    g0 = grids[0]
    # A tube has a different origin per slice; a static cube shares one. Emit v2
    # (origins[]) only when origins actually vary — old static cubes stay v1.
    origins = [(g["lat0"], g["lon0"]) for g in grids]
    is_tube = any(o != origins[0] for o in origins)
    header = {
        "v": 2 if is_tube else 1, "scale": SCALE,
        "source": cube.get("source", "gfs"),
        "generated_at": cube.get("generated_at"),
        "latest_cycle_utc": cube.get("latest_cycle_utc"),
        "levelHpa": cube["levelHpa"], "gridStep": cube["gridStep"],
        "t0Ms": cube["t0Ms"], "stepMs": cube["stepMs"], "bounds": cube["bounds"],
        "lat0": g0["lat0"], "dLat": g0["dLat"], "nLat": g0["nLat"],
        "lon0": g0["lon0"], "dLon": g0["dLon"], "nLon": g0["nLon"],
        "nGrids": len(grids),
    }
    if is_tube:
        header["origins"] = [[round(la, 4), round(lo, 4)] for la, lo in origins]
    hb = json.dumps(header, separators=(",", ":")).encode("utf-8")
    hb += b" " * ((-(4 + len(hb))) % 4)            # pad so the payload starts 4-byte aligned
    parts = [struct.pack("<I", len(hb)), hb]
    for g in cube["grids"]:
        for comp in ("U", "V"):
            a = np.asarray(g[comp], dtype=np.float64)
            parts.append(np.clip(np.round(a * SCALE), -32000, 32000).astype("<i2").tobytes())
    return b"".join(parts)


def write_cube(device, suffix, cube, nlat, nlon, tag):
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"{device}{suffix}.slwc")
    with open(out, "wb") as f:
        f.write(pack_cube(cube))
    print(f"    {tag}: {len(cube['grids'])} grids {nlat}x{nlon} @ {cube['gridStep']}° "
          f"({cube['stepMs']//3600000}h step) -> {os.path.getsize(out)//1024} KB (.slwc)")


def build_cube(device, fixes, target_p, latest):
    first_fix = tparse(fixes[0]["t"])
    last_fix = tparse(fixes[-1]["t"])
    now = datetime.now(timezone.utc)
    gap_h = max(0, (now - last_fix).total_seconds() / 3600)
    pad_h = HORIZON_H + min(gap_h, MAX_GAP_H)
    lo, hi, _ = bracket_levels(target_p)
    print(f"  {device}: interp {target_p:.1f}mb ({lo}↔{hi}), gap {gap_h:.0f}h")

    # ── Reconstruction cube: full mission (first fix → now+horizon), 3-hourly. ──
    # Its box is dominated by the full-mission track; the forward leg is unused by
    # reconstruction, so use a SMALL forward pad (a big one would push the
    # continent-wide box past the point budget and coarsen the historical grid).
    if os.environ.get("SKIP_RECON") != "1":     # dev: skip the slow full-mission recon when iterating on the tube
        recon_bounds = bounds_for_forecast(fixes, HORIZON_H, pad_cap=8)
        recon_step = choose_grid_step(recon_bounds)
        recon_start = floor_step(first_fix, RECON_STEP_H) - timedelta(hours=RECON_STEP_H)
        recon_end = floor_step(now, RECON_STEP_H) + timedelta(hours=HORIZON_H + 2 * RECON_STEP_H)
        recon, rla, rlo = sample_grids(recon_bounds, recon_step, recon_start, recon_end,
                                       RECON_STEP_H, target_p, latest, now, "recon")
        write_cube(device, "", recon, rla, rlo, "recon")

    # ── Forecast cube: recent track + dead-reckon + cone, HOURLY, finest grid. ──
    if FC_TUBE:
        build_tube_fc(device, fixes, last_fix, gap_h, target_p, latest, now)
        return
    lookback_h = min(gap_h, MAX_GAP_H) + FC_BIAS_H
    cutoff = now - timedelta(hours=lookback_h)
    fc_fixes = [f for f in fixes if tparse(f["t"]) >= cutoff]
    if len(fc_fixes) < 2:
        fc_fixes = fixes[-min(len(fixes), 20):]
    fc_bounds = bounds_for_forecast(fc_fixes, pad_h, pad_cap=PAD_CAP_DEG)
    fc_step = choose_grid_step(fc_bounds)
    fc_start = floor_step(now - timedelta(hours=lookback_h), FC_STEP_H) - timedelta(hours=FC_STEP_H)
    fc_end = floor_step(now, FC_STEP_H) + timedelta(hours=HORIZON_H + 2 * FC_STEP_H)
    fc, fla, flo = sample_grids(fc_bounds, fc_step, fc_start, fc_end,
                                FC_STEP_H, target_p, latest, now, "fcast")
    write_cube(device, "-fc", fc, fla, flo, "fcast")


def build_tube_fc(device, fixes, last_fix, gap_h, target_p, latest, now):
    """Forecast cube as a trajectory-following tube (P1). Time span: from
    FC_BIAS_H before the last fix (covers the bias-fit fixes) through the
    dead-reckon (capped at DEAD_RECKON_CAP_H) and, if the gap is within the cap,
    HORIZON_H of true forward forecast. Each hourly slice is a moderate box
    centered on the pre-integrated nominal position (or the known track, before the
    last fix)."""
    last_fix_ms = int(last_fix.timestamp() * 1000)
    now_ms = int(now.timestamp() * 1000)
    step_ms = FC_STEP_H * 3600 * 1000
    cap_ms = DEAD_RECKON_CAP_H * 3600 * 1000
    reach_ms = min(now_ms, last_fix_ms + cap_ms)         # furthest the dead-reckon goes
    reached_now = reach_ms >= now_ms - step_ms
    end_ms = reach_ms + (HORIZON_H * 3600 * 1000 if reached_now else 0)
    start_ms = (last_fix_ms // step_ms) * step_ms - FC_BIAS_H * 3600 * 1000
    n_slices = int(round((end_ms - start_ms) / step_ms)) + 1
    slice_ms = [start_ms + k * step_ms for k in range(n_slices)]

    prefetch_fields(slice_ms, target_p, latest)          # parallel cache warm-up
    fixes_ms = [(int(tparse(f["t"]).timestamp() * 1000), f["lat"], f["lon"]) for f in fixes]
    centers = nominal_centers(slice_ms, last_fix_ms, fixes[-1]["lat"], fixes[-1]["lon"],
                              target_p, latest)
    for k, t_ms in enumerate(slice_ms):                  # fill pre-last-fix slices from the track
        if centers[k] is None:
            centers[k] = interp_track(fixes_ms, t_ms)

    step = choose_grid_step({"latMin": 0, "latMax": 2 * TUBE_HALF_DEG,
                             "lonMin": 0, "lonMax": 2 * TUBE_HALF_DEG})
    cov_h = (reach_ms - last_fix_ms) / 3.6e6
    print(f"    tube: {n_slices} slices @ {step}° ±{TUBE_HALF_DEG}°, "
          f"covers fix→+{cov_h:.0f}h (gap {gap_h:.0f}h{'' if reached_now else ', capped'})"
          f"{' +' + str(HORIZON_H) + 'h fwd' if reached_now else ''}", flush=True)
    fc, fla, flo = sample_tube(centers, TUBE_HALF_DEG, step, slice_ms, target_p, latest, now, "tube")
    write_cube(device, "-fc", fc, fla, flo, "tube")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    devices = [(only, None)] if only else active_devices()
    if not devices:
        print("no active devices")
        return
    latest = latest_cycle()
    print(f"latest GFS cycle {latest.isoformat()} | devices: {[d for d, _ in devices]}")
    for d, launched in devices:
        try:
            fixes = mission_fixes(d, mission_since(launched))
            if len(fixes) < 1:
                print(f"  {d}: no fixes, skipping")
                continue
            build_cube(d, fixes, float_pressure(d), latest)
        except Exception as e:
            print(f"  {d}: FAILED {e}")


if __name__ == "__main__":
    main()
