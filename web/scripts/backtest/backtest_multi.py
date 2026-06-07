"""Multi-source GEFS / AIGEFS / ECMWF forecast-replay backtest, 3 subplots.
From a known past fix, each source runs OUR ensemble technique using the cycle it
would have had THEN, integrated forward to the verify time, scored vs the actual.

Data is pickled after compute, so plot tweaks are free:
  python3 -u scripts/backtest/backtest_multi.py <test>            # fetch + compute + cache + plot
  python3 -u scripts/backtest/backtest_multi.py <test> --plot-only # re-draw from cache, no download
Outputs (pickles + PNGs) go to $BACKTEST_OUT (default /tmp); the coastline GeoJSON is
cached next to this script on first run. Run from the `web/` directory.
"""
import sys, math, pickle, os, json, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))     # web/scripts — the ingest modules
OUT = os.environ.get("BACKTEST_OUT", "/tmp")     # pickles + PNGs land here (not committed)
import numpy as np
import gfs_ingest as g
import gefs_ingest as ge
import aigefs_ingest as ai
import ecmwf_ingest as ec
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

DEVICE = "stratolink-3"; DT_MIN = 30
TESTS = {
    "1": dict(start="2026-05-18T02:03", verify="2026-05-19T13:58"),
    "2": dict(start="2026-05-19T22:28", verify="2026-05-29T17:46"),
}
LINE = {"GEFS": "#6b93c4", "AIGEFS": "#6cae8e", "ECMWF": "#bd83ac"}   # muted source colours
COAST = os.path.join(HERE, "ne_110m_coastline.geojson")          # cached basemap (gitignored)
COAST_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_coastline.geojson"
def pkl_path(test): return os.path.join(OUT, f"bt_test{test}.pkl")

