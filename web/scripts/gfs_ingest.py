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
import sys
import time
import urllib.parse
import urllib.request
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
        grids.append({
            "lat0": float(lats[0]), "dLat": step, "nLat": len(lats),
            "lon0": float(lons[0]), "dLon": step, "nLon": len(lons),
            "U": [round(float(x), 1) for x in U.ravel()],
            "V": [round(float(x), 1) for x in V.ravel()],
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


def write_cube(device, suffix, cube, nlat, nlon, tag):
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"{device}{suffix}.json")
    json.dump(cube, open(out, "w"))
    print(f"    {tag}: {len(cube['grids'])} grids {nlat}x{nlon} @ {cube['gridStep']}° "
          f"({cube['stepMs']//3600000}h step) -> {os.path.getsize(out)//1024} KB")


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
    recon_bounds = bounds_for_forecast(fixes, HORIZON_H, pad_cap=8)
    recon_step = choose_grid_step(recon_bounds)
    recon_start = floor_step(first_fix, RECON_STEP_H) - timedelta(hours=RECON_STEP_H)
    recon_end = floor_step(now, RECON_STEP_H) + timedelta(hours=HORIZON_H + 2 * RECON_STEP_H)
    recon, rla, rlo = sample_grids(recon_bounds, recon_step, recon_start, recon_end,
                                   RECON_STEP_H, target_p, latest, now, "recon")
    write_cube(device, "", recon, rla, rlo, "recon")

    # ── Forecast cube: recent track + dead-reckon + cone, HOURLY, finest grid. ──
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
