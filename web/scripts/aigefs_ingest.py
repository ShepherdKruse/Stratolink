#!/usr/bin/env python3
"""
AIGEFS (NOAA's GraphCast AI ensemble) -> per-member WindCubes.

A second, MODEL-INDEPENDENT source for the ensemble: GEFS members all share the
physics model (FV3), so they capture initial-condition uncertainty but under-
represent MODEL error (e.g. a biased jet position that advects a balloon
consistently wrong). AIGEFS is a structurally different model (GraphCast), so
pooling its members with the GEFS members is a poor-man's multi-model ensemble —
wider, better-calibrated spread against exactly the error our long dead-reckons
are most exposed to.

Writes one binary cube per member as {device}-aNN.slwc (the 'a' prefix marks AI
members; the compute pools `-mNN` physics + `-aNN` AI cubes into one ensemble).
Additive and best-effort: invoked from gefs_ingest after the physics members, in
a try/except, so an AIGEFS hiccup never breaks the GFS/GEFS pipeline.

Source: noaa-nws-graphcastgfs-pds (NODD, free), GRIB2 + .idx byte-range, 0.25°,
pres files with 250/300 hPa U/V, 31 members (mem000-mem030), 6-hourly to 384h.

Run: python3 scripts/aigefs_ingest.py [device]
     AIGEFS_N_MEMBERS=4 python3 scripts/aigefs_ingest.py stratolink-3   (fast subset)
"""
import io
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pygrib

import gfs_ingest as g  # shared: supa, http_get, mission_fixes, float_pressure, bounds, pack_cube, ...

AIGEFS_BUCKET = "https://noaa-nws-graphcastgfs-pds.s3.amazonaws.com"
N_MEMBERS = int(os.environ.get("AIGEFS_N_MEMBERS", "31"))
MEMBERS = list(range(min(31, max(1, N_MEMBERS))))   # mem000 .. mem030
AIGEFS_STEP_H = 6          # AIGEFS forecast-hour cadence (and our integration step)
PAD_CAP_DEG = 40           # legacy static box only
AIGEFS_TUBE = os.environ.get("AIGEFS_TUBE", "1") != "0"   # AIGEFS_TUBE=0 reverts to the static box
TUBE_STEP = 0.5            # tube box step (AIGEFS is 0.25° native; 0.5 keeps cubes small + matches GEFS)


def aigefs_url(mem, cyc, fhr):
    return (f"{AIGEFS_BUCKET}/EAGLE_ensemble/aigefs.{cyc:%Y%m%d}/{cyc:%H}/mem{mem:03d}/"
            f"model/atmos/grib2/aigefs.t{cyc:%H}z.pres.f{fhr:03d}.grib2")


