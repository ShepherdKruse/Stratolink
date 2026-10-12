#!/usr/bin/env python3
"""
GFS -> WindCube ingest (production). For each planned balloon it derives the
forecast region / pressure level / time window from Supabase telemetry (mirroring
the app's boundsForForecast + chooseGridStep + snapPressure so the cube matches
what computeMonteCarloForecast asks for), then builds a multi-cycle cube from
NOAA's free NODD S3 (byte-range U/V via the .idx: past 3-hourly *analyses* +
forward *forecast* from the latest cycle) and writes it to .windcube/cubes/.

Which balloons: the plan written by scripts/plan_forecasts.ts (FORECAST_PLAN,
default .windcube/plan.json) — the devices it marked `build`; without a fresh
plan (local runs) the legacy fleet query (status=flying, connected) or the one
requested device. What was built is appended to the ingest manifest
(FORECAST_MANIFEST, default .windcube/manifest.json) for the compute step and
the job summary. scripts/compute_forecasts.ts then reads the cubes from disk.

Env: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, FORECAST_PLAN, FORECAST_MANIFEST.
Run: python3 scripts/gfs_ingest.py            (planned / all active devices)
     python3 scripts/gfs_ingest.py stratolink-3   (one device)
"""
import io
import json
import math
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

# GitHub Actions pipes stdout, which Python then block-buffers: a step killed at
# its timeout loses everything still in the buffer (the member lines we most want
# to see). Line-buffer it so each progress line lands as it is printed.
try:
    sys.stdout.reconfigure(line_buffering=True)
except (AttributeError, ValueError):  # not a real text stream (tests, pipes closed)
    pass


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
#   - reconstruction cube ({device}): full mission, 3-HOURLY, a tube along the
#     observed track at the native 0.25° (see "reconstruction tube" below). Drives
#     the historical track only.
FC_STEP_H = 1                    # forecast cube time step (hourly forecast hours)
RECON_STEP_H = 3                 # reconstruction cube time step
# Hours of margin BEFORE the last fix that the forecast cube covers. The compute
# integrates forward from the last fix (sampleWind time-interpolates between the
# bracketing hourly slices, so one slice before it is enough); nothing earlier is
# read since the bias became neutral (lib/wind/monteCarloForecast.ts neutralBias
# — the chord-fit bias that once needed 36 h of pre-fix track is gone). The
# historical track lives in the reconstruction cube.
FC_BIAS_H = 1
HOURLY_FHR_MAX = 120             # GFS publishes hourly forecast hours through f120
# Cube resolution is now bounded by SIZE, not API calls (we own the GFS download).
# A higher point budget => a much finer grid than Open-Meteo's 120-pt cap allowed.
MAX_GRID_PTS = 8000
# Cap full-mission lookback (matches the app's MAX_HISTORY). Override to replay a
# flight older than the cap locally (HISTORY_DAYS=365; pair it with the compute's
# FORECAST_HISTORY_DAYS so both sides see the same fixes).
HISTORY_DAYS = int(os.environ.get("HISTORY_DAYS", "90"))
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
# Cap the dead-reckon the tube covers. Beyond ~2 weeks even a perfect tube is a
# globe-sized cloud (predictability is gone), so don't fetch/integrate past it;
# the compute then truncates honestly (coverage_limited). 14 days balances showing
# a useful long-drift path against runtime — a very-long-gap full ensemble at this
# cap can brush the workflow's GEFS-step timeout (continue-on-error → GEFS complete,
# AIGEFS partial; bump the step timeout for guaranteed full AIGEFS). Small value
# for fast local iteration: FC_DEAD_RECKON_CAP_H=48.
DEAD_RECKON_CAP_H = int(os.environ.get("FC_DEAD_RECKON_CAP_H", str(14 * 24)))
TUBE_SUBSTEP_H = 1.0 / 6.0       # nominal integration sub-step (matches BALLOON_STEP_HOURS)
# ── Trajectory-following reconstruction tube ─────────────────────────────────
# The reconstruction cube used to be ONE static box around the whole mission plus
# pads, which for a continental flight forced choose_grid_step to 0.5–1° while GFS
# is natively 0.25°. Like the forecast tube, lay one box per 3-hourly slice along
# the OBSERVED track instead (interp_track of the fixes): every slice is small
# enough to stay at 0.25°, and the historical bridges never stray from the
# fix-to-fix corridor by more than the smoother's particle wander, so a box only
# has to be wide enough for that cloud (recon_half_deg). The forward leg the
# static box carried (last fix → now+horizon) is unused by the reconstruction —
# the forecast tube owns that — so the tube ends two steps past the last fix.
RECON_TUBE = os.environ.get("RECON_TUBE", "1") != "0"   # RECON_TUBE=0 → legacy static box
# Half-width (deg) of a slice box from the length of the GPS gap the slice sits
# in: base + per-hour growth, clamped. Calibrated to the long-gap smoother
# (lib/wind/pathReconstructionLongGap.ts): its particles follow the wind under a
# bounded AR(1) heading/speed perturbation (12°, 15 %) plus their own pressure,
# so a cloud spreads around the wind trajectory it is laid along roughly in
# proportion to the gap length. 9° covers gaps ≤ 60 h; +0.05°/h adds 5° per
# 100 h (a 200 h gap gets 16°); 20° (≈2200 km at mid-latitudes) caps the box.
# Long gaps lay their boxes along the forward/backward wind trajectories (see
# LONG_GAP_H), shorter ones along the chord. Every sample is checked at compute
# time (`cubeCovers`): the smoother penalises lineages that leave the tube, and
# the raw / posterior-weighted outside fractions are logged per gap.
RECON_HALF_BASE_DEG = 6.0
RECON_HALF_PER_H = 0.05
RECON_HALF_MIN_DEG = float(os.environ.get("RECON_HALF_MIN_DEG", "9"))
RECON_HALF_MAX_DEG = float(os.environ.get("RECON_HALF_MAX_DEG", "20"))
# Point budget for one recon slice. Resolution is bounded by SIZE only (the GRIB
# messages are whole-globe regardless of the box): the widest box, ±20° at 0.25°,
# is 161² = 25,921 points = 104 KB per slice, so even a two-week mission stays
# ≲ 12 MB. The forecast tube keeps the tighter MAX_GRID_PTS; this budget just has
# to admit the native 0.25° at the cap — choose_grid_step still coarsens the whole
# cube if the cap is raised past what fits.
RECON_MAX_GRID_PTS = int(os.environ.get("RECON_MAX_GRID_PTS", "26000"))
GFS_LEVELS = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30]
# ── Multi-level reconstruction cube (.slwc v4) ───────────────────────────────
# The long-gap smoother gives every particle its own pressure (a balloon loses
# ground by riding a different level's wind, not by flying across the flow), so
# the reconstruction cube stores the two GFS levels bracketing the float
# pressure UNBLENDED plus RECON_LEVELS_EACH_SIDE more on each side; the reader
# rebuilds the float-level grids by the same linear-in-pressure blend the
# single-level cube used, so every other consumer is unchanged. The 0.25°
# pgrb2 files also carry 350 and 450 hPa (GFS_LEVELS predates that; it stays
# as is for the forecast and GEFS cubes), so a ~280 hPa float gets
# 200/250/300/350. RECON_LEVELS_EACH_SIDE=0 writes the legacy single-level
# (blended) v3 cube. The inner pair is already fetched for the blend; each
# extra level adds one more pair of byte-range GRIB fetches per slice.
RECON_LEVEL_SET = sorted(set(GFS_LEVELS) | {350, 450})
RECON_LEVELS_EACH_SIDE = int(os.environ.get("RECON_LEVELS_EACH_SIDE", "1"))
# Long GPS gaps (≥ LONG_GAP_H, mirrors CFG.LONG_GAP_HR in
# lib/wind/pathReconstructionLongGap.ts) are bridged by a two-filter smoother:
# a forward particle cloud from fix A meets a backward one from fix B at the
# gap's midpoint. Their slice boxes follow the clouds — the float-level wind
# trajectory forward from A until LONG_GAP_JOIN_MARGIN_H past the midpoint,
# backward from B from that long before it — instead of the time-linear chord:
# a balloon crosses an ocean in two days and then loiters for four, and the
# chord tube cut exactly that path off (stratolink-3's 201 h gap left the
# chord's boxes from hour ~22 to ~135).
LONG_GAP_H = 6
LONG_GAP_JOIN_MARGIN_H = 12
# The backward cloud is also covered from this long before the midpoint: the
# final bridges' forward halves lean toward where it is (they must meet it), so
# in the last day or so before the meeting they sit on its side of the forward
# cloud, outside a box sized by the forward cloud alone. At most a quarter of the
# gap (never less than LONG_GAP_JOIN_MARGIN_H), so short long-gaps stay tight.
LONG_GAP_BACKWARD_LEAD_H = 36
# A long gap whose forward and backward trajectories are this far apart (deg, in
# lat or lon) at a slice falls back to the chord there: the winds cannot connect
# its fixes (e.g. a pre-launch gap on the ground, where the float-level winds run
# a fictitious balloon off in opposite directions), and a box spanning both
# would coarsen the whole cube's grid for nothing.
LONG_GAP_MAX_SPREAD_DEG = 30
# Long-gap box SIZE: a pilot cloud of RECON_PILOT_N particles with the smoother's
# own perturbation (bounded AR(1) heading and speed, mirroring CFG.DIR_SIGMA_DEG /
# SPEED_SIGMA / PERTURB_TAU_H in lib/wind/pathReconstructionLongGap.ts) is run
# forward from the gap's first fix and backward from its second, and each slice's
# box is that cloud's 1–99 % extent padded by RECON_PILOT_MARGIN_DEG — capped at
# the old size (the trajectories ± recon_half_deg). A single half-width per gap
# made every box of stratolink-3's 201 h gap 33° tall, around clouds 1–9° across
# near the fixes; mid-gap, where the forward cloud (which doesn't know the far fix
# until the two meet) spans ~30°, the cap keeps the box as it was.
# Coarse outer field (.slwc v5): per reconstruction slice, the float-level wind at
# RECON_OUTER_STEP° over RECON_OUTER_LAT and ±RECON_OUTER_HALF_LON° of longitude
# around the fine box. A particle that leaves the fine box reads these real (if
# coarser) winds instead of the box's edge-clamped value, so it is not penalised:
# box size then only sets resolution, never which particles survive. ~32 KB a
# slice. RECON_OUTER=0 writes no outer field (v4/v3 cube).
RECON_OUTER = os.environ.get("RECON_OUTER", "1") != "0"
RECON_OUTER_STEP = 1.5
RECON_OUTER_LAT = (-10.0, 85.0)
RECON_OUTER_HALF_LON = 90.0
RECON_PILOT_N = 200
RECON_PILOT_MARGIN_DEG = 3.0
PILOT_DIR_SIGMA_DEG = 12.0
PILOT_SPEED_SIGMA = 0.15
PILOT_TAU_H = 18.0
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
    q = urllib.parse.urlencode(params, safe=",()")  # keep commas/parens (select/order/in.()); encode +,: in timestamps
    u = f"{SUPA_URL}/rest/v1/{path}?{q}"
    body = http_get(u, headers={"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"})
    return json.loads(body)


