#!/usr/bin/env python3
"""
ECMWF AIFS-ENS -> per-member WindCubes ({device}-eNN.slwc).

A third, fully-INDEPENDENT center for the ensemble. GEFS (physics) and AIGEFS
(NOAA GraphCast) both lean on NOAA's analysis and lineage, so they agree too much
and under-state model uncertainty; ECMWF's AI ensemble is an independent model +
analysis, and in testing it spreads ~3x wider over a long dead-reckon — i.e. it
exposes structural uncertainty the NOAA-only cloud hides.

ECMWF open data layout differs from GFS/GEFS: ONE GRIB2 file per (cycle, step)
holding ALL 50 members, selected via a `number` key in the per-step `.index`
(shared across members → far fewer index fetches). 0.25°, pres files carry
250/300 hPa U/V, 6-hourly cycles, members 1..50. Some (cycle, step) slots are
missing — remapped to the nearest available valid time.

Reuses gfs_ingest helpers + the .slwc packer. Invoked best-effort from
gefs_ingest alongside GEFS/AIGEFS (added to the GH Actions step later).

Run: python3 scripts/ecmwf_ingest.py [device]
     ECMWF_N_MEMBERS=6 python3 scripts/ecmwf_ingest.py stratolink-3   (fast subset)
"""
import io
import os
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pygrib

import gfs_ingest as g  # shared: http_get, mission_fixes, float_pressure, bounds, bracket_levels, pack_cube, ...

BASE = "https://ecmwf-forecasts.s3.amazonaws.com"
N_MEMBERS = int(os.environ.get("ECMWF_N_MEMBERS", "50"))
MEMBERS = list(range(1, min(50, max(1, N_MEMBERS)) + 1))   # AIFS-ENS perturbed members 1..50
CUBE_STEP_H = 6           # cube time step (ECMWF is heavy at 0.25°; 6-hourly keeps it sane)
PAD_CAP_DEG = 40


def iurl(cyc, step):
    return (f"{BASE}/{cyc:%Y%m%d}/{cyc:%H}z/aifs-ens/0p25/enfo/"
            f"{cyc:%Y%m%d}{cyc:%H}0000-{step}h-enfo-pf.index")


def gurl(cyc, step):
    return iurl(cyc, step)[:-6] + ".grib2"