def floor6(t): return t.replace(minute=0, second=0, microsecond=0, hour=(t.hour//6)*6)
def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*6371*math.asin(math.sqrt(h))
def nearest_fix(fixes, ts):
    t = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    f = min(fixes, key=lambda f: abs((g.tparse(f["t"])-t).total_seconds()))
    return (f["lat"], f["lon"]), g.tparse(f["t"])
def bilin(arr, lat, lon):
    nlat, nlon = arr.shape; dlat = 180.0/(nlat-1); dlon = 360.0/nlon
    fr = (90.0-lat)/dlat; fc = (lon % 360.0)/dlon
    r0 = max(0, min(nlat-2, int(math.floor(fr)))); c0 = int(math.floor(fc)) % nlon
    dr = fr-r0; dc = fc-c0; c1 = (c0+1) % nlon
    return (arr[r0,c0]*(1-dr)*(1-dc) + arr[r0,c1]*(1-dr)*dc +
            arr[r0+1,c0]*dr*(1-dc) + arr[r0+1,c1]*dr*dc)
def _try(fn):
    try: fn(); return True
    except Exception: return False
def as_of_cycle(start_t, lag_h, exists):
    c = floor6(start_t - timedelta(hours=lag_h))
    for _ in range(12):
        if exists(c): return c
        c -= timedelta(hours=6)
    raise SystemExit("no published cycle")
def integrate(F, FHRS, p0, t0, tv):
    lat, lon = p0; path = [(lat, lon)]; dt = DT_MIN*60; t = t0
    while t < tv:
        h = (t - F["as_of"]).total_seconds()/3600
        a = max(f for f in FHRS if f <= h); b = min(f for f in FHRS if f >= h)
        fr = 0 if b == a else (h-a)/(b-a)
        ua, va = F[a]; ub, vb = F[b]
        u = bilin(ua, lat, lon)*(1-fr) + bilin(ub, lat, lon)*fr
        v = bilin(va, lat, lon)*(1-fr) + bilin(vb, lat, lon)*fr
        lat += v*dt/111320.0; lon += u*dt/(111320.0*math.cos(math.radians(lat)))
        path.append((lat, lon)); t += timedelta(seconds=dt)
    return path
def fhrs_for(as_of, t0, tv, step):
    f_lo = int((t0-as_of).total_seconds()//3600); f_hi = int(math.ceil((tv-as_of).total_seconds()/3600))
    return list(range(max(0, (f_lo//step)*step), ((f_hi//step)+1)*step + 1, step))

def gefs_fhrs(as_of, t0, tv):
    """GEFS pgrb2ap5 cadence: 3-hourly to 240h, then 6-hourly (f243 etc. don't exist)."""
    f_lo = int((t0-as_of).total_seconds()//3600); f_hi = int(math.ceil((tv-as_of).total_seconds()/3600))
    fhrs = list(range(max(0, (f_lo//3)*3), min(240, ((f_hi//3)+1)*3) + 1, 3))
    if f_hi > 240:
        fhrs += list(range(246, ((f_hi//6)+1)*6 + 1, 6))
    return fhrs

def member_source(name, members, fetch_level, as_of, FHRS, lo, hi, w, p0, t0, tv):
    levels = [lo] if lo == hi else [lo, hi]; paths = []
    for mem in members:
        try:
            cache = {}; tasks = [(fhr, lv) for fhr in FHRS for lv in levels]
            with ThreadPoolExecutor(max_workers=8) as ex:
                for (fhr, lv), uv in ex.map(lambda t: (t, fetch_level(mem, as_of, t[0], t[1])), tasks):
                    cache[(fhr, lv)] = uv
            F = {"as_of": as_of}
            for fhr in FHRS:
                if lo == hi: F[fhr] = cache[(fhr, lo)]
                else:
                    ua, va = cache[(fhr, hi)]; ub, vb = cache[(fhr, lo)]
                    F[fhr] = (ua*(1-w)+ub*w, va*(1-w)+vb*w)
            paths.append(integrate(F, FHRS, p0, t0, tv))
        except Exception as e:
            print(f"    {name} {mem}: skipped ({e})", flush=True)
    print(f"  {name}: {len(paths)}/{len(members)} members", flush=True)
    return paths

def ecmwf_source(as_of, FHRS, lo, hi, w, p0, t0, tv):
    levels = [hi] if lo == hi else [lo, hi]; idxmap = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for cs, m in ex.map(lambda s: ec.fetch_index((as_of, s), levels), FHRS):
            if m: idxmap[cs] = m
    members = [m for m in ec.MEMBERS if all((as_of, s) in idxmap and m in idxmap[(as_of, s)] for s in FHRS)]
    paths = []
    for k, mem in enumerate(members):
        try:
            F = {"as_of": as_of}
            with ThreadPoolExecutor(max_workers=6) as ex:
                for s, uv in ex.map(lambda s: (s, ec.fetch_member_field(mem, (as_of, s), idxmap, lo, hi, w)), FHRS):
                    u, v = uv                       # ECMWF is lon -180..180; roll to 0..360 for the sampler
                    F[s] = (np.roll(u, u.shape[1]//2, axis=1), np.roll(v, v.shape[1]//2, axis=1))
            paths.append(integrate(F, FHRS, p0, t0, tv))
            print(f"    ECMWF [{k+1:2d}/{len(members)}] member {mem}", flush=True)
        except Exception as e:
            print(f"    ECMWF e{mem}: skipped ({e})", flush=True)
    print(f"  ECMWF: {len(paths)}/{len(members)} members", flush=True)
    return paths

def score(paths, pv):
    ends = np.array([p[-1] for p in paths]); mean = ends.mean(axis=0)
    coslat = math.cos(math.radians(mean[0]))
    xy = np.column_stack([(ends[:,1]-mean[1])*111.32*coslat, (ends[:,0]-mean[0])*111.32])
    cov = np.cov(xy.T); av = np.array([(pv[1]-mean[1])*111.32*coslat, (pv[0]-mean[0])*111.32])
    md2 = float(av @ np.linalg.solve(cov, av))
    return dict(paths=[[list(p) for p in pth] for pth in paths], ends=ends, mean=mean, cov=cov,
                coslat=coslat, miss=km(tuple(mean), pv), best=min(km(tuple(e), pv) for e in ends),
                spread=float(np.mean([km(tuple(mean), tuple(e)) for e in ends])),
                in50=md2 <= 1.386, in90=md2 <= 4.605, md2=md2)

# ── basemap ──────────────────────────────────────────────────────────────────
_coast = None
def coastlines():
    global _coast
    if _coast is None:
        try:
            if not os.path.exists(COAST):                       # download once, cache next to script
                urllib.request.urlretrieve(COAST_URL, COAST)
            _coast = [f["geometry"]["coordinates"] for f in json.load(open(COAST))["features"]]
        except Exception:
            _coast = []                                          # basemap is optional — skip if unavailable
    return _coast
def add_basemap(ax):
    for line in coastlines():
        xs = [c[0] for c in line]; ys = [c[1] for c in line]
        ax.plot(xs, ys, "-", color="#bfc6cc", lw=0.6, zorder=0.5, solid_capstyle="round")

# ── plotting ─────────────────────────────────────────────────────────────────
def draw(ax, name, R, p0, pv, extent, show_x, show_y):
    c = LINE[name]; add_basemap(ax)
    for p in R["paths"]:
        ax.plot([q[1] for q in p], [q[0] for q in p], "-", color=c, alpha=0.20, lw=0.6, zorder=1)
    ax.plot(R["ends"][:,1], R["ends"][:,0], ".", color=c, ms=3, alpha=0.45, zorder=2)
    vals, vecs = np.linalg.eigh(R["cov"]); th = np.linspace(0, 2*np.pi, 120)
    for chi2, ls in [(1.386, ":"), (4.605, "--")]:
        a = np.sqrt(chi2*np.maximum(vals, 0)); e = vecs @ (a[:,None]*np.array([np.cos(th), np.sin(th)]))
        ax.plot(R["mean"][1]+e[0]/(111.32*R["coslat"]), R["mean"][0]+e[1]/111.32, ls, color=c, lw=1.1, alpha=0.75, zorder=3)
    ax.plot(p0[1], p0[0], marker="o", color="#404040", ms=4, mec="white", mew=0.5, zorder=6, label="start")
    ax.plot(R["mean"][1], R["mean"][0], marker="D", mfc="none", mec=c, ms=5, mew=1.0, zorder=6, label="forecast mean")
    ax.plot(pv[1], pv[0], marker="x", color="#c0392b", ms=6, mew=1.3, zorder=7, label="actual")
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect(1/math.cos(math.radians(R["mean"][0])))
    ax.grid(alpha=0.18, lw=0.5, zorder=0); ax.set_xlabel("lon", fontsize=9)
    if show_y: ax.set_ylabel("lat", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.set_title(f"{name} · {R['n']} members · as-of {R['as_of']:%m-%d %HZ}\n"
                 f"miss {R['miss']:.0f} · best {R['best']:.0f} · spread {R['spread']:.0f} km   "
                 f"(in 50% {'Y' if R['in50'] else 'N'} · 90% {'Y' if R['in90'] else 'N'})",
                 fontsize=8.5, color="#333", linespacing=1.3)

def make_figure(P):
    R, p0, pv = P["R"], tuple(P["p0"]), tuple(P["pv"])
    allpts = [p0, pv] + [tuple(e) for k in R for e in R[k]["ends"]]
    lons = [q[1] for q in allpts]; lats = [q[0] for q in allpts]
    px = (max(lons)-min(lons))*0.07+0.4; py = (max(lats)-min(lats))*0.07+0.4
    extent = (min(lons)-px, max(lons)+px, min(lats)-py, max(lats)+py)
    # Size the figure to the data so the (fixed geographic-aspect) panels fill the
    # frame — no vertical dead space. constrained_layout handles the rest.
    clat = (extent[2]+extent[3])/2; A = 1/math.cos(math.radians(clat))
    lon_span = extent[1]-extent[0]; lat_span = extent[3]-extent[2]
    W = 11; panel_w = W - 1.4; panel_h = panel_w * A * lat_span/lon_span   # 3 stacked rows, full-width
    fig_h = min(16.0, max(5.0, 3*panel_h + 1.2))
    fig, axes = plt.subplots(3, 1, figsize=(W, fig_h), sharex=True, sharey=True, constrained_layout=True)
    for i, (ax, name) in enumerate(zip(axes, ["GEFS", "AIGEFS", "ECMWF"])):
        if name in R: draw(ax, name, R[name], p0, pv, extent, show_x=(i == 2), show_y=True)
        else: ax.text(0.5, 0.5, f"{name}\n(no data)", ha="center", va="center"); ax.axis("off")
    axes[0].legend(loc="upper left", fontsize=7.5, framealpha=0.6, borderpad=0.4, handlelength=1.4)
    fig.suptitle(f"Forecast-replay backtest — test {P['test']}:  {P['t0']:%Y-%m-%d %HZ} +{P['gap_h']:.0f}h"
                 f"   (actual displacement {P['disp']:.0f} km)", fontsize=11.5)
    out = os.path.join(OUT, f"backtest_multi_test{P['test']}.png"); fig.savefig(out, dpi=240)
    print(f"  plot -> {out}", flush=True)

def run(test):
    cfg = TESTS[test]
    fixes = g.mission_fixes(DEVICE, datetime(2026, 5, 16, tzinfo=timezone.utc))
    p0, t0 = nearest_fix(fixes, cfg["start"]); pv, tv = nearest_fix(fixes, cfg["verify"])
    target_p = g.float_pressure(DEVICE); lo, hi, w = g.bracket_levels(target_p)
    gap_h = (tv-t0).total_seconds()/3600
    print(f"TEST {test}: {t0:%m-%d %H:%M}Z ({p0[0]:.2f},{p0[1]:.2f}) -> {tv:%m-%d %H:%M}Z "
          f"({pv[0]:.2f},{pv[1]:.2f})  gap {gap_h:.0f}h  actual {km(p0,pv):.0f} km  ({target_p:.1f}mb)", flush=True)
    g_as = as_of_cycle(t0, 6, lambda c: _try(lambda: g.http_get(ge.gefs_member_url("gec00", c, 0)+".idx")))
    a_as = as_of_cycle(t0, 9, ai.cycle_exists)
    e_as = as_of_cycle(t0, 9, lambda c: ec.fetch_index((c, 0), [hi])[1] is not None)
    src = {}
    src["GEFS"] = (member_source("GEFS", ge.ALL_MEMBERS, ge.fetch_member_level, g_as, gefs_fhrs(g_as, t0, tv), lo, hi, w, p0, t0, tv), g_as)
    src["AIGEFS"] = (member_source("AIGEFS", ai.MEMBERS, ai.fetch_member_level, a_as, fhrs_for(a_as, t0, tv, 6), lo, hi, w, p0, t0, tv), a_as)
    src["ECMWF"] = (ecmwf_source(e_as, fhrs_for(e_as, t0, tv, 6), lo, hi, w, p0, t0, tv), e_as)
    R = {}
    for k, (paths, as_of) in src.items():
        if len(paths) >= 3:
            s = score(paths, pv); s["as_of"] = as_of; s["n"] = len(paths); R[k] = s
            print(f"  {k}: mean miss {s['miss']:.0f} | best {s['best']:.0f} | spread {s['spread']:.0f} | in90 {s['in90']}", flush=True)
    P = dict(test=test, R=R, p0=list(p0), pv=list(pv), t0=t0, tv=tv, gap_h=gap_h, disp=km(p0, pv), target_p=target_p)
    pickle.dump(P, open(pkl_path(test), "wb")); print(f"  cached -> {pkl_path(test)}", flush=True)  # save BEFORE plotting
    try: make_figure(P)
    except Exception as e: print(f"  PLOT FAILED ({e}) — data cached, re-run with --plot-only", flush=True)

if __name__ == "__main__":
    test = next((a for a in sys.argv[1:] if not a.startswith("--")), "1")
    if "--plot-only" in sys.argv:
        make_figure(pickle.load(open(pkl_path(test), "rb"))); print("re-plotted from cache (no download)")
    else:
        run(test)