# ── Supabase: fleet + recent track + level ───────────────────────────────────
# Mirror of lib/devices/aliases.ts DEVICE_ID_ALIASES. Telemetry can arrive under
# an alias id (a second receiver / firmware id for the same balloon) and the
# compute's fetchTelemetryMerged folds those rows into the canonical device — so
# the cube must be built from the SAME merged fix set: the tube is centered on
# the observed track, and a receiver's missing fixes would shift both its
# centers and its gap widths. test_forecast_ingest.py checks this map against
# the TS source so the two can't drift apart silently.
DEVICE_ID_ALIASES = {"stratolink-3-eu": "stratolink-3"}


def telemetry_device_ids(device):
    """Every telemetry device_id to query for a canonical (or alias) device."""
    canonical = DEVICE_ID_ALIASES.get(device, device)
    return [canonical] + sorted(a for a, c in DEVICE_ID_ALIASES.items() if c == canonical)


def device_id_filter(device):
    return "in.(" + ",".join(telemetry_device_ids(device)) + ")"


def active_devices():
    rows = supa("devices", {"select": "device_id,status,launched_at", "connection_status": "eq.connected"})
    return [(r["device_id"], r.get("launched_at")) for r in rows
            if r.get("status") == "flying" and r["device_id"] not in DEVICE_ID_ALIASES]


# ── Activity plan (scripts/plan_forecasts.ts) + ingest manifest ──────────────
_WINDCUBE_DIR = os.path.join(os.path.dirname(__file__), "..", ".windcube")
PLAN_PATH = os.environ.get("FORECAST_PLAN") or os.path.join(_WINDCUBE_DIR, "plan.json")
MANIFEST_PATH = os.environ.get("FORECAST_MANIFEST") or os.path.join(_WINDCUBE_DIR, "manifest.json")
PLAN_MAX_AGE_H = 12              # mirrors PLAN_MAX_AGE_H in lib/wind/forecastPlan.ts


def load_plan(path=None):
    """The activity plan written by scripts/plan_forecasts.ts, or None when there
    is none (local runs) or it is stale — a leftover file must never silently
    shrink the fleet, so an old plan is ignored (and the legacy query used)."""
    path = path or PLAN_PATH
    try:
        with open(path) as f:
            plan = json.load(f)
    except (OSError, ValueError):
        return None
    try:
        age_h = (datetime.now(timezone.utc) - tparse(plan["generated_at"])).total_seconds() / 3600
    except (KeyError, TypeError, ValueError, AttributeError):
        age_h = float("inf")
    if not isinstance(plan.get("devices"), list) or not (-1 <= age_h <= PLAN_MAX_AGE_H):
        print(f"ignoring stale or malformed plan {path} (generated {plan.get('generated_at')})", flush=True)
        return None
    return plan


def planned_devices(only=None, plan=None):
    """(device_id, launched_at) pairs to ingest this run. With a plan: the devices
    it marked `build` (skipped ones are logged with the plan's reason, and an
    explicitly requested device that the plan skipped stays skipped). Without
    one: the legacy fleet query, or the one requested device."""
    plan = plan if plan is not None else load_plan()
    if plan is None:
        return [(only, None)] if only else active_devices()
    out, seen = [], False
    for d in plan.get("devices", []):
        if only and d.get("device_id") != only:
            continue
        seen = True
        if d.get("action") == "build":
            out.append((d["device_id"], d.get("launched_at")))
        else:
            print(f"  {d.get('device_id')}: skipped by plan — {d.get('reason', '')}", flush=True)
    if only and not seen:
        print(f"  {only}: not in the plan — nothing to build", flush=True)
    return out


def _manifest_read():
    try:
        with open(MANIFEST_PATH) as f:
            m = json.load(f)
        if isinstance(m, dict) and isinstance(m.get("sources"), dict):
            return m
    except (OSError, ValueError):
        pass
    return {"version": 1, "sources": {}}