def latest_cycle():
    c = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    c = c.replace(hour=(c.hour // 6) * 6)
    for _ in range(8):
        try:
            g.http_get(iurl(c, 0))
            return c
        except Exception:  # noqa: BLE001
            c -= timedelta(hours=6)
    raise SystemExit("no published AIFS-ENS cycle")


def ideal(t, latest):
    cyc = latest if t > latest else t.replace(minute=0, second=0, microsecond=0).replace(
        hour=(t.hour // 6) * 6)
    return cyc, max(0, round((t - cyc).total_seconds() / 3600 / 3) * 3)


def fetch_index(cs, levels):
    """Per (cycle,step) index → {number: {(param,levelist): (offset, length)}}. Shared
    across members. None on 404 (missing slot)."""
    c, s = cs
    try:
        m = {}
        want = {str(lv) for lv in levels}
        for e in (json.loads(l) for l in g.http_get(iurl(c, s)).decode().splitlines() if l.strip()):
            if e.get("param") in ("u", "v") and e.get("levtype") == "pl" and e.get("levelist") in want:
                m.setdefault(int(e.get("number", 0)), {})[(e["param"], e["levelist"])] = (
                    int(e["_offset"]), int(e["_length"]))
        return cs, m
    except Exception:  # noqa: BLE001
        return cs, None


def fetch_member_field(mem, cs, idx, lo, hi, w):
    """Interpolated (u, v) global 0.25° arrays for one member at (cycle, step)."""
    c, s = cs
    rec = idx[cs][mem]
    buf = io.BytesIO()
    msgs = [("u", str(hi)), ("v", str(hi))] + ([] if lo == hi else [("u", str(lo)), ("v", str(lo))])
    for key in msgs:
        off, ln = rec[key]
        buf.write(g.http_get(gurl(c, s), rng=f"{off}-{off+ln-1}"))
    tmp = os.path.join(g.OUTDIR, f".e{mem:03d}_{c:%Y%m%d%H}_{s}.grib2")
    os.makedirs(g.OUTDIR, exist_ok=True)
    open(tmp, "wb").write(buf.getvalue())
    fields = {}
    gr = pygrib.open(tmp)
    for grb in gr:
        if grb.shortName in ("u", "v"):
            fields[(grb.shortName, int(grb.level))] = np.asarray(grb.values, dtype=float)
    gr.close()
    os.remove(tmp)
    if lo == hi:
        return fields[("u", hi)], fields[("v", hi)]
    u = fields[("u", hi)] * (1 - w) + fields[("u", lo)] * w
    v = fields[("v", hi)] * (1 - w) + fields[("v", lo)] * w
    return u, v


def build_device(device, fixes, target_p, latest):
    now = datetime.now(timezone.utc)
    last_fix = g.tparse(fixes[-1]["t"])
    gap_h = max(0, (now - last_fix).total_seconds() / 3600)
    span_h = min(gap_h, g.MAX_GAP_H) + g.HORIZON_H
    bounds = g.bounds_for_forecast(fixes, span_h, pad_cap=PAD_CAP_DEG)
    step = g.choose_grid_step(bounds)
    lo, hi, w = g.bracket_levels(target_p)
    levels = [hi] if lo == hi else [lo, hi]
    print(f"  {device}: ECMWF {len(MEMBERS)} members, interp {target_p:.1f}mb ({lo}↔{hi}), "
          f"gap {gap_h:.0f}h, box step {step}°", flush=True)

    lats = np.arange(bounds["latMin"], bounds["latMax"] + 1e-6, step)
    lons = np.arange(bounds["lonMin"], bounds["lonMax"] + 1e-6, step)
    rows_idx = np.round((90.0 - lats) / 0.25).astype(int).clip(0, 720)
    cols_idx = (np.round((lons % 360.0) / 0.25).astype(int)) % 1440

    start = g.floor_step(last_fix, CUBE_STEP_H)
    end = g.floor_step(now, CUBE_STEP_H) + timedelta(hours=g.HORIZON_H + CUBE_STEP_H)
    times = []
    t = start
    while t <= end:
        times.append(t)
        t += timedelta(hours=CUBE_STEP_H)

    # Per-(cycle,step) index, shared across members; remap missing slots to nearest.
    need = sorted({ideal(t, latest) for t in times})
    idx = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for cs, m in ex.map(lambda cs: fetch_index(cs, levels), need):
            if m:
                idx[cs] = m
    avail = sorted(idx.keys())
    if not avail:
        raise SystemExit("no ECMWF indexes available in range")
    if len(need) - len(avail):
        print(f"    ({len(need)-len(avail)}/{len(need)} (cycle,step) missing — remapped to nearest)", flush=True)

    def vt(cs):
        return cs[0] + timedelta(hours=cs[1])

    def nearest(c, s):
        ideal_t = c + timedelta(hours=s)
        return min(avail, key=lambda a: abs((vt(a) - ideal_t).total_seconds()))

    schedule = [(t, nearest(*ideal(t, latest))) for t in times]   # (grid_time, (cyc,step))
    uniq = sorted({cs for _, cs in schedule})
    # members present in every needed slot (ECMWF sets are complete, but be safe)
    members = [m for m in MEMBERS if all(m in idx[cs] for cs in uniq)]

    built = 0
    for mem in members:
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                fld = dict(zip(uniq, ex.map(lambda cs: fetch_member_field(mem, cs, idx, lo, hi, w), uniq)))
            t0 = int(times[0].timestamp() * 1000)
            grids = []
            for gt, cs in schedule:
                u, v = fld[cs]
                U = u[np.ix_(rows_idx, cols_idx)]
                V = v[np.ix_(rows_idx, cols_idx)]
                grids.append({"lat0": float(lats[0]), "dLat": step, "nLat": len(lats),
                              "lon0": float(lons[0]), "dLon": step, "nLon": len(lons),
                              "U": U.ravel(), "V": V.ravel()})
            cube = {
                "source": "ecmwf-aifs", "generated_at": now.isoformat(),
                "latest_cycle_utc": latest.isoformat(), "member": f"e{mem:02d}",
                "levelHpa": round(target_p, 1), "gridStep": step,
                "t0Ms": t0, "stepMs": CUBE_STEP_H * 3600 * 1000,
                "bounds": {"latMin": float(lats[0]), "latMax": float(lats[-1]),
                           "lonMin": float(lons[0]), "lonMax": float(lons[-1])},
                "grids": grids,
            }
            g.write_cube(device, f"-e{mem-1:02d}", cube, len(lats), len(lons), f"e{mem-1:02d}")
            built += 1
        except Exception as e:  # noqa: BLE001
            print(f"    e{mem-1:02d}: skipped ({e})", flush=True)
    print(f"  {device}: ECMWF built {built}/{len(members)} members", flush=True)


def run(only=None):
    devices = [(only, None)] if only else g.active_devices()
    if not devices:
        print("no active devices")
        return
    latest = latest_cycle()
    print(f"latest AIFS-ENS cycle {latest.isoformat()} | members {len(MEMBERS)} | devices {[d for d, _ in devices]}")
    for d, launched in devices:
        try:
            fixes = g.mission_fixes(d, g.mission_since(launched))
            if len(fixes) < 1:
                print(f"  {d}: no fixes, skipping")
                continue
            build_device(d, fixes, g.float_pressure(d), latest)
        except Exception as e:  # noqa: BLE001
            print(f"  {d}: ECMWF FAILED {e}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
