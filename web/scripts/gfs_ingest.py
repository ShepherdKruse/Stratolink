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
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pygrib

# ── Config (mirror the app) ──────────────────────────────────────────────────
HORIZON_H = 24
RECENT_DAYS = 14
MAX_GAP_H = 72
STEP_H = 3                       # cube time step
MAX_GRID_PTS = 120               # chooseGridStep budget
GFS_LEVELS = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30]
BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
OUTDIR = os.path.join(os.path.dirname(__file__), "..", ".windcube", "cubes")
TIMEOUT = 90

SUPA_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
SUPA_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


# ── HTTP ─────────────────────────────────────────────────────────────────────
def http_get(u, rng=None, headers=None):
    req = urllib.request.Request(u, headers=headers or {})
    if rng:
        req.add_header("Range", f"bytes={rng}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def supa(path, params):
    if not SUPA_URL or not SUPA_KEY:
        raise SystemExit("NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    q = urllib.parse.urlencode(params, safe=",")  # keep commas (select/order); encode +,: in timestamps
    u = f"{SUPA_URL}/rest/v1/{path}?{q}"
    body = http_get(u, headers={"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"})
    return json.loads(body)


# ── Supabase: fleet + recent track + level ───────────────────────────────────
def active_devices():
    rows = supa("devices", {"select": "device_id,status"})
    return [r["device_id"] for r in rows if r.get("status") == "flying"]


def recent_fixes(device):
    since = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = supa("telemetry", {
        "device_id": f"eq.{device}",
        "time": f"gte.{since}",
        "lat": "not.is.null", "lon": "not.is.null",
        "select": "time,lat,lon,altitude_m", "order": "time.asc",
    })
    fixes = [{"lat": r["lat"], "lon": r["lon"], "t": r["time"], "alt": r.get("altitude_m")} for r in rows]
    if len(fixes) < 5:  # quiet longer than the window — fall back to the last handful
        rows = supa("telemetry", {
            "device_id": f"eq.{device}", "lat": "not.is.null", "lon": "not.is.null",
            "select": "time,lat,lon,altitude_m", "order": "time.desc", "limit": "50",
        })
        fixes = [{"lat": r["lat"], "lon": r["lon"], "t": r["time"], "alt": r.get("altitude_m")} for r in rows][::-1]
    return fixes


def latest_level(device):
    rows = supa("telemetry", {
        "device_id": f"eq.{device}", "pressure": "not.is.null",
        "select": "pressure", "order": "time.desc", "limit": "1",
    })
    p = rows[0]["pressure"] if rows else 285.0
    return min(GFS_LEVELS, key=lambda lv: abs(lv - p))


# ── Region / grid step (faithful ports of the app) ───────────────────────────
def bounds_for_forecast(fixes, forecast_hours):
    lats = [f["lat"] for f in fixes]; lons = [f["lon"] for f in fixes]
    base = dict(latMin=min(lats) - 4, latMax=max(lats) + 4, lonMin=min(lons) - 4, lonMax=max(lons) + 4)
    dLatPerH, dLonPerH = 0.35, 0.45
    if len(fixes) >= 2:
        a, b = fixes[-2], fixes[-1]
        dtH = (datetime.fromisoformat(b["t"]).timestamp() - datetime.fromisoformat(a["t"]).timestamp()) / 3600
        if dtH > 0.15:
            dLatPerH = (b["lat"] - a["lat"]) / dtH
            dLonPerH = (b["lon"] - a["lon"]) / dtH
    padH = forecast_hours * 1.35
    padLat = abs(dLatPerH * padH) + 6
    padLon = abs(dLonPerH * padH) + 6
    up = padLat if dLatPerH >= 0 else 6
    down = padLat if dLatPerH <= 0 else 6
    east = padLon if dLonPerH >= 0 else 6
    west = padLon if dLonPerH <= 0 else 6
    return dict(latMin=base["latMin"] - down, latMax=base["latMax"] + up,
                lonMin=base["lonMin"] - west, lonMax=base["lonMax"] + east)


def choose_grid_step(b, max_pts=MAX_GRID_PTS):
    spanLat, spanLon = b["latMax"] - b["latMin"], b["lonMax"] - b["lonMin"]
    for step in [1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        n = (round(spanLat / step) + 1) * (round(spanLon / step) + 1)
        if n <= max_pts:
            return step
    return 4.0


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
    if t <= latest:
        cyc = t.replace(minute=0, second=0, microsecond=0)
        return cyc.replace(hour=(cyc.hour // 6) * 6), 0
    return latest, 0


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


def floor3(t):
    t = t.replace(minute=0, second=0, microsecond=0)
    return t.replace(hour=(t.hour // STEP_H) * STEP_H)


def build_cube(device, fixes, level, latest):
    last_fix = datetime.fromisoformat(fixes[-1]["t"]).astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    gap_h = max(0, (now - last_fix).total_seconds() / 3600)
    bounds = bounds_for_forecast(fixes, HORIZON_H + min(gap_h, MAX_GAP_H))
    step = choose_grid_step(bounds)
    start = floor3(last_fix) - timedelta(hours=STEP_H)
    end = floor3(now) + timedelta(hours=HORIZON_H + 2 * STEP_H)

    lats = np.arange(bounds["latMin"], bounds["latMax"] + 1e-6, step)
    lons = np.arange(bounds["lonMin"], bounds["lonMax"] + 1e-6, step)
    rows_idx = np.round((90.0 - lats) / 0.25).astype(int).clip(0, 720)
    cols_idx = (np.round((lons % 360.0) / 0.25).astype(int)) % 1440

    times, grids = [], []
    t = start
    while t <= end:
        cyc, fhr = pick_source(t, latest)
        uv = fetch_uv(cyc, fhr, level)
        U = uv["u"][np.ix_(rows_idx, cols_idx)]
        V = uv["v"][np.ix_(rows_idx, cols_idx)]
        times.append(int(t.timestamp() * 1000))
        grids.append({
            "lat0": float(lats[0]), "dLat": step, "nLat": len(lats),
            "lon0": float(lons[0]), "dLon": step, "nLon": len(lons),
            "U": [round(float(x), 3) for x in U.ravel()],
            "V": [round(float(x), 3) for x in V.ravel()],
        })
        t += timedelta(hours=STEP_H)

    cube = {
        "source": "gfs", "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "levelHpa": level, "gridStep": step,
        "t0Ms": times[0], "stepMs": STEP_H * 3600 * 1000,
        "bounds": {"latMin": float(lats[0]), "latMax": float(lats[-1]),
                   "lonMin": float(lons[0]), "lonMax": float(lons[-1])},
        "grids": grids,
    }
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"{device}.json")
    json.dump(cube, open(out, "w"))
    print(f"  {device}: level {level}mb, {len(grids)} grids {len(lats)}x{len(lons)} @ {step}°, "
          f"gap {gap_h:.0f}h -> {os.path.getsize(out)//1024} KB")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    devices = [only] if only else active_devices()
    if not devices:
        print("no active devices")
        return
    latest = latest_cycle()
    print(f"latest GFS cycle {latest.isoformat()} | devices: {devices}")
    for d in devices:
        try:
            fixes = recent_fixes(d)
            if len(fixes) < 1:
                print(f"  {d}: no recent fixes, skipping")
                continue
            build_cube(d, fixes, latest_level(d), latest)
        except Exception as e:
            print(f"  {d}: FAILED {e}")


if __name__ == "__main__":
    main()