def _manifest_write(m):
    d = os.path.dirname(MANIFEST_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=1)
    os.replace(tmp, MANIFEST_PATH)       # atomic: a reader never sees a torn file


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def manifest_source_begin(source, **meta):
    """Start (and reset) one source's record in the manifest shared with
    lib/wind/forecastManifest.ts: {started_at, devices: {}, **meta}."""
    m = _manifest_read()
    m["sources"][source] = {"started_at": _now_iso(), "devices": {}, **meta}
    _manifest_write(m)


def manifest_device(source, device, **fields):
    """Merge per-device facts (built/expected members, cubes, errors) into the
    source's record. Called after EVERY member or cube write, so a step killed at
    its timeout still leaves an accurate count behind for the compute + summary."""
    m = _manifest_read()
    src = m["sources"].setdefault(source, {"started_at": _now_iso(), "devices": {}})
    src.setdefault("devices", {}).setdefault(device, {}).update(fields)
    _manifest_write(m)


def manifest_source_end(source):
    """Stamp finished_at + seconds. A source without it in the summary was killed."""
    m = _manifest_read()
    src = m["sources"].setdefault(source, {"started_at": _now_iso(), "devices": {}})
    src["finished_at"] = _now_iso()
    try:
        src["seconds"] = round((tparse(src["finished_at"]) - tparse(src["started_at"])).total_seconds(), 1)
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    _manifest_write(m)


def mission_since(launched_at):
    """Earliest time to fetch fixes from: launch, but never older than HISTORY_DAYS."""
    floor = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
    if launched_at:
        lt = tparse(launched_at)
        if lt > floor:
            floor = lt
    return floor.strftime("%Y-%m-%dT%H:%M:%SZ")


def mission_fixes(device, since_iso):
    """All GPS fixes since launch (full mission), canonical + alias ids merged by
    time like the compute's fetchTelemetryMerged — for the cube's track + span."""
    rows = supa("telemetry", {
        "device_id": device_id_filter(device),
        "time": f"gte.{since_iso}",
        "lat": "not.is.null", "lon": "not.is.null",
        "select": "time,lat,lon,altitude_m", "order": "time.asc", "limit": "50000",
    })
    # Drop corrupt coordinates (the telemetry has occasional garbage fixes, e.g.
    # lat -222) — a single outlier blows up the bounding box and coarsens the grid.
    # One row per timestamp (an alias can echo the canonical row's time).
    seen = set()
    out = []
    for r in rows:
        if not (-90 <= r["lat"] <= 90 and -180 <= r["lon"] <= 180) or r["time"] in seen:
            continue
        seen.add(r["time"])
        out.append({"lat": r["lat"], "lon": r["lon"], "t": r["time"], "alt": r.get("altitude_m")})
    return out


def mission_track(device, launched_at):
    """Mission GPS fixes; falls back to the launch record when there are none.

    A device that has been released but not heard since (radio blackout) has
    zero fixes in its mission window, but the launch site + stamped time are
    real information — enough to build a cube around the launch point so the
    forecast can simulate the drift from there. Mirrors the same fallback in
    web/lib/wind/buildForecastInput.ts."""
    fixes = mission_fixes(device, mission_since(launched_at))
    if fixes:
        return fixes
    rows = supa("devices", {
        "device_id": f"eq.{device}",
        "select": "launch_lat,launch_lon,launched_at",
    })
    r = rows[0] if rows else {}
    lat, lon, lt = r.get("launch_lat"), r.get("launch_lon"), r.get("launched_at")
    if lat is None or lon is None or not lt or tparse(lt) > datetime.now(timezone.utc):
        return []
    print(f"  {device}: no fixes — seeding from launch record ({lat}, {lon} @ {lt})")
    return [{"lat": lat, "lon": lon, "t": lt, "alt": None}]


