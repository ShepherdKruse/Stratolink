#!/usr/bin/env python3
"""
GEFS ensemble -> per-member WindCubes.

For each active balloon, build ONE cube per GEFS member ({device}-mNN.slwc) so the
forecast can integrate a real trajectory per member (flow-dependent spread) instead
of jittering a single deterministic field. Each member's cube spans the SAME box /
time window; the compute streams them one at a time (the binary .slwc format keeps
that cheap).

Winds are 250<->300 hPa interpolated to the float pressure (reuses gfs_ingest's
bracket_levels), 0.5 deg GEFS (pgrb2ap5), time-correct: future from the latest
cycle's forecast hours, the past gap from the cycle valid then. Reuses gfs_ingest
for Supabase, bounds, grid step, and the .slwc packer.

Env: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
Run: python3 scripts/gefs_ingest.py [device]
     GEFS_N_MEMBERS=4 python3 scripts/gefs_ingest.py stratolink-3   (fast subset for testing)
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

GEFS_BUCKET = "https://noaa-gefs-pds.s3.amazonaws.com"
ALL_MEMBERS = ["gec00"] + [f"gep{i:02d}" for i in range(1, 31)]   # control + 30 perturbed
N_MEMBERS = int(os.environ.get("GEFS_N_MEMBERS", "31"))
MEMBERS = ALL_MEMBERS[:max(1, min(31, N_MEMBERS))]

GEFS_STEP_H = 3            # GEFS forecast-hour cadence (and our integration step)
PAD_CAP_DEG = 40           # generous downwind pad — the member cloud is wide for a long gap (legacy static box)
GEFS_TUBE = os.environ.get("GEFS_TUBE", "1") != "0"   # GEFS_TUBE=0 reverts to the legacy static box
TUBE_STEP = 0.5            # GEFS native resolution — the tube box step


# ── GEFS source ──────────────────────────────────────────────────────────────
def gefs_member_url(mem, cyc, fhr):
    return (f"{GEFS_BUCKET}/gefs.{cyc:%Y%m%d}/{cyc:%H}/atmos/pgrb2ap5/"
            f"{mem}.t{cyc:%H}z.pgrb2a.0p50.f{fhr:03d}")


def gefs_latest_cycle():
    c = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    c = c.replace(hour=(c.hour // 6) * 6)
    for _ in range(8):
        try:
            g.http_get(gefs_member_url("gec00", c, 0) + ".idx")
            return c
        except Exception:  # noqa: BLE001 — cycle not published yet
            c -= timedelta(hours=6)
    raise SystemExit("no published GEFS cycle")


def gefs_pick(t, latest):
    """(cycle, fhr) for the GEFS field valid at t: future -> latest cycle forecast
    hours; past -> the containing 6h cycle's nearest 3-hourly short-range hour."""
    cyc = latest if t > latest else t.replace(minute=0, second=0, microsecond=0).replace(
        hour=(t.hour // 6) * 6)
    fhr = round((t - cyc).total_seconds() / 3600 / GEFS_STEP_H) * GEFS_STEP_H
    return cyc, max(0, fhr)


def fetch_member_level(mem, cyc, fhr, level):
    """Byte-range U/V (global 0.5 deg) for one member/cycle/fhr/level."""
    base = gefs_member_url(mem, cyc, fhr)
    rows = [ln.split(":") for ln in g.http_get(base + ".idx").decode().splitlines() if ln]
    starts = [int(r[1]) for r in rows]
    want = {}
    for i, r in enumerate(rows):
        if r[3] in ("UGRD", "VGRD") and r[4] == f"{level} mb":
            end = starts[i + 1] - 1 if i + 1 < len(starts) else ""
            want[r[3]] = f"{starts[i]}-{end}"
    if "UGRD" not in want or "VGRD" not in want:
        raise SystemExit(f"{mem} {cyc:%Y%m%d%H} f{fhr}: UGRD/VGRD@{level}mb missing")
    buf = io.BytesIO()
    for v in ("UGRD", "VGRD"):
        buf.write(g.http_get(base, rng=want[v]))
    tmp = os.path.join(g.OUTDIR, f".{mem}{cyc:%Y%m%d%H}f{fhr}_{level}.grib2")
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


# ── Per-member cube ──────────────────────────────────────────────────────────
def member_cube(mem, schedule, lats, lons, rows_idx, cols_idx, step, target_p, latest, now):
    """Build one member's cube. `schedule` = list of (t, cyc, fhr); winds are
    prefetched concurrently, then sampled+interpolated per step (no network)."""
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
        "source": "gefs", "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "member": mem, "levelHpa": round(target_p, 1), "gridStep": step,
        "t0Ms": times[0], "stepMs": GEFS_STEP_H * 3600 * 1000,
        "bounds": {"latMin": float(lats[0]), "latMax": float(lats[-1]),
                   "lonMin": float(lons[0]), "lonMax": float(lons[-1])},
        "grids": grids,
    }


def member_prefetch(mem, schedule, target_p):
    """Prefetch all of a member's (cyc, fhr) fields concurrently, interpolated to
    `target_p`. Returns field(cyc, fhr) -> (u, v) reading from the warm cache, so
    BOTH the nominal pre-integration and the per-slice box cuts hit zero network."""
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
    """One member's TUBE cube: pre-integrate the nominal through THIS member's flow,
    then cut a 0.5° box per slice centered on where the member goes then. Per-slice
    geometry lives in the v2 .slwc header. Fine resolution + full path coverage,
    vs the legacy single coarse box that clamped once the member left it."""
    field = member_prefetch(mem, schedule, target_p)
    sched_field = [(cyc, fhr) for _, cyc, fhr in schedule]
    step_ms = GEFS_STEP_H * 3600 * 1000

    def field_at(k):
        return field(*sched_field[k])

    def wind_fn(lat, lon, t_ms):
        # snap to the nearest scheduled slice so sub-steps always hit a prefetched
        # (cyc, fhr) — calling gefs_pick directly can land on an fhr we didn't fetch.
        k = max(0, min(len(slice_ms) - 1, round((t_ms - slice_ms[0]) / step_ms)))
        return g.bilin_uv(*field_at(k), lat, lon)

    centers = g.integrate_nominal_centers(slice_ms, slice_ms[0], start_lat, start_lon, wind_fn)

    cube, n, _ = g.build_tube_grids(centers, g.TUBE_HALF_DEG, TUBE_STEP, slice_ms, field_at,
                                    "gefs", target_p, latest, now)
    cube["member"] = mem
    return cube, n


def build_device(device, fixes, target_p, latest):
    now = datetime.now(timezone.utc)
    last_fix = g.tparse(fixes[-1]["t"])
    last_lat, last_lon = fixes[-1]["lat"], fixes[-1]["lon"]
    gap_h = max(0, (now - last_fix).total_seconds() / 3600)
    lo, hi, _ = g.bracket_levels(target_p)

    # Dead-reckon span: capped at DEAD_RECKON_CAP_H (beyond that the cloud is
    # globe-sized — the compute truncates honestly). +HORIZON forward only if the
    # cap reaches "now". Same cadence + cap as the GFS tube.
    reach = min(now, last_fix + timedelta(hours=g.DEAD_RECKON_CAP_H))
    reached_now = reach >= now - timedelta(hours=GEFS_STEP_H)
    end = reach + timedelta(hours=g.HORIZON_H + GEFS_STEP_H if reached_now else 0)
    start = g.floor_step(last_fix, GEFS_STEP_H)
    schedule, t = [], start
    while t <= end:
        cyc, fhr = gefs_pick(t, latest)
        schedule.append((t, cyc, fhr))
        t += timedelta(hours=GEFS_STEP_H)
    slice_ms = [int(t.timestamp() * 1000) for t, _, _ in schedule]

    if not GEFS_TUBE:
        return build_device_static(device, fixes, target_p, latest, now, last_fix, schedule)

    cov_h = (reach - last_fix).total_seconds() / 3600
    print(f"  {device}: GEFS {len(MEMBERS)} members TUBE @ {TUBE_STEP}° ±{g.TUBE_HALF_DEG}°, "
          f"interp {target_p:.1f}mb ({lo}↔{hi}), gap {gap_h:.0f}h, "
          f"{len(schedule)} slices fix→+{cov_h:.0f}h{'' if reached_now else ' (capped)'}", flush=True)
    for mi, mem in enumerate(MEMBERS):
        cube, n = member_cube_tube(mem, schedule, slice_ms, last_lat, last_lon, target_p, latest, now)
        g.write_cube(device, f"-m{mi:02d}", cube, n, n, f"m{mi:02d}")


def build_device_static(device, fixes, target_p, latest, now, last_fix, schedule):
    """Legacy: one coarse static box per member (GEFS_TUBE=0)."""
    span_h = min(max(0, (now - last_fix).total_seconds() / 3600), g.MAX_GAP_H) + g.HORIZON_H
    bounds = g.bounds_for_forecast(fixes, span_h, pad_cap=PAD_CAP_DEG)
    step = g.choose_grid_step(bounds)
    lats = np.arange(bounds["latMin"], bounds["latMax"] + 1e-6, step)
    lons = np.arange(bounds["lonMin"], bounds["lonMax"] + 1e-6, step)
    rows_idx = np.round((90.0 - lats) / 0.5).astype(int).clip(0, 360)
    cols_idx = (np.round((lons % 360.0) / 0.5).astype(int)) % 720
    print(f"  {device}: GEFS {len(MEMBERS)} members STATIC box step {step}°", flush=True)
    for mi, mem in enumerate(MEMBERS):
        cube = member_cube(mem, schedule, lats, lons, rows_idx, cols_idx, step, target_p, latest, now)
        g.write_cube(device, f"-m{mi:02d}", cube, len(lats), len(lons), f"m{mi:02d}")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    devices = [(only, None)] if only else g.active_devices()
    if not devices:
        print("no active devices")
        return
    latest = gefs_latest_cycle()
    print(f"latest GEFS cycle {latest.isoformat()} | members {len(MEMBERS)} | devices {[d for d, _ in devices]}")
    for d, launched in devices:
        try:
            fixes = g.mission_fixes(d, g.mission_since(launched))
            if len(fixes) < 1:
                print(f"  {d}: no fixes, skipping")
                continue
            build_device(d, fixes, g.float_pressure(d), latest)
        except Exception as e:  # noqa: BLE001
            print(f"  {d}: FAILED {e}")

    # Also build AIGEFS (GraphCast AI) member cubes — a model-independent source
    # pooled into the same ensemble (see aigefs_ingest). Best-effort: a failure
    # here must NOT break the physics-GEFS / GFS pipeline, so it's fully isolated.
    try:
        import aigefs_ingest
        print("--- AIGEFS (AI ensemble) ---")
        aigefs_ingest.run(only)
    except Exception as e:  # noqa: BLE001
        print(f"AIGEFS ingest failed (non-fatal, GEFS/GFS unaffected): {e}")


if __name__ == "__main__":
    main()