def latest_cycle():
    c = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    c = c.replace(hour=(c.hour // 6) * 6)
    for _ in range(12):
        try:
            g.http_get(aigefs_url(0, c, 0) + ".idx")
            return c
        except Exception:  # noqa: BLE001 — cycle not published yet
            c -= timedelta(hours=6)
    raise SystemExit("no published AIGEFS cycle")


def ideal_cycle(t, latest):
    """The cycle we'd ideally source valid-time t from (latest for the future, the
    containing 6h cycle for the past)."""
    return latest if t > latest else t.replace(minute=0, second=0, microsecond=0).replace(
        hour=(t.hour // 6) * 6)


def cycle_exists(cyc):
    """AIGEFS occasionally skips a cycle; probe via mem000's idx (a cycle is
    published all-members-at-once, so mem000 is representative)."""
    try:
        g.http_get(aigefs_url(0, cyc, 0) + ".idx")
        return True
    except Exception:  # noqa: BLE001
        return False


def fetch_member_level(mem, cyc, fhr, level):
    """Byte-range U/V (global 0.25°) for one member/cycle/fhr/level from the pres file."""
    base = aigefs_url(mem, cyc, fhr)
    rows = [ln.split(":") for ln in g.http_get(base + ".idx").decode().splitlines() if ln]
    starts = [int(r[1]) for r in rows]
    want = {}
    for i, r in enumerate(rows):
        if r[3] in ("UGRD", "VGRD") and r[4] == f"{level} mb":
            end = starts[i + 1] - 1 if i + 1 < len(starts) else ""
            want[r[3]] = f"{starts[i]}-{end}"
    if "UGRD" not in want or "VGRD" not in want:
        raise SystemExit(f"aigefs mem{mem:03d} {cyc:%Y%m%d%H} f{fhr}: UGRD/VGRD@{level}mb missing")
    buf = io.BytesIO()
    for v in ("UGRD", "VGRD"):
        buf.write(g.http_get(base, rng=want[v]))
    tmp = os.path.join(g.OUTDIR, f".ai{mem:03d}{cyc:%Y%m%d%H}f{fhr}_{level}.grib2")
    os.makedirs(g.OUTDIR, exist_ok=True)
    open(tmp, "wb").write(buf.getvalue())
    out = {}
    grb_f = pygrib.open(tmp)
    for grb in grb_f:
        if grb.typeOfLevel == "isobaricInhPa" and int(grb.level) == level and grb.shortName in ("u", "v"):
            out[grb.shortName] = np.asarray(grb.values, dtype=float)
    grb_f.close()
    os.remove(tmp)
    return out["u"], out["v"]


def member_cube(mem, schedule, lats, lons, rows_idx, cols_idx, step, target_p, latest, now):
    lo, hi, w = g.bracket_levels(target_p)
    levels = [lo] if lo == hi else [lo, hi]
    uniq = sorted({(cyc, fhr) for _, cyc, fhr in schedule})

    def fetch(task):
        cyc, fhr, lv = task
        return task, fetch_member_level(mem, cyc, fhr, lv)

    cache = {}
    tasks = [(cyc, fhr, lv) for (cyc, fhr) in uniq for lv in levels]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for task, uv in ex.map(fetch, tasks):
            cache[task] = uv

    def field(cyc, fhr):
        if lo == hi:
            return cache[(cyc, fhr, lo)]
        ua, va = cache[(cyc, fhr, hi)]
        ub, vb = cache[(cyc, fhr, lo)]
        return ua * (1 - w) + ub * w, va * (1 - w) + vb * w

    times, grids = [], []
    for t, cyc, fhr in schedule:
        u, v = field(cyc, fhr)
        U = u[np.ix_(rows_idx, cols_idx)]
        V = v[np.ix_(rows_idx, cols_idx)]
        times.append(int(t.timestamp() * 1000))
        grids.append({"lat0": float(lats[0]), "dLat": step, "nLat": len(lats),
                      "lon0": float(lons[0]), "dLon": step, "nLon": len(lons),
                      "U": U.ravel(), "V": V.ravel()})
    return {
        "source": "aigefs", "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "member": f"ai{mem:03d}", "levelHpa": round(target_p, 1), "gridStep": step,
        "t0Ms": times[0], "stepMs": AIGEFS_STEP_H * 3600 * 1000,
        "bounds": {"latMin": float(lats[0]), "latMax": float(lats[-1]),
                   "lonMin": float(lons[0]), "lonMax": float(lons[-1])},
        "grids": grids,
    }


def member_prefetch(mem, schedule, target_p):
    """Prefetch a member's (cyc, fhr) fields concurrently, interpolated to
    `target_p`. Returns field(cyc, fhr) -> (u, v) from the warm cache."""
    lo, hi, w = g.bracket_levels(target_p)
    levels = [lo] if lo == hi else [lo, hi]
    uniq = sorted({(cyc, fhr) for _, cyc, fhr in schedule})

    def fetch(task):
        cyc, fhr, lv = task
        return task, fetch_member_level(mem, cyc, fhr, lv)

    cache = {}
    tasks = [(cyc, fhr, lv) for (cyc, fhr) in uniq for lv in levels]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for task, uv in ex.map(fetch, tasks):
            cache[task] = uv

    def field(cyc, fhr):
        if lo == hi:
            return cache[(cyc, fhr, lo)]
        ua, va = cache[(cyc, fhr, hi)]
        ub, vb = cache[(cyc, fhr, lo)]
        return ua * (1 - w) + ub * w, va * (1 - w) + vb * w
    return field


def member_cube_tube(mem, schedule, slice_ms, start_lat, start_lon, target_p, latest, now):
    """One AIGEFS member's TUBE cube (see gefs_ingest.member_cube_tube)."""
    field = member_prefetch(mem, schedule, target_p)
    sched_field = [(cyc, fhr) for _, cyc, fhr in schedule]
    step_ms = AIGEFS_STEP_H * 3600 * 1000

    def field_at(k):
        return field(*sched_field[k])

    def wind_fn(lat, lon, t_ms):
        # LINEAR time-interp between bracketing slices — match the compute's
        # sampleWind so the nominal doesn't drift out of its own tube over a long gap.
        f = (t_ms - slice_ms[0]) / step_ms
        k0 = max(0, min(len(slice_ms) - 2, int(f)))
        frac = max(0.0, min(1.0, f - k0))
        ua, va = g.bilin_uv(*field_at(k0), lat, lon)
        ub, vb = g.bilin_uv(*field_at(k0 + 1), lat, lon)
        return ua * (1 - frac) + ub * frac, va * (1 - frac) + vb * frac

    centers = g.integrate_nominal_centers(slice_ms, slice_ms[0], start_lat, start_lon, wind_fn)
    cube, n, _ = g.build_tube_grids(centers, g.TUBE_HALF_DEG, TUBE_STEP, slice_ms, field_at,
                                    "aigefs", target_p, latest, now)
    cube["member"] = f"ai{mem:03d}"
    return cube, n


def build_device(device, fixes, target_p, latest):
    now = datetime.now(timezone.utc)
    last_fix = g.tparse(fixes[-1]["t"])
    last_lat, last_lon = fixes[-1]["lat"], fixes[-1]["lon"]
    gap_h = max(0, (now - last_fix).total_seconds() / 3600)
    lo, hi, _ = g.bracket_levels(target_p)

    # Dead-reckon span capped at DEAD_RECKON_CAP_H; +HORIZON forward only if the cap
    # reaches "now" (mirrors the GFS/GEFS tube).
    reach = min(now, last_fix + timedelta(hours=g.DEAD_RECKON_CAP_H))
    reached_now = reach >= now - timedelta(hours=AIGEFS_STEP_H)
    end = reach + timedelta(hours=g.HORIZON_H + AIGEFS_STEP_H if reached_now else 0)
    start = g.floor_step(last_fix, AIGEFS_STEP_H)
    times = []
    t = start
    while t <= end:
        times.append(t)
        t += timedelta(hours=AIGEFS_STEP_H)

    # Probe which of the needed cycles actually exist (AIGEFS skips some), then
    # remap every step to the NEAREST available cycle — a missing cycle just
    # becomes a slightly-longer-lead forecast for the same valid time, instead of
    # 404'ing the whole device.
    needed = sorted({ideal_cycle(t, latest) for t in times})
    avail = [c for c in needed if cycle_exists(c)]
    if not avail:
        raise SystemExit("no AIGEFS cycles available in the needed range")
    missing = len(needed) - len(avail)
    if missing:
        print(f"    ({missing}/{len(needed)} cycles missing — remapped to nearest available)", flush=True)

    def nearest(c):
        return min(avail, key=lambda a: abs((a - c).total_seconds()))

    schedule = []
    for t in times:
        cyc = nearest(ideal_cycle(t, latest))
        fhr = max(0, round((t - cyc).total_seconds() / 3600 / AIGEFS_STEP_H) * AIGEFS_STEP_H)
        schedule.append((t, cyc, fhr))
    slice_ms = [int(t.timestamp() * 1000) for t in times]

    cov_h = (reach - last_fix).total_seconds() / 3600
    mode = f"TUBE @ {TUBE_STEP}° ±{g.TUBE_HALF_DEG}°" if AIGEFS_TUBE else "STATIC"
    print(f"  {device}: AIGEFS {len(MEMBERS)} members {mode}, interp {target_p:.1f}mb ({lo}↔{hi}), "
          f"gap {gap_h:.0f}h, {len(schedule)} slices fix→+{cov_h:.0f}h{'' if reached_now else ' (capped)'}", flush=True)

    if not AIGEFS_TUBE:
        return build_device_static(device, fixes, target_p, latest, now, schedule)

    # Per-member isolation: AIGEFS publishes incomplete member sets, so one
    # member's 404 must not abort the rest.
    built = 0
    for mem in MEMBERS:
        try:
            cube, n = member_cube_tube(mem, schedule, slice_ms, last_lat, last_lon, target_p, latest, now)
            g.write_cube(device, f"-a{mem:02d}", cube, n, n, f"a{mem:02d}")
            built += 1
        except Exception as e:  # noqa: BLE001
            print(f"    a{mem:02d}: skipped ({e})", flush=True)
    print(f"  {device}: AIGEFS built {built}/{len(MEMBERS)} members", flush=True)


def build_device_static(device, fixes, target_p, latest, now, schedule):
    """Legacy: one coarse static box per member (AIGEFS_TUBE=0)."""
    last_fix = g.tparse(fixes[-1]["t"])
    span_h = min(max(0, (now - last_fix).total_seconds() / 3600), g.MAX_GAP_H) + g.HORIZON_H
    bounds = g.bounds_for_forecast(fixes, span_h, pad_cap=PAD_CAP_DEG)
    step = g.choose_grid_step(bounds)
    lats = np.arange(bounds["latMin"], bounds["latMax"] + 1e-6, step)
    lons = np.arange(bounds["lonMin"], bounds["lonMax"] + 1e-6, step)
    rows_idx = np.round((90.0 - lats) / 0.25).astype(int).clip(0, 720)
    cols_idx = (np.round((lons % 360.0) / 0.25).astype(int)) % 1440
    built = 0
    for mem in MEMBERS:
        try:
            cube = member_cube(mem, schedule, lats, lons, rows_idx, cols_idx, step, target_p, latest, now)
            g.write_cube(device, f"-a{mem:02d}", cube, len(lats), len(lons), f"a{mem:02d}")
            built += 1
        except Exception as e:  # noqa: BLE001
            print(f"    a{mem:02d}: skipped ({e})", flush=True)
    print(f"  {device}: AIGEFS built {built}/{len(MEMBERS)} members", flush=True)


def run(only=None):
    devices = [(only, None)] if only else g.active_devices()
    if not devices:
        print("no active devices")
        return
    latest = latest_cycle()
    print(f"latest AIGEFS cycle {latest.isoformat()} | members {len(MEMBERS)} | devices {[d for d, _ in devices]}")
    for d, launched in devices:
        try:
            fixes = g.mission_fixes(d, g.mission_since(launched))
            if len(fixes) < 1:
                print(f"  {d}: no fixes, skipping")
                continue
            build_device(d, fixes, g.float_pressure(d), latest)
        except Exception as e:  # noqa: BLE001
            print(f"  {d}: AIGEFS FAILED {e}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