def float_pressure(device):
    """Robust estimate of the balloon's float pressure (hPa): the median of the
    last ~200 non-null readings, restricted to the float band (80–400 hPa) so a
    single noisy packet — or ground/ascent/garbage rows — can't shift it. The
    cube is then interpolated to this pressure rather than snapped to the nearest
    standard GFS level (so ~280 hPa is sampled as 280, not 300). Fallback 285."""
    rows = supa("telemetry", {
        "device_id": device_id_filter(device), "pressure": "not.is.null",
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
            # float32, not float64: a whole-globe 0.25° field is 8.3 MB as f64; the
            # parallel prefetch holds hundreds of them (recon + a 14-day fc tube), so
            # f64 blew past the runner's RAM (OOM, exit 143). Lossless here — cubes
            # quantize to int16 = round(value*10) anyway.
            out[grb.shortName] = np.asarray(grb.values, dtype=np.float32)
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


def recon_levels(p, each_side=None):
    """Pressure levels (hPa, ascending) stored in the multi-level reconstruction
    cube: the RECON_LEVEL_SET levels bracketing `p` plus `each_side` more on each
    side (clamped to the set). [] when each_side is 0 (single-level cube)."""
    each_side = RECON_LEVELS_EACH_SIDE if each_side is None else each_side
    if each_side <= 0:
        return []
    lv = RECON_LEVEL_SET
    hi = min((x for x in lv if x >= p), default=lv[-1])
    lo = max((x for x in lv if x <= p), default=lv[0])
    return lv[max(0, lv.index(lo) - each_side): lv.index(hi) + each_side + 1]


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
    w0, w1 = np.float32(1 - w), np.float32(w)   # keep the blend in float32 (don't upcast)
    out = {"u": a["u"] * w0 + b["u"] * w1, "v": a["v"] * w0 + b["v"] * w1}
    _uv_p_cache[key] = out
    return out


def clear_field_cache(keep=()):
    """Free the whole-globe field caches between cube builds — they grow with every
    fetched (cycle, fhr) and would otherwise hold the tube's hundreds of fields in
    RAM while the recon prefetches hundreds more (OOM on a long mission). `keep` =
    (cycle, fhr) pairs the next build samples too; those stay warm instead of
    being downloaded twice."""
    keep = set(keep)
    for cache in (_uv_cache, _uv_p_cache):
        for key in [k for k in cache if (k[0], k[1]) not in keep]:
            del cache[key]


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

    # Prefetch every needed (cycle, fhr) field IN PARALLEL before the sampling loop.
    # The source field depends only on a step's TIME, so they can all be fetched up
    # front; the loop then reads the warm cache. The serial per-grid fetch was the
    # mission-length-scaling bottleneck — a long full-mission recon (hundreds of
    # 3-hourly grids) crept past the job timeout. (Mirrors the tube's prefetch.)
    _tt, _want = start, set()
    while _tt <= end:
        _want.add(pick_source(_tt, latest)); _tt += timedelta(hours=step_h)
    print(f"      {tag}: prefetch {len(_want)} fields (parallel)…", flush=True)
    with ThreadPoolExecutor(max_workers=8) as _ex:
        list(_ex.map(lambda cf: fetch_uv_p(cf[0], cf[1], target_p), sorted(_want)))

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
    # The box's labeled geometry (lat0 + k·step) must land ON source rows/cols,
    # or the rows picked below are silently up to half a cell off the labels — a
    # systematic position error in every sample. Needs half_deg and step to be
    # multiples of the source spacing (build_tube_grids snaps half_deg).
    assert abs(lat0 / dlat - round(lat0 / dlat)) < 1e-6 and abs(step / dlat - round(step / dlat)) < 1e-6, \
        f"cut_box: half {half_deg}°/step {step}° not on the {dlat}° source lattice"
    lats = lat0 + np.arange(n) * step
    lons = lon0 + np.arange(n) * step
    rows = np.round((90.0 - lats) / dlat).astype(int).clip(0, nlat - 1)
    cols = (np.round((lons % 360.0) / dlon).astype(int)) % nlon
    return float(lats[0]), float(lons[0]), u[np.ix_(rows, cols)].ravel(), v[np.ix_(rows, cols)].ravel()


def cut_box_rect(u, v, clat, clon, half_lat, half_lon, step, nlat_box, nlon_box):
    """`cut_box` for a rectangular box: `nlat_box`×`nlon_box` points at `step`°
    around (clat, clon) with separate half-extents (multiples of `step`). Same
    lattice snapping and unwrapped-longitude conventions."""
    nlat, nlon = u.shape
    dlat = 180.0 / (nlat - 1); dlon = 360.0 / nlon
    lat0 = round(clat / dlat) * dlat - half_lat
    lon0 = round(clon / dlon) * dlon - half_lon
    assert abs(lat0 / dlat - round(lat0 / dlat)) < 1e-6 and abs(lon0 / dlon - round(lon0 / dlon)) < 1e-6 \
        and abs(step / dlat - round(step / dlat)) < 1e-6, \
        f"cut_box_rect: half {half_lat}/{half_lon}°, step {step}° not on the {dlat}° source lattice"
    lats = lat0 + np.arange(nlat_box) * step
    lons = lon0 + np.arange(nlon_box) * step
    rows = np.round((90.0 - lats) / dlat).astype(int).clip(0, nlat - 1)
    cols = (np.round((lons % 360.0) / dlon).astype(int)) % nlon
    return float(lats[0]), float(lons[0]), u[np.ix_(rows, cols)].ravel(), v[np.ix_(rows, cols)].ravel()


def integrate_positions(times_ms, start_ms, start_lat, start_lon, wind_fn, direction=1):
    """Unperturbed trajectory from (start_lat, start_lon) at `start_ms`, forward
    (`direction` 1) or backward through time-reversed winds (−1), sampled at each
    of `times_ms` on that side of the start (in any order); {t: (lat, lon)}. Same
    TUBE_SUBSTEP_H Euler steps and unwrapped longitudes as the nominal centers."""
    want = sorted((t for t in times_ms if (t - start_ms) * direction >= 0), key=lambda t: (t - start_ms) * direction)
    out = {}
    lat, lon, t_ms = start_lat, start_lon, start_ms
    dt_ms = TUBE_SUBSTEP_H * 3600 * 1000
    k = 0
    while k < len(want):
        while k < len(want) and (want[k] - t_ms) * direction <= 1:
            out[want[k]] = (lat, lon); k += 1
        if k >= len(want):
            break
        u, v = wind_fn(lat, lon, t_ms)
        coslat = max(np.cos(np.radians(lat)), 0.05)
        lat += direction * v * dt_ms / 1000 / 111_320
        lon += direction * u * dt_ms / 1000 / (111_320 * coslat)
        t_ms += direction * dt_ms
    return out


def pilot_envelopes(times_ms, start_ms, start_lat, start_lon, wind_fn, direction=1, n=None, seed=0):
    """Run a pilot cloud of `n` particles from (start_lat, start_lon) at
    `start_ms`, forward (`direction` 1) or backward through time-reversed winds
    (−1), each following `wind_fn` under the smoother's bounded AR(1) heading and
    speed perturbation, and return {t: (lat_lo, lat_hi, lon_lo, lon_hi)} — the
    cloud's full extent per axis — at each of `times_ms` on that side of the
    start. Pure Python (seeded `random`), so it runs without numpy."""
    import random
    n = n or RECON_PILOT_N
    rng = random.Random(seed)
    want = sorted((t for t in times_ms if (t - start_ms) * direction >= 0), key=lambda t: (t - start_ms) * direction)
    dt_h = TUBE_SUBSTEP_H
    rho = math.exp(-dt_h / PILOT_TAU_H); inn = math.sqrt(1 - rho * rho)
    lat = [start_lat] * n; lon = [start_lon] * n
    hd = [rng.gauss(0, PILOT_DIR_SIGMA_DEG) for _ in range(n)]
    sp = [rng.gauss(0, PILOT_SPEED_SIGMA) for _ in range(n)]
    lo_i, hi_i = 0, n - 1                                    # the cloud's full extent
    out, t_ms, k = {}, start_ms, 0
    while k < len(want):
        while k < len(want) and (want[k] - t_ms) * direction <= 1:
            la = sorted(lat); lo = sorted(lon)
            out[want[k]] = (la[lo_i], la[hi_i], lo[lo_i], lo[hi_i]); k += 1
        if k >= len(want):
            break
        for i in range(n):
            hd[i] = rho * hd[i] + inn * rng.gauss(0, PILOT_DIR_SIGMA_DEG)
            sp[i] = rho * sp[i] + inn * rng.gauss(0, PILOT_SPEED_SIGMA)
            u, v = wind_fn(lat[i], lon[i], t_ms)
            c, s_ = math.cos(math.radians(hd[i])), math.sin(math.radians(hd[i])); f = max(0.2, 1 + sp[i])
            ur, vr = (u * c - v * s_) * f, (u * s_ + v * c) * f
            lat[i] += direction * vr * dt_h * 3600 / 111_320
            lon[i] += direction * ur * dt_h * 3600 / (111_320 * max(math.cos(math.radians(lat[i])), 0.05))
        t_ms += direction * dt_h * 3600 * 1000
    return out


def integrate_nominal_centers(slice_ms, start_ms, start_lat, start_lon, wind_fn,
                              track_step_ms=None):
    """Pre-integrate ONE nominal trajectory (neutral bias, no perturbation) forward
    from (start_lat, start_lon) at `start_ms`, snapshotting its position at each
    slice time ≥ start_ms. `wind_fn(lat, lon, t_ms) -> (u, v)` supplies the field
    (GFS or a GEFS member). Longitude is left UNWRAPPED so the tube's per-slice
    origins + union bounds form a continuous range the integrator agrees with.
    Slices before start_ms stay None for the caller to fill. Cheap: the global
    fields are fetched/cached once and reused to cut the boxes.

    Returns (centers, track). `track` is None unless `track_step_ms` is given, in
    which case it also snapshots every `track_step_ms` from start_ms to the last
    slice — a denser sampling of the SAME walk, stored in the cube header so the
    compute can read the true path instead of the grid-snapped box centers."""
    centers = [None] * len(slice_ms)
    track_ms = []
    if track_step_ms:
        t = start_ms
        while t <= slice_ms[-1]:
            track_ms.append(t)
            t += track_step_ms
    track = [None] * len(track_ms)
    lat, lon = start_lat, start_lon
    k = 0
    while k < len(slice_ms) and slice_ms[k] < start_ms:
        k += 1
    first_fwd = k
    while k < len(slice_ms) and slice_ms[k] <= start_ms:      # slice exactly at start
        centers[k] = (lat, lon); k += 1
    tk = 0
    while tk < len(track_ms) and track_ms[tk] <= start_ms:
        track[tk] = (lat, lon); tk += 1
    dt_s = TUBE_SUBSTEP_H * 3600
    t_ms = start_ms
    end_ms = slice_ms[-1]
    while t_ms < end_ms and (k < len(slice_ms) or tk < len(track_ms)):
        u, v = wind_fn(lat, lon, t_ms)
        coslat = max(np.cos(np.radians(lat)), 0.05)
        lat += v * dt_s / 111_320
        lon += u * dt_s / (111_320 * coslat)
        t_ms += TUBE_SUBSTEP_H * 3600 * 1000
        while k < len(slice_ms) and slice_ms[k] <= t_ms + 1:
            centers[k] = (lat, lon); k += 1
        while tk < len(track_ms) and track_ms[tk] <= t_ms + 1:
            track[tk] = (lat, lon); tk += 1
    for j in range(first_fwd, len(slice_ms)):                 # trailing (shouldn't happen)
        if centers[j] is None:
            centers[j] = (lat, lon)
    for j in range(len(track_ms)):
        if track[j] is None:
            track[j] = (lat, lon)
    return centers, (track if track_step_ms else None)


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
    # No hourly track for the fc tube: its slices are already hourly, so the
    # stored per-slice centers ARE the hourly true path.
    centers, _ = integrate_nominal_centers(slice_ms, last_fix_ms, last_lat, last_lon, wind_fn)
    return centers


def build_tube_grids(centers, half_deg, step, slice_ms, field_at, source, levelHpa, latest, now, tag=""):
    """Assemble a tube cube from pre-computed `centers`: one `step`° box per slice,
    cut from the whole-globe field returned by `field_at(k) -> (u, v)`. `half_deg`
    is one number (every slice the same size → v2 header, per-slice origins only)
    or a per-slice list (sizes vary → v3 header, which adds per-slice `dims`; the
    reconstruction tube widens its boxes inside long GPS gaps). Half-widths are
    snapped UP to a multiple of `step` so each box's origin stays on the source
    lattice (cut_box asserts it). Returns (cube_dict, max_n, max_n)."""
    halves = list(half_deg) if isinstance(half_deg, (list, tuple)) else [half_deg] * len(centers)
    assert len(halves) == len(centers), "one half-width per slice"
    halves = [math.ceil(h / step - 1e-9) * step for h in halves]
    grids = []
    uminLat = uminLon = float("inf"); umaxLat = umaxLon = float("-inf")
    for k, (clat, clon) in enumerate(centers):
        n = int(round(2 * halves[k] / step)) + 1
        u, v = field_at(k)
        lat0, lon0, U, V = cut_box(u, v, clat, clon, halves[k], step, n)
        grids.append({"lat0": lat0, "dLat": step, "nLat": n,
                      "lon0": lon0, "dLon": step, "nLon": n, "U": U, "V": V})
        uminLat = min(uminLat, lat0); umaxLat = max(umaxLat, lat0 + (n - 1) * step)
        uminLon = min(uminLon, lon0); umaxLon = max(umaxLon, lon0 + (n - 1) * step)
        if tag and ((k + 1) % 24 == 0 or k + 1 == len(centers)):
            print(f"      {tag}: {k + 1}/{len(centers)} slices", flush=True)
    n = max(g["nLat"] for g in grids)
    return {
        "source": source, "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "levelHpa": round(levelHpa, 1), "gridStep": step,
        "t0Ms": slice_ms[0], "stepMs": int(slice_ms[1] - slice_ms[0]) if len(slice_ms) > 1 else FC_STEP_H * 3600 * 1000,
        "bounds": {"latMin": uminLat, "latMax": umaxLat, "lonMin": uminLon, "lonMax": umaxLon},
        "grids": grids,
        # The TRUE (unsnapped) per-slice centers. cut_box snaps each box ORIGIN to
        # the source lattice (required for exact sampling), which quantizes the box
        # centers to 0.25-0.5° — reading those back as the trajectory drew straight
        # chords and right-angle staircases. Keep the real path alongside.
        "centers": centers,
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
    """GFS tube: cut a box per slice from the GFS field (interpolated to target_p).
    `half_deg` may be per-slice (see build_tube_grids)."""
    def field_at(k):
        cyc, fhr = pick_source(datetime.fromtimestamp(slice_ms[k] / 1000, timezone.utc), latest)
        uv = fetch_uv_p(cyc, fhr, target_p)
        return uv["u"], uv["v"]
    return build_tube_grids(centers, half_deg, step, slice_ms, field_at,
                            "gfs", target_p, latest, now, tag)


# ── Reconstruction tube helpers ──────────────────────────────────────────────
def unwrap_lons(lons):
    """Longitudes made continuous across ±180 (no ±360 jump between consecutive
    fixes), anchored so the LAST value keeps its raw longitude — the forecast
    tube's nominal walk starts from that raw value, so the two tubes agree there.
    A box is cut with its origin unwrapped and the compute wraps every query into
    the box's range (windAt), so unwrapped origins sample correctly either way."""
    out = [0.0] * len(lons)
    if not lons:
        return out
    out[-1] = lons[-1]
    for i in range(len(lons) - 2, -1, -1):
        d = (lons[i] - lons[i + 1] + 180.0) % 360.0 - 180.0     # shortest signed step
        out[i] = out[i + 1] + d
    return out


def gap_hours_at(fixes_ms, t_ms, step_ms):
    """Length (h) of the LONGEST GPS gap whose span touches (t_ms - step_ms,
    t_ms + step_ms) — i.e. of any bridge that will read the slice at t_ms: the
    compute blends the two slices bracketing an instant, so a slice is read by
    every instant within one step of it. 0 when no gap reaches the slice (the
    lead-in slice before the first fix, the trailing ones after the last)."""
    best = 0.0
    for (ta, _, _), (tb, _, _) in zip(fixes_ms, fixes_ms[1:]):
        if tb > t_ms - step_ms and ta < t_ms + step_ms:
            best = max(best, (tb - ta) / 3.6e6)
    return best


def recon_half_deg(gap_h):
    """Slice-box half-width (deg) for a slice inside a `gap_h`-hour GPS gap — see
    the RECON_HALF_* notes for the calibration against the long-gap smoother."""
    return min(RECON_HALF_MAX_DEG, max(RECON_HALF_MIN_DEG, RECON_HALF_BASE_DEG + RECON_HALF_PER_H * gap_h))


def outer_box(clon, step=None):
    """(clat, clon, half_lat, half_lon, n_lat, n_lon) of the coarse outer grid
    around a fine box centred at longitude `clon`: RECON_OUTER_LAT in latitude,
    ±RECON_OUTER_HALF_LON in longitude, half-extents snapped up to the step and
    the centre to the 0.25° source lattice (cut_box_rect's requirements)."""
    step = step or RECON_OUTER_STEP
    clat = (RECON_OUTER_LAT[0] + RECON_OUTER_LAT[1]) / 2
    hl = math.ceil((RECON_OUTER_LAT[1] - RECON_OUTER_LAT[0]) / 2 / step - 1e-9) * step
    ho = math.ceil(RECON_OUTER_HALF_LON / step - 1e-9) * step
    clat = round(clat / 0.25) * 0.25; clon = round(clon / 0.25) * 0.25
    return clat, clon, hl, ho, int(round(2 * hl / step)) + 1, int(round(2 * ho / step)) + 1


def recon_slice_needs(fixes_ms, slice_ms, step_ms, wind_fn):
    """Per reconstruction slice, the boxes it must cover, as (lat_lo, lat_hi,
    lon_lo, lon_hi). A slice is read by every bridge whose gap touches
    (t − step, t + step). A gap shorter than LONG_GAP_H needs the chord
    (interp_track) ± recon_half_deg. A long gap needs where the smoother's clouds
    are: a pilot cloud forward from its first fix (slices up to
    LONG_GAP_JOIN_MARGIN_H past the midpoint) and backward from its second (slices
    from that long before it), 1–99 % extent ± RECON_PILOT_MARGIN_DEG, capped at
    the unperturbed trajectories ± recon_half_deg; where the two trajectories are
    > LONG_GAP_MAX_SPREAD_DEG apart the winds can't connect the fixes and the slice
    needs the chord. Slices no gap touches (the lead-in and trailing ones) need
    the chord. A sample between two slices reads BOTH of them (the compute
    blends them in time, and `cubeCovers` asks for both boxes), so a slice's box
    must hold the clouds over its whole read window (t − step, t + step), not
    just at t: in a jet the cloud moves ~5° in 3 h, and boxes sized at t alone
    clipped the leading edge of the final bridges. `fixes_ms` = [(t_ms, lat,
    lon_unwrapped)]; `wind_fn(lat, lon, t_ms) -> (u, v)`."""
    chord = [interp_track(fixes_ms, t) for t in slice_ms]
    around = lambda p, h: (p[0] - h, p[0] + h, p[1] - h, p[1] + h)
    needs = [[] for _ in slice_ms]
    margin = LONG_GAP_JOIN_MARGIN_H * 3.6e6
    m = RECON_PILOT_MARGIN_DEG
    for (ta, la, loa), (tb, lb, lob) in zip(fixes_ms, fixes_ms[1:]):
        idx = [k for k, t in enumerate(slice_ms) if tb > t - step_ms and ta < t + step_ms]
        if not idx:
            continue
        gap_h = (tb - ta) / 3.6e6
        h = recon_half_deg(gap_h)
        if gap_h < LONG_GAP_H:
            for k in idx:
                needs[k].append(around(chord[k], h))
            continue
        tm = (ta + tb) / 2
        lead = max(margin, min(LONG_GAP_BACKWARD_LEAD_H * 3.6e6, (tb - ta) / 4))
        window = lambda t: (t - step_ms, t - step_ms / 2, t, t + step_ms / 2, t + step_ms)
        f_times = sorted({w for k in idx if slice_ms[k] <= tm + margin for w in window(slice_ms[k])})
        b_times = sorted({w for k in idx if slice_ms[k] >= tm - lead for w in window(slice_ms[k])})
        fwd = integrate_positions(f_times, ta, la, loa, wind_fn, 1)
        bwd = integrate_positions(b_times, tb, lb, lob, wind_fn, -1)
        seed = int(ta // 1000) % (2 ** 31)
        fenv = pilot_envelopes(f_times, ta, la, loa, wind_fn, 1, seed=seed)
        benv = pilot_envelopes(b_times, tb, lb, lob, wind_fn, -1, seed=seed + 1)
        for k in idx:
            t = slice_ms[k]
            pts, env = [], []
            for w in window(t):                                  # the clouds over the slice's read window
                if w <= tm + margin and w <= tb:
                    pts.append(fwd.get(w, (la, loa)))            # times before A sit at A
                    env.append(fenv.get(w, around((la, loa), 0)))
                if w >= tm - lead and w >= ta:
                    pts.append(bwd.get(w, (lb, lob)))            # times after B sit at B
                    env.append(benv.get(w, around((lb, lob), 0)))
            if not pts:
                pts, env = [(la, loa)], [around((la, loa), 0)]
            if (max(p[0] for p in pts) - min(p[0] for p in pts) > LONG_GAP_MAX_SPREAD_DEG
                    or max(p[1] for p in pts) - min(p[1] for p in pts) > LONG_GAP_MAX_SPREAD_DEG):
                needs[k].append(around(chord[k], h))
                continue
            cap = (min(p[0] for p in pts) - h, max(p[0] for p in pts) + h, min(p[1] for p in pts) - h, max(p[1] for p in pts) + h)
            want = [min(e[0] for e in env) - m, max(e[1] for e in env) + m, min(e[2] for e in env) - m, max(e[3] for e in env) + m]
            for p in pts:                                    # always hold the trajectories themselves
                want = [min(want[0], p[0] - m), max(want[1], p[0] + m), min(want[2], p[1] - m), max(want[3], p[1] + m)]
            needs[k].append((max(want[0], cap[0]), min(want[1], cap[1]), max(want[2], cap[2]), min(want[3], cap[3])))
    for k in range(len(slice_ms)):
        if not needs[k]:
            needs[k].append(around(chord[k], recon_half_deg(0)))
    return needs


def cover_boxes(needs, step):
    """Rectangular slice boxes: the union of each slice's needed boxes, half-
    extents snapped UP to multiples of `step` so origins stay on the source
    lattice. Returns [(clat, clon, half_lat, half_lon)]."""
    boxes = []
    for nd in needs:
        a, b = min(x[0] for x in nd), max(x[1] for x in nd)
        c, d = min(x[2] for x in nd), max(x[3] for x in nd)
        boxes.append(((a + b) / 2, (c + d) / 2, math.ceil((b - a) / 2 / step - 1e-9) * step, math.ceil((d - c) / 2 / step - 1e-9) * step))
    return boxes


def _evict_fields(keys, levels):
    """Drop the whole-globe fields of the (cycle, fhr) `keys` from both caches."""
    for cyc, fhr in keys:
        for L in levels:
            _uv_cache.pop((cyc, fhr, L), None)
        for key in [k for k in _uv_cache if k[0] == cyc and k[1] == fhr]:
            del _uv_cache[key]
        for key in [k for k in _uv_p_cache if k[0] == cyc and k[1] == fhr]:
            del _uv_p_cache[key]


def sample_tube_rect(boxes, step, slice_ms, levels, target_p, latest, now, tag=""):
    """Cut one rectangular box per slice (see cover_boxes). With `levels` the
    box is cut from each listed GFS level UNBLENDED (multi-level cube, v4);
    without, from the field interpolated to `target_p` (single-level, v3).
    Slices are cut in time-ordered chunks with parallel fetches, and each
    chunk's whole-globe fields are evicted once no later slice needs them, so
    the extra levels don't multiply the ingest's peak memory."""
    keys = [pick_source(datetime.fromtimestamp(ms / 1000, timezone.utc), latest) for ms in slice_ms]

    def cut(k):
        clat, clon, hl, ho = boxes[k]
        nla = int(round(2 * hl / step)) + 1
        nlo = int(round(2 * ho / step)) + 1
        cyc, fhr = keys[k]
        g = {"dLat": step, "nLat": nla, "dLon": step, "nLon": nlo}
        if levels:
            g["levels"] = []
            for L in levels:
                f = fetch_uv(cyc, fhr, L)
                lat0, lon0, U, V = cut_box_rect(f["u"], f["v"], clat, clon, hl, ho, step, nla, nlo)
                g["levels"].append((U, V))
        else:
            f = fetch_uv_p(cyc, fhr, target_p)
            lat0, lon0, U, V = cut_box_rect(f["u"], f["v"], clat, clon, hl, ho, step, nla, nlo)
            g["U"], g["V"] = U, V
        g["lat0"], g["lon0"] = lat0, lon0
        if RECON_OUTER:
            oc = outer_box(clon)
            f = fetch_uv_p(cyc, fhr, target_p)
            olat0, olon0, OU, OV = cut_box_rect(f["u"], f["v"], oc[0], oc[1], oc[2], oc[3], RECON_OUTER_STEP, oc[4], oc[5])
            g["outer"] = (olat0, olon0, oc[4], oc[5], OU, OV)
        return g

    grids = [None] * len(slice_ms)
    chunk = 24
    for c0 in range(0, len(slice_ms), chunk):
        ks = list(range(c0, min(len(slice_ms), c0 + chunk)))
        with ThreadPoolExecutor(max_workers=8) as ex:
            for k, g in zip(ks, ex.map(cut, ks)):
                grids[k] = g
        later = set(keys[c0 + chunk:])
        _evict_fields({keys[k] for k in ks} - later, levels)
        if tag:
            print(f"      {tag}: {ks[-1] + 1}/{len(slice_ms)} slices", flush=True)
    uminLat = min(g["lat0"] for g in grids); umaxLat = max(g["lat0"] + (g["nLat"] - 1) * step for g in grids)
    uminLon = min(g["lon0"] for g in grids); umaxLon = max(g["lon0"] + (g["nLon"] - 1) * step for g in grids)
    cube = {
        "source": "gfs", "generated_at": now.isoformat(), "latest_cycle_utc": latest.isoformat(),
        "levelHpa": round(target_p, 1), "gridStep": step,
        "t0Ms": slice_ms[0], "stepMs": int(slice_ms[1] - slice_ms[0]) if len(slice_ms) > 1 else RECON_STEP_H * 3600 * 1000,
        "bounds": {"latMin": uminLat, "latMax": umaxLat, "lonMin": uminLon, "lonMax": umaxLon},
        "grids": grids,
        "centers": [(b[0], b[1]) for b in boxes],
    }
    if levels:
        cube["levels"] = list(levels)
    return cube, max(g["nLat"] for g in grids), max(g["nLon"] for g in grids)


def build_tube_recon(device, fixes, target_p, latest, now):
    """Reconstruction cube as a trajectory-following tube: one RECON_STEP_H slice
    from one step before the first fix to two past the last, each a box at the
    native resolution laid along where the bridges will look — the observed
    track's chord for short and medium gaps, the forward/backward wind
    trajectories for long ones (recon_slice_covers) — padded by a half-width
    from the local gap length (recon_half_deg). With RECON_LEVELS_EACH_SIDE > 0
    every box holds several pressure levels around the float (recon_levels,
    .slwc v4); otherwise the single blended float level (v3)."""
    t_start = time.time()
    first_fix = tparse(fixes[0]["t"])
    last_fix = tparse(fixes[-1]["t"])
    step_ms = RECON_STEP_H * 3600 * 1000
    start = floor_step(first_fix, RECON_STEP_H) - timedelta(hours=RECON_STEP_H)
    end = floor_step(last_fix, RECON_STEP_H) + timedelta(hours=2 * RECON_STEP_H)
    start_ms = int(start.timestamp() * 1000)
    n_slices = int(round((end - start).total_seconds() * 1000 / step_ms)) + 1
    slice_ms = [start_ms + k * step_ms for k in range(n_slices)]

    lons = unwrap_lons([f["lon"] for f in fixes])
    fixes_ms = [(int(tparse(f["t"]).timestamp() * 1000), f["lat"], lo) for f, lo in zip(fixes, lons)]
    halves = [recon_half_deg(gap_hours_at(fixes_ms, t, step_ms)) for t in slice_ms]
    prefetch_fields(slice_ms, target_p, latest)          # parallel cache warm-up (float level)
    t_fetched = time.time()

    def wind_fn(lat, lon, t_ms):
        # Linear in time between the two bracketing (prefetched) slices, as the
        # compute reads the cube — NOT pick_source at the sub-step's own instant,
        # which would ask for hourly forecast hours the 3-hourly prefetch never
        # fetched and download them one by one.
        f = min(max((t_ms - slice_ms[0]) / step_ms, 0.0), len(slice_ms) - 1.0)
        k0 = min(int(f), len(slice_ms) - 2) if len(slice_ms) > 1 else 0
        w = f - k0
        out = []
        for k in ((k0, k0 + 1) if len(slice_ms) > 1 else (k0,)):
            cyc, fhr = pick_source(datetime.fromtimestamp(slice_ms[k] / 1000, timezone.utc), latest)
            out.append(sample_global(fetch_uv_p(cyc, fhr, target_p), lat, lon))
        if len(out) == 1:
            return out[0]
        return out[0][0] * (1 - w) + out[1][0] * w, out[0][1] * (1 - w) + out[1][1] * w
    needs = recon_slice_needs(fixes_ms, slice_ms, step_ms, wind_fn)
    t_covered = time.time()
    # Grid step from the largest box (unsnapped extents; resolution is bounded by size only).
    unions = [(min(x[0] for x in nd), max(x[1] for x in nd), min(x[2] for x in nd), max(x[3] for x in nd)) for nd in needs]
    big = max(unions, key=lambda u: (u[1] - u[0]) * (u[3] - u[2]))
    step = choose_grid_step({"latMin": big[0], "latMax": big[1], "lonMin": big[2], "lonMax": big[3]}, max_pts=RECON_MAX_GRID_PTS)
    boxes = cover_boxes(needs, step)
    levels = recon_levels(target_p)
    longest = max(((b[0] - a[0]) / 3.6e6 for a, b in zip(fixes_ms, fixes_ms[1:])), default=0.0)
    print(f"    recon tube: {n_slices} slices @ {step}° half {min(halves):.0f}–{max(halves):.1f}°, "
          f"largest box {2 * max(b[2] for b in boxes):.0f}×{2 * max(b[3] for b in boxes):.0f}° "
          f"(longest gap {longest:.0f}h), levels {levels or [round(target_p, 1)]} hPa, "
          f"{start:%Y-%m-%dT%H}Z → {end:%Y-%m-%dT%H}Z", flush=True)
    recon, rla, rlo = sample_tube_rect(boxes, step, slice_ms, levels, target_p, latest, now, "recon")
    write_cube(device, "", recon, rla, rlo, "recon")
    print(f"    recon: built in {time.time() - t_start:.0f} s (float-level prefetch {t_fetched - t_start:.0f} s, "
          f"wind-following covers {t_covered - t_fetched:.0f} s, boxes {time.time() - t_covered:.0f} s)", flush=True)


SCALE = 10  # store winds as int16 = round(value*SCALE); lossless vs the old 0.1 rounding


def pack_cube(cube):
    """Pack a cube dict into the .slwc binary form (see windCube.ts cubeFromBinary):
      [uint32 LE headerLen][header JSON utf-8, padded to a 4-byte boundary]
      [ per grid: int16 U[nLat*nLon] then int16 V[nLat*nLon], little-endian ].
    Geometry is constant across grids, so it lives in the header once."""
    grids = cube["grids"]
    g0 = grids[0]
    # A tube has a different origin per slice; a static cube shares one. Emit v2
    # (origins[]) only when origins actually vary — old static cubes stay v1. A
    # tube whose slice boxes differ in SIZE (the reconstruction tube widens inside
    # long gaps) is v3: it also carries per-slice dims, since the reader walks the
    # payload by each grid's point count.
    # A multi-level cube (grids carry "levels" = [(U, V) per level], header
    # `levels` in hPa, ascending) is v4: v3's per-slice origins + dims, and per
    # grid the int16 U then V of each level in turn.
    origins = [(g["lat0"], g["lon0"]) for g in grids]
    dims = [(g["nLat"], g["nLon"]) for g in grids]
    levels = cube.get("levels") or []
    outer = all("outer" in g for g in grids)
    dims_vary = bool(levels) or outer or any(d != dims[0] for d in dims)
    is_tube = dims_vary or any(o != origins[0] for o in origins)
    header = {
        "v": 5 if outer else (4 if levels else (3 if dims_vary else (2 if is_tube else 1))), "scale": SCALE,
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
    if dims_vary:
        header["dims"] = [[a, b] for a, b in dims]
    if levels:
        header["levels"] = [int(L) if float(L).is_integer() else L for L in levels]
    if outer:
        header["outer"] = {"dLat": RECON_OUTER_STEP, "dLon": RECON_OUTER_STEP,
                           "origins": [[round(g["outer"][0], 4), round(g["outer"][1], 4)] for g in grids],
                           "dims": [[g["outer"][2], g["outer"][3]] for g in grids]}
    # True trajectory metadata (optional, tube-only; [lat, lon], lon UNWRAPPED like
    # origins). Old readers ignore unknown header keys, so v stays 2.
    if is_tube and cube.get("centers"):
        assert len(cube["centers"]) == len(grids), "centers/grids length mismatch"
        header["centers"] = [[round(la, 4), round(lo, 4)] for la, lo in cube["centers"]]
    if is_tube and cube.get("track"):
        tr = cube["track"]
        header["track"] = {"t0Ms": tr["t0Ms"], "stepMs": tr["stepMs"],
                           "points": [[round(la, 4), round(lo, 4)] for la, lo in tr["points"]]}
    hb = json.dumps(header, separators=(",", ":")).encode("utf-8")
    hb += b" " * ((-(4 + len(hb))) % 4)            # pad so the payload starts 4-byte aligned
    parts = [struct.pack("<I", len(hb)), hb]
    for g in cube["grids"]:
        for U, V in (g["levels"] if levels else [(g["U"], g["V"])]):
            for a in (U, V):
                a = np.asarray(a, dtype=np.float64)
                parts.append(np.clip(np.round(a * SCALE), -32000, 32000).astype("<i2").tobytes())
    if outer:                                    # v5: the outer grids follow every fine grid
        for g in cube["grids"]:
            for a in (g["outer"][4], g["outer"][5]):
                parts.append(np.clip(np.round(np.asarray(a, dtype=np.float64) * SCALE), -32000, 32000).astype("<i2").tobytes())
    return b"".join(parts)


def write_cube(device, suffix, cube, nlat, nlon, tag):
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"{device}{suffix}.slwc")
    with open(out, "wb") as f:
        f.write(pack_cube(cube))
    nlev = len(cube.get("levels") or [None])
    print(f"    {tag}: {len(cube['grids'])} grids ≤{nlat}x{nlon} × {nlev} level(s) @ {cube['gridStep']}° "
          f"({cube['stepMs']//3600000}h step) -> {os.path.getsize(out)//1024} KB (.slwc)", flush=True)


def fields_for(start, end, step_h, latest):
    """The (cycle, fhr) source fields a `step_h`-hourly span from start to end needs."""
    want, t = set(), start
    while t <= end:
        want.add(pick_source(t, latest))
        t += timedelta(hours=step_h)
    return want


def build_cube(device, fixes, target_p, latest):
    first_fix = tparse(fixes[0]["t"])
    last_fix = tparse(fixes[-1]["t"])
    now = datetime.now(timezone.utc)
    gap_h = max(0, (now - last_fix).total_seconds() / 3600)
    lo, hi, _ = bracket_levels(target_p)
    print(f"  {device}: interp {target_p:.1f}mb ({lo}↔{hi}), gap {gap_h:.0f}h, {len(fixes)} fix(es)", flush=True)
    clear_field_cache()                          # fresh per device (free the prior device's fields)

    # ── Forecast cube FIRST: last fix + dead-reckon + cone, HOURLY, finest grid. ──
    # Built before the recon so the few fields both sample (the recon's trailing
    # slices bracket the last fix, where the tube starts) are fetched once.
    if FC_TUBE:
        build_tube_fc(device, fixes, last_fix, gap_h, target_p, latest, now)
    else:
        build_static_fc(device, fixes, last_fix, gap_h, target_p, latest, now)

    # ── Reconstruction cube: full mission (first fix → last fix), 3-hourly. ──
    # Nothing after the last fix is ever sampled (the bridges run fix → fix), so
    # the span ends there, not at now + horizon — which for a long-dark balloon put
    # ~90% of the grids on a period with no fixes. One fix (or a launch-record
    # seed) has no gap to bridge: write nothing; compute keys devices on the fc cube.
    # Default is the trajectory tube (build_tube_recon); the static box is the
    # RECON_TUBE=0 legacy path. Either way, the fields the forecast tube already
    # fetched inside the recon's span stay warm across the cache clear.
    recon_start = floor_step(first_fix, RECON_STEP_H) - timedelta(hours=RECON_STEP_H)
    recon_end = floor_step(last_fix, RECON_STEP_H) + timedelta(hours=2 * RECON_STEP_H)
    if len(fixes) < 2:
        print(f"    recon: skipped ({len(fixes)} fix — nothing to reconstruct)", flush=True)
    elif os.environ.get("SKIP_RECON") == "1":   # dev: skip the slow full-mission recon when iterating on the tube
        print("    recon: skipped (SKIP_RECON=1)", flush=True)
    elif RECON_TUBE:
        clear_field_cache(keep=fields_for(recon_start, recon_end, RECON_STEP_H, latest))  # tube's overlap stays warm
        build_tube_recon(device, fixes, target_p, latest, now)
        clear_field_cache()
    else:
        recon_bounds = bounds_for_forecast(fixes, HORIZON_H, pad_cap=8)
        recon_step = choose_grid_step(recon_bounds)
        clear_field_cache(keep=fields_for(recon_start, recon_end, RECON_STEP_H, latest))  # tube's overlap stays warm
        recon, rla, rlo = sample_grids(recon_bounds, recon_step, recon_start, recon_end,
                                       RECON_STEP_H, target_p, latest, now, "recon")
        write_cube(device, "", recon, rla, rlo, "recon")
        del recon
        clear_field_cache()

def cubes_written(device, since_ts):
    """Which of a device's two GFS cubes this run wrote, for the manifest:
    {"fc": bool, "recon": bool}. Judged by file mtime ≥ `since_ts`, so a stale
    local file from an earlier run doesn't count (CI starts from a clean tree)."""
    out = {}
    for key, suffix in (("fc", "-fc"), ("recon", "")):
        path = os.path.join(OUTDIR, f"{device}{suffix}.slwc")
        out[key] = os.path.exists(path) and os.path.getmtime(path) >= since_ts - 1
    return out


def build_static_fc(device, fixes, last_fix, gap_h, target_p, latest, now):
    """Legacy forecast cube (FC_TUBE=0): one static box around the recent track,
    padded downwind for the gap + horizon."""
    pad_h = HORIZON_H + min(gap_h, MAX_GAP_H)
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
    FC_BIAS_H before the last fix (one bracketing slice of margin) through the
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
    devices = planned_devices(only)
    manifest_source_begin("gfs")
    if not devices:
        print("no devices to build — no NOAA download", flush=True)
        manifest_source_end("gfs")
        return
    latest = latest_cycle()
    print(f"latest GFS cycle {latest.isoformat()} | devices: {[d for d, _ in devices]}", flush=True)
    failed = []
    for d, launched in devices:
        t0 = time.time()
        try:
            fixes = mission_track(d, launched)
            if len(fixes) < 1:
                print(f"  {d}: no fixes, skipping", flush=True)
                manifest_device("gfs", d, fc=False, recon=False, n_fixes=0, error="no fixes")
                continue
            build_cube(d, fixes, float_pressure(d), latest)
            manifest_device("gfs", d, n_fixes=len(fixes), seconds=round(time.time() - t0, 1), **cubes_written(d, t0))
        except Exception as e:
            print(f"  {d}: FAILED {e}", flush=True)
            manifest_device("gfs", d, error=str(e), seconds=round(time.time() - t0, 1))
            failed.append(d)
    manifest_source_end("gfs")
    if failed:
        raise SystemExit(f"GFS ingestion failed for {len(failed)} device(s)")


if __name__ == "__main__":
    main()
